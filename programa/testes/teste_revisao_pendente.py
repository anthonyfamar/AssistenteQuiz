# TESTE - ler a revisao das tentativas antigas ANTES de comecar outra tentativa.
#
# Moodle simulado (so no navegador, sem rede). Confere, na pagina inicial do quiz:
#   A) duas tentativas ja finalizadas que o programa nao leu: abre a revisao de cada uma (uma vez so),
#      guarda as certas e erradas, fecha a revisao e SO ENTAO comeca a nova tentativa;
#   B) quiz sem mais tentativas: le a revisao pendente antes de voltar ao curso;
#   C) revisao que o programa nao consegue ler: em vez de ficar parado, avisa, fecha a revisao e segue
#      para a nova tentativa; como nada foi guardado, na proxima execucao tenta de novo;
#   D) tentativa que o programa ja leu (mesmo attempt= do link) nao e aberta de novo;
#   E) link sem o attempt= no endereco: a tentativa e reconhecida pelo numero da linha e lida so uma vez;
#   F) revisao aberta pelo USUARIO: guarda na memoria e deixa a pagina aberta (nao clica em "Terminar");
#      se ele abrir uma que ja estava salva, o programa avisa que ja estava e NAO repete nada na memoria;
#   G) modo "so sugerir" (sem Responder): nao clica em nada;
#   H) a lista do que ja foi lido fica salva: ao abrir o programa de novo, nao reabre as revisoes lidas.
import contextlib
import io
import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

import quizbot.assistente as modulo
from quizbot.armazenamento import ArmazenamentoLocal
from quizbot.assistente import AssistenteQuiz
from quizbot.memoria import Memoria, RevisoesLidas
from quizbot.models import Question
from quizbot.page_reader import PageReader
from quizbot.presenter import Presenter
from quizbot.responder import Responder

modulo.PAUSA_APOS_CLICAR = 0.05
modulo.ESPERA_PELA_REVISAO = 1.0
modulo.ESPERA_PELA_REVISAO_ANTIGA = 1.0
VIEW = "http://quiz.test/mod/quiz/view.php?id=7"


class Tela(Presenter):
    def __init__(self):
        self.avisos = []

    def mostrar(self, question, suggestion):
        pass

    def avisar(self, mensagem):
        self.avisos.append(mensagem)


