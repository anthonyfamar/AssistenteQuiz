import io
import os
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

try:
    import httpx
except ModuleNotFoundError:
    import httpx2 as httpx
from openai import APIStatusError, APITimeoutError

from quizbot import registro
from quizbot.config import PROVEDORES, TIMEOUT_API
from quizbot.models import Question
from quizbot.solvers import fabrica

assert TIMEOUT_API == 15.0
assert PROVEDORES["gemini"].modelos_reserva == ("gemini-3.7-flash", "gemini-3.6-flash", "gemini-3-flash-preview")

# --- fabrica: principal do .env primeiro, depois reservas do mesmo provedor, depois o proximo provedor ---
tmp = Path(tempfile.mkdtemp()) / "vazio.env"
tmp.write_text("")
fabrica.ARQUIVO_ENV = tmp  # nenhum .env de verdade e lido neste teste
for k in list(os.environ):
    if k.startswith(("GEMINI_", "GROQ_", "OPENROUTER_", "MISTRAL_", "OLLAMA_")):
        del os.environ[k]
os.environ.update({
    "GEMINI_API_KEY": "chave-gemini-falsa-123456", "GEMINI_MODEL": "gemini-3.8-flash", "GEMINI_MODEL_VISAO": "gemini-3.8-flash",
    "GROQ_API_KEY": "chave-groq-falsa-1234567", "GROQ_MODEL": "openai/gpt-oss-120b",
})
saida = io.StringIO()
with redirect_stdout(saida):
    fb = fabrica.montar_solver()
ordem = [s.descricao for s in fb._solvers]
assert ordem == ["gemini (gemini-3.8-flash)", "gemini (gemini-3.7-flash)", "gemini (gemini-3.6-flash)",
                 "gemini (gemini-3-flash-preview)", "groq (openai/gpt-oss-120b)", "groq (qwen/qwen3.8-27b)",
                 "groq (openai/gpt-oss-20b)"], ordem
assert "[ia] ordem de tentativa: gemini (gemini-3.8-flash) > gemini (gemini-3.7-flash)" in saida.getvalue()
assert "chave" not in saida.getvalue().lower().replace("chave-", "X") or "falsa" not in saida.getvalue()  # nenhuma chave impressa
# imagem: reservas do gemini aceitam (principal tem visao); groq sem MODEL_VISAO nao aceita
assert [s.aceita_imagens for s in fb._solvers] == [True, True, True, True, False, False, False]
# se o .env ja usa um dos reservas como principal, nao duplica
os.environ["GEMINI_MODEL"] = "gemini-3.7-flash"
with redirect_stdout(io.StringIO()):
    ordem2 = [s.descricao for s in fabrica.montar_solver()._solvers]
assert ordem2.count("gemini (gemini-3.7-flash)") == 1, ordem2
os.environ["GEMINI_MODEL"] = "gemini-3.8-flash"
print("fabrica: ordem principal > reservas > proximo provedor ok")

# --- comportamento: 3.8 fora do ar -> 3.7 responde; passada a pausa, tenta o 3.8 de novo PRIMEIRO ---
req = httpx.Request("POST", "https://x/y")
chamadas = []
sondas = []  # pedidos de teste do vigia (segundo plano), separados das consultas reais


def espera(condicao, segundos=8.0):
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.02)
    return False


def cliente(modelo_resposta):
    def criar(**kw):
        if kw["messages"][-1]["content"] == "Responda apenas: ok":
            sondas.append(kw["model"])
        else:
            chamadas.append(kw["model"])
        acao = modelo_resposta.get(kw["model"])
        if isinstance(acao, Exception):
            raise acao
        msg = SimpleNamespace(content='{"indice": 1, "explicacao": "ok"}')
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=criar)))


erro503 = APIStatusError("503", response=httpx.Response(503, request=req), body={"error": "high demand"})
estado = {"gemini-3.8-flash": erro503}
c = cliente(estado)
for s in fb._solvers:
    s._client = c
