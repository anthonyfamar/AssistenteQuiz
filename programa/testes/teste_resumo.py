import sys
import threading
import time
from urllib.parse import parse_qs, urlparse

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

import quizbot.assistente as modulo
from quizbot.assistente import AssistenteQuiz
from quizbot.models import Suggestion
from quizbot.page_reader import PageReader
from quizbot.presenter import Presenter
from quizbot.responder import Responder
from quizbot.solvers.base import Solver, SolverError

modulo.PAUSA_APOS_CLICAR = 0.05
modulo.PAUSA_APOS_ABRIR_QUESTAO = 0.3

# ---- o HTML real que o Anthony colou (resumo com as 10 "Ainda nao respondida") ----
LINHAS = "".join(
    f'<tr class="quizsummary{n} notyetanswered{" lastrow" if n == 10 else ""}">'
    f'<td class="cell c0" style="text-align: center"><a href="">{n}</a></td>'
    f'<td class="cell c1 lastcol" style="text-align: center">Ainda não respondida</td></tr>'
    for n in range(1, 11)
)
RESUMO_REAL = f"""<div role="main"><span id="maincontent"></span><h3 tabindex="0">Resumo de tentativas</h3>
<table class="generaltable quizsummaryofattempt boxaligncenter" tabindex="0"><thead><tr>
<th class="header c0" style="text-align: center" scope="col">Pergunta</th>
<th class="header c1 lastcol" style="text-align: center" scope="col">Status</th></tr></thead>
<tbody>{LINHAS}</tbody></table></div>"""

# ---- o bloco "info" real de uma questao ----
INFO_REAL = ('<div class="info"><h3 class="no" tabindex="0" title="Questão 8">Questão <span class="qno">8</span></h3>'
             '<div class="state botoes" tabindex="0" title="Ainda não respondida">Ainda não respondida</div></div>')


class Falso(Solver):
    def __init__(self):
        self.chamadas = []
        self.nao_responde = set()

    def solve(self, question):
        n = int(question.enunciado.split()[-1])
        self.chamadas.append(n)
        if n in self.nao_responde:
            raise SolverError("IA fora do ar")
        return Suggestion(indice=1, explicacao="x", origem="falso")


class Tela(Presenter):
    def __init__(self):
        self.avisos = []

    def mostrar(self, question, suggestion):
        pass

    def avisar(self, mensagem):
        self.avisos.append(mensagem)


class Site:
    """Um quiz de 'total' questoes, uma por pagina, como o Moodle."""

    def __init__(self, total=10, respondidas=None, links_quebrados=()):
        self.total = total
        self.respondidas = dict(respondidas or {})  # numero -> indice marcado
        self.enviado = False
        self.links_quebrados = set(links_quebrados)

    def questao(self, n):
        marcada = self.respondidas.get(n)
        estado = "Resposta salva" if marcada is not None else "Ainda não respondida"
        classe = "answersaved" if marcada is not None else "notyetanswered"
        radios = "".join(
            f'<div class="r{i}"><input type="radio" name="q" id="a{i}" value="{i}"{" checked" if marcada == i else ""}>'
            f'<label for="a{i}">{"abcde"[i]}. Alternativa {i}</label></div>'
            for i in range(5)
        )
        ultimo = n == self.total
        destino = "/summary" if ultimo else f"/attempt?page={n + 1}"
        rotulo = "Terminar tentativa ..." if ultimo else "Próxima página"
        return f"""<html><body><div role="main"><form>
<div class="que multichoice deferredfeedback {classe}"><div class="info"><h3 class="no">Questão <span class="qno">{n}</span></h3>
<div class="state">{estado}</div></div>
<div class="content"><div class="formulation"><div class="qtext"><p>Enunciado numero {n}</p></div>
<div class="ablock"><div class="answer">{radios}</div></div></div></div></div>
<input type="submit" name="next" value="{rotulo}" class="mod_quiz-next-nav btn btn-primary"
 onclick="var c=document.querySelector('input[type=radio]:checked'); location.href='/go?q={n}&a='+(c?c.value:'')+'&to={destino}'; return false">
</form></div></body></html>"""

    def resumo(self):
        linhas = []
        for n in range(1, self.total + 1):
            ok = n in self.respondidas
            href = "#" if n in self.links_quebrados else f"/attempt?page={n}"
            linhas.append(
                f'<tr class="quizsummary{n} {"answersaved" if ok else "notyetanswered"}{" lastrow" if n == self.total else ""}">'
                f'<td class="cell c0" style="text-align: center"><a href="{href}">{n}</a></td>'
                f'<td class="cell c1 lastcol">{"Resposta salva" if ok else "Ainda não respondida"}</td></tr>'
            )
        return f"""<html><body><div role="main"><h3>Resumo de tentativas</h3>
<table class="generaltable quizsummaryofattempt boxaligncenter"><thead><tr><th>Pergunta</th><th>Status</th></tr></thead>
<tbody>{"".join(linhas)}</tbody></table>
<button type="button" class="btn btn-primary" onclick="document.getElementById('c').style.display='block'">Enviar tudo e terminar</button>
<div id="c" style="display:none"><input type="button" id="id_yuiconfirmyes99" value="Enviar tudo e terminar" onclick="location.href='/send'"></div>
</div></body></html>"""

    def atender(self, rota):
        url = urlparse(rota.request.url)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/attempt":
            corpo = self.questao(int(q["page"]))
        elif url.path == "/go":
            if q.get("a", "") != "":
                self.respondidas[int(q["q"])] = int(q["a"])
            corpo = f"<html><body><script>location.replace('{q['to']}')</script></body></html>"
        elif url.path == "/summary":
            corpo = self.resumo()
        elif url.path == "/send":
            self.enviado = True
            corpo = "<html><body><div role='main'>Tentativa enviada</div></body></html>"
        else:
            corpo = "<html><body>?</body></html>"
        rota.fulfill(status=200, content_type="text/html; charset=utf-8", body=corpo)