class Site:
    """Quiz com tentativas ja finalizadas. Cada tentativa: (numero, id no Moodle, nota, alternativa errada na Q1)."""

    def __init__(self, tentativas, esgotado=False, href_com_attempt=True, ilegivel=False):
        self.tentativas = tentativas
        self.esgotado = esgotado
        self.href_com_attempt = href_com_attempt
        self.ilegivel = ilegivel
        self.aberturas = []  # id de cada revisao aberta (cada ida a review.php)
        self.iniciou = []  # quantas aberturas ja tinham acontecido quando a nova tentativa comecou
        self.voltou = False
        self.terminou_revisao = 0

    def painel(self):
        linhas = ""
        for numero, id_moodle, nota, _ in self.tentativas:
            href = (f"/mod/quiz/review.php?attempt={id_moodle}&cmid=7" if self.href_com_attempt
                    else f"/mod/quiz/review.php?n={numero}&cmid=7")
            linhas += (f'<tr><td class="cell c0">{numero}</td>'
                       f'<td class="cell c1">Finalizada<span class="statedetails">Enviada(s) hoje</span></td>'
                       f'<td class="cell c2">{str(nota).replace(".", ",")}0</td>'
                       f'<td class="cell c3 lastcol"><a title="Analise as suas respostas a esta tentativa" href="{href}">Revisão</a></td></tr>')
        tabela = ('<table class="generaltable quizattemptsummary"><thead><tr><th>Tentativa</th><th>Estado</th>'
                  '<th>Nota / 10,00</th><th>Revisão</th></tr></thead><tbody>' + linhas + '</tbody></table>')
        if self.esgotado:
            fim = ('<div class="box quizattempt"><p>Não são permitidas outras tentativas</p><div class="continuebutton">'
                   '<button type="submit" onclick="location.href=\'/course/view.php?id=1\'; return false">Voltar ao curso</button></div></div>')
        else:
            fim = ('<div class="box quizattempt"><button type="submit" '
                   'onclick="location.href=\'/mod/quiz/attempt.php?attempt=999\'; return false">Fazer uma outra tentativa</button></div>')
        return f'<html><body><div role="main">{tabela}{fim}</div></body></html>'

    def revisao(self, id_moodle):
        errada_na_q1 = next((e for _, i, _, e in self.tentativas if str(i) == str(id_moodle)), 0)
        blocos = ""
        for n in (1, 2):
            marcada = errada_na_q1 if n == 1 else 1  # Q1 errada (muda por tentativa); Q2 certa (alternativa B)
            alts = ""
            for i in range(4):
                marca = "" if self.ilegivel or i != marcada else ("incorrect" if n == 1 else "correct")
                alts += (f'<div class="r{i} {marca}"><input type="radio" disabled {"checked" if i == marcada else ""}>'
                         f'<label>{"abcd"[i]}. Alternativa {i} da questao {n}</label></div>')
            blocos += (f'<div class="que multichoice"><div class="info"><h3 class="no">Questão <span class="qno">{n}</span></h3></div>'
                       f'<div class="content"><div class="formulation"><div class="qtext"><p>Enunciado numero {n}</p></div>'
                       f'<div class="ablock"><div class="answer">{alts}</div></div></div></div></div>')
        return (f'<html><body><div role="main">{blocos}<a class="mod_quiz-next-nav btn btn-primary" '
                f'href="/mod/quiz/view.php?id=7&fim=1">Terminar revisão</a></div></body></html>')

    def atender(self, rota):
        url = urlparse(rota.request.url)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/mod/quiz/view.php":
            if "fim" in q:
                self.terminou_revisao += 1
            corpo = self.painel()
        elif url.path == "/mod/quiz/review.php":
            id_moodle = q.get("attempt") or next((str(i) for n, i, _, _ in self.tentativas if str(n) == q.get("n")), "?")
            self.aberturas.append(id_moodle)
            corpo = self.revisao(id_moodle)
        elif url.path == "/mod/quiz/attempt.php":
            self.iniciou.append(len(self.aberturas))
            corpo = "<html><body>tentativa nova</body></html>"
        elif url.path == "/course/view.php":
            self.voltou = True
            corpo = "<html><body>curso</body></html>"
        else:
            corpo = "<html><body>?</body></html>"
        rota.fulfill(status=200, content_type="text/html; charset=utf-8", body=corpo)


def uma_memoria(pasta=None):
    pasta = pasta or Path(tempfile.mkdtemp())
    return Memoria(ArmazenamentoLocal(pasta, "teste"), "teste")


def cenario(nav, site, com_responder=True, inicio=VIEW, pasta=None):
    # "pasta" reaproveitada = o mesmo PC abrindo o programa de novo (mesma memoria e mesma lista de lidas)
    ctx = nav.new_context()
    ctx.route(re.compile(r"http://quiz\.test/.*"), site.atender)
    pagina = ctx.new_page()
    pagina.goto(inicio)
    pasta = pasta or Path(tempfile.mkdtemp())
    memoria = uma_memoria(pasta)
    tela = Tela()
    assistente = AssistenteQuiz(
        PageReader(ctx), None, tela, intervalo=0.05, parar=threading.Event(),
        responder=Responder(ctx) if com_responder else None, finalizar=True, tentativas=True,
        memoria=memoria, pausa_voltar=0.3, revisoes_lidas=RevisoesLidas(pasta / "revisoes-lidas.json"),
    )
    assistente.pasta = pasta
    return ctx, pagina, assistente, memoria, tela


def rodar(assistente, ate, limite=25.0):
    saida = io.StringIO()
    fim = time.monotonic() + limite
    with contextlib.redirect_stdout(saida):
        while time.monotonic() < fim and not ate():
            assistente._passo()
            time.sleep(0.05)
    return saida.getvalue()


def Q(n):
    return Question(f"Enunciado numero {n}", tuple(f"Alternativa {i} da questao {n}" for i in range(4)))


