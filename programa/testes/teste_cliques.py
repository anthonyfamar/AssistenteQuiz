import io
import sys
import time
from contextlib import redirect_stdout

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from quizbot.responder import Responder, _clicar, _marcar


def pagina(corpo):
    return f"<html><head><title>t</title></head><body>{corpo}</body></html>"


# --- 1) site LENTO: o clique deu certo, entao devolve True (antes dava False depois de 2 s) ---
def lento(rota):
    time.sleep(3.5)
    rota.fulfill(status=200, content_type="text/html", body=pagina("<p>chegou</p>"))


MENU = ('<ul class="timeline"><li><div class="timeline-status"><i></i></div>'
        '<div class="timeline-item"><a href="/lento">Unidade de Ensino 1</a></div></li></ul>')

with sync_playwright() as p:
    nav = None
    for canal in ("chrome", "msedge"):
        try:
            nav = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception:
            pass
    ctx = nav.new_context()
    ctx.route("http://site.test/inicio", lambda r: r.fulfill(status=200, content_type="text/html", body=pagina(MENU)))
    ctx.route("http://site.test/lento", lento)
    pag = ctx.new_page()
    pag.goto("http://site.test/inicio")
    t = time.monotonic()
    assert Responder(ctx).abrir_unidade("Unidade de Ensino 1") is True
    assert time.monotonic() - t < 1.5, time.monotonic() - t
    pag.wait_for_url("**/lento", timeout=10000)
    pag.wait_for_load_state()
    assert "chegou" in pag.content()
    nav.close()
print("site lento: o clique devolve True na hora e a pagina chega depois ok")


# --- 2) pagina oculta (janela minimizada): o clique normal esgota o tempo -> clica pelo DOM ---
class Falso:
    def __init__(self, oculta, click_falha=True):
        self.oculta, self.click_falha, self.chamadas = oculta, click_falha, []

    def click(self, **kw):
        self.chamadas.append(("click", kw))
        if self.click_falha:
            raise PlaywrightTimeoutError("Timeout 2000ms exceeded.\nwaiting for element to be stable")

    def check(self, **kw):
        self.chamadas.append(("check", kw))
        raise PlaywrightTimeoutError("Timeout 2000ms exceeded.")

    def evaluate(self, js, **kw):
        if "visibilityState" in js:
            return self.oculta
        self.chamadas.append(("dom", js))


import quizbot.responder as R

R.CLIQUE_PELO_DOM = False  # estes testes sao do caminho antigo, o do clique de mouse
f = Falso(oculta=True)
saida = io.StringIO()
with redirect_stdout(saida):
    _clicar(f)
    _marcar(f)
assert f.chamadas[0][0] == "click" and f.chamadas[0][1] == {"timeout": 2000, "no_wait_after": True}, f.chamadas
assert [c for c in f.chamadas if c[0] == "dom"] == [("dom", "el => el.click()")] * 2, f.chamadas
assert "pagina oculta" in saida.getvalue()

# pagina VISIVEL: nada de clicar pelo DOM (o erro aparece e vai para o registro)
f = Falso(oculta=False)
saida = io.StringIO()
with redirect_stdout(saida):
    for chamar in (_clicar, _marcar):
        try:
            chamar(f)
            raise AssertionError("devia dar erro")
        except PlaywrightTimeoutError:
            pass
assert not [c for c in f.chamadas if c[0] == "dom"], f.chamadas
assert saida.getvalue().count("[clique]") == 2, saida.getvalue()

# clique que funciona de primeira: nao mexe em mais nada
f = Falso(oculta=True, click_falha=False)
_clicar(f)
assert [c[0] for c in f.chamadas] == ["click"]
print("pagina oculta: clica pelo DOM; pagina visivel: erro registrado, sem atalho ok")
R.CLIQUE_PELO_DOM = True  # o padrao

# --- 3) PADRAO: clique DENTRO da pagina. Nao depende do mouse (que e o que falha com a janela minimizada) ---
from playwright.sync_api import Error as PlaywrightError

PAGINA = """<html><head><title></title></head><body>
<div class="que"><div class="answer">
  <div><input type="radio" name="q" id="a0" value="0"><label for="a0">a</label></div>
  <div><input type="radio" name="q" id="a1" value="1" style="pointer-events:none"><label for="a1">b</label></div>
</div></div>
<input type="submit" class="mod_quiz-next-nav" value="Proxima" onclick="document.title+='[proxima]'; return false">
<button id="coberto" onclick="document.title+='[coberto]'">Coberto</button>
<div style="position:fixed;left:0;top:0;width:100vw;height:100vh;background:rgba(0,0,0,0.01)"></div>
<button id="desab" disabled onclick="document.title+='[desab]'">Desabilitado</button>
</body></html>"""

with sync_playwright() as p:
    nav = None
    for canal in ("chrome", "msedge"):
        try:
            nav = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception:
            pass
    ctx = nav.new_context()
    pag = ctx.new_page()
    pag.set_content(PAGINA)
    radio_sem_mouse = pag.locator("#a1")  # pointer-events:none: um clique de MOUSE nao o alcanca
    botao_coberto = pag.locator("#coberto")  # tem uma camada por cima: o mouse clicaria na camada

    # prova de que o mouse nao funciona nesses casos (e por isso o DOM e mais seguro)
    try:
        radio_sem_mouse.check(timeout=800)
        mouse_funcionou = True
    except PlaywrightError:
        mouse_funcionou = False
    assert not mouse_funcionou, "o teste precisa de um elemento que o mouse nao alcanca"

    # pelo DOM: marca e clica do mesmo jeito
    _marcar(radio_sem_mouse)
    assert radio_sem_mouse.is_checked()
    _marcar(radio_sem_mouse)  # ja marcada: nao desmarca nem quebra
    assert radio_sem_mouse.is_checked()
    _clicar(botao_coberto)
    _clicar(pag.locator("input.mod_quiz-next-nav"))
    assert pag.title() == "[coberto][proxima]", pag.title()

    # desabilitado: NAO finge que clicou (devolve erro, e o programa trata como falha)
    saida = io.StringIO()
    with redirect_stdout(saida):
        try:
            _clicar(pag.locator("#desab"))
            raise AssertionError("devia falhar")
        except PlaywrightError:
            pass
    assert "[desab]" not in pag.title() and "[clique]" in saida.getvalue()

    # pelo Responder: a questao e marcada e confere
    pag.set_content(PAGINA.replace('style="pointer-events:none"', ""))
    r = Responder(ctx)
    assert r.clicar(1) is True and pag.locator("#a1").is_checked()
    assert r.clicar(9) is False  # indice que nao existe
    nav.close()
print("clique pelo DOM: funciona onde o mouse nao alcanca, confere a marca e recusa botao desabilitado ok")
print("TUDO OK")
