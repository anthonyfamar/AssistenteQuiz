import sys
import threading

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import quizbot.assistente as A
from quizbot.models import Question, Suggestion
from quizbot.solvers.base import SolverError

A.PAUSA_APOS_CLICAR = 0
A.PAUSA_ENTRE_TENTATIVAS = 0

Q1 = Question("Pergunta 1", ("x", "y", "z"))
Q2 = Question("Pergunta 2", ("x", "y", "z"))


class Leitor:
    def __init__(self, atual):
        self.atual = atual

    def ler_questao(self): return self.atual
    def questao_ja_respondida(self): return False
    def numero_da_questao(self): return None
    def ler_resumo(self): return None
    def ler_menu(self): return None
    def ler_painel(self): return None


class Tela:
    def __init__(self):
        self.avisos, self.ofertas, self.mostradas, self.consultas = [], [], [], 0

    def avisar(self, m): self.avisos.append(m)
    def consultando(self): self.consultas += 1
    def mostrar(self, q, s): self.mostradas.append(s)

    def oferecer_tentar_de_novo(self, mensagem, tentar):
        self.ofertas.append((mensagem, tentar))


class Resp:
    def __init__(self, marca=(True,), avanca=(True,)):
        self.marca, self.avanca, self.log = list(marca), list(avanca), []

    def clicar(self, i):
        self.log.append(("clicar", i))
        return self.marca.pop(0) if len(self.marca) > 1 else self.marca[0]

    def avancar(self):
        self.log.append("avancar")
        return self.avanca.pop(0) if len(self.avanca) > 1 else self.avanca[0]


class Solver:
    def __init__(self, respostas):
        self.respostas, self.chamadas = list(respostas), 0

    def solve(self, q):
        self.chamadas += 1
        r = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        if isinstance(r, Exception):
            raise r
        return Suggestion(indice=r, explicacao="x", origem="falso")


def montar(leitor, resp, solver):
    tela = Tela()
    return A.AssistenteQuiz(leitor, solver, tela, responder=resp, parar=threading.Event()), tela


# 1) nao conseguiu MARCAR (2 tentativas): a SUGESTAO foi mostrada, oferece "Tentar de novo" e NAO avanca
leitor, resp = Leitor(Q1), Resp(marca=(False, False))
a, tela = montar(leitor, resp, Solver([1]))
a._passo()
assert resp.log == [("clicar", 1), ("clicar", 1)], resp.log  # 2 tentativas, nao avancou
assert len(tela.mostradas) == 1 and tela.mostradas[0].indice == 1  # a sugestao ficou na tela
assert len(tela.ofertas) == 1 and "alternativa B" in tela.ofertas[0][0] and "tente de novo" in tela.ofertas[0][0], tela.ofertas
print("falhou ao marcar: sugestao mantida + oferta de 'Tentar de novo', sem avancar ok")

# ... o usuario toca no botao: marca (agora funciona) e avanca; o fluxo segue
resp.marca = [True]
resp.avanca = [True]
resp.log.clear()
tela.ofertas[0][1]()  # o botao da janela: so avisa (outra thread)
assert a._repetir.is_set() and resp.log == []  # ainda nao agiu: quem age e o laco
a._passo()
assert resp.log == [("clicar", 1), "avancar"], resp.log
assert not a._repetir.is_set() and a._repeticao is None
assert tela.consultas == 1 and a._solver.chamadas == 1  # NAO consultou a IA de novo
print("'Tentar de novo': o laco marca, avanca e segue, sem gastar IA ok")

# 2) MARCOU, nao conseguiu AVANCAR (e a pagina ainda e a mesma questao): oferece de novo
leitor, resp = Leitor(Q1), Resp(avanca=(False, False))
a, tela = montar(leitor, resp, Solver([2]))
a._passo()
assert resp.log == [("clicar", 2), "avancar", "avancar"], resp.log
assert "Marquei a alternativa C, mas não consegui avançar" in tela.ofertas[0][0], tela.ofertas
resp.avanca = [True]
resp.log.clear()
tela.ofertas[0][1]()
a._passo()
assert resp.log == [("clicar", 2), "avancar"], resp.log  # marcar e seguro de repetir (so clica se faltar)
print("marcou mas nao avancou: oferece e, ao tocar, avanca ok")

# 3) o "avancar" falhou, mas a pagina JA mudou (avancou sozinho): nao repete, nao oferece nada
leitor = Leitor(Q1)
resp = Resp(avanca=(False,))
a, tela = montar(leitor, resp, Solver([1]))


class LeitorQueAvanca(Leitor):
    def __init__(self):
        super().__init__(Q1)
        self.chamadas = 0

    def ler_questao(self):
        self.chamadas += 1
        return Q1 if self.chamadas == 1 else Q2  # 1a leitura (do laco): Q1; depois a pagina mudou


leitor = LeitorQueAvanca()
a, tela = montar(leitor, Resp(avanca=(False,)), Solver([1]))
a._passo()
assert tela.ofertas == [], tela.ofertas
print("avancar que 'falhou' mas a pagina ja mudou: nao repete nem oferece ok")

# 4) a IA NAO conseguiu sugerir: tambem oferece "Tentar de novo" (a questao nao fica parada)
leitor, resp = Leitor(Q1), Resp()
solver = Solver([SolverError("todas as IAs fora do ar"), 0])
a, tela = montar(leitor, resp, solver)
a._passo()
assert solver.chamadas == 1 and tela.mostradas == [] and resp.log == []
assert "Não consegui uma sugestão" in tela.ofertas[0][0], tela.ofertas
tela.ofertas[0][1]()
a._passo()
assert solver.chamadas == 2 and len(tela.mostradas) == 1  # consultou de novo
assert resp.log == [("clicar", 0), "avancar"], resp.log
print("IA sem resposta: oferece 'Tentar de novo', consulta de novo e segue ok")

# 5) o usuario seguiu sozinho (a pagina mudou) antes de tocar: o botao nao faz nada
leitor, resp = Leitor(Q1), Resp(marca=(False, False))
a, tela = montar(leitor, resp, Solver([1]))
a._passo()
leitor.atual = Q2  # o usuario marcou e avancou na mao
resp.marca, resp.log = [True], []
tela.ofertas[0][1]()
a._passo()
assert resp.log == [], resp.log
print("usuario seguiu sozinho antes de tocar: o botao nao repete nada ok")

# 6) questao nova: a oferta antiga some (nao vale mais)
leitor, resp = Leitor(Q1), Resp(marca=(False, False))
a, tela = montar(leitor, resp, Solver([1]))
a._passo()
assert a._repeticao is not None
leitor.atual = Q2
resp.marca = [True]
a._passo()  # le a questao 2
assert a._repeticao is None
print("questao nova: a oferta anterior e descartada ok")
print("TUDO OK")