with sync_playwright() as p:
    nav = None
    for canal in ("chrome", "msedge"):
        try:
            nav = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception:
            pass
    assert nav, "nenhum navegador"

    # ---------- A) duas tentativas antigas, depois a nova ----------
    site = Site([(1, 101, 5.0, 0), (2, 102, 6.0, 2)])
    ctx, pag, ass, mem, tela = cenario(nav, site)
    registro = rodar(ass, lambda: site.iniciou)
    assert site.aberturas == ["101", "102"], site.aberturas  # cada revisao aberta UMA vez, em ordem
    assert site.iniciou == [2], site.iniciou  # a nova tentativa so comecou DEPOIS das duas revisoes
    assert site.terminou_revisao == 2, site.terminou_revisao  # o programa fechou as que ele abriu
    assert mem.erradas(Q(1)) == {"Alternativa 0 da questao 1", "Alternativa 2 da questao 1"}, mem.erradas(Q(1))
    assert mem.certa(Q(2)) == "Alternativa 1 da questao 2", mem.certa(Q(2))
    assert "[revisao] tentativa 1 ainda nao lida" in registro and "[revisao] tentativa 2 ainda nao lida" in registro
    # A janela guarda cada aviso por 5 s e os seguintes esperam na fila: para 2 tentativas (varias
    # etapas cada) ela ficaria muito atrasada. Tem que chegar UMA mensagem fixa para o processo todo.
    assert tela.avisos == ["Conferindo as revisões das tentativas anteriores…"], tela.avisos
    assert "tentativa 1 ainda nao lida" in registro and "tentativa 2 ainda nao lida" in registro  # o detalhe fica no log
    for entrada in mem._proprios.values():  # a memoria nunca repete uma alternativa errada
        assert len(entrada["erradas"]) == len(set(entrada["erradas"])), entrada
    print("A) leu a revisao das 2 tentativas antigas (guardou erradas e certas), fechou e so entao comecou a nova ok")
    ctx.close()

    # ---------- H) abrir o programa de novo: as revisoes ja lidas nao sao reabertas ----------
    site2 = Site([(1, 101, 5.0, 0), (2, 102, 6.0, 2)])
    ctx, pag, ass2, mem2, tela2 = cenario(nav, site2, pasta=ass.pasta)
    rodar(ass2, lambda: site2.iniciou)
    assert site2.aberturas == [] and site2.iniciou == [0], (site2.aberturas, site2.iniciou)  # foi direto
    print("H) programa aberto de novo: nao reabriu as revisoes ja lidas, foi direto para a nova tentativa ok")
    ctx.close()

    # ---------- B) sem mais tentativas: le a pendente antes de voltar ao curso ----------
    site = Site([(1, 101, 5.0, 0)], esgotado=True)
    ctx, pag, ass, mem, tela = cenario(nav, site)
    rodar(ass, lambda: site.voltou)
    assert site.voltou and site.aberturas == ["101"], (site.voltou, site.aberturas)
    assert mem.erradas(Q(1)) == {"Alternativa 0 da questao 1"}
    print("B) quiz esgotado: leu a revisao pendente e so depois voltou ao curso ok")
    ctx.close()

    # ---------- C) revisao ilegivel: avisa, fecha e segue sozinho (sem ficar parado) ----------
    site = Site([(1, 101, 5.0, 0)], ilegivel=True)
    ctx, pag, ass, mem, tela = cenario(nav, site)
    rodar(ass, lambda: site.iniciou, limite=15)
    assert site.iniciou == [1], site.iniciou  # seguiu para a nova tentativa sozinho
    assert site.terminou_revisao == 1, site.terminou_revisao  # fechou a revisao que ele mesmo abriu
    assert sum("Não consegui ler a revisão" in a for a in tela.avisos) == 1, tela.avisos
    assert site.aberturas == ["101"], site.aberturas  # nao insistiu nessa tentativa
    # nada foi guardado, entao NAO conta como lida: na proxima vez que o programa abrir, tenta de novo
    site3 = Site([(1, 101, 5.0, 0)])
    ctx3, pag3, ass3, mem3, tela3 = cenario(nav, site3, pasta=ass.pasta)
    rodar(ass3, lambda: site3.iniciou)
    assert site3.aberturas == ["101"] and mem3.erradas(Q(1)) == {"Alternativa 0 da questao 1"}, site3.aberturas
    print("C) revisao ilegivel: avisou, fechou e seguiu sozinho; na proxima execucao tentou de novo e leu ok")
    ctx3.close()
    ctx.close()

    # ---------- D) a tentativa 101 o programa ja leu: so abre a 102 ----------
    site = Site([(1, 101, 5.0, 0), (2, 102, 6.0, 2)])
    ctx, pag, ass, mem, tela = cenario(nav, site)
    ass._revisoes_lidas.add("101")
    rodar(ass, lambda: site.iniciou)
    assert site.aberturas == ["102"], site.aberturas
    print("D) tentativa ja lida (mesmo attempt=) nao e aberta de novo ok")
    ctx.close()

    # ---------- E) link sem attempt= no endereco: reconhece pelo numero da linha ----------
    site = Site([(1, 101, 5.0, 0)], href_com_attempt=False)
    ctx, pag, ass, mem, tela = cenario(nav, site)
    rodar(ass, lambda: site.iniciou)
    assert site.aberturas == ["101"] and site.iniciou == [1], (site.aberturas, site.iniciou)
    print("E) link sem attempt=: lida uma vez so, pelo numero da linha ok")
    ctx.close()

    # ---------- F) revisao aberta pelo USUARIO: guarda e deixa aberta ----------
    site = Site([(1, 101, 5.0, 0)])
    ctx, pag, ass, mem, tela = cenario(nav, site, inicio="http://quiz.test/mod/quiz/review.php?attempt=101&cmid=7")
    registro = rodar(ass, lambda: False, limite=1.5)
    assert mem.erradas(Q(1)) == {"Alternativa 0 da questao 1"} and mem.certa(Q(2)), "nao guardou"
    assert site.terminou_revisao == 0 and not any("Revisão terminada" in a for a in tela.avisos), tela.avisos
    assert "revisao aberta pelo usuario" in registro, registro
    assert any("guardei" in a for a in tela.avisos), tela.avisos
    print("F) revisao aberta pelo usuario: guardou na memoria e deixou a pagina aberta ok")
    ctx.close()
    # o usuario abre a MESMA revisao de novo (outra execucao): confere e diz que ja estava salva, sem repetir
    site_f2 = Site([(1, 101, 5.0, 0)])
    ctx, pag, ass_f2, mem_f2, tela_f2 = cenario(nav, site_f2, pasta=ass.pasta,
                                                inicio="http://quiz.test/mod/quiz/review.php?attempt=101&cmid=7")
    rodar(ass_f2, lambda: False, limite=1.5)
    assert any("já estava salvo" in a for a in tela_f2.avisos), tela_f2.avisos
    assert not any("guardei" in a for a in tela_f2.avisos) and site_f2.terminou_revisao == 0
    for entrada in mem_f2._proprios.values():
        assert len(entrada["erradas"]) == len(set(entrada["erradas"])), entrada
    print("F2) revisao ja salva aberta de novo: conferiu, avisou que ja estava e nao repetiu nada ok")
    ctx.close()

    # ---------- G) so sugerir (sem Responder): nao clica em nada ----------
    site = Site([(1, 101, 5.0, 0)])
    ctx, pag, ass, mem, tela = cenario(nav, site, com_responder=False)
    rodar(ass, lambda: False, limite=1.0)
    assert site.aberturas == [] and not site.iniciou, (site.aberturas, site.iniciou)
    print("G) modo so sugerir: nao clicou em nada ok")
    ctx.close()
    nav.close()

# a lista de lidas: arquivo estragado ou ausente nao derruba nada (comeca vazia); gravacao e inteira
arquivo = Path(tempfile.mkdtemp()) / "pasta nova" / "revisoes-lidas.json"
assert "1" not in RevisoesLidas(arquivo)  # sem arquivo
lista = RevisoesLidas(arquivo)
lista.add("55")
assert "55" in RevisoesLidas(arquivo) and not list(arquivo.parent.glob("*.tmp"))  # criou a pasta, sem sobra
arquivo.write_text("{ isto nao e json", encoding="utf-8")
assert "55" not in RevisoesLidas(arquivo)  # estragado: comeca vazio, sem erro
print("lista de lidas: ausente, estragada e gravacao inteira ok")
print("TUDO OK")
