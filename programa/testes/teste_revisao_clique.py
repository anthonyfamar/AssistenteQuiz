import sys
import threading

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from playwright.sync_api import sync_playwright

from quizbot.assistente import AssistenteQuiz
from quizbot.models import Question, Resultado
from quizbot.responder import Responder

PAGINA = """
<input type="submit" name="next" value="Próxima página" class="mod_quiz-next-nav btn btn-primary">
<a class="mod_quiz-next-nav btn btn-primary" onclick="document.title='clicou'">Terminar revisão</a>
"""
OUTRA = '<a class="mod_quiz-next-nav btn btn-primary">Outro link</a><input class="mod_quiz-next-nav" value="x">'

with sync_playwright() as p:
    navegador = None
    for canal in ("chrome", "msedge"):
        try:
            navegador = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception as erro:
            print("sem", canal, type(erro).__name__)
    assert navegador, "nenhum navegador"
    contexto = navegador.new_context()
    aba = contexto.new_page()
    r = Responder(contexto)

    aba.set_content(PAGINA)
    assert r.terminar_revisao() is True
    assert aba.title() == "clicou"
    aba.set_content(OUTRA)
    assert r.terminar_revisao() is False  # nao clica em outro link nem no <input>
    aba.set_content("<p>nada</p>")
    assert r.terminar_revisao() is False
    print("responder.terminar_revisao ok (a sem href)")

    # laco: so clica depois de guardar; clica uma vez; destrava quando sai da revisao
    class Leitor:
        def __init__(self):
            self.revisao = True
        def ler_revisao(self):
            return [Resultado(Question("Q?", ("a", "b")), 0, True)] if self.revisao else []
        def ler_questao(self):
            return None
        def ler_resumo(self):
            return None
        def questao_ja_respondida(self):
            return False
        def numero_da_questao(self):
            return None

    class Mem:
        def __init__(self):
            self.chamadas = 0
        def garantir_guardado(self):
            return True
        def registrar_revisao(self, rs):
            self.chamadas += 1
            return (0, 1) if self.chamadas == 1 else (0, 0)

    class Pres:
        def __init__(self):
            self.msgs = []
        def avisar(self, m):
            self.msgs.append(m)
        def consultando(self): pass
        def mostrar(self, *a): pass

    cliques = []
    class Resp:
        def terminar_revisao(self):
            cliques.append(1); return True
        def terminar(self): return False

    leitor, pres = Leitor(), Pres()
    a = AssistenteQuiz(leitor, None, pres, responder=Resp(), finalizar=True, memoria=Mem())
    a._passo(); a._passo(); a._passo()
    assert len(cliques) == 1, cliques  # nao clica repetido
    leitor.revisao = False
    a._passo()
    leitor.revisao = True  # outra revisao (2a tentativa)
    a._passo()
    assert len(cliques) == 2, cliques
    print("laco ok:", pres.msgs)
    navegador.close()
print("TUDO OK")
