import sys

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from playwright.sync_api import sync_playwright

from quizbot.responder import Responder


def link(href):
    return (f'<a class="mod_quiz-next-nav btn btn-primary" href="{href}" '
            f'onclick="document.title+=\'x\'; return false">Terminar revisão</a>')


with sync_playwright() as p:
    nav = None
    for canal in ("chrome", "msedge"):
        try:
            nav = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception:
            pass
    ctx = nav.new_context()
    aba = ctx.new_page()
    r = Responder(ctx)

    # o caso real: um link no menu lateral escondido (0x0) e outro visivel no fim da pagina
    escondido = '<aside style="display:none">' + link("/a") + "</aside>"
    aba.set_content(escondido + "<p>meio</p>" + link("/a"))
    assert r.terminar_revisao() is True and aba.title() == "x", aba.title()  # clicou UMA vez, no visivel
    aba.set_content(escondido)  # so o escondido: nao clica
    assert r.terminar_revisao() is False and aba.title() == ""
    aba.set_content(link("/a") + link("/b"))  # dois visiveis: ambiguo, nao adivinha
    assert r.terminar_revisao() is False and aba.title() == ""
    aba.set_content(link("/a"))  # um so continua funcionando
    assert r.terminar_revisao() is True
    aba.set_content("<p>nada</p>")
    assert r.terminar_revisao() is False
    nav.close()
print("revisao dupla ok")
