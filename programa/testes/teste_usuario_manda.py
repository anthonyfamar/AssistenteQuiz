# TESTE - o clique do usuario vale mais que o programa.
#
# A IA demora e o usuario pode mudar de questao nesse tempo; o programa NAO pode marcar nem avancar a
# resposta velha na questao nova (isso desfaria o clique dele). Confere os tres momentos:
#   1) mudou de questao enquanto a IA respondia -> descarta a sugestao (nao mostra, nao marca, nao avanca);
#   2) mudou depois de marcar, antes de avancar -> nao avanca;
#   3) nada mudou -> o fluxo normal (marca e avanca).
import io
import pathlib
import sys
import threading
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import quizbot.assistente as A
from quizbot.models import Question, Suggestion

A.PAUSA_APOS_CLICAR = 0
A.PAUSA_ENTRE_TENTATIVAS = 0

Q1 = Question("Pergunta 1", ("x", "y", "z"))
Q2 = Question("Pergunta 2", ("x", "y", "z"))


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
        self.avisos, self.ofertas, self.mostradas = [], [], []

    def avisar(self, m): self.avisos.append(m)
    def consultando(self): pass
    def mostrar(self, q, s): self.mostradas.append(s)
    def oferecer_tentar_de_novo(self, mensagem, tentar): self.ofertas.append(mensagem)


class Resp:
    def __init__(self, ao_marcar=None):
        self.log, self.ao_marcar = [], ao_marcar

    def clicar(self, i):
        self.log.append(("clicar", i))
        if self.ao_marcar:
            self.ao_marcar()
        return True

    def avancar(self):
        self.log.append("avancar")
        return True


class IaLenta:
    """A resposta chega depois de o usuario ter mudado de questao (o clique dele acontece dentro do solve)."""

    def __init__(self, leitor=None):
        self.leitor = leitor

    def solve(self, questao):
        if self.leitor is not None:
            self.leitor.atual = Q2  # o usuario clicou em outra questao enquanto a IA pensava
        return Suggestion(indice=1, explicacao="x", origem="falso")


def montar(leitor, solver, resp):
    tela = Tela()
    return A.AssistenteQuiz(leitor, solver, tela, responder=resp, parar=threading.Event()), tela


def quieto(fn):
    saida = io.StringIO()
    with redirect_stdout(saida):
        fn()
    return saida.getvalue()


# 1) o usuario mudou de questao ENQUANTO a IA respondia
leitor, resp = Leitor(), Resp()
a, tela = montar(leitor, IaLenta(leitor), resp)
log = quieto(a._passo)
assert resp.log == [] and tela.mostradas == [] and tela.ofertas == [], (resp.log, tela.mostradas, tela.ofertas)
assert "descartei a sugestao antiga" in log, log
print("mudou de questao durante a consulta: a sugestao velha foi descartada (nada marcado, nada avancado) ok")

# 2) mudou DEPOIS de marcar, antes de avancar
leitor = Leitor()
resp = Resp(ao_marcar=lambda: setattr(leitor, "atual", Q2))
a, tela = montar(leitor, IaLenta(), resp)
log = quieto(a._passo)
assert resp.log == [("clicar", 1)], resp.log  # marcou (ainda era a Q1) e NAO avancou
assert "nao avancei" in log and tela.ofertas == [], (log, tela.ofertas)
print("mudou de questao depois de marcar: nao empurrou o usuario para a proxima ok")

# 3) nada mudou: fluxo normal
leitor, resp = Leitor(), Resp()
a, tela = montar(leitor, IaLenta(), resp)
quieto(a._passo)
assert resp.log == [("clicar", 1), "avancar"] and len(tela.mostradas) == 1 and tela.ofertas == [], (resp.log, tela.ofertas)
print("questao igual: marca e avanca como sempre ok")
print("TUDO OK")
