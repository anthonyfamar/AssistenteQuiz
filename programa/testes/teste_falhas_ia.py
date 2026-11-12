import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

try:
    import httpx
except ModuleNotFoundError:  # a versao instalada do openai usa o httpx2
    import httpx2 as httpx
from openai import APIStatusError, APITimeoutError

from quizbot import registro
from quizbot.models import Question, Suggestion
from quizbot.solvers.api import ApiSolver
from quizbot.solvers.base import Solver, SolverError
from quizbot.solvers.fallback import FallbackSolver

CHAVE = "AIzaSy-CHAVE-SECRETA-123456"
os.environ["GEMINI_API_KEY"] = CHAVE  # o registro deve esconder qualquer valor assim
Q = Question("Quanto e 1+1?", ("1", "2"))
req = httpx.Request("POST", "https://x/y")


def status(codigo, corpo):
    resp = httpx.Response(codigo, request=req)
    return APIStatusError(f"Error code: {codigo} - {corpo} (chave {CHAVE})", response=resp, body=corpo)


class ClienteFalso:
    def __init__(self, acao):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=acao))


def api(acao, nome="gemini", modelo="gemini-3.8-flash"):
    return ApiSolver(nome, ClienteFalso(acao), modelo)


def levanta(e):
    def f(**kw):
        raise e
    return f


def resposta(texto):
    msg = SimpleNamespace(content=texto)
    return lambda **kw: SimpleNamespace(choices=[SimpleNamespace(message=msg)])


# --- 1) ApiSolver: resumo claro + detalhe completo para cada tipo de erro ---
casos = [
    (status(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}}), "sobrecarregado", "503"),
    (APITimeoutError(request=req), "não respondeu a tempo", "APITimeoutError"),
    (status(429, {"error": "quota"}), "limite de uso", "429"),
    (status(401, {"error": "bad key"}), "chave recusada", "401"),
    (status(404, {"error": "no model"}), "modelo não encontrado", "404"),
]
for erro, trecho, no_detalhe in casos:
    try:
        api(levanta(erro)).solve(Q)
        raise AssertionError("devia falhar")
    except SolverError as e:
        assert trecho in e.resumo and "gemini-3.8-flash" in e.resumo, e.resumo
        assert "Modelo           : gemini-3.8-flash" in e.detalhe and "Tempo até falhar" in e.detalhe, e.detalhe
        assert no_detalhe in e.detalhe, e.detalhe
        assert e.__cause__ is erro  # o erro original continua encadeado (vai no rastro)
# o aviso da janela: uma frase direta por tipo de problema (o detalhe fica so no log)
avisos = {
    "503": "Algo deu errado: API do gemini fora do ar.",
    "APITimeoutError": "Algo deu errado: API do gemini não está respondendo.",
    "429": "Algo deu errado: API do gemini atingiu o limite de uso.",
    "401": "Algo deu errado: API do gemini recusou a chave.",
    "404": "Algo deu errado: API do gemini não achou o modelo.",
}
for erro, trecho, chave in casos:
    try:
        api(levanta(erro)).solve(Q)
    except SolverError as e:
        assert e.aviso == avisos[chave], (e.aviso, chave)
        assert "gemini-3.8-flash" not in e.aviso and "503" not in e.aviso
try:
    api(resposta("texto sem json")).solve(Q)
except SolverError as e:
    assert e.aviso == "Algo deu errado: API do gemini respondeu num formato errado.", e.aviso
status503 = casos[0][0]
try:
    api(levanta(status503)).solve(Q)
except SolverError as e:
    assert "high demand" in e.detalhe and "Resposta servidor" in e.detalhe
# formato errado: o detalhe guarda o texto que a IA devolveu
try:
    api(resposta("oi, nao sei responder")).solve(Q)
except SolverError as e:
    assert "fora do formato" in e.resumo and "oi, nao sei responder" in e.detalhe
assert api(resposta('{"indice": 1, "explicacao": "2"}')).solve(Q).origem == "gemini (gemini-3.8-flash)"
# sucesso continua igual
assert api(resposta('{"indice": 1, "explicacao": "2"}')).solve(Q).indice == 1
print("ApiSolver: resumo + detalhe ok")


# --- 2) FallbackSolver: log completo + alerta que aparece e some ---
class Falso(Solver):
    def __init__(self, nome, acoes):
        self._nome, self.acoes = nome, list(acoes)

    @property
    def nome(self):
        return self._nome

    def solve(self, question):
        a = self.acoes.pop(0) if len(self.acoes) > 1 else self.acoes[0]
        if isinstance(a, Exception):
            raise a
        return Suggestion(indice=a, explicacao="x", origem=self._nome)


ruim = api(levanta(status503))
bom = Falso("groq", [1])
alertas = []
fb = FallbackSolver([ruim, bom], cooldown=0.3, ao_mudar_problemas=lambda p: alertas.append(list(p)))
saida = io.StringIO()
with redirect_stdout(saida):
    s = fb.solve(Q)
