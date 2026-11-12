import sys
import threading

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from playwright.sync_api import sync_playwright

from quizbot.assistente import AssistenteQuiz
from quizbot.models import PainelQuiz, Situacao, Tentativa
from quizbot.page_reader import PageReader
from quizbot.responder import Responder

CLIQUE = "onclick=\"document.title += '[' + this.textContent.trim() + ']'; return false\""

COMECAR = f"""<div class="box quizattempt p-y-1"><div class="singlebutton quizstartbuttondiv">
<form method="post"><input type="hidden" name="cmid" value="5961521">
<button type="submit" class="btn btn-secondary" id="single_button6af0da271e5d28" title="" {CLIQUE}>Tentar responder o questionário agora</button>
</form></div></div>"""

TABELA_1 = """<table class="generaltable quizattemptsummary" tabindex="0"><thead><tr>
<th class="header c0" style="text-align:center;" scope="col">Tentativa</th>
<th class="header c1" style="text-align:left;" scope="col">Estado</th>
<th class="header c2" style="text-align:center;" scope="col">Nota / 10,00</th>
<th class="header c3 lastcol" style="text-align:center;" scope="col">Revisão</th></tr></thead>
<tbody><tr class="lastrow"><td class="cell c0" style="text-align:center;">1</td>
<td class="cell c1" style="text-align:left;">Finalizada<span class="statedetails">Enviada(s) domingo, 18 out 2026, 18:40</span></td>
<td class="cell c2" style="text-align:center;">{n1}</td></tr></tbody></table>"""

OUTRA = f"""<button type="submit" class="btn btn-secondary" id="single_button6af0d8bd4b6f08" title="" {CLIQUE}>Fazer uma outra tentativa</button>"""

TABELA_2 = """<table class="generaltable quizattemptsummary" tabindex="0"><thead><tr>
<th class="header c0" style="text-align:center;" scope="col">Tentativa</th>
<th class="header c1" style="text-align:left;" scope="col">Estado</th>
<th class="header c2" style="text-align:center;" scope="col">Nota / 10,00</th>
<th class="header c3 lastcol" style="text-align:center;" scope="col">Revisão</th></tr></thead>
<tbody><tr class="bestrow"><td class="cell c0" style="text-align:center;">1</td>
<td class="cell c1" style="text-align:left;">Finalizada<span class="statedetails">Enviada(s) sexta, 25 set 2026, 23:54</span></td>
<td class="cell c2" style="text-align:center;">{n1}</td></tr>
<tr class="lastrow"><td class="cell c0" style="text-align:center;">2</td>
<td class="cell c1" style="text-align:left;">Finalizada<span class="statedetails">Enviada(s) sábado, 7 nov 2026, 19:29</span></td>
<td class="cell c2" style="text-align:center;">{n2}</td></tr></tbody></table>"""

ESGOTADO = f"""<div class="box quizattempt p-y-1"><p tabindex="0" title="Não são permitidas outras tentativas" style="display: block;">Não são permitidas outras tentativas</p>
<div class="continuebutton"><form method="get"><input type="hidden" name="id" value="11424">
<button type="submit" class="btn btn-secondary" id="single_button6af0dcb11d7838" title="" {CLIQUE}>Voltar ao curso</button>
</form></div></div>"""

CONTINUAR = f"""<button type="submit" class="btn btn-secondary" id="single_button6af1037a7e7eb8" title="" {CLIQUE}>Continuar a última tentativa</button>"""


