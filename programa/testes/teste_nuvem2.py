import json
import os
import sys
import tempfile
import urllib.parse
from pathlib import Path

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import dotenv_values

from quizbot.armazenamento import (
    URL_LOGIN,
    ArmazenamentoEspelhado,
    ArmazenamentoFirestore,
    ArmazenamentoLocal,
    NuvemError,
)
from quizbot.memoria import Memoria
from quizbot.models import Question, Resultado

DOC = "https://firestore.googleapis.com/v1/projects/proj/databases/(default)/documents/memoria/geral"
estado = {"doc": None, "versao": 0, "logins": 0, "expira": "3600", "rejeitar_uma_vez": False,
          "bloquear": False, "corrida": None, "patches": 0, "gets": 0}


def guardar(conteudo):
    estado["versao"] += 1
    estado["doc"] = {"questoes": json.dumps(conteudo, ensure_ascii=False)}


def servidor(metodo, url, cabecalhos, corpo):
    """Transporte falso: imita o login do Firebase e o documento memoria/geral."""
    parsed = urllib.parse.urlparse(url)
    params = dict(urllib.parse.parse_qsl(parsed.query))
    if url.startswith(URL_LOGIN):
        assert params["key"] == "CHAVE" and corpo["email"] == "m@x.app"
        estado["logins"] += 1
        if corpo["password"] != "s3nha":
            return 400, {"error": {"message": "INVALID_LOGIN_CREDENTIALS"}}
        return 200, {"idToken": f"tok{estado['logins']}", "expiresIn": estado["expira"]}
    assert cabecalhos["Authorization"].startswith("Bearer tok")
    if estado["rejeitar_uma_vez"]:
        estado["rejeitar_uma_vez"] = False
        return 401, {}
    if estado["bloquear"]:
        return 403, {"error": {"message": "PERMISSION_DENIED"}}
    assert url.split("?")[0] == DOC, url  # nunca fala com outro documento
    if metodo == "GET":
        estado["gets"] += 1
        if estado["doc"] is None:
            return 404, {"error": {"message": "NOT_FOUND"}}
        return 200, {"name": "x/memoria/geral", "updateTime": f"t{estado['versao']}",
                     "fields": {"questoes": {"stringValue": estado["doc"]["questoes"]}}}
    if metodo == "PATCH":
        estado["patches"] += 1
        if estado["corrida"] is not None:  # outro PC grava entre a leitura e a gravacao
            outro, estado["corrida"] = estado["corrida"], None
            atual = json.loads(estado["doc"]["questoes"]) if estado["doc"] else {}
            guardar({**atual, **outro})
        if "currentDocument.exists" in params and estado["doc"] is not None:
            return 409, {"error": {"message": "ALREADY_EXISTS"}}
        if "currentDocument.updateTime" in params and params["currentDocument.updateTime"] != f"t{estado['versao']}":
            return 400, {"error": {"message": "FAILED_PRECONDITION: the document was changed"}}
        guardar(json.loads(corpo["fields"]["questoes"]["stringValue"]))
        return 200, {}
    return 404, {}


def nuvem(senha="s3nha"):
    return ArmazenamentoFirestore("proj", "CHAVE", "m@x.app", senha, servidor)


def entrada(*erradas, certa=None, enun="Q"):
    e = {"enunciado": enun, "erradas": [] if certa else list(erradas)}
    if certa:
        e["certa"] = certa
    return e


# senha errada -> erro claro
try:
    nuvem("errada").ler_todos(); raise AssertionError("devia falhar")
except NuvemError as erro:
    assert "senha" in str(erro), erro
# banco vazio -> nada; grava (cria) e le de volta, acentos preservados, entrando UMA vez so
n = nuvem()
assert n.ler_todos() == {}
n.gravar({"k1": entrada(certa="ação")})
assert n.ler_todos() == {"geral": {"k1": entrada(certa="ação")}}
assert estado["logins"] == 2, estado["logins"]  # 1 da senha errada + 1 desta sessao
# gravar de novo JUNTA com o que ja estava la (nao apaga o aprendizado de outro PC)
n.gravar({"k2": entrada("x")})
assert json.loads(estado["doc"]["questoes"]) == {"k1": entrada(certa="ação"), "k2": entrada("x")}
# token vencido: entra de novo sozinho
estado["expira"] = "30"; n2 = nuvem(); estado["logins"] = 0
n2.ler_todos(); n2.ler_todos()
assert estado["logins"] == 2; estado["expira"] = "3600"
# 401 uma vez
n3 = nuvem(); n3.ler_todos(); estado["logins"] = 0; estado["rejeitar_uma_vez"] = True
assert "geral" in n3.ler_todos() and estado["logins"] == 1
# regras bloqueando
estado["bloquear"] = True
try:
    nuvem().ler_todos(); raise AssertionError("devia falhar")
