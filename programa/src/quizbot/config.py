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

# Pagina de RESUMO da tentativa (a que tem o "Enviar tudo e terminar"): uma linha por questao,
# <tr class="quizsummary8 notyetanswered"> com o numero da questao num link. Antes de enviar o
# programa confere esta tabela: uma linha com a classe abaixo e uma questao sem resposta.
SELETOR_TABELA_RESUMO = "table.quizsummaryofattempt"
CLASSE_NAO_RESPONDIDA = "notyetanswered"
# Na tela de UMA questao: a alternativa que ja esta marcada (resposta guardada) e o numero
# da questao ("Questao 8"). Questao ja respondida nao e respondida de novo: so se avanca.
SELETOR_RADIO_MARCADO = ".que .answer input[type=radio]:checked"
SELETOR_NUMERO_DA_QUESTAO = ".que .info .qno"
# Quantas vezes o programa volta do resumo para a MESMA questao sem resposta antes de desistir
# (e nao enviar). E quantos segundos espera, depois de clicar no numero, a pagina trocar.
MAX_VISITAS_POR_QUESTAO = 2
PAUSA_APOS_ABRIR_QUESTAO = 5.0

# CURSO: o menu das unidades (ul.timeline), o titulo da unidade aberta (h1), as atividades
# dela e o "caminho" (breadcrumb) do topo das paginas de quiz.
# - Cada <li> do menu tem um link com o nome da unidade e um icone cuja barra de progresso e o
#   PRIMEIRO numero do linear-gradient (100% = barra cheia). A unidade aberta tem "active".
# - Atividade feita tem dentro do icone o <i class="... format_list_topics_complete">.
# - Os dois quizzes que importam sao achados pelo texto do link (o "U3 -" muda de unidade).
# O menu das unidades aparece tambem nas paginas das atividades (prova, resumo, painel do quiz),
# cujo endereco tem "/mod/". So vale como pagina do CURSO a que NAO e de uma atividade: sem isso o
# programa clicaria numa unidade no meio de uma prova e sairia dela.
FRAGMENTO_URL_ATIVIDADE = "/mod/"
SELETOR_MENU_UNIDADES = "ul.timeline"
SELETOR_LINK_UNIDADE = "ul.timeline .timeline-item a"
SELETOR_TITULO_UNIDADE = ".ct-section-active-topic h1"
SELETOR_ATIVIDADES = ".ct-list"
SELETOR_LINK_ATIVIDADE = ".ct-list h3 a"
CLASSE_ATIVIDADE_CONCLUIDA = "format_list_topics_complete"
SELETOR_CAMINHO = "ol.breadcrumb li.breadcrumb-item"
SELETOR_LINK_CURSO = 'ol.breadcrumb a[href*="/course/view.php"]'
# O quiz e achado pelo NOME INTEIRO: "U<numero> - <trecho>" (sem acento e em minuscula para
# comparar). So o trecho nao basta: "Pre Aula 4 - U1 - Atividade de Aprendizagem" e
# "Pos Aula 4 - U1 - Avaliacao da Unidade" sao arquivos de apoio, nao os quizzes.
# O icone do quiz desempata se houver mais de um candidato (os arquivos tem "icon-add_box").
CLASSE_ICONE_QUIZ = "icon-library_books"
# (tipo, trecho do nome, nome para mostrar nos avisos), na ordem em que o programa trabalha.
QUIZZES_DO_CURSO = (
    ("aprendizagem", "atividade de aprendizagem", "Atividade de Aprendizagem"),
    ("avaliacao", "avaliacao da unidade", "Avaliação da Unidade"),
)
# CURSOS COM SECOES: a unidade tem "U1 - Secao 1/2/3" no menu e os quizzes ficam DENTRO de cada
# secao (nao na unidade): "U3S2 - Atividade Diagnostica", "U3S2 - Atividade de Aprendizagem" e,
# so na secao 3, "U3 - Avaliacao da Unidade". Quais quizzes cada secao tem e lido da pagina.
# Quem NAO e unidade (ex.: "Livro Didatico", "Avalie sua disciplina") e ignorado: so entra no
# roteiro o item do menu cujo nome (sem acento, minuscula) combina com PADRAO_NOME_UNIDADE.
PADRAO_NOME_UNIDADE = r"^unidade\b"
SELETOR_LINK_SECAO = "ul.timeline .timeline-menu li a"
# Os tres quizzes que um curso com secoes pode ter (a ordem de trabalho e a da pagina).
TIPOS_DE_QUIZ = (
    ("diagnostica", "atividade diagnostica", "Atividade Diagnóstica"),
    *QUIZZES_DO_CURSO,
)
# Ao chegar na pagina do curso, espera antes de comecar (mudar de pagina cancela).
PAUSA_ANTES_DE_COMECAR_CURSO = 5.0
# Depois de clicar numa unidade/atividade, espera a pagina trocar antes de decidir de novo.
PAUSA_APOS_ABRIR_CURSO = 4.0
# O usuario pode abrir uma unidade/secao quando quiser: a analise recomeca dali. Para saber se a
# mudanca de pagina foi dele ou do programa: depois de um clique (ou da volta de um quiz) o
# programa considera "dele" a PRIMEIRA mudanca de pagina ate este tempo (s); e, quando a
# pagina nova nao deixa ver onde esta (ainda carregando), insiste por este tempo (s).
TEMPO_DA_NAVEGACAO_NOSSA = 15.0
TEMPO_PARA_LER_ESCOLHA = 10.0
# Fora das paginas do curso por este tempo (s), o proximo endereco do curso deixa de contar como
# escolha do usuario (so passa a ser "onde esta").
TEMPO_FORA_DO_CURSO = 3.0
# Quantas vezes tenta abrir a mesma unidade/atividade antes de desistir e avisar.
MAX_TENTATIVAS_CURSO = 2

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
# Ao acabar as tentativas (ou tirar a nota maxima), quantos segundos mostrar a nota antes
# de voltar ao curso.
PAUSA_ANTES_DE_VOLTAR = 5.0
# Com tentativas sobrando (nota maxima de primeira) nao existe o botao "Voltar ao curso":
# o programa volta pelo historico do navegador (a seta de voltar) ate cair na pagina do
# curso, reconhecida por este pedaco do endereco. Passa pelo maximo de paginas abaixo e,
# se nao achar o curso, para onde estiver e avisa.
FRAGMENTO_URL_CURSO = "/course/view.php"
MAX_VOLTAS_NO_HISTORICO = 25