def executar(p, site, inicio, falso=None, segundos=40):
    navegador = None
    for canal in ("chrome", "msedge"):
        try:
            navegador = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception:
            continue
    assert navegador, "sem navegador"
    contexto = navegador.new_context()
    contexto.route("http://quiz.test/**", site.atender)
    pagina = contexto.new_page()
    pagina.goto(inicio)
    falso = falso or Falso()
    tela = Tela()
    ass = AssistenteQuiz(
        PageReader(contexto), falso, tela, intervalo=0.05, parar=threading.Event(),
        responder=Responder(contexto), finalizar=True,
    )
    fim = time.monotonic() + segundos
    while time.monotonic() < fim and not site.enviado:
        ass._passo()
        time.sleep(0.05)
    # dar uns ticks extras: se fosse enviar de novo/algo mais, apareceria
    for _ in range(10):
        ass._passo()
        time.sleep(0.05)
    navegador.close()
    return falso, tela


with sync_playwright() as p:
    # 1) leitor com o HTML REAL colado: 10 sem resposta; com algumas respondidas, so faltam as outras
    navegador = None
    for canal in ("chrome", "msedge"):
        try:
            navegador = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception:
            continue
    ctx = navegador.new_context()
    pag = ctx.new_page()
    pag.set_content(RESUMO_REAL)
    leitor = PageReader(ctx)
    r = leitor.ler_resumo()
    assert r is not None and r.faltam == tuple(range(1, 11)), r
    pag.set_content(RESUMO_REAL.replace("quizsummary9 notyetanswered", "quizsummary9 answersaved")
                    .replace("quizsummary10 notyetanswered", "quizsummary10 answersaved"))
    r = leitor.ler_resumo()
    assert r.faltam == tuple(range(1, 9)), r.faltam
    pag.set_content("<html><body><p>nao e resumo</p></body></html>")
    assert leitor.ler_resumo() is None
    # o bloco "info" real: numero da questao e estado
    pag.set_content(f'<div class="que"><div class="qtext">E 8</div><div class="answer"><input type="radio"><label>a</label></div>{INFO_REAL}</div>')
    assert leitor.numero_da_questao() == 8
    assert leitor.questao_ja_respondida() is False
    pag.set_content(pag.content().replace('<input type="radio">', '<input type="radio" checked>'))
    assert leitor.questao_ja_respondida() is True
    navegador.close()
    print("leitor: resumo real, numero da questao e 'ja respondida' ok")

    # 2) o caso do Anthony: 1-8 sem resposta, 9 e 10 respondidas, comeca na pagina 9
    site = Site(total=10, respondidas={9: 3, 10: 4})
    falso, tela = executar(p, site, "http://quiz.test/attempt?page=9")
    assert site.enviado, (site.respondidas, tela.avisos)
    assert sorted(site.respondidas) == list(range(1, 11)), site.respondidas
    assert falso.chamadas == list(range(1, 9)), falso.chamadas  # IA so nas 8 que faltavam
    assert site.respondidas[9] == 3 and site.respondidas[10] == 4  # as respondidas ficaram como estavam
    assert any("Faltam 8 questão(ões)" in a for a in tela.avisos), tela.avisos
    print("caso do Anthony: respondeu so as 8 que faltavam, manteve 9 e 10, enviou completo ok")

    # 3) so uma no meio sem resposta: vai la, responde, e envia
    site = Site(total=10, respondidas={n: 0 for n in range(1, 11) if n != 4})
    falso, tela = executar(p, site, "http://quiz.test/summary")
    assert site.enviado and falso.chamadas == [4] and site.respondidas[4] == 1, (falso.chamadas, site.respondidas)
    print("so a questao 4 faltava: respondeu so ela e enviou ok")

    # 4) tudo respondido: envia direto, sem gastar IA
    site = Site(total=10, respondidas={n: 0 for n in range(1, 11)})
    falso, tela = executar(p, site, "http://quiz.test/summary")
    assert site.enviado and falso.chamadas == [] and not any("Faltam" in a for a in tela.avisos)
    print("tudo respondido: envia direto, sem IA ok")

    # 5) a IA nao consegue responder a questao 5: NAO envia (nunca enviar em branco)
    site = Site(total=6, respondidas={n: 0 for n in (1, 2, 3, 4, 6)})
    falso = Falso()
    falso.nao_responde = {5}
    falso, tela = executar(p, site, "http://quiz.test/summary", falso, segundos=6)
    assert not site.enviado and 5 not in site.respondidas, (site.enviado, site.respondidas)
    print("IA falhou na questao 5: nao enviou ok")

    # 6) o link da questao 3 nao leva a lugar nenhum: tenta so 2 vezes, avisa e NAO envia
    site = Site(total=5, respondidas={n: 0 for n in (1, 2, 4, 5)}, links_quebrados={3})
    falso, tela = executar(p, site, "http://quiz.test/summary", segundos=8)
    assert not site.enviado and 3 not in site.respondidas
    assert any("Não consegui responder a questão 3" in a for a in tela.avisos), tela.avisos
    print("link que nao abre: tentou 2 vezes, avisou e nao enviou ok")

print("TUDO OK")
