# TESTE - leitura da pagina de REVISAO a partir dos arquivos HTML de exemplo (pasta html/).
#
# Cada arquivo e uma revisao de 3 questoes. Para cada um confere que o programa:
#   - le as 3 questoes e a alternativa marcada (e se estava certa);
#   - NAO deixa o icone de "Correto" (img.questioncorrectnessicon) virar texto/imagem da questao;
#   - le cada questao IGUAL a como a leu durante a tentativa (so assim a memoria a reconhece depois).
# A "tentativa" e montada a partir do proprio arquivo (tira icones e marcas, uma questao por vez).
#
# Arquivos de exemplo:
#   revisao_icone_fora_e_dentro.html -> estrutura REAL (textos resumidos) de uma revisao em que o icone
#                                       fica fora do texto da alternativa (Q1) e dentro dele (Q2, Q3);
#   revisao_sem_icone.html           -> o formato simples (alternativas sem icone), reconstruido.
# O {{IMAGEM}} do HTML e trocado por uma imagem servida em outro endereco (como a do site real).
import http.server
import pathlib
import re
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

from quizbot.page_reader import PageReader

PASTA_HTML = pathlib.Path(__file__).resolve().parent / "html"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63600000"
    "02000001e221bc330000000049454e44ae426082"
)

# Faz a pagina da revisao parecer a da tentativa: so a questao de numero i, sem icones e marcas.
JS_COMO_TENTATIVA = """
i => {
    Array.from(document.querySelectorAll('.que')).forEach((q, k) => { if (k !== i) q.remove(); });
    document.querySelectorAll('.questioncorrectnessicon, .state, .grade, .questionflag').forEach(e => e.remove());
    document.querySelectorAll('.correct, .incorrect').forEach(e => e.classList.remove('correct', 'incorrect'));
    document.querySelectorAll('input[type=radio]').forEach(r => { r.disabled = false; });
}
"""


class Imagem(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.end_headers()
        self.wfile.write(PNG)

    def log_message(self, *args):
        pass


def servir(html):
    # O Playwright chama o tratador com (rota, pedido): o HTML fica guardado aqui, fora dos argumentos.
    return lambda rota: rota.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)


servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Imagem)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
URL_IMAGEM = f"http://127.0.0.1:{servidor.server_port}/figura.png"

arquivos = sorted(PASTA_HTML.glob("revisao_*.html"))
assert arquivos, f"nenhum arquivo revisao_*.html em {PASTA_HTML}"

with sync_playwright() as p:
    navegador = None
    for canal in ("chrome", "msedge"):
        try:
            navegador = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception:
            pass
    assert navegador, "nem o Chrome nem o Edge foram achados"

    for arquivo in arquivos:
        html = arquivo.read_text(encoding="utf-8").replace("{{IMAGEM}}", URL_IMAGEM)
        total = len(re.findall(r'class="que ', html))
        contexto = navegador.new_context()
        # O HTML aponta para imagens do site real (icones do Moodle): nada de internet no teste.
        # Qualquer endereco externo responde na hora com uma imagem vazia.
        contexto.route(
            re.compile(r"https?://(?!quiz\.test|127\.0\.0\.1).*"),
            lambda r: r.fulfill(status=200, content_type="image/svg+xml", body="<svg xmlns='http://www.w3.org/2000/svg'/>"),
        )
        contexto.route(re.compile(r"http://quiz\.test/.*"), servir(html))
        aba = contexto.new_page()
        leitor = PageReader(contexto)

        da_tentativa = []
        for i in range(total):
            aba.goto("http://quiz.test/revisao")
            aba.evaluate(JS_COMO_TENTATIVA, i)
            questao = leitor.ler_questao()
            assert questao is not None, f"{arquivo.name}: nao leu a questao {i + 1} no modo tentativa"
            da_tentativa.append(questao)

        aba.goto("http://quiz.test/revisao")
        resultados = leitor.ler_revisao()
        assert len(resultados) == total, f"{arquivo.name}: leu {len(resultados)} de {total} questoes da revisao"
        for i, (resultado, tentativa) in enumerate(zip(resultados, da_tentativa), start=1):
            assert resultado.acertou, f"{arquivo.name}: Q{i} devia ser 'certa'"
            assert resultado.questao == tentativa, (
                f"{arquivo.name}: Q{i} lida na revisao difere da lida na tentativa:\n"
                f"{resultado.questao}\n--- tentativa:\n{tentativa}"
            )
            texto = resultado.questao.enunciado + " ".join(resultado.questao.alternativas)
            assert "grade_correct" not in texto and "Correto" not in " ".join(resultado.questao.alternativas), (
                f"{arquivo.name}: Q{i}: o icone de certo entrou no texto"
            )
        print(f"{arquivo.name}: {total} de {total} questoes lidas, iguais as da tentativa, sem icone no texto ok")
        contexto.close()
    navegador.close()
print("TUDO OK")
