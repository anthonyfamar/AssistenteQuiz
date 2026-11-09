# CONFIG - todas as configuracoes num lugar so.
#
# Guarda: seletores CSS do site (enunciado, alternativas), intervalo do polling,
# provedor de IA e modelo. A API key NAO fica aqui: fica no .env.
#
# Os seletores abaixo sao do Moodle. Para outro site: F12 -> Inspecionar -> achar
# o bloco da questao -> usar classes estaveis (nunca ids gerados a cada acesso).
import os
import socket
from dataclasses import dataclass
from pathlib import Path

# Pasta "programa" (onde ficam src/, requirements.txt e o .env). Este arquivo esta em
# programa/src/quizbot/config.py. O .env fica sempre aqui, e todo o programa usa este caminho.
PASTA_PROGRAMA = Path(__file__).resolve().parents[2]
ARQUIVO_ENV = PASTA_PROGRAMA / ".env"

# Seletores do Moodle.
SELETOR_ENUNCIADO = ".que .qtext"
SELETOR_ALTERNATIVAS = ".que .answer label"
# Bolinhas (radio) das alternativas, na ordem da tela. O id e o name mudam a cada
# tentativa e a cada questao, entao a alternativa e escolhida pela POSICAO.
SELETOR_RADIOS = ".que .answer input[type=radio]"
# Botao de avancar de pagina do Moodle.
SELETOR_BOTAO_PROXIMA = "input.mod_quiz-next-nav"
# Pagina de REVISAO (depois de enviar): cada bloco de questao e o que o Moodle marca como
# certo/errado. O Moodle poe a classe "correct" ou "incorrect" na linha da alternativa
# que foi marcada (so nela); as outras ficam sem classe e a resposta certa nao aparece.
SELETOR_QUESTAO = ".que"
SELETOR_MARCADAS = ".que .answer .correct, .que .answer .incorrect"
CLASSE_CORRETA = "correct"
# Finalizar a tentativa (so na pagina de resumo). Os ids mudam a cada acesso:
# o botao da pagina e achado pelo texto, e o da janelinha pelo comeco do id.
TEXTO_BOTAO_FINALIZAR = "Enviar tudo e terminar"
SELETOR_CONFIRMAR_FINALIZAR = 'input[id^="id_yuiconfirmyes"]'

# Terminar a revisao (so na pagina de revisao). E um <a>, nao um <input>: o seletor
# "a." deixa de confundir com o botao "Proxima pagina", que tem a mesma classe.
SELETOR_BOTAO_TERMINAR_REVISAO = "a.mod_quiz-next-nav"
TEXTO_BOTAO_TERMINAR_REVISAO = "Terminar revisão"

# Pagina INICIAL do quiz (as tentativas). Os botoes tem ids que mudam a cada acesso, entao
# cada um e achado pelo texto. O programa decide pelo que a pagina mostra, sem contar
# tentativas no codigo: o limite vem do proprio Moodle.
SELETOR_TABELA_TENTATIVAS = "table.quizattemptsummary"
TEXTO_BOTAO_COMECAR = "Tentar responder o questionário agora"  # nenhuma tentativa ainda
TEXTO_BOTAO_CONTINUAR = "Continuar a última tentativa"  # saiu no meio e abriu de novo
TEXTO_BOTAO_OUTRA = "Fazer uma outra tentativa"
TEXTO_SEM_MAIS_TENTATIVAS = "Não são permitidas outras tentativas"
TEXTO_BOTAO_VOLTAR = "Voltar ao curso"
# Ao acabar as tentativas, quantos segundos mostrar a nota antes de voltar ao curso.
PAUSA_ANTES_DE_VOLTAR = 20.0

# Tira o "a. " ou "b) " do comeco de cada alternativa (o presenter ja poe as letras).
PADRAO_PREFIXO_ALTERNATIVA = r"^[a-zA-Z][.)]\s+"

INTERVALO_POLLING = 0.5

# Modo automatico: segundos de espera depois de marcar a alternativa e antes de avancar
# (da tempo de ver a marca na tela).
PAUSA_APOS_CLICAR = 1.0

