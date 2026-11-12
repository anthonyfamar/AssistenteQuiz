import http.server
import sys
import threading

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

from quizbot.page_reader import PageReader

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><circle cx="8" cy="8" r="7" fill="green"/></svg>'
ICONE = '<img class="questioncorrectnessicon" alt="Correto" src="/theme/image.php/kroton/core/1794436560/i/grade_correct">'


def opcoes(n, escolhida=None, correta=None, revisao=False):
    html = ""
    for i in range(5):
        marca = ""
        icone = ""
        if revisao and i == escolhida:
            marca = " correct" if escolhida == correta else " incorrect"
            icone = ICONE
        # estrutura REAL: texto da alternativa num <p> dentro do <label>; o icone cai dentro do <p> (Q2/Q3)
        # ou fora do label (Q1)
        dentro = icone if n != 1 else ""
        fora = icone if n == 1 else ""
        html += (f'<div class="r{i}{marca}"><input type="radio" {"checked disabled" if revisao and i == escolhida else ""}>'
                 f'<label class="m-l-1"><span class="answernumber">{"abcde"[i]}. </span><p>Texto da alternativa {i} da questao {n} {dentro}</p></label>{fora}</div>')
    return html


def questao(n, revisao=False):
    escolhida, correta = {1: (0, 0), 2: (1, 1), 3: (2, 2)}[n]
    figura = '<img src="/figura.png" alt="fig">' if n == 1 else ""
    return (f'<div class="que multichoice deferredfeedback{" correct" if revisao else ""}"><div class="content"><div class="formulation clearfix">'
            f'<div class="qtext"><p>Enunciado da questao numero {n}</p>{figura}</div>'
            f'<div class="ablock"><div class="answer">{opcoes(n, escolhida, correta, revisao)}</div></div></div></div></div>')


PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        caminho = self.path.split("?")[0]
        if caminho.endswith("/i/grade_correct"):
            self.send_response(200); self.send_header("Content-Type", "image/svg+xml"); self.end_headers(); self.wfile.write(SVG); return
        if caminho == "/figura.png":
            self.send_response(200); self.send_header("Content-Type", "image/png"); self.end_headers(); self.wfile.write(PNG); return
        revisao = caminho == "/review"
        n = int(self.path.split("n=")[1]) if "n=" in self.path else None
        corpo = "<html><body>" + (questao(n) if n else "".join(questao(k, revisao) for k in (1, 2, 3))) + "</body></html>"
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(corpo.encode())

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"

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
    leitor = PageReader(ctx)
    # o que o programa le NA TENTATIVA (uma questao por pagina)
    da_tentativa = {}
    for n in (1, 2, 3):
        pag.goto(f"{base}/attempt?n={n}")
        da_tentativa[n] = leitor.ler_questao()
        assert da_tentativa[n] is not None
    # o que le NA REVISAO (as 3 na mesma pagina, com o icone de certo no meio do texto de Q2 e Q3)
    pag.goto(f"{base}/review")
    rs = leitor.ler_revisao()
    print("questoes lidas na revisao:", len(rs), "de 3")
    assert len(rs) == 3, len(rs)
    for n, r in zip((1, 2, 3), rs):
        assert r.questao == da_tentativa[n], f"Q{n}: a questao da revisao difere da da tentativa:\n{r.questao}\n{da_tentativa[n]}"
        assert r.acertou and r.indice == {1: 0, 2: 1, 3: 2}[n], (n, r.indice, r.acertou)
    print("revisao: 3 de 3 lidas, iguais as da tentativa (a memoria vai reconhecer), indice e 'acertou' corretos")
    nav.close()
print("TUDO OK")
