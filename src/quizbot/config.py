# CONFIG - todas as configuracoes num lugar so.
#
# Guarda: seletores CSS do site (enunciado, alternativas), intervalo do polling,
# provedor de IA e modelo. A API key NAO fica aqui: fica no .env.
#
# Os seletores abaixo sao do Moodle. Para outro site: F12 -> Inspecionar -> achar
# o bloco da questao -> usar classes estaveis (nunca ids gerados a cada acesso).
import os
from dataclasses import dataclass
from pathlib import Path

# Seletores do Moodle (AVAEDUC). Para o demo/quiz_local.html, use
# "#enunciado" e "#alternativas .alternativa".
SELETOR_ENUNCIADO = ".que .qtext"
SELETOR_ALTERNATIVAS = ".que .answer label"

# Tira o "a. " ou "b) " do comeco de cada alternativa (o presenter ja poe as letras).
PADRAO_PREFIXO_ALTERNATIVA = r"^[a-zA-Z][.)]\s+"

INTERVALO_POLLING = 1.0 

# Chrome do assistente: aberto com a porta de depuracao e um perfil separado, fora
# do projeto (guarda o login do usuario). O programa abre o Chrome se precisar.
PORTA_DEBUG = 9222
URL_CDP = f"http://localhost:{PORTA_DEBUG}"
PERFIL_CHROME = Path.home() / "chrome-assistente"
CAMINHOS_CHROME = (
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
)


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