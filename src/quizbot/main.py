# MAIN - o ponto de entrada: e este arquivo que se executa (ou o iniciar.bat).
#
# Abre a janelinha, garante o Chrome do assistente aberto (porta de depuracao 9222)
# e conecta a ele so para LER a pagina. O usuario faz login e navega sozinho, sem
# senha em codigo ou .env. Monta as pecas (PageReader, Solver, Presenter) e entrega
# ao AssistenteQuiz.
#
# Threads: a janela (tkinter) fica na thread principal; o assistente (Playwright,
# IA, leitura) roda em outra, porque o Playwright sincrono precisa ser criado e usado
# pela mesma thread.
import threading

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from quizbot.assistente import AssistenteQuiz
from quizbot.chrome import ChromeError, garantir_chrome
from quizbot.config import INTERVALO_POLLING, URL_CDP
from quizbot.janela import JanelaPresenter
from quizbot.page_reader import NavegadorFechado, PageReader
from quizbot.presenter import Presenter
from quizbot.solvers import Solver, SolverError
from quizbot.solvers.fabrica import montar_solver


def trabalhar(solver: Solver, presenter: Presenter, parar: threading.Event) -> None:
    try:
        garantir_chrome()
    except ChromeError as erro:
        presenter.avisar(str(erro))
        return

    with sync_playwright() as playwright:
        try:
            navegador = playwright.chromium.connect_over_cdp(URL_CDP)
        except PlaywrightError:
            presenter.avisar(f"Nao consegui conectar ao Chrome em {URL_CDP}.")
            return
        if not navegador.contexts:
            presenter.avisar("O Chrome esta aberto, mas sem nenhuma janela. Abra uma aba.")
            return

        assistente = AssistenteQuiz(
            reader=PageReader(navegador.contexts[0]),
            solver=solver,
            presenter=presenter,
            intervalo=INTERVALO_POLLING,
            parar=parar,
        )
        print("Conectado ao Chrome. Assistente rodando.")
        try:
            assistente.rodar()
        except (NavegadorFechado, PlaywrightError):
            if not parar.is_set():
                presenter.avisar("O Chrome foi fechado. Encerrado.")


def main() -> None:
    parar = threading.Event()
    janela = JanelaPresenter(ao_fechar=parar.set)

    try:
        solver = montar_solver()
    except SolverError as erro:
        janela.avisar(str(erro))
        janela.executar()
        return

    thread = threading.Thread(target=trabalhar, args=(solver, janela, parar), daemon=True)
    thread.start()
    try:
        janela.executar()
    except KeyboardInterrupt:
        pass
    finally:
        parar.set()
        thread.join(timeout=5)
        print("Encerrado.")


if __name__ == "__main__":
    main()
