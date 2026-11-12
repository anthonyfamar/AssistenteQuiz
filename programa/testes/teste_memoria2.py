import base64
import json
import sys
import tempfile
from pathlib import Path

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from playwright.sync_api import sync_playwright

from quizbot.armazenamento import (
    Armazenamento,
    ArmazenamentoEspelhado,
    ArmazenamentoLocal,
    juntar_dados,
)
from quizbot.assistente import AssistenteQuiz
from quizbot.memoria import Memoria
from quizbot.models import Imagem, Question, Resultado, Suggestion
from quizbot.page_reader import PageReader
from quizbot.responder import Responder
from quizbot.solvers import Solver, SolverComMemoria

PNG = b"\x89PNG\r\n\x1a\n"

# ============ navegador de verdade: leitura da revisao, cliques, imagens ============
REVISAO = """
<div class="que multichoice incorrect"><div class="content"><div class="formulation clearfix">
 <div class="qtext"><p>Qual a representacao?</p></div>
 <div class="ablock"><div class="answer">
  <div class="r0 incorrect"><input type="radio" disabled value="0" checked="checked">
     <label for="a0">a. um</label> <img class="questioncorrectnessicon" alt="Incorreto"></div>
  <div class="r1"><input type="radio" disabled value="1"><label for="a1">b. dois</label> </div>
  <div class="r0"><input type="radio" disabled value="2"><label for="a2">c. tres</label> </div>
 </div></div></div></div></div>
<div class="que multichoice correct"><div class="content"><div class="formulation clearfix">
 <div class="qtext"><p>Metodo da bissecção?</p></div>
 <div class="ablock"><div class="answer">
  <div class="r0 correct"><input type="radio" disabled value="0" checked="checked">
     <label for="b0">a. I e III.</label> <img class="questioncorrectnessicon" alt="Correto"></div>
  <div class="r1"><input type="radio" disabled value="1"><label for="b1">b. I e II.</label> </div>
 </div></div></div></div></div>
"""
VIVA = """
<div class="que"><div class="qtext"><p>Pergunta viva?</p></div><div class="answer">
 <div class="r0"><input type="radio" value="0"><label>a. um</label></div>
 <div class="r1"><input type="radio" value="1"><label>b. dois</label></div>
 <div class="r0"><input type="radio" value="2"><label>c. tres</label></div></div></div>
<input type="submit" name="next" value="Finalizar tentativa ..." class="mod_quiz-next-nav btn btn-primary">
"""
RESUMO = """<button type="submit" class="btn btn-secondary" id="single_button6ae">Enviar tudo e terminar</button>
<script>document.querySelector('button').onclick = e => { e.preventDefault();
  const d = document.createElement('div');
  d.innerHTML = '<input type="button" class="btn btn-primary" id="id_yuiconfirmyes-yui_99" value="Enviar tudo e terminar">';
  document.body.appendChild(d); d.querySelector('input').onclick = () => document.title = 'ENVIADO'; };</script>"""


def uri(n):
    return "data:image/png;base64," + base64.b64encode(PNG + bytes([n]) * 20).decode()


def pagina_imagens(ordem):
    alts = "".join(
        f'<div class="r{i % 2}"><input type="radio" value="{i}"><label>{"abc"[i]}. <img src="{uri(n)}"></label></div>'
        for i, n in enumerate(ordem)
    )
    return f'<div class="que"><div class="qtext"><p>Qual figura?</p></div><div class="answer">{alts}</div></div>'


def cod(n):
    return "[img:" + Imagem(dados=PNG + bytes([n]) * 20, tipo="image/png").codigo + "]"


with sync_playwright() as p:
    try:
        nav = p.chromium.launch(channel="msedge", headless=True)
    except Exception:
        nav = p.chromium.launch(headless=True)
    ctx = nav.new_context()
    pag = ctx.new_page()
    reader = PageReader(ctx)

    pag.set_content(REVISAO)
    res = reader.ler_revisao()
    assert len(res) == 2 and not res[0].acertou and res[1].acertou, res
    assert res[0].questao.alternativas == ("um", "dois", "tres")
    pag.set_content(VIVA)
    assert reader.ler_revisao() == [] and reader.ler_questao().alternativas == ("um", "dois", "tres")
    r = Responder(ctx)
    assert r.clicar(2) and pag.locator("input[value='2']").is_checked() and not r.clicar(9)
    pag.set_content(RESUMO)
    assert r.terminar() and pag.title() == "ENVIADO"
    pag.set_content(pagina_imagens([1, 2, 3])); l1 = reader.ler_questao()
    pag.set_content(pagina_imagens([3, 1, 2])); l2 = reader.ler_questao()
    assert l1.assinaturas == (cod(1), cod(2), cod(3)) and l2.assinaturas == (cod(3), cod(1), cod(2))
    nav.close()