except NuvemError as erro:
    assert "regras" in str(erro), erro
estado["bloquear"] = False
print("cliente da nuvem ok")

# DOIS PCs gravando ao mesmo tempo: ninguem perde nada
guardar({"base": entrada("b")})
estado["corrida"] = {"do_outro_pc": entrada("o")}  # o outro PC grava no meio da gravacao
nuvem().gravar({"meu": entrada("m")})
final = json.loads(estado["doc"]["questoes"])
assert set(final) == {"base", "do_outro_pc", "meu"}, final
# corrida com o documento ainda inexistente
estado["doc"] = None; estado["versao"] = 0
estado["corrida"] = {"outro": entrada("o")}
nuvem().gravar({"meu": entrada("m")})
assert set(json.loads(estado["doc"]["questoes"])) == {"outro", "meu"}
print("gravacao simultanea ok")

# memoria completa: um PC aprende, o outro (sem arquivo nenhum) usa; senha errada nao quebra
estado["doc"] = None; estado["versao"] = 0
q = Question("Cinco?", ("a1", "b1", "c1"))
pastas = [Path(tempfile.mkdtemp()) for _ in range(3)]
m1 = Memoria(ArmazenamentoEspelhado(ArmazenamentoLocal(pastas[0], "PC1"), nuvem()), "PC1")
assert m1.registrar(q, 0, False)
m2 = Memoria(ArmazenamentoEspelhado(ArmazenamentoLocal(pastas[1], "PC2"), nuvem()), "PC2")
assert m2.erradas(q) == {"a1"}
assert m2.registrar(q, 1, False)
m1.atualizar()
assert m1.erradas(q) == {"a1", "b1"}
assert m2.registrar(q, 2, True)  # achou a certa: as erradas somem do documento geral
m3 = Memoria(ArmazenamentoEspelhado(ArmazenamentoLocal(pastas[2], "PC3"), nuvem()), "PC3")
assert m3.certa(q) == "c1" and m3.erradas(q) == frozenset()
doc_final = json.loads(estado["doc"]["questoes"])
(unica,) = doc_final.values()
assert unica["erradas"] == [] and unica["certa"] == "c1", doc_final
m4 = Memoria(ArmazenamentoEspelhado(ArmazenamentoLocal(Path(tempfile.mkdtemp()), "PC4"), nuvem("ERRADA")), "PC4")
assert m4.erradas(q) == frozenset() and m4.registrar(q, 1, False)  # segue so local
print("memoria sobre a nuvem ok")

# um salvamento normal = uma gravacao
estado["patches"] = 0
m5 = Memoria(ArmazenamentoEspelhado(ArmazenamentoLocal(Path(tempfile.mkdtemp()), "PC5"), nuvem()), "PC5")
lote = [Resultado(Question(f"Q{i}?", ("x", "y", "z")), i % 3, i not in (2, 7)) for i in range(10)]
m5.registrar_revisao(lote)
assert estado["patches"] == 1, estado["patches"]
print("lote = 1 gravacao ok")

# .env e janela
from quizbot.configurar import JanelaConfiguracao, valor_env

env = Path(tempfile.mkdtemp()) / ".env"
for senha in ["abc123", "pa#ss w0rd", "a'b\"c", "x\\y\\\\z", "#$%&*()=+[]{};:,.<>?/|`~!@", "ação-ü"]:
    env.write_text(f"MEMORIA_SENHA={valor_env(senha)}\n", encoding="utf-8")
    assert dotenv_values(env)["MEMORIA_SENHA"] == senha
print("valor_env ok")

env.write_text("AUTOMATICO=sim\nAUTOMATICO_FINALIZAR=nao\nNOME_PC=NOTEBOOK\n", encoding="utf-8")
try:
    janela = JanelaConfiguracao(env)
except Exception as erro:
    print("janela nao testada:", type(erro).__name__)
else:
    janela._chaves["gemini"].set("chaveGemini123"); janela._senha.set("pa#ss'w\\rd"); janela._salvar()
    lido = dotenv_values(env)
    assert lido["MEMORIA_SENHA"] == "pa#ss'w\\rd" and lido["NOME_PC"] == "NOTEBOOK"
    assert "AUTOMATICO" not in lido and "AUTOMATICO_FINALIZAR" not in lido, lido  # chaves antigas somem
    print("janela ok")

import quizbot.main as M
os.environ.pop("MEMORIA_SENHA", None)
assert isinstance(M._montar_memoria()._armazenamento, ArmazenamentoLocal)
os.environ["MEMORIA_SENHA"] = "qualquer"
assert isinstance(M._montar_memoria()._armazenamento, ArmazenamentoEspelhado)
print("TUDO OK")
