# TESTE - cotas e esperas dos provedores de IA.
#
# Confere (com solvers falsos, sem internet):
#   - como o tempo de espera e lido de cada provedor (Gemini, Groq, OpenRouter);
#   - limite por minuto de poucos segundos (Groq): o modelo NAO fica 30 s fora; volta no instante certo;
#   - erro permanente (402 "pede credito pago"): sai da fila de vez, sem testes em segundo plano;
#   - quando ninguem responde: o aviso diz a situacao de cada provedor e quanto falta (em horas);
#   - o assistente espera sozinho e tenta de novo se a espera for curta; se for longa, mostra o aviso.
import io
import pathlib
import sys
import threading
import time
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

try:
    import httpx
except ImportError:  # a biblioteca openai deste ambiente usa o pacote httpx2
    import httpx2 as httpx
from openai import APIStatusError

import quizbot.assistente as A
from quizbot.models import Question, Suggestion
from quizbot.solvers.api import espera_da_cota, explicar_erro, frase_curta
from quizbot.solvers.base import Solver, SolverError
from quizbot.solvers.fallback import FallbackSolver, formatar_espera

REQ = httpx.Request("POST", "https://x.test")


def erro429(corpo=None, mensagem="429", cabecalhos=None):
    return APIStatusError(mensagem, response=httpx.Response(429, request=REQ, headers=cabecalhos or {}), body=corpo)


# ---------- 1) como cada provedor diz quanto esperar ----------
groq = erro429(
    {"message": "Rate limit reached ... on tokens per minute (TPM): Limit 8000, Used 7024, Requested 1158. Please try again in 1.365s.",
     "type": "tokens"},
    "Error code: 429 - Please try again in 1.365s. Need more tokens?",
)
assert abs(espera_da_cota(groq) - 1.365) < 1e-6
assert abs(espera_da_cota(erro429(None, "Please try again in 7m12.5s.")) - 432.5) < 1e-6
assert abs(espera_da_cota(erro429(None, "Please retry in 5h55m51.547422961s.")) - (5 * 3600 + 55 * 60 + 51.547422961)) < 1e-6
assert espera_da_cota(erro429(None, "x", {"retry-after": "17"})) == 17.0
assert espera_da_cota(erro429([{"error": {"details": [{"retryDelay": "21351s"}]}}])) == 21351.0
reset = int((time.time() + 3 * 3600) * 1000)  # OpenRouter: epoch em milissegundos
horas = espera_da_cota(erro429({"error": {"metadata": {"headers": {"X-RateLimit-Reset": str(reset)}}}}))
assert 3 * 3600 - 5 < horas <= 3 * 3600 + 1, horas
assert espera_da_cota(erro429("sem informacao nenhuma")) is None  # o servidor nao disse: desconhecido
e402 = APIStatusError("402", response=httpx.Response(402, request=REQ), body={"message": "Add usage credits"})
assert espera_da_cota(e402) is None
assert "crédito" in explicar_erro(e402) and "crédito" in frase_curta(e402)
print("tempo de espera lido de Gemini, Groq (texto e cabecalho) e OpenRouter; 402 explicado ok")

assert formatar_espera(1.4) == "1 s" and formatar_espera(0.2) == "1 s"
assert formatar_espera(45) == "45 s" and formatar_espera(61) == "2 min" and formatar_espera(432) == "8 min"
assert formatar_espera(3600) == "1 h" and formatar_espera(21351) == "5 h 56 min", formatar_espera(21351)
print("formatar_espera ok")


# ---------- 2) solvers falsos ----------
Q = Question("Enunciado de teste", ("a", "b", "c"))


class Falso(Solver):
    """Responde conforme um roteiro: cada item e uma Suggestion ou um SolverError."""

    def __init__(self, nome, apelido, roteiro):
        self._nome, self._apelido, self.roteiro, self.chamadas = nome, apelido, list(roteiro), 0

    @property
    def nome(self):
        return self._nome

    @property
    def apelido(self):
        return self._apelido

    def solve(self, question):
        self.chamadas += 1
        item = self.roteiro.pop(0) if len(self.roteiro) > 1 else self.roteiro[0]
        if isinstance(item, Exception):
            raise item
        return item

    def solve_com_limite(self, question, timeout):
        return self.solve(question)

    def sondar(self, timeout):
        return False  # os testes nao dependem do vigia


def ok(origem):
    return Suggestion(indice=1, explicacao="x", origem=origem)


def quieto(fn, *args):
    with redirect_stdout(io.StringIO()):
        return fn(*args)


# 2a) Groq: limite por minuto de 1,4 s. Gemini fora por 6 h, Ollama pede credito.
gemini = Falso("gemini", "Gemini", [SolverError("g", motivo="limite de uso (cota) atingido", espera_sugerida=21351.0)])
groq_s = Falso("groq", "Groq", [SolverError("q", motivo="limite de uso (cota) atingido", espera_sugerida=1.4), ok("groq")])
ollama = Falso("ollama-cloud", "Ollama Cloud", [SolverError("o", motivo="pede crédito pago (erro 402)", permanente=True)])
fb = FallbackSolver([gemini, groq_s, ollama], cooldown=30.0)  # cooldown LONGO: provar que nao e ele que segura o Groq

try:
    quieto(fb.solve, Q)
    raise AssertionError("devia ter falhado: todos falharam neste instante")
except SolverError as erro:
    assert erro.espera_sugerida is not None and 0 < erro.espera_sugerida <= 1.5, erro.espera_sugerida
    espera_vista = erro.espera_sugerida
print("todos falharam, mas a que volta primeiro pediu 1,4 s: espera_sugerida =", f"{espera_vista:.1f} s")