fb._cooldown = 0.3
fb._timeout_rapido, fb._timeout_final = 5.0, 15.0
alertas = []
fb._ao_mudar_problemas = lambda p: alertas.append(list(p))
Q = Question("Q?", ("a", "b"))

with redirect_stdout(io.StringIO()):
    s1 = fb.solve(Q)
assert s1.origem == "gemini (gemini-3.7-flash)" and chamadas == ["gemini-3.8-flash", "gemini-3.7-flash"], (s1.origem, chamadas)
assert alertas == [["Algo deu errado: API do Gemini fora do ar."]], alertas  # nome amigavel, sem modelo
with redirect_stdout(io.StringIO()):
    fb.solve(Q)
assert chamadas[2:] == ["gemini-3.7-flash"]  # na pausa nao insiste no 3.8
# o 3.8 continua ruim: o vigia testa em segundo plano, falha, e ele NAO volta para a fila
assert espera(lambda: "gemini-3.8-flash" in sondas), sondas
time.sleep(0.05)
assert 0 in fb._pausados
with redirect_stdout(io.StringIO()):
    s2 = fb.solve(Q)
assert s2.origem == "gemini (gemini-3.7-flash)" and chamadas[3:] == ["gemini-3.7-flash"], chamadas
# o 3.8 melhorou: so quando o vigia confirma ele volta a ser o primeiro
estado.clear()
with redirect_stdout(io.StringIO()):
    assert espera(lambda: 0 not in fb._pausados), "o vigia nao devolveu o 3.8"
    s3 = fb.solve(Q)
assert s3.origem == "gemini (gemini-3.8-flash)" and chamadas[-1] == "gemini-3.8-flash", (s3.origem, chamadas)
print("reserva: 3.8 falha -> 3.7; o vigia testa em segundo plano e so devolve o 3.8 quando responde ok")

# 3.8 e 3.7 falham: o Gemini inteiro sai da fila e vai direto ao Groq
estado.update({"gemini-3.8-flash": erro503, "gemini-3.7-flash": APITimeoutError(request=req)})
fb._timeout_rapido = 0.0  # no teste, toda falha conta como "lenta" (demorou o limite inteiro)
saida = io.StringIO()
with redirect_stdout(saida):
    s4 = fb.solve(Q)
t = saida.getvalue()
# 3.8 e 3.7 falharam na mesma questao: o Gemini inteiro e pausado e vai direto ao Groq (nao tenta o 3.6)
assert s4.origem == "groq (openai/gpt-oss-120b)", s4.origem
assert "gemini-3.6-flash" not in chamadas[-3:], chamadas[-3:]
assert "passou para gemini (gemini-3.7-flash)" in t and "todos os modelos de gemini" in t, t
assert alertas[-1] == ["Algo deu errado: API do Gemini fora do ar.", "Algo deu errado: API do Gemini não está respondendo."], alertas[-1]
# durante a pausa do provedor, o Gemini nem e tocado
n = len(chamadas)
with redirect_stdout(io.StringIO()):
    fb.solve(Q)
assert chamadas[n:] == ["openai/gpt-oss-120b"], chamadas[n:]
print("dois falham (lentos) no mesmo provedor: pausa o provedor e vai ao proximo ok")
fb._timeout_rapido = 5.0

# intervalo do teste dobra a cada falha seguida e tem teto (conta feita num solver sem vigias)
from quizbot.solvers.fallback import FallbackSolver
from quizbot.solvers.fallback import TETO_PAUSA_VEZES
conta = FallbackSolver([fb._solvers[0]], cooldown=0.3)
assert abs(conta._pausa_para(0) - 0.3) < 1e-9
conta._falhas_seguidas[0] = 2
assert abs(conta._pausa_para(0) - 0.6) < 1e-9
conta._falhas_seguidas[0] = 99
assert abs(conta._pausa_para(0) - 0.3 * TETO_PAUSA_VEZES) < 1e-9  # teto

