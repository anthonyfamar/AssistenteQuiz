# CONFIG - todas as configuracoes num lugar so.
#
# Guarda: seletores CSS do site (enunciado, alternativas), intervalo do polling,
# provedor de IA e modelo. A API key NAO fica aqui: fica no .env.
#
# TODO: preencher os seletores quando o site for escolhido
#       (F12 -> Inspecionar -> botao direito -> Copy -> Copy selector).
from dataclasses import dataclass
from pathlib import Path

SELETOR_ENUNCIADO = "#enunciado"
SELETOR_ALTERNATIVAS = "#alternativas .alternativa"

INTERVALO_POLLING = 1.0 

RAIZ = Path(__file__).resolve().parents[2]
URL_INICIAL = (RAIZ / "demo" / "quiz_local.html").as_uri()


# Um provedor de IA gratuito. chave_env e modelo_env sao NOMES de variaveis do .env
# (a chave em si nunca aparece no codigo).
# so_free = so aceita modelo terminado em ":free" (trava para nao gastar).
@dataclass(frozen=True)
class Provedor:
    nome: str
    base_url: str
    chave_env: str
    modelo_env: str
    so_free: bool = False


PROVEDORES = {
    "gemini": Provedor(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
    ),
    "groq": Provedor(
        "groq",
        "https://api.groq.com/openai/v1",
        "GROQ_API_KEY",
        "GROQ_MODEL",
    ),
    "openrouter": Provedor(
        "openrouter",
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        so_free=True,
    ),
    "ollama-cloud": Provedor(
        "ollama-cloud",
        "https://ollama.com/v1",
        "OLLAMA_API_KEY",
        "OLLAMA_CLOUD_MODEL",
    ),
}

ORDEM_PADRAO = "gemini,groq,openrouter,ollama-cloud"
TIMEOUT_API = 20.0
COOLDOWN_PROVEDOR = 60.0