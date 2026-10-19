# CHROME - garante que o navegador do assistente esta aberto com a porta de depuracao.
#
# garantir_chrome() -> se a porta 9222 nao responde, abre o navegador (Chrome ou, se
#                      nao houver, o Edge; perfil separado, fora do projeto) e espera
#                      ate a porta subir. Se nao conseguir, levanta ChromeError.
# achar_navegador() -> caminho do navegador: o CAMINHO_NAVEGADOR do .env, se existir,
#                      senao o primeiro de CAMINHOS_NAVEGADOR que existir.
# O usuario faz login e navega sozinho nessa janela. O programa so le.
import os
import socket
import subprocess
import time
from pathlib import Path

from quizbot.config import CAMINHOS_NAVEGADOR, PERFIL_NAVEGADOR, PORTA_DEBUG


class ChromeError(Exception):
    """Nao foi possivel deixar o navegador pronto para a conexao."""


def porta_aberta() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORTA_DEBUG), timeout=0.5):
            return True
    except OSError:
        return False


def achar_navegador() -> str | None:
    manual = os.environ.get("CAMINHO_NAVEGADOR", "").strip().strip('"')
    candidatos = ([Path(manual)] if manual else []) + list(CAMINHOS_NAVEGADOR)
    for caminho in candidatos:
        if caminho.exists():
            return str(caminho)
    return None


def garantir_chrome(espera: float = 15.0) -> None:
    if porta_aberta():
        return

    executavel = achar_navegador()
    if executavel is None:
        raise ChromeError(
            "Nao encontrei o Chrome nem o Edge. Abra a configuracao e indique onde o "
            "navegador esta instalado."
        )

    # DETACHED_PROCESS: o navegador nao fecha junto com este programa nem com o terminal.
    separado = getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        [
            executavel,
            f"--remote-debugging-port={PORTA_DEBUG}",
            f"--user-data-dir={PERFIL_NAVEGADOR}",
        ],
        creationflags=separado,
    )

    limite = time.monotonic() + espera
    while time.monotonic() < limite:
        if porta_aberta():
            return
        time.sleep(0.5)
    raise ChromeError(
        "O navegador abriu, mas sem a porta de depuracao. Se o navegador do assistente ja "
        "estava aberto, feche todas as janelas dele e tente de novo."
    )
