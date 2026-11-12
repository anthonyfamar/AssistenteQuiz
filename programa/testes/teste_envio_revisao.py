import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

import quizbot.assistente as modulo
from quizbot.armazenamento import ArmazenamentoLocal
from quizbot.assistente import AssistenteQuiz
from quizbot.memoria import Memoria
from quizbot.models import Suggestion
from quizbot.page_reader import PageReader
from quizbot.presenter import Presenter
from quizbot.responder import Responder
from quizbot.solvers.base import Solver

modulo.PAUSA_APOS_CLICAR = 0.05
modulo.PAUSA_APOS_ABRIR_QUESTAO = 0.3
TOTAL = 5
SEM_MARCAS = len(sys.argv) > 1 and sys.argv[1] == "sem_marcas"
ILEGIVEL = len(sys.argv) > 1 and sys.argv[1] == "ilegivel"  # tem gabarito, mas o programa nao consegue ler
if SEM_MARCAS or ILEGIVEL:
    modulo.ESPERA_PELA_REVISAO = 1.0
import http.server

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")


class _Img(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.end_headers()
        self.wfile.write(PNG)

    def log_message(self, *a):
        pass


_srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Img)
threading.Thread(target=_srv.serve_forever, daemon=True).start()
IMG = f"http://127.0.0.1:{_srv.server_port}/imagem.png"  # imagem em OUTRO endereco, como a do Anthony


class Falso(Solver):
    def solve(self, question):
        return Suggestion(indice=1, explicacao="x", origem="falso")


class Tela(Presenter):
    def __init__(self):
        self.avisos = []

    def mostrar(self, question, suggestion):
        pass

    def avisar(self, mensagem):
        self.avisos.append(mensagem)


class Site:
    def __init__(self):
        self.respondidas = {}
        self.revisao_lida = False
        self.terminou = False

    def figura(self, n):
        return f'<img src="{IMG}">' if n in (1, 3) else ""

    def questao(self, n):
        marcada = self.respondidas.get(n)
        radios = "".join(
            f'<div class="r{i}"><input type="radio" name="q" id="a{i}" value="{i}"{" checked" if marcada == i else ""}>'
            f'<label for="a{i}">{"abcde"[i]}. Alternativa {i} da questao {n}</label></div>' for i in range(5))
        ultimo = n == TOTAL
        destino = "/mod/quiz/summary.php" if ultimo else f"/mod/quiz/attempt.php?page={n + 1}"
        return f"""<html><body><div role="main"><form>
<div class="que multichoice"><div class="info"><h3 class="no">Questão <span class="qno">{n}</span></h3><div class="state">{"Resposta salva" if marcada is not None else "Ainda não respondida"}</div></div>
<div class="content"><div class="formulation"><div class="qtext"><p>Enunciado numero {n}</p>{self.figura(n)}</div>
<div class="ablock"><div class="answer">{radios}</div></div></div></div></div>
<input type="submit" name="next" value="{'Terminar tentativa ...' if ultimo else 'Próxima página'}" class="mod_quiz-next-nav btn btn-primary"
 onclick="var c=document.querySelector('input[type=radio]:checked'); location.href='/go?q={n}&a='+(c?c.value:'')+'&to={destino}'; return false">
</form></div></body></html>"""

    def resumo(self):
        linhas = "".join(
            f'<tr class="quizsummary{n} {"answersaved" if n in self.respondidas else "notyetanswered"}"><td class="cell c0"><a href="/mod/quiz/attempt.php?page={n}">{n}</a></td>'
            f'<td>{"Resposta salva" if n in self.respondidas else "Ainda não respondida"}</td></tr>' for n in range(1, TOTAL + 1))
        return f"""<html><body><div role="main"><h3>Resumo de tentativas</h3>
<table class="generaltable quizsummaryofattempt"><thead><tr><th>Pergunta</th><th>Status</th></tr></thead><tbody>{linhas}</tbody></table>
<button type="button" class="btn btn-primary" onclick="document.getElementById('c').style.display='block'">Enviar tudo e terminar</button>
<div id="c" style="display:none"><input type="button" id="id_yuiconfirmyes99" value="Enviar tudo e terminar" onclick="location.href='/mod/quiz/review.php?attempt=9'"></div></div></body></html>"""

    def revisao(self):
        blocos = ""
        for n in range(1, TOTAL + 1):
            alts = "".join(
                f'<div class="r{i} {("" if SEM_MARCAS else ("correct" if i == 1 else ("incorrect" if i == 0 and n % 2 == 0 else "")))}"><input type="radio" disabled {"checked" if i == self.respondidas.get(n) else ""}>'
                f'<label>{"abcde"[i]}. Alternativa {i} da questao {n}</label></div>' for i in range(5))
            blocos += (f'<div class="que multichoice"><div class="info"><h3 class="no">Questão <span class="qno">{n}</span></h3></div>'
                       f'<div class="content"><div class="formulation"><div class="{"x" if ILEGIVEL else "qtext"}"><p>Enunciado numero {n}</p>{self.figura(n)}</div>'
                       f'<div class="ablock"><div class="answer">{alts}</div></div></div></div></div>')
        return (f'<html><body><div role="main">{blocos}<a class="mod_quiz-next-nav btn btn-primary" href="/mod/quiz/view.php?fim=1">Terminar revisão</a></div></body></html>')

    def atender(self, rota):
        url = urlparse(rota.request.url)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.hostname == "cdn.test":
            rota.fulfill(status=200, content_type="image/png", body=PNG, headers={"Access-Control-Allow-Origin": "*"})
            return
        if url.path == "/mod/quiz/attempt.php":
            corpo = self.questao(int(q["page"]))
        elif url.path == "/go":
            if q.get("a", "") != "":
                self.respondidas[int(q["q"])] = int(q["a"])
            corpo = f"<html><body><script>location.replace('{q['to']}')</script></body></html>"
        elif url.path == "/mod/quiz/summary.php":
            corpo = self.resumo()
        elif url.path == "/mod/quiz/review.php":
            corpo = self.revisao()
        elif url.path == "/mod/quiz/view.php":
            self.terminou = "fim" in q
            corpo = "<html><body><div role='main'>pagina do quiz</div></body></html>"
        else:
            corpo = "<html><body>?</body></html>"
        rota.fulfill(status=200, content_type="text/html; charset=utf-8", body=corpo)