# o Ollama (402) saiu de vez: sem vigia, e nao e chamado de novo
assert 2 in fb._permanentes and 2 not in fb._vigias
time.sleep(1.6)  # passou o 1,4 s do Groq (NAO os 30 s do cooldown)
sugestao = quieto(fb.solve, Q)
assert sugestao.origem == "groq", sugestao
assert ollama.chamadas == 1, f"o Ollama (pede credito) foi chamado de novo: {ollama.chamadas}x"
assert gemini.chamadas == 1  # o Gemini tem 6 h pela frente: nao foi tentado de novo
print("Groq voltou no instante pedido (1,4 s), sem esperar 30 s; Gemini (6 h) e Ollama (402) nao foram insistidos ok")

# 2b) ninguem responde: o aviso diz o que acontece com cada um e quanto falta
gemini2 = Falso("gemini", "Gemini", [SolverError("g", motivo="limite de uso (cota) atingido", espera_sugerida=21351.0)])
groq2 = Falso("groq", "Groq", [SolverError("q", motivo="limite de uso por dia atingido", espera_sugerida=432.0)])
router = Falso("openrouter", "OpenRouter", [SolverError("r", motivo="limite de uso (cota) atingido")])  # sem previsao
ollama2 = Falso("ollama-cloud", "Ollama Cloud", [SolverError("o", motivo="pede crédito pago (erro 402)", permanente=True)])
fb2 = FallbackSolver([gemini2, groq2, router, ollama2], cooldown=30.0)
try:
    quieto(fb2.solve, Q)
    raise AssertionError("devia falhar")
except SolverError as erro:
    texto = str(erro)
    assert "Gemini: limite de uso (cota) atingido, volta em 5 h 56 min, às " in texto, texto
    assert "Groq: limite de uso por dia atingido, volta em 8 min" in texto, texto
    assert "OpenRouter: limite de uso (cota) atingido, sem previsão" in texto, texto
    assert "Ollama Cloud: pede crédito pago (erro 402), fora da fila" in texto, texto
    assert "Volte mais tarde: a primeira a voltar é Groq, em 8 min." in texto, texto
    assert 430 <= erro.espera_sugerida <= 432.5
print("aviso quando ninguem responde:\n   " + texto)

# 2c) tudo pausado numa questao seguinte: o mesmo aviso (nao o antigo 'todos em pausa')
try:
    quieto(fb2.solve, Q)
    raise AssertionError("devia falhar")
except SolverError as erro:
    assert "Volte mais tarde" in str(erro) and "5 h 56 min" in str(erro)
print("questao seguinte (tudo em pausa): mesmo aviso, com a hora que falta ok")


# ---------- 3) o assistente espera sozinho se a espera for curta ----------
A.PAUSA_APOS_CLICAR = 0
A.PAUSA_ENTRE_TENTATIVAS = 0
Q1 = Question("Pergunta 1", ("x", "y", "z"))


class Leitor:
    def __init__(self):
        self.atual = Q1

    def ler_questao(self): return self.atual
    def questao_ja_respondida(self): return False
    def numero_da_questao(self): return None
    def ler_resumo(self): return None
    def ler_menu(self): return None
    def ler_painel(self): return None


class Tela:
    def __init__(self):
        self.ofertas, self.mostradas, self.avisos = [], [], []

    def avisar(self, m): self.avisos.append(m)
    def consultando(self): pass
    def mostrar(self, q, s): self.mostradas.append(s)
    def oferecer_tentar_de_novo(self, mensagem, tentar): self.ofertas.append((mensagem, tentar))


class Resp:
    def clicar(self, i): return True
    def avancar(self): return True


def montar(solver):
    tela = Tela()
    return A.AssistenteQuiz(Leitor(), solver, tela, responder=Resp(), parar=threading.Event()), tela


# espera curta (0,3 s): espera e tenta de novo SOZINHO, sem oferecer nada ao usuario
curto = Falso("groq", "Groq", [SolverError("q", espera_sugerida=0.3), ok("groq")])
a, tela = montar(curto)
ini = time.monotonic()
quieto(a._passo)
assert curto.chamadas == 2 and len(tela.mostradas) == 1 and tela.ofertas == [], (curto.chamadas, tela.ofertas)
assert 0.3 <= time.monotonic() - ini < 3
print("espera curta: o assistente esperou 0,3 s e tentou de novo sozinho (1 sugestao, nenhuma oferta) ok")

# espera curta que NAO resolve: tenta so UMA vez a mais (nao fica em laco) e depois oferece
teimoso = Falso("groq", "Groq", [SolverError("q", espera_sugerida=0.2)])
a, tela = montar(teimoso)
quieto(a._passo)
assert teimoso.chamadas == 2 and len(tela.ofertas) == 1, (teimoso.chamadas, tela.ofertas)
print("espera curta que nao resolve: 2 tentativas no total, depois 'Tentar de novo' ok")

# espera longa (horas): nao espera; mostra o aviso com as horas e o botao
longo = Falso("gemini", "Gemini", [SolverError(
    "nenhuma IA respondeu agora. Gemini: limite de uso (cota) atingido, volta em 5 h 56 min, às 04:31. "
    "Volte mais tarde: a primeira a voltar é Gemini, em 5 h 56 min.", espera_sugerida=21351.0)])
a, tela = montar(longo)
ini = time.monotonic()
quieto(a._passo)
assert longo.chamadas == 1 and time.monotonic() - ini < 2
assert len(tela.ofertas) == 1 and "5 h 56 min" in tela.ofertas[0][0] and "Volte mais tarde" in tela.ofertas[0][0], tela.ofertas
assert tela.ofertas[0][0].startswith("Não consegui uma sugestão: ")
print("espera longa: nao esperou; o aviso mostra as horas e fica com o botao ok")
print("TUDO OK")