def pagina(*partes, n1="9,00", n2="8,00"):
    return "".join(p.replace("{n1}", n1).replace("{n2}", n2) for p in partes)


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
    leitor, resp = PageReader(contexto), Responder(contexto)

    # --- LEITURA (so olha) ---
    aba.set_content("<p>login</p>")
    assert leitor.ler_painel() is None

    aba.set_content(pagina(COMECAR))
    assert leitor.ler_painel() == PainelQuiz(Situacao.SEM_TENTATIVA)

    aba.set_content(pagina(TABELA_1, OUTRA, n1="9,00"))
    pn = leitor.ler_painel()
    assert pn.situacao is Situacao.PODE_REFAZER and pn.nota_maxima == 10.0, pn
    assert pn.tentativas == (Tentativa(1, "Finalizada", 9.0),), pn
    assert not pn.tudo_certo and pn.ultima.nota == 9.0

    aba.set_content(pagina(TABELA_1, OUTRA, n1="10,00"))
    assert leitor.ler_painel().tudo_certo

    aba.set_content(pagina(TABELA_2, ESGOTADO, n1="9,00", n2="8,00"))
    pn = leitor.ler_painel()
    assert pn.situacao is Situacao.ESGOTADO and len(pn.tentativas) == 2
    assert pn.ultima.nota == 8.0 and pn.melhor.nota == 9.0 and pn.melhor.numero == 1
    resumo = pn.resumo_das_notas()
    assert "8,00" in resumo and "9,00" in resumo and "tentativa 1" in resumo and "maior nota" in resumo, resumo

    aba.set_content(pagina(TABELA_2, ESGOTADO, n1="8,00", n2="9,00"))
    assert leitor.ler_painel().resumo_das_notas() == "Nota final: 9,00 de 10,00."

    aba.set_content(pagina(TABELA_1, CONTINUAR, n1="Não avaliada"))
    pn = leitor.ler_painel()
    assert pn.situacao is Situacao.EM_ANDAMENTO and pn.ultima is None
    print("leitura do painel ok")

    # --- CLIQUES (cada texto, so o botao certo) ---
    aba.set_content(pagina(COMECAR)); assert resp.iniciar_tentativa(); assert aba.title() == "[Tentar responder o questionário agora]"
    aba.set_content(pagina(TABELA_1, OUTRA)); assert resp.iniciar_tentativa(); assert aba.title() == "[Fazer uma outra tentativa]"
    aba.set_content(pagina(CONTINUAR)); assert resp.iniciar_tentativa(); assert aba.title() == "[Continuar a última tentativa]"
    aba.set_content(pagina(ESGOTADO)); assert not resp.iniciar_tentativa() and aba.title() == ""
    assert resp.voltar_ao_curso() and aba.title() == "[Voltar ao curso]"
    aba.set_content("<p>nada</p>"); assert not resp.iniciar_tentativa() and not resp.voltar_ao_curso()
    print("cliques ok")

    # --- FLUXO COMPLETO no Chrome: o assistente decide e clica ---
    class Pres:
        def __init__(self): self.msgs = []
        def avisar(self, m): self.msgs.append(m)
        def oferecer_tentar_de_novo(self, m, tentar): self.msgs.append(m)
        def consultando(self): pass
        def mostrar(self, *a): pass

    def rodar(html, ticks=3, **kw):
        aba.set_content(html)
        pres = Pres()
        a = AssistenteQuiz(leitor, None, pres, responder=resp, tentativas=kw.pop("tentativas", True),
                           pausa_voltar=kw.pop("pausa", 2.0), parar=threading.Event(), **kw)
        for _ in range(ticks):
            a._passo()
        return aba.title(), pres.msgs

    t, m = rodar(pagina(COMECAR))
    assert t == "[Tentar responder o questionário agora]", t  # clicou UMA vez so
    t, m = rodar(pagina(CONTINUAR))
    assert t == "[Continuar a última tentativa]", t
    t, m = rodar(pagina(TABELA_1, OUTRA, n1="9,00"))
    assert t == "[Fazer uma outra tentativa]", t
    t, m = rodar(pagina(TABELA_1, OUTRA, n1="10,00"), pausa=1.0)
    # nota maxima: mostra a nota, espera e tenta voltar; aqui (sem historico) nao consegue e avisa
    assert t == "" and any("Acertou tudo" in x and "Voltando ao curso em 1 s" in x for x in m), (t, m)
    assert any("Não consegui voltar ao curso" in x for x in m), m
    t, m = rodar(pagina(TABELA_1, OUTRA, n1="Não avaliada"))
    assert t == "" and any("Não consegui ler a nota" in x for x in m) and len(m) == 1, (t, m)
    t, m = rodar(pagina(COMECAR), tentativas=False)
    assert t == "", t  # desligado pelo .bat: nao clica
    print("fluxo (comecar/continuar/outra/parar) ok")

    # esgotado: mostra a nota, espera e clica em Voltar ao curso (2 s no teste em vez de 20)
    import time
    ini = time.monotonic()
    t, m = rodar(pagina(TABELA_2, ESGOTADO, n1="9,00", n2="8,00"), ticks=1, pausa=2.0)
    dur = time.monotonic() - ini
    assert t == "[Voltar ao curso]" and 1.9 <= dur < 6, (t, dur)
    assert "Fica a maior nota: 9,00" in m[0] and "Voltando ao curso em 2 s" in m[0], m
    # o clique so acontece uma vez mesmo com varios ticks seguidos
    aba.set_content(pagina(TABELA_2, ESGOTADO))
    pres = Pres()
    a = AssistenteQuiz(leitor, None, pres, responder=resp, tentativas=True, pausa_voltar=1.0, parar=threading.Event())
    a._passo(); titulo = aba.title(); a._passo(); a._passo()
    assert titulo == "[Voltar ao curso]" and aba.title() == titulo
    # se a pagina mudar durante a espera, cancela e NAO clica
    aba.set_content(pagina(TABELA_2, ESGOTADO))
    class LeitorMuda(PageReader):
        n = 0
        def ler_painel(self):
            LeitorMuda.n += 1
            return super().ler_painel() if LeitorMuda.n == 1 else None
    b = AssistenteQuiz(LeitorMuda(contexto), None, Pres(), responder=resp, tentativas=True, pausa_voltar=3.0, parar=threading.Event())
    b._passo()
    assert aba.title() == "", aba.title()
    # pedido de parar durante a espera: sai na hora, sem clicar
    aba.set_content(pagina(TABELA_2, ESGOTADO))
    ev = threading.Event(); ev.set()
    c = AssistenteQuiz(leitor, None, Pres(), responder=resp, tentativas=True, pausa_voltar=5.0, parar=ev)
    ini = time.monotonic(); c._passo()
    assert aba.title() == "" and time.monotonic() - ini < 1
    print("esgotado (nota, espera, voltar, cancelar) ok")
    navegador.close()

# sem Responder (modo so-sugestao) nunca age
from quizbot.assistente import AssistenteQuiz as A
print("TUDO OK")
