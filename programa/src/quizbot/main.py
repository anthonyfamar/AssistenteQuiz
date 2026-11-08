# MAIN - o ponto de entrada: e este arquivo que se executa (ou o iniciar.bat).
#
# Abre a janelinha, garante o Chrome do assistente aberto (porta de depuracao 9222)
# e conecta a ele para ler a pagina e, no modo automatico, agir nela. O usuario faz
# login sozinho, sem senha em codigo ou .env. Monta as pecas (PageReader, Solver,
# Presenter e, se AUTOMATICO nao for "nao", o Responder) e entrega ao AssistenteQuiz.
#
# Chaves do .env (valem "sim" se faltarem): AUTOMATICO (marca e avanca) e
# AUTOMATICO_FINALIZAR (envia a tentativa). Sao lidas DEPOIS de montar_solver(), que
# e quem carrega o .env.
#
# Threads: a janela (tkinter) fica na thread principal; o assistente (Playwright,
# IA, leitura) roda em outra, porque o Playwright sincrono precisa ser criado e usado
# pela mesma thread.
import os
import threading

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from quizbot.assistente import AssistenteQuiz
from quizbot.chrome import ChromeError, garantir_chrome
from quizbot.armazenamento import (
    Armazenamento,
    ArmazenamentoEspelhado,
    ArmazenamentoFirestore,
    ArmazenamentoLocal,
)
from quizbot.config import (
    FIREBASE_CHAVE_API,
    FIREBASE_PROJETO,
    INTERVALO_POLLING,
    MEMORIA_EMAIL,
    NOME_PC,
    PASTA_MEMORIA,
    URL_CDP,
)
from quizbot.janela import JanelaPresenter
from quizbot.memoria import Memoria
from quizbot.page_reader import NavegadorFechado, PageReader
from quizbot.presenter import Presenter
from quizbot.responder import Responder
from quizbot.solvers import Solver, SolverComMemoria, SolverError
from quizbot.solvers.fabrica import montar_solver


def _ligado(nome: str) -> bool:
    # Chave faltando ou vazia vale "sim"; so desliga com um destes valores.
    valor = os.getenv(nome, "").strip().lower() or "sim"
    return valor not in ("nao", "não", "n", "0", "false", "off")


def _montar_memoria() -> Memoria:
    # Sempre grava um arquivo local. Se houver a senha da memoria no .env (MEMORIA_SENHA),
    # espelha na nuvem e assim os PCs dividem o que aprenderam. Sem senha ou sem internet,
    # o programa segue so com o local (nunca trava por causa da nuvem).
    nome = os.getenv("NOME_PC", "").strip() or NOME_PC
    local = ArmazenamentoLocal(PASTA_MEMORIA, nome)
    armazenamento: Armazenamento = local
    senha = os.getenv("MEMORIA_SENHA", "").strip()
    if not senha:
        print("[memoria] sem senha da memoria no .env; usando so o arquivo local.")
    else:
        nuvem = ArmazenamentoFirestore(FIREBASE_PROJETO, FIREBASE_CHAVE_API, MEMORIA_EMAIL, senha)
        armazenamento = ArmazenamentoEspelhado(local, nuvem)
        print(f"[memoria] nuvem ligada; este PC se chama {nome!r}.")
    return Memoria(armazenamento, nome)


def trabalhar(
    solver: Solver,
    presenter: Presenter,
    parar: threading.Event,
    automatico: bool,
    finalizar: bool,
    memoria: Memoria,
) -> None:
    try:
        garantir_chrome()
    except ChromeError as erro:
        presenter.avisar(str(erro))
        return

    with sync_playwright() as playwright:
        try:
            navegador = playwright.chromium.connect_over_cdp(URL_CDP)
        except PlaywrightError:
            presenter.avisar(f"Nao consegui conectar ao navegador em {URL_CDP}.")
            return
        if not navegador.contexts:
            presenter.avisar("O navegador esta aberto, mas sem nenhuma janela. Abra uma aba.")
            return

        memoria.atualizar()  # ja baixa a memoria dos outros PCs; erro de login aparece agora
        contexto = navegador.contexts[0]
        assistente = AssistenteQuiz(
            reader=PageReader(contexto),
            solver=solver,
            presenter=presenter,
            intervalo=INTERVALO_POLLING,
            parar=parar,
            responder=Responder(contexto) if automatico else None,
            finalizar=finalizar,
            memoria=memoria,
        )
        print(
            "Conectado ao navegador. Assistente rodando "
            f"(automatico: {'sim' if automatico else 'nao'}, "
            f"finalizar: {'sim' if automatico and finalizar else 'nao'})."
        )
        try:
            assistente.rodar()
        except (NavegadorFechado, PlaywrightError):
            if not parar.is_set():
                presenter.avisar("O navegador foi fechado. Encerrado.")


def main() -> None:
    parar = threading.Event()
    janela = JanelaPresenter(ao_fechar=parar.set)

    try:
        solver = montar_solver()
    except SolverError as erro:
        janela.avisar(str(erro))
        janela.executar()
        return

    automatico = _ligado("AUTOMATICO")
    finalizar = _ligado("AUTOMATICO_FINALIZAR")
    memoria = _montar_memoria()
    solver = SolverComMemoria(solver, memoria)
    thread = threading.Thread(
        target=trabalhar,
        args=(solver, janela, parar, automatico, finalizar, memoria),
        daemon=True,
    )
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
