# MAIN - o ponto de entrada: e este arquivo que se executa.
#
# Conecta ao Chrome que o USUARIO abriu (com a porta de depuracao 9222) e so le
# a pagina. O usuario faz login e navega sozinho, sem senha em codigo ou .env.
# Monta as pecas (PageReader, Solver, Presenter) e entrega ao AssistenteQuiz.
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from quizbot.assistente import AssistenteQuiz
from quizbot.config import INTERVALO_POLLING, URL_CDP
from quizbot.page_reader import NavegadorFechado, PageReader
from quizbot.presenter import TerminalPresenter
from quizbot.solvers import SolverError
from quizbot.solvers.fabrica import montar_solver

COMANDO_CHROME = (
    '& "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
    '--remote-debugging-port=9222 --user-data-dir="$env:USERPROFILE\\chrome-assistente"'
)


def main() -> None:
    try:
        solver = montar_solver()
    except SolverError as erro:
        print(f"[erro] {erro}")
        return

    with sync_playwright() as playwright:
        try:
            navegador = playwright.chromium.connect_over_cdp(URL_CDP)
        except PlaywrightError:
            print(f"[erro] Nao consegui conectar ao Chrome em {URL_CDP}.")
            print("Abra o Chrome com este comando (PowerShell) e tente de novo:")
            print(COMANDO_CHROME)
            return
        if not navegador.contexts:
            print("[erro] O Chrome esta aberto, mas sem nenhuma janela. Abra uma aba e tente de novo.")
            return

        assistente = AssistenteQuiz(
            reader=PageReader(navegador.contexts[0]),
            solver=solver,
            presenter=TerminalPresenter(),
            intervalo=INTERVALO_POLLING,
        )

        print("Conectado ao Chrome. Assistente rodando. Ctrl+C no terminal para sair.")
        try:
            assistente.rodar()
        except KeyboardInterrupt:
            print("\nEncerrado.")
        except (NavegadorFechado, PlaywrightError):
            print("\nO Chrome foi fechado. Encerrado.")


if __name__ == "__main__":
    main()