with sync_playwright() as p:
    nav = None
    for canal in ("chrome", "msedge"):
        try:
            nav = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception:
            pass
    ctx = nav.new_context()
    site = Site()
    ctx.route(re.compile(r"http://quiz\.test/.*"), site.atender)
    pag = ctx.new_page()
    pag.goto("http://quiz.test/mod/quiz/attempt.php?page=1")
    pasta = Path(tempfile.mkdtemp())
    memoria = Memoria(ArmazenamentoLocal(pasta, "teste"), "teste")
    tela = Tela()
    ass = AssistenteQuiz(PageReader(ctx), Falso(), tela, intervalo=0.05, parar=threading.Event(),
                         responder=Responder(ctx), finalizar=True, tentativas=True, curso=True,
                         memoria=memoria, pausa_voltar=0.3, pausa_curso=1)
    import contextlib
    import io

    saida = io.StringIO()  # o que o programa escreve no registro durante o fluxo
    fim = time.monotonic() + (6 if ILEGIVEL else 40)
    with contextlib.redirect_stdout(saida):
        while time.monotonic() < fim and not site.terminou:
            ass._passo()
            time.sleep(0.05)
    print(saida.getvalue(), end="")
    print("avisos:", tela.avisos)
    if not (SEM_MARCAS or ILEGIVEL):
        # placar da revisao: quem respondeu e quantas acertou (o falso responde sempre a alternativa B)
        assert saida.getvalue().count("[acerto] falso: 3 de 5") == 1, saida.getvalue()
        print("placar por provedor no registro, uma vez so ok")
    if SEM_MARCAS or ILEGIVEL:  # nao deu para ler a revisao: NUNCA termina sozinho (perderia dados); so avisa, uma vez
        assert not site.terminou
        assert sum("ainda não consegui ler a revisão" in a for a in tela.avisos) == 1, tela.avisos
        print("revisao ilegivel (sem marcas ou com estrutura diferente): nao terminou, avisou UMA vez ok")
        nav.close()
        raise SystemExit(0)
    assert site.terminou, "nao terminou a revisao"
    assert "Tentativa enviada." in tela.avisos and "Revisão terminada." in tela.avisos, tela.avisos
    assert any(a.startswith("Revisão lida: guardei") for a in tela.avisos), tela.avisos
    arquivo = next(pasta.glob("memoria-*.json"))
    assert arquivo.stat().st_size > 10, "nada foi salvo"
    print("responder 5 questoes (2 com imagem de outro endereco) -> resumo -> enviar -> revisao -> salvar -> terminar revisao: ok")
    nav.close()
print("TUDO OK")
