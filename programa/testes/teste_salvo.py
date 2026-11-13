import sys
import tempfile
from pathlib import Path

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from quizbot.armazenamento import Armazenamento, ArmazenamentoEspelhado, ArmazenamentoLocal, juntar_dados
from quizbot.assistente import AssistenteQuiz
from quizbot.memoria import Memoria
from quizbot.models import Question, Resultado


class Nuvem(Armazenamento):
    def __init__(self):
        self.fora = True
        self.gravacoes = 0
        self.dados = {}

    def ler_todos(self):
        if self.fora:
            raise ConnectionError("sem internet")
        return {"geral": self.dados}

    def gravar(self, dados):
        if self.fora:
            raise ConnectionError("sem internet")
        self.gravacoes += 1
        self.dados = juntar_dados(self.dados, dados)
        return True


class Leitor:
    def ler_revisao(self):
        return [Resultado(Question("Q?", ("a", "b")), 0, True), Resultado(Question("R?", ("a", "b")), 1, False)]
    def ler_questao(self):
        return None


class Pres:
    def __init__(self): self.msgs = []
    def avisar(self, m): self.msgs.append(m)
    def consultando(self): pass
    def mostrar(self, *a): pass


class Resp:
    def __init__(self): self.cliques = 0
    def terminar_revisao(self): self.cliques += 1; return True
    def terminar(self): return False


agora = [0.0]
pasta = Path(tempfile.mkdtemp())
nuvem = Nuvem()
mem = Memoria(ArmazenamentoEspelhado(ArmazenamentoLocal(pasta, "PC"), nuvem), "PC", relogio=lambda: agora[0])

# 1) nuvem fora do ar: o local grava, ele CLICA na hora (nao espera a nuvem)
resp, pres = Resp(), Pres()
a = AssistenteQuiz(Leitor(), None, pres, responder=resp, finalizar=True, memoria=mem)
a._enviada_em = 1.0  # o programa acabou de enviar a tentativa: a revisao e dele (ele fecha)
a._passo(); a._passo()
assert resp.cliques == 1, resp.cliques
assert (pasta / "memoria-PC.json").exists() and nuvem.dados == {}
assert not any("salvar" in m for m in pres.msgs), pres.msgs
print("1) clica com a nuvem fora do ar ok")

# 2) a nuvem volta: na proxima leitura (5 min depois) o que so estava no local SOBE sozinho
nuvem.fora = False
agora[0] += 301
mem.erradas(Question("outra?", ("x", "y")))  # qualquer uso dispara a sincronia
assert len(nuvem.dados) == 2 and nuvem.gravacoes == 1, (nuvem.dados, nuvem.gravacoes)
# e nao grava de novo se nao ha diferenca (poupa as escritas)
agora[0] += 301
mem.erradas(Question("outra?", ("x", "y")))
assert nuvem.gravacoes == 1, nuvem.gravacoes
print("2) sobe sozinho depois, sem regravar a toa ok")

# 3) fechou o programa com algo pendente: ao abrir de novo, sobe
nuvem2 = Nuvem()
mem_a = Memoria(ArmazenamentoEspelhado(ArmazenamentoLocal(pasta, "PC"), nuvem2), "PC")
mem_a.registrar(Question("S?", ("a", "b")), 0, False)  # nuvem2 fora: so local
assert nuvem2.dados == {}
nuvem2.fora = False
mem_b = Memoria(ArmazenamentoEspelhado(ArmazenamentoLocal(pasta, "PC"), nuvem2), "PC")  # reabre
mem_b.atualizar()
assert len(nuvem2.dados) >= 3, nuvem2.dados  # tudo que o PC sabia chegou na nuvem
print("3) reabrir sobe o pendente ok")

# 4) nada grava (disco falhando E nuvem fora): NAO clica, nao derruba o laco, avisa uma vez
class Disco(Armazenamento):
    def ler_todos(self): return {}
    def gravar(self, dados): raise PermissionError("sem permissao")

nuvem3 = Nuvem()
mem3 = Memoria(ArmazenamentoEspelhado(Disco(), nuvem3), "PC3", relogio=lambda: agora[0])
resp3, pres3 = Resp(), Pres()
c = AssistenteQuiz(Leitor(), None, pres3, responder=resp3, finalizar=True, memoria=mem3)
c._enviada_em = 1.0
c._passo(); c._passo()
assert resp3.cliques == 0
assert len([m for m in pres3.msgs if "salvar" in m]) == 1, pres3.msgs
# o disco volta a funcionar (aqui: a nuvem volta): na proxima tentativa (10 s) grava e clica
nuvem3.fora = False
agora[0] += 11
c._passo()
assert resp3.cliques == 1 and len(nuvem3.dados) == 2
print("4) so espera se nada gravou ok")

# 5) disco falhando mas nuvem ok: guardou na nuvem, clica
nuvem4 = Nuvem(); nuvem4.fora = False
mem4 = Memoria(ArmazenamentoEspelhado(Disco(), nuvem4), "PC4")
resp4 = Resp()
d = AssistenteQuiz(Leitor(), None, Pres(), responder=resp4, finalizar=True, memoria=mem4)
d._enviada_em = 1.0
d._passo()
assert resp4.cliques == 1 and len(nuvem4.dados) == 2
print("5) so a nuvem gravou: clica ok")

# 6) so local, sem nuvem configurada
mem5 = Memoria(ArmazenamentoLocal(Path(tempfile.mkdtemp()), "PC5"), "PC5")
resp5 = Resp()
e = AssistenteQuiz(Leitor(), None, Pres(), responder=resp5, finalizar=True, memoria=mem5)
e._enviada_em = 1.0
e._passo()
assert resp5.cliques == 1
print("TUDO OK")