# Memoria (respostas certas e erradas): tudo fica na pasta do usuario, fora do projeto e do
# Git, ao lado do ambiente do instalador. Cada PC grava so o seu arquivo (memoria-<PC>.json).
# Apague a pasta para recomecar.
PASTA_USUARIO = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "AssistenteQuiz"
PASTA_MEMORIA = PASTA_USUARIO / "memoria"
NOME_PC = socket.gethostname()  # pode ser trocado com NOME_PC no .env
# Registro (log): tudo que o programa conta fica em assistente.log, na pasta do usuario. A cada
# execucao o arquivo recomeca e o anterior vira assistente.log.1, para nao crescer sem parar.
PASTA_LOGS = PASTA_USUARIO / "logs"
ARQUIVO_LOG = PASTA_LOGS / "assistente.log"
# Tela de escolha do modo: segundos ate comecar sozinho no Automatico.
PAUSA_ESCOLHA = 30
# Nuvem (Firebase/Firestore, plano gratuito Spark). O programa entra no banco com um
# usuario unico (e-mail abaixo) e a SENHA, que fica so no .env de cada PC (MEMORIA_SENHA).
# A "chave da API web" abaixo e PUBLICA por desenho: so identifica o projeto. Quem protege
# o banco sao o login e as regras do Firestore, entao ela pode ficar no codigo.
FIREBASE_PROJETO = "assistentequiz-853a4"
FIREBASE_CHAVE_API = "AIzaSyDfEJ2gMArPdrQCTzhAuqhAHUCgjbmgl-k"
MEMORIA_EMAIL = "memoria@assistentequiz.app"
# De quanto em quanto tempo (segundos) a memoria relê o que os outros PCs aprenderam.
# Cada leitura gasta so 1 leitura por PC das 50 mil diarias do plano gratuito.
INTERVALO_SINCRONIA = 300.0
# Se a gravacao na nuvem falhar, de quanto em quanto tempo (segundos) tentar de novo.
INTERVALO_REGRAVAR = 10.0

# Navegador do assistente: Chrome (ou o Edge, que ja vem no Windows), aberto com a porta
# de depuracao e um perfil separado, fora do projeto (guarda o login do usuario).
# O programa abre o navegador se precisar. Para indicar o caminho na mao, ponha
# CAMINHO_NAVEGADOR no .env (a janela de configuracao faz isso).
PORTA_DEBUG = 9222
URL_CDP = f"http://localhost:{PORTA_DEBUG}"
PERFIL_NAVEGADOR = Path.home() / "chrome-assistente"
CAMINHOS_NAVEGADOR = (
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
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
    modelo_visao_env: str
    so_free: bool = False
    max_imagens: int = 5
    rotulo: str = ""
    dica: str = ""
    url_chave: str = ""
    modelo_sugerido: str = ""
    modelo_visao_sugerido: str = ""


# modelo_visao_env = modelo usado nas questoes COM imagem (precisa enxergar). Se ficar
# vazio no .env, o provedor so e usado em questoes sem imagem.
# max_imagens = limite de imagens por pedido que o provedor aceita.
# rotulo, dica, url_chave e os modelos sugeridos alimentam a janela de configuracao
# (configurar.py). Os nomes de modelo mudam com o tempo: a janela deixa editar.
PROVEDORES = {
    "gemini": Provedor(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "GEMINI_MODEL_VISAO",
        rotulo="Gemini (Google)",
        dica="Recomendado e gratuito. Basta ter uma conta Google. Esta chave ja e suficiente.",
        url_chave="https://aistudio.google.com/apikey",
        modelo_sugerido="gemini-3.8-flash",
        modelo_visao_sugerido="gemini-3.8-flash",
    ),
    "groq": Provedor(
        "groq",
        "https://api.groq.com/openai/v1",
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "GROQ_MODEL_VISAO",
        max_imagens=3,
        rotulo="Groq",
        dica="Opcional (reserva). Gratuito.",
        url_chave="https://console.groq.com/keys",
        modelo_sugerido="openai/gpt-oss-120b",
        modelo_visao_sugerido="qwen/qwen3.8-27b",
    ),
    "openrouter": Provedor(
        "openrouter",
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        "OPENROUTER_MODEL_VISAO",
        so_free=True,
        rotulo="OpenRouter",
        dica="Opcional (reserva). Use so modelos terminados em :free e nao compre creditos.",
        url_chave="https://openrouter.ai/keys",
        modelo_sugerido="google/gemma-4-31b-it:free",
        modelo_visao_sugerido="google/gemma-4-31b-it:free",
    ),
    "ollama-cloud": Provedor(
        "ollama-cloud",
        "https://ollama.com/v1",
        "OLLAMA_API_KEY",
        "OLLAMA_CLOUD_MODEL",
        "OLLAMA_CLOUD_MODEL_VISAO",
        rotulo="Ollama Cloud",
        dica="Opcional (reserva). Nao adicione creditos.",
        url_chave="https://ollama.com/settings/keys",
        modelo_sugerido="gemma4:31b",
    ),
}

ORDEM_PADRAO = "gemini,groq,openrouter,ollama-cloud"
MAX_BYTES_IMAGEM = 4 * 1024 * 1024
TIMEOUT_API = 30.0
COOLDOWN_PROVEDOR = 60.0