# Tira o "a. " ou "b) " do comeco de cada alternativa (o presenter ja poe as letras).
PADRAO_PREFIXO_ALTERNATIVA = r"^[a-zA-Z][.)]\s+"

INTERVALO_POLLING = 0.5

# Modo automatico: segundos de espera depois de marcar a alternativa e antes de avancar
# (da tempo de ver a marca na tela).
PAUSA_APOS_CLICAR = 1.0
# Se marcar a alternativa ou avancar falhar, o programa tenta mais uma vez depois deste tempo; se
# falhar de novo, mostra a sugestao com um botao "Tentar de novo" (nao deixa o usuario sem nada).
PAUSA_ENTRE_TENTATIVAS = 1.0
# Toda espera do programa e feita em fatias deste tamanho (segundos), e a cada fatia o Playwright
# atende o navegador (dormir "parado" deixa as mensagens do navegador sem resposta ate a proxima chamada).
FATIA_DE_ESPERA = 0.25
# Depois de enviar a tentativa, a revisao deve ser lida em segundos. Passando deste tempo (s) sem
# ler, o programa registra o que a pagina mostra e avisa o usuario (nao fica mudo).
ESPERA_PELA_REVISAO = 20.0
# Como o programa clica: True = DENTRO da pagina (el.click()), que funciona com o navegador
# MINIMIZADO; False = clique de mouse simulado do Playwright, que depende de o navegador desenhar a
# janela (minimizado, o clique funciona mas a confirmacao demora e vira falso erro).
CLIQUE_PELO_DOM = True

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
# Para o navegador continuar trabalhando com a janela minimizada ou coberta por outras (senao ele
# "dorme" as paginas: temporizadores lentos e sem animacao, e o programa nao consegue clicar).
# Valem so quando o programa abre o navegador; se ele ja estava aberto, feche-o e deixe o
# programa abrir de novo.
FLAGS_SEM_SONECA = (
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling",
)
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
    # Modelos reserva DO MESMO provedor, do melhor para o pior. Se o modelo do .env falhar
    # (sobrecarregado, fora do ar), o programa tenta estes ANTES de passar para outro
    # provedor. Escolhidos da mesma linha do modelo principal, so um pouco abaixo (nunca
    # modelos muito antigos). Depois da pausa, o principal e sempre tentado primeiro.
    modelos_reserva: tuple[str, ...] = ()
    # Reservas que NAO enxergam imagem: entram depois das outras e so respondem questao de texto.
    reservas_so_texto: tuple[str, ...] = ()
    # Modelos que "pensam" antes de responder levam uns 10 s: multiplica o tempo de espera deles.
    fator_de_espera: float = 1.0


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
        # Cada modelo do Gemini tem a cota do dia SEPARADA (a mensagem do erro 429 diz "por dia, por
        # projeto, por modelo"). O 3-flash-preview respondeu 4 de 4 nas questoes de teste em 2,8 s.
        # Os "lite" levam ~6 s (mais que o tempo rapido) e errram mais: ficaram de fora.
        modelos_reserva=("gemini-3.7-flash", "gemini-3.6-flash", "gemini-3-flash-preview"),
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
        # Na Groq cada modelo tem o proprio limite no plano gratuito (30/min, 1000/dia, 8 mil
        # tokens/min e 200 mil tokens/dia, segundo a documentacao oficial): os reservas dao outra
        # cota quando o principal bate no limite POR MINUTO. qwen3.8-27b: 11 de 12 nos testes e
        # enxerga imagem; gpt-oss-20b: 6 de 8, so texto.
        modelos_reserva=("qwen/qwen3.8-27b",),
        reservas_so_texto=("openai/gpt-oss-20b",),
    ),
    "openrouter": Provedor(
        "openrouter",
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        "OPENROUTER_MODEL_VISAO",
        so_free=True,
        rotulo="OpenRouter",
        dica=(
            "Opcional (reserva). Use so modelos terminados em :free e nao compre creditos. "
            "O plano gratuito permite 50 respostas por dia (tentativas que falham tambem contam)."
        ),
        url_chave="https://openrouter.ai/keys",
        # Os modelos gratuitos mudam toda hora e os "gemma" vivem saturados na origem (erro 429
        # "temporarily rate-limited upstream"). Em 11/2026 estes dois responderam certo; todos
        # os reservas enxergam imagem (o programa manda imagem tambem para os reservas).
        modelo_sugerido="nvidia/nemotron-3-ultra-550b-a55b:free",
        modelo_visao_sugerido="nvidia/nemotron-3.5-super-vl:free",
        modelos_reserva=(
            "nvidia/nemotron-3.5-super-vl:free",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
            "google/gemma-4-31b-it:free",
            "google/gemma-4-26b-a4b-it:free",
        ),
        fator_de_espera=2.0,
    ),
}

