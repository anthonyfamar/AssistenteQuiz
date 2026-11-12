# TESTE - a lista de provedores: so entram os que tem API GRATIS de verdade.
#
# Ollama Cloud (erro 402) e Mistral (a documentacao oficial diz que o plano gratuito nao inclui a API)
# foram retirados. Confere: o catalogo; a ordem montada pela fabrica (principal, reservas, proximo
# provedor); o aviso quando um .env antigo ainda cita um provedor retirado; e a janela de configuracao
# (tira os retirados da ordem e do arquivo, poe na ordem o provedor que ganhou chave).
import io
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import dotenv_values

from quizbot.config import ORDEM_PADRAO, PROVEDORES, PROVEDORES_REMOVIDOS
from quizbot.solvers import fabrica

# ---------- catalogo ----------
assert set(PROVEDORES) == {"gemini", "groq", "openrouter"}, list(PROVEDORES)
assert set(PROVEDORES_REMOVIDOS) == {"ollama-cloud", "mistral"}
assert not set(PROVEDORES) & set(PROVEDORES_REMOVIDOS)
assert "402" in PROVEDORES_REMOVIDOS["ollama-cloud"] and "API" in PROVEDORES_REMOVIDOS["mistral"]
assert ORDEM_PADRAO == "gemini,groq,openrouter"
assert set(ORDEM_PADRAO.split(",")) == set(PROVEDORES), (ORDEM_PADRAO, list(PROVEDORES))
print("catalogo: so Gemini, Groq e OpenRouter; Ollama e Mistral retirados (com o motivo) ok")

# ---------- fabrica ----------
tmp = pathlib.Path(tempfile.mkdtemp()) / "vazio.env"
tmp.write_text("")
fabrica.ARQUIVO_ENV = tmp  # nenhum .env de verdade e lido neste teste
for k in list(os.environ):
    if k.startswith(("GEMINI_", "GROQ_", "OPENROUTER_", "MISTRAL_", "OLLAMA_")) or k == "ORDEM_PROVEDORES":
        del os.environ[k]
os.environ.update({
    "GROQ_API_KEY": "chave-groq-falsa-1234567", "GROQ_MODEL": "openai/gpt-oss-120b",
    "OPENROUTER_API_KEY": "chave-openrouter-falsa-1234567",
    "OPENROUTER_MODEL": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "OPENROUTER_MODEL_VISAO": "nvidia/nemotron-3.5-super-vl:free",
    "ORDEM_PROVEDORES": "groq,openrouter",
})
saida = io.StringIO()
with redirect_stdout(saida):
    fb = fabrica.montar_solver()
ordem = [s.descricao for s in fb._solvers]
assert ordem[:4] == ["groq (openai/gpt-oss-120b)", "groq (qwen/qwen3.8-27b)", "groq (openai/gpt-oss-20b)",
                     "openrouter (nvidia/nemotron-3-ultra-550b-a55b:free)"], ordem
assert [s.apelido for s in fb._solvers] == ["Groq"] * 3 + ["OpenRouter"] * (len(ordem) - 3)
assert all(s.fator_de_espera == 1.0 for s in fb._solvers[:3])
assert all(s.fator_de_espera == 2.0 for s in fb._solvers[3:])  # modelos que pensam devagar: mais tempo
assert "falsa" not in saida.getvalue()  # nenhuma chave impressa
print("fabrica: groq (principal, qwen, gpt-oss-20b) > openrouter (com mais tempo de espera) ok")

# imagem: o gpt-oss-20b NAO enxerga, mesmo com o provedor tendo modelo de visao; o qwen enxerga
os.environ["GROQ_MODEL_VISAO"] = "qwen/qwen3.8-27b"
with redirect_stdout(io.StringIO()):
    fb_visao = fabrica.montar_solver()
visao = {s.descricao: s.aceita_imagens for s in fb_visao._solvers[:3]}
assert visao == {"groq (openai/gpt-oss-120b)": True, "groq (qwen/qwen3.8-27b)": True, "groq (openai/gpt-oss-20b)": False}, visao
del os.environ["GROQ_MODEL_VISAO"]
print("imagem: 120b (via qwen) e qwen enxergam; o gpt-oss-20b (so texto) nunca recebe imagem ok")

# .env antigo que ainda cita provedores retirados: aviso claro, sem derrubar nada
os.environ["ORDEM_PROVEDORES"] = "groq,ollama-cloud,mistral,inventado,openrouter"
saida = io.StringIO()
with redirect_stdout(saida):
    fb = fabrica.montar_solver()
texto = saida.getvalue()
assert "'ollama-cloud' foi retirado do programa" in texto and "erro 402" in texto, texto
assert "'mistral' foi retirado do programa" in texto and "cobranca" in texto, texto
assert "provedor desconhecido em ORDEM_PROVEDORES: 'inventado'" in texto, texto
assert {s.nome for s in fb._solvers} == {"groq", "openrouter"} and fb._solvers[0].nome == "groq"
print("ordem antiga: aviso explica por que foram retirados; nome inventado continua avisando ok")

# ---------- janela de configuracao ----------
from quizbot.configurar import JanelaConfiguracao

env = pathlib.Path(tempfile.mkdtemp()) / ".env"
env.write_text(
    "ORDEM_PROVEDORES=gemini,groq,mistral,ollama-cloud\r\n"
    "GEMINI_API_KEY=chaveG\r\nGEMINI_MODEL=gemini-3.8-flash\r\nGEMINI_MODEL_VISAO=gemini-3.8-flash\r\n"
    "MISTRAL_API_KEY=chaveM\r\nMISTRAL_MODEL=mistral-large-latest\r\n"
    "OLLAMA_API_KEY=chaveO\r\nOLLAMA_CLOUD_MODEL=gemma4:31b\r\nOLLAMA_CLOUD_MODEL_VISAO=\r\n"
    "NOME_PC=NOTEBOOK\r\n",
    encoding="utf-8",
)
try:
    janela = JanelaConfiguracao(env)
except Exception as erro:
    print("janela nao testada:", type(erro).__name__)
else:
    janela._chaves["openrouter"].set("chaveR123")
    janela._salvar()
    lido = dotenv_values(env)
    ordem = lido["ORDEM_PROVEDORES"].split(",")
    assert ordem == ["gemini", "groq", "openrouter"], ordem  # retirados fora; o que ganhou chave entrou
    proibidas = [k for k in lido if k.startswith(("OLLAMA_", "MISTRAL_"))]
    assert not proibidas, proibidas
    assert lido["OPENROUTER_API_KEY"] == "chaveR123" and lido["GEMINI_API_KEY"] == "chaveG" and lido["NOME_PC"] == "NOTEBOOK"
    print("janela: tirou Ollama e Mistral da ordem e do arquivo, poe na ordem o provedor que ganhou chave ok")
print("TUDO OK")