# tudo se recupera: o vigia devolve os dois modelos e o 3.8 volta a ser o primeiro
estado.clear()
with redirect_stdout(io.StringIO()):
    assert espera(lambda: not fb._pausados, 15), fb._pausados
    r = fb.solve(Q)
assert r.origem == "gemini (gemini-3.8-flash)" and not fb._falhas_seguidas, fb._falhas_seguidas
print("teste dobra, tem teto e o Gemini inteiro volta quando responde ok")

# --- falha RAPIDA nao pausa o provedor: 3.8 e 3.7 dao 503 na hora, o 3.6 ainda e tentado ---
chamadas.clear()
sondas.clear()
estado2 = {"gemini-3.8-flash": erro503, "gemini-3.7-flash": erro503}
c2 = cliente(estado2)
fb2 = fabrica.montar_solver() if False else None
with redirect_stdout(io.StringIO()):
    fb2 = fabrica.montar_solver()
for s in fb2._solvers:
    s._client = c2
fb2._cooldown = 30
with redirect_stdout(io.StringIO()):
    r2 = fb2.solve(Q)
assert r2.origem == "gemini (gemini-3.6-flash)" and chamadas == ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"], (r2.origem, chamadas)
print("falha rapida (503 imediato): ainda tenta o 3.6 antes de sair do Gemini ok")

# --- cota (429): o vigia espera o tempo que o servidor pediu ---
from quizbot.solvers.api import espera_da_cota
e429 = APIStatusError(
    "429", response=httpx.Response(429, request=req),
    body=[{"error": {"code": 429, "details": [{"@type": "x.RetryInfo", "retryDelay": "29493s"}]}}],
)
assert espera_da_cota(e429) == 29493.0  # o tempo REAL (8 h): o teto de 1 h so vale para o vigia dormir
e429b = APIStatusError("429", response=httpx.Response(429, request=req), body={"error": {"details": [{"retryDelay": "42s"}]}})
assert espera_da_cota(e429b) == 42.0
assert espera_da_cota(APIStatusError("429", response=httpx.Response(429, request=req), body="sem info")) is None  # o servidor nao disse
assert espera_da_cota(erro503) is None
chamadas.clear()
sondas.clear()
estado3 = {"gemini-3.8-flash": APIStatusError("429", response=httpx.Response(429, request=req), body={"x": "retryDelay: '5s'"})}
fb3 = None
with redirect_stdout(io.StringIO()):
    fb3 = fabrica.montar_solver()
for s in fb3._solvers:
    s._client = cliente(estado3)
fb3._cooldown = 0.2
with redirect_stdout(io.StringIO()):
    r3 = fb3.solve(Q)
assert r3.origem == "gemini (gemini-3.7-flash)"
time.sleep(1.0)  # o vigia normal testaria varias vezes; o pedido do servidor (5 s) manda esperar
assert sondas == [], sondas
assert 0 in fb3._pausados
print("cota 429: o vigia respeita a espera pedida pelo servidor ok")

# --- espera curta: so o ultimo da fila espera o tempo cheio; imagem espera o dobro ---
usados = []
from quizbot.solvers.base import Solver, SolverError


class Lento(Solver):
    def __init__(self, nome, falha):
        self._n, self.falha = nome, falha

    @property
    def nome(self):
        return self._n

    def solve(self, q):
        raise AssertionError("o FallbackSolver deve chamar solve_com_limite")

    def solve_com_limite(self, q, timeout):
        usados.append((self._n, timeout))
        if self.falha:
            raise SolverError(f"{self._n} fora")
        from quizbot.models import Suggestion
        return Suggestion(indice=0, explicacao="x", origem=self._n)

    def sondar(self, timeout):
        return False


from quizbot.solvers.base import Solver, SolverError
f2 = FallbackSolver([Lento("a", True), Lento("b", True), Lento("c", False)], timeout_rapido=5, timeout_final=15, cooldown=60)
with redirect_stdout(io.StringIO()):
    f2.solve(Q)