print("navegador ok (revisao, cliques, imagens embaralhadas)")

# ============ memoria com varios PCs ============
pasta = Path(tempfile.mkdtemp())
tempo = [0.0]
relogio = lambda: tempo[0]


class Conta(Armazenamento):
    """Embrulha outro armazenamento contando leituras e gravacoes."""
    def __init__(self, base): self.base, self.leituras, self.gravacoes = base, 0, 0
    def ler_todos(self): self.leituras += 1; return self.base.ler_todos()
    def gravar(self, dados): self.gravacoes += 1; return self.base.gravar(dados)


ALTS = ("a1", "b1", "c1", "d1", "e1")
q = Question("Cinco?", ALTS)
emb = Question("Cinco?", ("e1", "c1", "a1", "d1", "b1"))  # mesma questao, embaralhada

c1 = Conta(ArmazenamentoLocal(pasta, "PC1"))
m1 = Memoria(c1, "PC1", intervalo=10, relogio=relogio)
assert c1.leituras == 0  # criar a memoria nao toca o armazenamento
assert m1.registrar(q, 0, False) is True and m1.registrar(q, 0, False) is False  # sem repetir
assert m1.registrar(q, 3, False) is True
m2 = Memoria(ArmazenamentoLocal(pasta, "PC2"), "PC2", intervalo=10, relogio=relogio)
assert m2.erradas(q) == {"a1", "d1"}  # o PC2 enxerga o que o PC1 aprendeu
assert m2.erradas(emb) == {"a1", "d1"}  # mesmo embaralhada
assert m2.registrar(q, 1, False) is True  # PC2 erra mais uma
tempo[0] = 20  # passou o intervalo: o PC1 relê
assert m1.erradas(q) == {"a1", "d1", "b1"}
assert m1.registrar(q, 1, False) is False  # ja sabia (veio do PC2)
print("erradas entre PCs ok")

# o PC1 acerta: guarda a certa e APAGA as erradas dele
assert m1.registrar(q, 2, True) is True
dados_pc1 = json.loads((pasta / "memoria-PC1.json").read_text(encoding="utf-8"))
(entrada,) = dados_pc1.values()
assert entrada["certa"] == "c1" and entrada["erradas"] == [], entrada
assert m1.registrar(q, 2, True) is False  # repetido
assert m1.registrar(q, 4, False) is False  # certa ja conhecida: erro novo e ignorado
# o PC2 passa a saber a certa; as erradas dele somem do arquivo dele ao sincronizar
tempo[0] = 40
assert m2.certa(q) == "c1" and m2.erradas(q) == frozenset()
dados_pc2 = json.loads((pasta / "memoria-PC2.json").read_text(encoding="utf-8"))
assert dados_pc2 == {}, dados_pc2  # nada sobrou: certa e do PC1, erradas apagadas
print("certa apaga erradas ok")

# revisao em lote grava UMA vez
c3 = Conta(ArmazenamentoLocal(Path(tempfile.mkdtemp()), "PC3"))
m3 = Memoria(c3, "PC3", relogio=relogio)
lote = [Resultado(Question(f"Q{i}?", ("x", "y", "z")), i % 3, i not in (2, 7)) for i in range(10)]
assert m3.registrar_revisao(lote) == (2, 8)
assert c3.gravacoes == 1, c3.gravacoes
assert m3.registrar_revisao(lote) == (0, 0) and c3.gravacoes == 1  # nada novo: nao grava
print("lote ok")

# juntar_dados nunca perde nada
a = {"k": {"enunciado": "E", "erradas": ["x"]}}
b = {"k": {"enunciado": "E", "erradas": ["y", "x"]}, "z": {"enunciado": "Z", "erradas": ["w"]}}
assert juntar_dados(a, b) == {
    "k": {"enunciado": "E", "erradas": ["x", "y"]},
    "z": {"enunciado": "Z", "erradas": ["w"]},
}

