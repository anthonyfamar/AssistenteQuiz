# CHROME - garante que o Chrome do assistente esta aberto com a porta de depuracao.
#
# garantir_chrome() -> se a porta 9222 nao responde, abre o Chrome (perfil separado,
#                      fora do projeto) e espera ate a porta subir.
#                      Se nao conseguir, levanta ChromeError com o motivo.
# O usuario faz login e navega sozinho nessa janela. O programa so le.
import socket
import subprocess
import time

from quizbot.config import CAMINHOS_CHROME, PERFIL_CHROME, PORTA_DEBUG


class ChromeError(Exception):
    """Nao foi possivel deixar o Chrome pronto para a conexao."""


def porta_aberta() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORTA_DEBUG), timeout=0.5):
            return True
    except OSError:
        return False


def _achar_chrome() -> str | None:
    for caminho in CAMINHOS_CHROME:
        if caminho.exists():
            return str(caminho)
    return None


def garantir_chrome(espera: float = 15.0) -> None:
    if porta_aberta():
        return

    executavel = _achar_chrome()
    if executavel is None:
        raise ChromeError(
            "Nao encontrei o Google Chrome. Instale-o ou ajuste CAMINHOS_CHROME no config.py."
        )

    # DETACHED_PROCESS: o Chrome nao fecha junto com este programa nem com o terminal.
    separado = getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        [
            executavel,
            f"--remote-debugging-port={PORTA_DEBUG}",
            f"--user-data-dir={PERFIL_CHROME}",
        ],
        creationflags=separado,
    )

    limite = time.monotonic() + espera
    while time.monotonic() < limite:
        if porta_aberta():
            return
        time.sleep(0.5)
    raise ChromeError(
        "O Chrome abriu, mas sem a porta de depuracao. Se o Chrome do assistente ja estava "
        "aberto, feche-o e tente de novo."
    )
