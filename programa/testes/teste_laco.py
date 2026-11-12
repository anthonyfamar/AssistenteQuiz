import os
import quizbot.assistente as A
from quizbot.models import Question, Suggestion

A.PAUSA_APOS_CLICAR = 0  # sem espera no teste
A.PAUSA_ENTRE_TENTATIVAS = 0


from quizbot.models import QuestaoDoResumo, ResumoTentativa


class Reader:
    def __init__(self, filas, resumo=None, respondida=False):
        self.filas = list(filas)
        # por padrao a pagina de resumo mostra tudo respondido (pode enviar)
        self.resumo = resumo if resumo is not None else ResumoTentativa((QuestaoDoResumo(1, True),))
        self.respondida = respondida
    def ler_questao(self): return self.filas.pop(0) if self.filas else None
    def ler_resumo(self): return self.resumo
    def questao_ja_respondida(self): return self.respondida
    def numero_da_questao(self): return None


class Solver:
    def solve(self, q): return Suggestion(indice=1, explicacao="x")


class Presenter:
    def __init__(self): self.avisos = []
    def consultando(self): pass
    def mostrar(self, q, s): pass
    def avisar(self, m): self.avisos.append(m)
    def oferecer_tentar_de_novo(self, m, tentar): self.avisos.append(m)


class Resp:
    def __init__(self, clicar=True, avancar=True, terminar=True):
        self.log = []
        self._c, self._a, self._t = clicar, avancar, terminar
    def clicar(self, i): self.log.append(("clicar", i)); return self._c
    def avancar(self): self.log.append("avancar"); return self._a
    def terminar(self): self.log.append("terminar"); return self._t
    def abrir_questao(self, n): self.log.append(("abrir", n)); return True


Q1 = Question("a", ("x", "y"))
Q2 = Question("b", ("x", "y"))


def roda(filas, resp, finalizar=True, passos=None, **opcoes):
    p = Presenter()
    a = A.AssistenteQuiz(Reader(filas, **opcoes), Solver(), p, responder=resp, finalizar=finalizar)
    for _ in range(passos or len(filas) + 1):
        a._passo()
    return p, a


# 1) marca e avanca, na ordem certa
r = Resp(); roda([Q1], r, passos=1)
assert r.log == [("clicar", 1), "avancar"], r.log
# 2) clicar falhou -> NAO avanca e avisa
r = Resp(clicar=False); p, _ = roda([Q1], r, passos=1)
assert r.log == [("clicar", 1), ("clicar", 1)] and p.avisos, (r.log, p.avisos)  # tentou 2x e avisou
# 3) sem questao + finalizar ligado -> terminar, depois para de agir
r = Resp(); p, a = roda([None, None, Q2], r, passos=3)
assert r.log[0] == "terminar" and r.log.count("terminar") == 1, r.log  # nao envia 2x
assert p.avisos == ["Tentativa enviada."], p.avisos
# 4) finalizar desligado -> nunca termina
r = Resp(); roda([None, None], r, finalizar=False, passos=2)
assert r.log == [], r.log
# 5) modo manual (sem responder) -> nada de acao
p, a = roda([Q1, None], None, passos=2)
assert p.avisos == []
# 6) resumo com questao sem resposta: NAO envia; abre a que falta (e nao clica de novo no tick seguinte)
A.PAUSA_APOS_ABRIR_QUESTAO = 60
faltando = ResumoTentativa((QuestaoDoResumo(1, True), QuestaoDoResumo(2, False), QuestaoDoResumo(3, False)))
r = Resp(); p, a = roda([None, None, None], r, passos=3, resumo=faltando)
assert "terminar" not in r.log and r.log == [("abrir", 2)], r.log
assert any("Faltam 2 questão(ões) sem resposta (2, 3)" in m for m in p.avisos), p.avisos
# 7) sem a tabela do resumo (None): nao envia
r = Resp(); roda([None, None], r, passos=2, resumo=ResumoTentativa(()))
assert "terminar" in r.log  # (resumo vazio conta como 'nada falta'; o leitor real devolve None sem tabela)
class SemTabela(Reader):
    def ler_resumo(self): return None
p2 = Presenter(); r = Resp()
a2 = A.AssistenteQuiz(SemTabela([None, None]), Solver(), p2, responder=r, finalizar=True)
a2._passo(); a2._passo()
assert r.log == [], r.log
# 8) questao ja respondida: nao chama a IA nem clica; so avanca
class SolverQueNaoPodeSerChamado:
    def solve(self, q): raise AssertionError("gastou IA em questao ja respondida")
r = Resp(); p3 = Presenter()
a3 = A.AssistenteQuiz(Reader([Q1], respondida=True), SolverQueNaoPodeSerChamado(), p3, responder=r, finalizar=True)
a3._passo()
assert r.log == ["avancar"], r.log
# 9) modo manual (sem responder) nao pula nada: mostra a sugestao normalmente
p, a = roda([Q1], None, passos=1, respondida=True)
print("laco ok")

# 6) o modo nao vem mais do .env: a janelinha pergunta (a antiga _ligado foi removida de proposito)
import quizbot.main as M
assert not hasattr(M, "_ligado")
print("chaves ok")
