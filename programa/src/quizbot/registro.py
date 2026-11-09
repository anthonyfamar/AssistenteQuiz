# REGISTRO - o "diario" do programa (log): tudo que antes aparecia no terminal.
#
# Sem a janela preta (pythonw) nao ha terminal, entao o que o programa conta vai para um
# arquivo: assistente.log, na pasta do usuario (veja ARQUIVO_LOG no config.py). Quem usa so
# precisa saber ONDE ele fica; quem desenvolve abre e ve o que aconteceu.
#
# iniciar()        -> chame uma vez, no comeco. Troca o print por uma copia que escreve no
#                     arquivo (com a hora de cada linha) e, se houver terminal, tambem nele.
#                     O arquivo recomeca a cada execucao; o anterior vira assistente.log.1.
# registrar_erro() -> grava o rastro completo (traceback) do erro que esta acontecendo.
# abrir_pasta()    -> abre a pasta do registro no Explorer.
#
# Chaves e senhas NUNCA vao para o arquivo: qualquer valor de variavel de ambiente cujo nome
# tenha KEY ou SENHA e trocado por *** antes de gravar (mensagens de erro de provedores
# as vezes citam um pedaco da chave).
import os
import sys
import time
import traceback
from pathlib import Path
from typing import TextIO

from quizbot.config import ARQUIVO_LOG

_MINIMO_SEGREDO = 6  # valores muito curtos (ex.: "sim") nao sao segredo e estragariam o texto


def _segredos() -> list[str]:
    valores = (
        valor
        for nome, valor in os.environ.items()
        if ("KEY" in nome.upper() or "SENHA" in nome.upper()) and len(valor) >= _MINIMO_SEGREDO
    )
    return sorted(set(valores), key=len, reverse=True)


def esconder_segredos(texto: str) -> str:
    for segredo in _segredos():
        texto = texto.replace(segredo, "***")
    return texto


class _Copia:
    """Parece um sys.stdout: escreve no arquivo (com hora) e, se existir, no terminal."""

    def __init__(self, arquivo: TextIO, terminal: TextIO | None) -> None:
        self._arquivo = arquivo
        self._terminal = terminal
        self._inicio_de_linha = True

    def write(self, texto: str) -> int:
        if self._terminal is not None:
            try:
                self._terminal.write(texto)
            except (OSError, ValueError, UnicodeError):
                pass  # o terminal nunca pode derrubar o programa
        seguro = esconder_segredos(texto)
        saida = []
        for pedaco in seguro.splitlines(keepends=True):
            if self._inicio_de_linha:
                saida.append(time.strftime("%H:%M:%S "))
            saida.append(pedaco)
            self._inicio_de_linha = pedaco.endswith("\n")
        self._arquivo.write("".join(saida))
        self._arquivo.flush()
        return len(texto)

    def flush(self) -> None:
        self._arquivo.flush()

    def isatty(self) -> bool:
        return False


def _abrir_arquivo(arquivo: Path) -> TextIO:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    if arquivo.exists():
        anterior = arquivo.with_name(arquivo.name + ".1")
        try:
            os.replace(arquivo, anterior)
        except OSError:
            pass  # arquivo em uso (outro programa aberto): segue e sobrescreve
    return open(arquivo, "w", encoding="utf-8", errors="replace")


def iniciar(arquivo: Path = ARQUIVO_LOG) -> Path:
    copia = _Copia(_abrir_arquivo(arquivo), sys.stdout)
    sys.stdout = copia
    sys.stderr = _Copia(copia._arquivo, sys.stderr)
    print(f"[registro] iniciado em {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return arquivo


def registrar_erro(contexto: str = "") -> None:
    """Grava o erro que esta sendo tratado agora (chame dentro de um 'except')."""
    if contexto:
        print(f"[erro] {contexto}")
    print(traceback.format_exc().rstrip())


def abrir_pasta(pasta: Path = ARQUIVO_LOG.parent) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    os.startfile(pasta)  # type: ignore[attr-defined]  # so existe no Windows
