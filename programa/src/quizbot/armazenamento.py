# ARMAZENAMENTO - onde a memoria fica guardada (e como ela viaja entre os PCs).
#
# Armazenamento (ABC) -> o contrato: ler_todos() e gravar(dados).
#                        Os "dados" sao um dicionario  chave-da-questao -> entrada, onde
#                        a entrada e {"enunciado": ..., "erradas": [...], "certa": ...}.
#                        A Memoria so conhece este contrato, nao sabe onde os dados ficam.
#  |- ArmazenamentoLocal     -> uma pasta no PC: um arquivo "memoria-<PC>.json" por maquina.
#  |- ArmazenamentoFirestore -> o banco na nuvem (Firebase/Firestore): UM documento so,
#                               memoria/geral, que todos os PCs leem e atualizam.
#                               Entra com e-mail e senha (a senha vem do .env) e fala com
#                               o Firestore pela API REST; nao precisa de arquivo de chave
#                               nem de biblioteca extra (usa so o urllib do Python).
#                               Para dois PCs nao se atropelarem, gravar() le o documento,
#                               junta com o que ja tinha la e so grava se ninguem mudou o
#                               documento nesse meio tempo (senao, repete).
#  |- ArmazenamentoEspelhado -> usa os dois: grava no local e na nuvem (um nao depende do
#                               outro). Se a nuvem falhar, o que ficou so no local sobe
#                               sozinho na proxima leitura (ao abrir e a cada 5 minutos):
#                               o que o local sabe e a nuvem nao e enviado.
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

PREFIXO_ARQUIVO = "memoria-"
COLECAO = "memoria"
DOCUMENTO = "geral"
TIMEOUT_NUVEM = 10.0
TENTATIVAS_GRAVAR = 4
URL_LOGIN = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
URL_FIRESTORE = "https://firestore.googleapis.com/v1"
_SENHA_ERRADA = {"INVALID_PASSWORD", "EMAIL_NOT_FOUND", "INVALID_LOGIN_CREDENTIALS"}

# Um "transporte" faz um pedido HTTP e devolve (codigo, json). O padrao usa o urllib; nos
# testes entra um falso, para nao depender da internet.
Transporte = Callable[[str, str, dict, "dict | None"], "tuple[int, dict]"]


class NuvemError(Exception):
    """Falha esperada ao falar com a nuvem (senha errada, regras do banco, sem internet)."""


class ConflitoNuvem(NuvemError):
    """O documento mudou entre a leitura e a gravacao (outro PC gravou no meio)."""


def _enviar_urllib(metodo: str, url: str, cabecalhos: dict, corpo: dict | None) -> tuple[int, dict]:
    pedido = urllib.request.Request(
        url,
        data=None if corpo is None else json.dumps(corpo).encode("utf-8"),
        method=metodo,
        headers={"Content-Type": "application/json", **cabecalhos},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_NUVEM) as resposta:
            texto = resposta.read().decode("utf-8")
            return resposta.status, (json.loads(texto) if texto else {})
    except urllib.error.HTTPError as erro:  # o servidor respondeu, com um codigo de erro
        try:
            return erro.code, json.loads(erro.read().decode("utf-8"))
        except ValueError:
            return erro.code, {}
    except (urllib.error.URLError, TimeoutError, OSError) as erro:
        raise NuvemError(f"sem conexao com a nuvem ({erro})") from erro


def juntar_entradas(a: dict, b: dict) -> dict:
    """Junta duas entradas da mesma questao. Se a certa e conhecida, as erradas somem."""
    certa = a.get("certa") or b.get("certa")
    erradas = [] if certa else list(dict.fromkeys([*a.get("erradas", []), *b.get("erradas", [])]))
    entrada = {"enunciado": a.get("enunciado") or b.get("enunciado") or "", "erradas": erradas}
    if certa:
        entrada["certa"] = certa
    return entrada


def juntar_dados(a: dict, b: dict) -> dict:
    """Junta dois conjuntos de dados (chave -> entrada), sem perder nada de nenhum."""
    return {
        chave: juntar_entradas(a.get(chave, {}), b.get(chave, {})) for chave in {*a, *b}
    }