texto = saida.getvalue()
assert s.origem == "groq"
assert alertas == [["Algo deu errado: API do gemini fora do ar."]], alertas  # direto e simples, sem modelo nem codigo
for trecho in ("PROBLEMA COM A IA", "FIM DO PROBLEMA", "Modelo           : gemini-3.8-flash", "Código HTTP      : 503",
               "high demand", "rastro técnico", "APIStatusError", "O programa fez   : tirou este modelo da fila",
               "passou para groq"):
    assert trecho in texto, (trecho, texto)
# a ordem do bloco: primeiro o que um humano precisa, so no fim o rastro tecnico
assert texto.index("O que aconteceu") < texto.index("O programa fez") < texto.index("rastro técnico") < texto.index("FIM DO PROBLEMA")
# durante a pausa nao tenta de novo nem repete o alerta
with redirect_stdout(io.StringIO()):
    fb.solve(Q)
assert len(alertas) == 1
# provedor ruim volta a funcionar: o vigia (segundo plano) percebe e ele volta para a fila
import time
ruim._client = ClienteFalso(resposta('{"indice": 0, "explicacao": "ok"}'))
saida = io.StringIO()
with redirect_stdout(saida):
    time.sleep(0.8)  # o vigia testa a cada 0.3 s (dobrando)
    s = fb.solve(Q)
assert "voltou a funcionar" in saida.getvalue(), saida.getvalue()
assert s.origem == "gemini (gemini-3.8-flash)", s.origem
print("FallbackSolver: log completo, vigia devolve o modelo para a fila ok")

# todos falham: a mensagem final usa os resumos curtos
a = FallbackSolver([api(levanta(status503)), api(levanta(APITimeoutError(request=req)), "groq", "m2")], cooldown=1)
try:
    with redirect_stdout(io.StringIO()):
        a.solve(Q)
except SolverError as e:
    assert "sobrecarregado" in str(e) and "não respondeu a tempo" in str(e) and "Traceback" not in str(e), str(e)
print("todos falham: mensagem curta ok")

# --- 3) o log real nao guarda a chave ---
with tempfile.TemporaryDirectory() as pasta:
    arq = Path(pasta) / "teste.log"
    antigo_out, antigo_err = sys.stdout, sys.stderr
    registro.iniciar(arq)
    try:
        FallbackSolver([api(levanta(status503))], cooldown=1).solve(Q)
    except SolverError:
        pass
    finally:
        sys.stdout._arquivo.close()
        sys.stdout, sys.stderr = antigo_out, antigo_err
    conteudo = arq.read_text(encoding="utf-8")
assert CHAVE not in conteudo and "***" in conteudo, "a chave vazou no log!"
assert "Código HTTP      : 503" in conteudo and "high demand" in conteudo
assert "[registro] arquivo:" in conteudo and "PROBLEMA" in conteudo and "Python" in conteudo
print("log: erro completo gravado e chave escondida ok")

# --- 4) janela: o alerta cabe no pior caso e some ---
from quizbot.janela import ALTURA, JanelaPresenter

j = JanelaPresenter()
longa = Suggestion(indice=0, explicacao="Esta e uma explicacao longa de duas frases para testar o tamanho. " * 2, origem="groq")
q = Question("e" * 50, ("alternativa bem comprida " * 4,) * 5)
j._exibir(q, longa)
j._mostrar_problemas([
    "gemini (gemini-3.8-flash): servidor sobrecarregado ou fora do ar (erro 503).",
])
j._raiz.update_idletasks()
altura_com = j._conteudo.winfo_reqheight()
print("altura pedida com 1 alerta:", altura_com, "de", ALTURA)
j._mostrar_problemas([])
j._raiz.update_idletasks()
altura_sem = j._conteudo.winfo_reqheight()
assert altura_sem < altura_com and not j._alerta.winfo_ismapped()
# a janela cresce so quando precisa: com alerta e texto longo, cabe tudo
j._mostrar_problemas(["gemini (gemini-3.8-flash): servidor sobrecarregado ou fora do ar (erro 503)."])
j._raiz.update_idletasks()
assert j._raiz.winfo_height() >= j._conteudo.winfo_reqheight(), (j._raiz.winfo_height(), j._conteudo.winfo_reqheight())
print("  janela com alerta + texto longo:", j._raiz.winfo_height(), "px")
# sugestao curta: volta ao tamanho normal
j._exibir(Question("e", ("a", "b")), Suggestion(indice=0, explicacao="curta"))
j._mostrar_problemas([])
j._raiz.update_idletasks()
assert j._raiz.winfo_height() == ALTURA, j._raiz.winfo_height()
# a tela de escolha do modo nao e afetada pelo ajuste
j2 = None
j._raiz.destroy()
print("janela: alerta cabe e some ok")
print("TUDO OK")
