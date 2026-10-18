# MAIN - o ponto de entrada: e este arquivo que se executa.
#
# Abre o navegador visivel (Playwright). O usuario faz login e navega sozinho,
# sem senha em codigo ou .env. Monta as pecas (PageReader, Solver, Presenter)
# e entrega ao AssistenteQuiz.
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from quizbot.assistente import AssistenteQuiz
from quizbot.config import INTERVALO_POLLING, URL_INICIAL
from quizbot.page_reader import PageReader
from quizbot.presenter import TerminalPresenter
from quizbot.solvers import FakeSolver

def main() -> None:
    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(headless=False)
        pagina = navegador.new_page()
        pagina.goto(URL_INICIAL)

        assistente = AssistenteQuiz(
            reader=PageReader(pagina),
            solver=FakeSolver(),
            presenter=TerminalPresenter(),
            intervalo=INTERVALO_POLLING,
        )

        print("Assistente rodando. Ctrl+C no terminal para sair.")
        try:
            assistente.rodar()
        except KeyboardInterrupt:
            print("\nEncerrado.")
        except PlaywrightError:
            print("\nO navegador foi fechado. Encerrado.")

if __name__ == "__main__":
    main()