# Provedores que ja existiram e foram retirados, com o motivo (um .env antigo pode ainda citar
# o nome em ORDEM_PROVEDORES: o programa avisa e ignora, a janela de configuracao tira da ordem).
# So entra provedor cuja API seja GRATIS de verdade: confira na documentacao OFICIAL (blogs e
# listas de terceiros ficam desatualizados), principalmente se a chave exige cobranca ativada.
PROVEDORES_REMOVIDOS = {
    "ollama-cloud": "a chave gratuita recebe erro 402 (pede credito pago) em todos os modelos desde 11/2026",
    "mistral": "o plano gratuito nao inclui a API: criar chave exige ativar cobranca (pay-as-you-go), segundo a documentacao oficial",
}

ORDEM_PADRAO = "gemini,groq,openrouter"
MAX_BYTES_IMAGEM = 4 * 1024 * 1024
# Quanto esperar (segundos) por UMA resposta antes de desistir e passar para o proximo modelo.
# Erro claro ("fora do ar", 503...) nao espera nada: passa para o proximo na hora.
TIMEOUT_RAPIDO = 5.0  # tentativa que ainda tem outro modelo livre depois dela
TIMEOUT_API = 15.0  # o ultimo da fila (e o limite padrao do cliente); imagem espera o dobro
# Modelo que falhou sai da fila; em segundo plano ele e testado (pedido minusculo) depois
# deste tempo, que dobra a cada teste que falha (ate 6x). So volta quando o teste passa.
COOLDOWN_PROVEDOR = 30.0
# Quando TODAS as IAs falham mas a que volta primeiro pediu so alguns segundos (limite por minuto,
# comum na Groq), o programa espera esse tempo e tenta de novo uma vez, sozinho. Acima disto, mostra
# o aviso com quanto falta para cada uma voltar.
ESPERA_CURTA_DA_IA = 20.0
# Tempo minimo (segundos) que um aviso fica na janelinha para dar tempo de ler: o alerta de
# falha da IA (some sozinho depois disso) e os avisos amarelos do corpo da janela (o
# "Consultando a IA..." seguinte espera a sua vez; a sugestao nunca espera).
# Estimativa humana: ~2,5 s para ler a frase + ~1,5 s para perceber e olhar = 4 s no limite; 5 s folgado.
SEGUNDOS_ALERTA = 5