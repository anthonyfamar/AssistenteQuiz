import http.server
import sys
import threading

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from playwright.sync_api import sync_playwright

from quizbot.assistente import AssistenteQuiz
from quizbot.page_reader import PageReader
from quizbot.responder import Responder

TABELA = """<table class="generaltable quizattemptsummary"><thead><tr>
<th scope="col">Tentativa</th><th scope="col">Estado</th><th scope="col">Nota / 10,00</th></tr></thead>
<tbody><tr><td>1</td><td>Finalizada<span class="statedetails">Enviada</span></td><td>10,00</td></tr></tbody></table>
<form><button type="submit">Fazer uma outra tentativa</button></form>"""


class Moodle(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        caminho = self.path.split("?")[0]
        if caminho == "/mod/quiz/attempt.php":  # tentativa ja enviada: o Moodle redireciona
            self.send_response(302)
            self.send_header("Location", "/mod/quiz/review.php?attempt=9")
            self.end_headers()
            return
        corpo = {
            "/course/view.php": "<h1>Curso</h1><a href='/mod/quiz/view.php?id=2'>quiz</a>",
            "/mod/quiz/view.php": TABELA,
            "/mod/quiz/review.php": "<h1>Revisao</h1>",
            "/mod/quiz/summary.php": "<h1>Resumo</h1>",
        }.get(caminho, "<h1>?</h1>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corpo.encode())

    def log_message(self, *a):
        pass


servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Moodle)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{servidor.server_port}"


class Pres:
    def __init__(self):
        self.msgs = []

    def avisar(self, m):
        self.msgs.append(m)

    def oferecer_tentar_de_novo(self, m, tentar):
        self.msgs.append(m)

    def consultando(self):
        pass

    def mostrar(self, *a):
        pass


with sync_playwright() as p:
    navegador = None
    for canal in ("chrome", "msedge"):
        try:
            navegador = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception as erro:
            print("sem", canal, type(erro).__name__)
    assert navegador
    contexto = navegador.new_context()
    aba = contexto.new_page()
    leitor, resp = PageReader(contexto), Responder(contexto)

    # historico real: curso -> quiz -> tentativa (redireciona p/ revisao) -> resumo -> revisao -> quiz
    for caminho in ("/course/view.php?id=1", "/mod/quiz/view.php?id=2", "/mod/quiz/summary.php?attempt=9",
                    "/mod/quiz/attempt.php?attempt=9&page=0", "/mod/quiz/review.php?attempt=9",
                    "/mod/quiz/view.php?id=2"):
        aba.goto(base + caminho)
    assert leitor.ler_painel().tudo_certo
    pres = Pres()
    a = AssistenteQuiz(leitor, None, pres, responder=resp, tentativas=True, pausa_voltar=1.0, parar=threading.Event())
    a._passo()
    print("url final:", aba.url, "| msgs:", pres.msgs)
    assert "/course/view.php" in aba.url, aba.url
    assert any("Acertou tudo" in m and "Voltando ao curso" in m for m in pres.msgs)
    assert not any("Não consegui" in m for m in pres.msgs)
    # nos ticks seguintes (ja no curso) nao faz mais nada
    a._passo(); a._passo()
    assert "/course/view.php" in aba.url
    print("nota maxima -> volta pelo historico ate o curso: ok")

    # sem curso no historico: nao fica andando; para onde estiver e avisa
    aba2 = contexto.new_page()
    aba.close()
    aba2.goto(base + "/mod/quiz/view.php?id=2")
    pres = Pres()
    b = AssistenteQuiz(leitor, None, pres, responder=resp, tentativas=True, pausa_voltar=1.0, parar=threading.Event())
    b._passo()
    assert "/mod/quiz/view.php" in aba2.url and any("Não consegui voltar" in m for m in pres.msgs), (aba2.url, pres.msgs)
    print("sem curso no historico: avisa e para: ok")

    # o clique no botao continua tendo prioridade quando ele existe (tentativas esgotadas)
    aba2.set_content("<p title='x'>Não são permitidas outras tentativas</p>"
                     "<button onclick=\"document.title='[voltou]'\">Voltar ao curso</button>")
    assert resp.voltar_ao_curso() and aba2.title() == "[voltou]"
    navegador.close()
print("TUDO OK")
