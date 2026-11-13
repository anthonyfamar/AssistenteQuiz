# MAIN - o ponto de entrada: e este arquivo que se executa (pelo atalho ou pelo
# iniciar.pyw, sem janela preta; ou, para ver as mensagens ao vivo, pelo terminal:
# python -m quizbot.main com PYTHONPATH=programa\src).
#
# Abre a janelinha, que mostra primeiro a tela de escolha do modo:
#   - Automatico: o programa faz tudo (marca, avanca, envia, confere a revisao, refaz as
#     tentativas, volta ao curso e percorre as unidades, fazendo os 2 quizzes de cada uma);
#   - So sugerir: so mostra a sugestao; o usuario faz o resto.
# Depois da escolha garante o Chrome do assistente aberto (porta de depuracao 9222) e
# conecta a ele. O usuario faz login sozinho, sem senha em codigo ou .env. Monta as pecas
# (PageReader, Solver, Presenter e, no Automatico, o Responder) e entrega ao AssistenteQuiz.
#
# Registro (log): tudo que o programa imprime vai para o arquivo assistente.log (veja
# registro.py). Se algo quebrar, a janelinha mostra so "algo deu errado" e a pasta do
# registro; os detalhes ficam la.
#
# Threads: a janela (tkinter) fica na thread principal; o assistente (Playwright,
# IA, leitura) roda em outra, porque o Playwright sincrono precisa ser criado e usado
# pela mesma thread.
import os
import threading

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from quizbot import registro
from quizbot.armazenamento import (
    Armazenamento,
    ArmazenamentoEspelhado,
    ArmazenamentoFirestore,
    ArmazenamentoLocal,
)
from quizbot.assistente import AssistenteQuiz
from quizbot.chrome import ChromeError, garantir_chrome
from quizbot.config import (
    FIREBASE_CHAVE_API,
    FIREBASE_PROJETO,
    INTERVALO_POLLING,
    MEMORIA_EMAIL,
    NOME_PC,
    PASTA_LOGS,
    PASTA_MEMORIA,
    URL_CDP,
)
from quizbot.janela import JanelaPresenter
from quizbot.memoria import Memoria, RevisoesLidas
from quizbot.page_reader import NavegadorFechado, PageReader
from quizbot.presenter import Presenter
from quizbot.responder import Responder
from quizbot.solvers import Solver, SolverComMemoria, SolverError
from quizbot.solvers.fabrica import montar_solver


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
            finalizar=automatico,
            memoria=memoria,
            tentativas=automatico,
            curso=automatico,
            # Lembra entre uma execucao e outra quais revisoes ja foram lidas (nao abre de novo).
            revisoes_lidas=RevisoesLidas(PASTA_MEMORIA / "revisoes-lidas.json"),
        )
        print(f"Conectado ao navegador. Assistente rodando (modo {'automatico' if automatico else 'so sugerir'}).")
        try:
            assistente.rodar()
        except (NavegadorFechado, PlaywrightError):
            if not parar.is_set():
                presenter.avisar("O navegador foi fechado. Encerrado.")


def _trabalhar_com_registro(
    janela: JanelaPresenter,
    solver: Solver,
    parar: threading.Event,
    automatico: bool,
    memoria: Memoria,
) -> None:
    # Erro que ninguem previu: vai inteiro para o registro e a janelinha so avisa.
    try:
        trabalhar(solver, janela, parar, automatico, memoria)
    except Exception:
        registro.registrar_erro("o assistente parou por um erro inesperado")
        janela.erro_inesperado(str(PASTA_LOGS))


def _erro_ao_abrir() -> None:
    # Se nem a janelinha abriu, o jeito de avisar e uma caixa de mensagem simples.
    try:
        import tkinter as tk
        from tkinter import messagebox

        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror(
            "AssistenteQuiz",
            f"Algo deu errado ao abrir o AssistenteQuiz.\n\nOs detalhes estao em:\n{PASTA_LOGS}",
        )
        raiz.destroy()
    except Exception:
        pass


def _executar() -> None:
    parar = threading.Event()
    janela = JanelaPresenter(ao_fechar=parar.set)

    try:
        solver = montar_solver(janela.problemas_nos_provedores)
    except SolverError as erro:
        janela.avisar(str(erro))
        janela.executar()
        return

    memoria = _montar_memoria()
    solver = SolverComMemoria(solver, memoria)
    threads: list[threading.Thread] = []

    def comecar(automatico: bool) -> None:
        print(f"[modo] {'automatico' if automatico else 'so sugerir'}")
        thread = threading.Thread(
            target=_trabalhar_com_registro,
            args=(janela, solver, parar, automatico, memoria),
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    janela.escolher_modo(comecar)
    try:
        janela.executar()
    except KeyboardInterrupt:
        pass
    finally:
        parar.set()
        for thread in threads:
            thread.join(timeout=5)
        print("Encerrado.")


def main() -> None:
    registro.iniciar()
    try:
        _executar()
    except Exception:
        registro.registrar_erro("erro ao abrir o programa")
        _erro_ao_abrir()
        raise SystemExit(1)  # codigo de saida de erro (quem roda pelo terminal percebe)


if __name__ == "__main__":
    main()