assert usados == [("a", 5), ("b", 5), ("c", 15)], usados  # c e o ultimo da fila: espera o tempo cheio
f3 = FallbackSolver([Lento("a", False)], timeout_rapido=5, timeout_final=15)
usados.clear()
f3.solve(Q)
assert usados == [("a", 15)], usados  # unico modelo: tempo cheio
from quizbot.models import Imagem
usados.clear()
f4 = FallbackSolver([Lento("a", True), Lento("b", False)], timeout_rapido=5, timeout_final=15, cooldown=60)
Qi = Question("Q?", ("a", "b"), (Imagem(b"x", "image/png"),))
with redirect_stdout(io.StringIO()):
    f4.solve(Qi)
assert usados == [("a", 10), ("b", 30)], usados
print("espera curta (5 s), ultimo da fila 15 s, imagem o dobro ok")

# --- registro: cabecalho e segredos escondidos ---
with tempfile.TemporaryDirectory() as pasta:
    arq = Path(pasta) / "r.log"
    antigo = sys.stdout, sys.stderr
    registro.iniciar(arq)
    try:
        os.environ["MEMORIA_SENHA"] = "senha-secreta-999"
        print("senha-secreta-999 vazou?")
        try:
            raise ValueError("falha de teste")
        except ValueError:
            registro.registrar_erro("erro de teste")
    finally:
        sys.stdout._arquivo.close()
        sys.stdout, sys.stderr = antigo
    texto = arq.read_text(encoding="utf-8")
assert "[registro] arquivo:" in texto and "procure por PROBLEMA" in texto
assert "senha-secreta-999" not in texto and "***" in texto
assert "PROBLEMA ===" in texto and "FIM DO PROBLEMA" in texto and "falha de teste" in texto
assert not hasattr(registro, "texto_para_ia")
print("registro: cabecalho, blocos PROBLEMA e segredos escondidos ok")

# --- janela: alerta simples (sem botoes); tela de erro inesperado continua com a pasta ---
from quizbot.config import PASTA_LOGS
from quizbot.janela import ALTURA, JanelaPresenter

j = JanelaPresenter()
assert not hasattr(j, "_botao_copiar") and not hasattr(j, "_botoes_log")
assert not j._botao_pasta.winfo_ismapped() and not j._alerta.winfo_ismapped()
j._mostrar_problemas(["gemini (gemini-3.8-flash): servidor sobrecarregado ou fora do ar (erro 503)."])
j._raiz.update()
assert j._alerta.winfo_ismapped() and not j._botao_pasta.winfo_ismapped()  # alerta SEM botao
assert "Detalhes" not in j._alerta.cget("text") and "botões" not in j._alerta.cget("text")
# a sugestao nao apaga o alerta
from quizbot.models import Suggestion
j._exibir(Question("e", ("a", "b")), Suggestion(indice=0, explicacao="x", origem="groq"))
j._raiz.update()
assert j._alerta.winfo_ismapped() and not j._botao_pasta.winfo_ismapped()
assert j._raiz.winfo_height() >= j._conteudo.winfo_reqheight()
# alerta some -> janela volta ao tamanho normal
j._mostrar_problemas([])
j._raiz.update()
assert not j._alerta.winfo_ismapped() and j._raiz.winfo_height() == ALTURA
# tela de erro inesperado: mostra a pasta e o botao (como foi aprovado antes) e cabe
j._erro(str(PASTA_LOGS))
j._raiz.update()
assert j._botao_pasta.winfo_ismapped() and j._raiz.winfo_height() >= j._conteudo.winfo_reqheight()
j._exibir(Question("e", ("a", "b")), Suggestion(indice=0, explicacao="x"))  # saiu do erro: botao some
j._raiz.update()
assert not j._botao_pasta.winfo_ismapped()
j._raiz.destroy()
print("janela: alerta simples sem botoes, erro inesperado com a pasta ok")
print("TUDO OK")