# ============ nuvem que cai: o local segue, e a nuvem alcanca depois ============
class Remoto(Armazenamento):
    def __init__(self): self.docs, self.fora = {}, False
    def ler_todos(self):
        if self.fora: raise ConnectionError("sem internet")
        return json.loads(json.dumps(self.docs))
    def gravar(self, dados):
        if self.fora: raise ConnectionError("sem internet")
        self.docs["PCX"] = json.loads(json.dumps(dados))


remoto = Remoto()
esp = ArmazenamentoEspelhado(ArmazenamentoLocal(Path(tempfile.mkdtemp()), "PCX"), remoto)
mx = Memoria(esp, "PCX", relogio=relogio)
remoto.fora = True
assert mx.registrar(q, 0, False) is True  # sem internet: nao quebra, grava no local
assert esp.erro_nuvem and "PCX" not in remoto.docs
remoto.fora = False
assert mx.registrar(q, 1, False) is True  # voltou: a gravacao leva TUDO de uma vez
assert remoto.docs["PCX"] and len(next(iter(remoto.docs["PCX"].values()))["erradas"]) == 2
assert esp.erro_nuvem is None
# outro PC (sem arquivo local) le o que PCX subiu
my = Memoria(
    ArmazenamentoEspelhado(ArmazenamentoLocal(Path(tempfile.mkdtemp()), "PCY"), remoto),
    "PCY", relogio=relogio,
)
assert my.erradas(q) == {"a1", "b1"}
print("nuvem cai e volta ok")


# ============ solver com memoria ============
class Interno(Solver):
    def __init__(self, devolve): self.devolve, self.visto = devolve, None
    def solve(self, question):
        self.visto = question
        return Suggestion(indice=self.devolve, explicacao="ia", origem="x")


mem = Memoria(ArmazenamentoLocal(Path(tempfile.mkdtemp()), "S"), "S", relogio=relogio)
i = Interno(3); s = SolverComMemoria(i, mem).solve(q)
assert s.indice == 3 and i.visto is q  # nada conhecido: pergunta a questao inteira
mem.registrar(q, 0, False); mem.registrar(q, 3, False)
i = Interno(2); s = SolverComMemoria(i, mem).solve(q)
assert i.visto.alternativas == ("b1", "c1", "e1") and s.indice == 4  # IA nao ve as erradas
mem.registrar(q, 1, False); mem.registrar(q, 2, False)
i = Interno(0); s = SolverComMemoria(i, mem).solve(q)
assert s.indice == 4 and i.visto is None and s.origem == "memória"  # sobrou 1
mem2 = Memoria(ArmazenamentoLocal(Path(tempfile.mkdtemp()), "S2"), "S2", relogio=relogio)
mem2.registrar(q, 2, True)
i = Interno(0); s = SolverComMemoria(i, mem2).solve(emb)  # certa conhecida, questao embaralhada
assert emb.alternativas[s.indice] == "c1" and i.visto is None
print("solver ok")


# ============ laco: revisao guarda certas e erradas ============
class FReader:
    def __init__(self, rev): self.rev = list(rev)
    def ler_revisao(self): return self.rev.pop(0) if self.rev else []
    def ler_questao(self): return None


class Pres:
    def __init__(self): self.avisos = []
    def consultando(self): pass
    def mostrar(self, q, s): pass
    def avisar(self, m): self.avisos.append(m)


mem = Memoria(ArmazenamentoLocal(Path(tempfile.mkdtemp()), "L"), "L", relogio=relogio)
qa, qb = Question("Laco?", ("x", "y", "z")), Question("Outra?", ("p", "q"))
rev = [Resultado(qa, 1, False), Resultado(qb, 0, True)]
pres = Pres()
asst = AssistenteQuiz(FReader([rev, rev]), Interno(0), pres, memoria=mem)
asst._passo(); asst._passo()
assert mem.erradas(qa) == {"y"} and mem.certa(qb) == "p"
assert len(pres.avisos) == 1  # a 2a leitura da mesma revisao nao repete o aviso
print("laco ok")
print("TUDO OK")