def nome_seguro(nome: str) -> str:
    """Nome do PC servindo de nome de arquivo (so letras, numeros, - e _)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", nome).strip("_") or "PC"


class Armazenamento(ABC):
    @abstractmethod
    def ler_todos(self) -> dict[str, dict]:
        """Devolve  nome-da-fonte -> dados  de tudo que esta guardado."""

    @abstractmethod
    def gravar(self, dados: dict) -> bool:
        """Grava os dados deste PC (sem perder o que ja estava guardado por outros).

        Devolve True se chegou em TODOS os destinos; False se chegou so em alguns.
        Levanta erro (OSError/NuvemError) se nao chegou em NENHUM."""


class ArmazenamentoLocal(Armazenamento):
    def __init__(self, pasta: Path, nome: str) -> None:
        self._pasta = pasta
        self._nome = nome_seguro(nome)

    @property
    def _arquivo(self) -> Path:
        return self._pasta / f"{PREFIXO_ARQUIVO}{self._nome}.json"

    def ler_todos(self) -> dict[str, dict]:
        todos: dict[str, dict] = {}
        for arquivo in self._pasta.glob(f"{PREFIXO_ARQUIVO}*.json"):
            try:
                dados = json.loads(arquivo.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(dados, dict):
                todos[arquivo.stem.removeprefix(PREFIXO_ARQUIVO)] = dados
        return todos

    def gravar(self, dados: dict) -> bool:
        self._pasta.mkdir(parents=True, exist_ok=True)
        temporario = self._arquivo.with_suffix(".tmp")
        temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporario, self._arquivo)
        return True


class ArmazenamentoFirestore(Armazenamento):
    """Um documento so, memoria/geral, com os dados guardados como texto JSON."""

    def __init__(
        self,
        projeto: str,
        chave_api: str,
        email: str,
        senha: str,
        transporte: Transporte | None = None,
    ) -> None:
        self._projeto = projeto
        self._chave_api = chave_api
        self._email = email
        self._senha = senha
        self._enviar = transporte or _enviar_urllib
        self._token: str | None = None
        self._vence_em = 0.0

    @property
    def _url_documento(self) -> str:
        base = f"{URL_FIRESTORE}/projects/{self._projeto}/databases/(default)/documents"
        return f"{base}/{COLECAO}/{DOCUMENTO}"

    def _entrar(self) -> None:
        url = f"{URL_LOGIN}?{urllib.parse.urlencode({'key': self._chave_api})}"
        codigo, dados = self._enviar(
            "POST", url, {}, {"email": self._email, "password": self._senha, "returnSecureToken": True}
        )
        if codigo != 200:
            motivo = _motivo(codigo, dados)
            if motivo in _SENHA_ERRADA:
                raise NuvemError("senha da memoria incorreta")
            raise NuvemError(f"login recusado ({motivo})")
        self._token = dados["idToken"]
        self._vence_em = time.monotonic() + int(dados.get("expiresIn", 3600)) - 60

    def _cabecalho(self) -> dict[str, str]:
        if self._token is None or time.monotonic() >= self._vence_em:
            self._entrar()
        return {"Authorization": f"Bearer {self._token}"}

    def _pedir(
        self, metodo: str, url: str, corpo: dict | None = None, aceitar: tuple[int, ...] = ()
    ) -> tuple[int, dict]:
        codigo, dados = self._enviar(metodo, url, self._cabecalho(), corpo)
        if codigo == 401:  # token recusado: entra de novo, uma vez so
            self._token = None
            codigo, dados = self._enviar(metodo, url, self._cabecalho(), corpo)
        if codigo < 400 or codigo in aceitar:
            return codigo, dados
        motivo = _motivo(codigo, dados)
        if codigo == 403:
            raise NuvemError("o banco recusou o acesso (confira as regras do Firestore)")
        if codigo == 409 or "FAILED_PRECONDITION" in motivo or "ALREADY_EXISTS" in motivo:
            raise ConflitoNuvem(motivo)
        raise NuvemError(f"a nuvem respondeu com erro ({motivo})")

    def _ler_documento(self) -> tuple[dict, str | None]:
        """Devolve (dados, hora da ultima mudanca). Documento inexistente: ({}, None)."""
        codigo, documento = self._pedir("GET", self._url_documento, aceitar=(404,))
        if codigo == 404:
            return {}, None
        texto = documento.get("fields", {}).get("questoes", {}).get("stringValue", "{}")
        try:
            conteudo = json.loads(texto)
        except ValueError:
            conteudo = {}
        return (conteudo if isinstance(conteudo, dict) else {}), documento.get("updateTime")

    def ler_todos(self) -> dict[str, dict]:
        conteudo, hora = self._ler_documento()
        return {DOCUMENTO: conteudo} if hora is not None else {}

    def gravar(self, dados: dict) -> bool:
        for _ in range(TENTATIVAS_GRAVAR):
            atual, hora = self._ler_documento()
            # So grava se o documento continua como foi lido (ou continua sem existir).
            condicao = (
                {"currentDocument.updateTime": hora} if hora else {"currentDocument.exists": "false"}
            )
            corpo = {
                "fields": {
                    "questoes": {"stringValue": json.dumps(juntar_dados(atual, dados), ensure_ascii=False)}
                }
            }
            try:
                self._pedir("PATCH", f"{self._url_documento}?{urllib.parse.urlencode(condicao)}", corpo)
                return True
            except ConflitoNuvem:
                continue  # outro PC gravou no meio: le de novo e junta de novo
        raise NuvemError("outro PC estava gravando ao mesmo tempo; tente de novo")


def _motivo(codigo: int, dados: dict) -> str:
    try:
        return str(dados["error"]["message"]).split(" ")[0]
    except (KeyError, TypeError):
        return f"HTTP {codigo}"


class ArmazenamentoEspelhado(Armazenamento):
    def __init__(self, local: Armazenamento, remoto: Armazenamento) -> None:
        self._local = local
        self._remoto = remoto
        self.erro_nuvem: str | None = None

    def ler_todos(self) -> dict[str, dict]:
        todos = self._local.ler_todos()
        try:
            na_nuvem = self._remoto.ler_todos()
        except Exception as erro:  # a rede e os servicos do Google falham de muitas formas
            self._avisar(erro)
            return todos
        self.erro_nuvem = None
        self._subir_o_que_falta(todos, na_nuvem)
        for nome, dados in na_nuvem.items():
            todos[nome] = juntar_dados(todos.get(nome, {}), dados)
        return todos

    def _subir_o_que_falta(self, locais: dict[str, dict], nuvem: dict[str, dict]) -> None:
        """Se o arquivo local sabe algo que a nuvem nao sabe (ex.: a nuvem estava fora do ar
        na hora de gravar), sobe agora. So grava se houver diferenca de verdade."""
        nosso: dict = {}
        for dados in locais.values():
            nosso = juntar_dados(nosso, dados)
        la: dict = {}
        for dados in nuvem.values():
            la = juntar_dados(la, dados)
        if juntar_dados(la, nosso) == la:
            return
        try:
            self._remoto.gravar(nosso)
        except Exception as erro:
            self._avisar(erro)

    def gravar(self, dados: dict) -> bool:
        # Tenta os dois destinos, um nao depende do outro. So levanta erro se NENHUM guardou.
        erro_local: OSError | None = None
        try:
            self._local.gravar(dados)
        except OSError as erro:
            erro_local = erro
            print(f"[memoria] nao consegui gravar o arquivo local ({erro})")
        try:
            self._remoto.gravar(dados)
        except Exception as erro:
            self._avisar(erro)
            if erro_local is not None:
                raise erro_local
            return False  # ficou no local; _subir_o_que_falta leva para a nuvem depois
        self.erro_nuvem = None
        return erro_local is None

    def _avisar(self, erro: Exception) -> None:
        mensagem = f"{type(erro).__name__}: {str(erro)[:150]}"
        if mensagem != self.erro_nuvem:
            print(f"[memoria] sem acesso a nuvem, usando so o arquivo local ({mensagem})")
        self.erro_nuvem = mensagem
