# AssistenteQuiz

Programa em Python que acompanha um quiz web em tempo real. Quando a questão na tela muda, ele lê o enunciado e as alternativas, consulta uma IA e mostra uma sugestão de resposta com uma explicação curta. Quem lê, decide e clica é sempre o usuário.

## Regras de trabalho (valem sempre)

1. **Confirmar antes de mudar a estrutura.** Antes de criar ou mudar qualquer arquivo ou pasta, eu mostro o que vai ser criado e como vai ficar, e espero seu "pode".
Um pedido genérico como "crie" não conta como OK para um conteúdo que você ainda não viu.
2. **Responder em português** e ensinar: o Anthony quer aprender Playwright, APIs de IA e POO.
3. **Código em pequenos passos**, com cada conceito e cada linha explicados. Um passo por vez.
4. Projeto pensado para ser bonito e digno de GitHub: código limpo, README claro.

## Como funciona

- O programa abre o navegador do assistente (Chrome ou, se não houver, o Edge, que já vem no Windows) com a porta de depuração e um perfil separado. O usuário faz login e navega sozinho, no ritmo dele. O Playwright só se conecta a esse navegador e lê a página (olha todas as abas e iframes).
- Um laço (polling) consulta a página a cada ~0,5 segundo e lê o texto (DOM) com seletores CSS. Fórmulas (imagens do Wiris) viram texto a partir do MathML. Imagens de verdade são baixadas (sem tirar print da tela) e enviadas só a provedores com modelo de visão (`*_MODEL_VISAO`).
- Se o enunciado é diferente do último lido, é uma questão nova (guarda a anterior para não repetir a consulta).
- A questão vai para o `Solver`, que consulta a IA e devolve a sugestão (alternativa + explicação).
- A sugestão aparece numa janelinha tkinter (ou no terminal, trocando só uma classe). A janela fica na thread principal e o assistente roda em outra, ligados por uma fila.
- Se a página não tiver questão (login, menu), os seletores não acham nada e o assistente fica quieto.

## Decisões

- **Só leitura:** a classe que acessa a página não tem método de clicar ou enviar. O limite vem do desenho do código.
- **IA:** apenas APIs gratuitas e configuráveis (Gemini no AI Studio, Groq ou OpenRouter; Ollama Cloud e Mistral foram retirados em 11/2026 por não terem API gratuita de verdade; antes de incluir um provedor, conferir na documentação OFICIAL, não em blogs). Planos gratuitos têm limite e mudam sem aviso: confirmar os valores atuais no site do provedor. A resposta deve ser estruturada (índice + explicação). Se a IA errar o formato ou a cota acabar, o assistente avisa em vez de inventar uma sugestão. Se um provedor falhar, o `FallbackSolver` tenta o próximo (o que falhou fica fora da fila até o servidor liberar: o tempo que ele disser, ou testes em segundo plano; veja "Cotas e provedores" no Progresso). Nada de pagar: sem faturamento no Gemini, sem créditos no OpenRouter (só modelos `:free`, travado no código).
- **Login:** manual, no navegador do assistente (perfil `chrome-assistente`, na pasta do usuário, fora do projeto). Nenhuma senha em código ou `.env`.
- **Navegador com porta de depuração:** a porta 9222 só aceita conexões locais, mas qualquer programa do PC pode controlar esse navegador enquanto ele estiver aberto. Usar só para o quiz e fechar depois. Nada de disfarçar a automação.
- **Instalação para leigos (Windows):** `1-INSTALAR.bat` → `instalar.ps1`. Instala o Python oficial do python.org só para o programa (confere a assinatura digital, sem administrador, sem mexer no PATH), cria o ambiente em `%LOCALAPPDATA%\AssistenteQuiz\venv` (caminho curto de propósito: o Windows limita caminhos a 260 caracteres e o Playwright tem pastas fundas; os `.bat` usam a `.venv` da pasta se ela existir), instala os componentes, abre a janela de configuração (`configurar.py`, que grava o `.env`) e cria os atalhos. Os arquivos `.bat`, `.ps1` e `LEIA-ME.txt` ficam em CRLF (`.gitattributes`); o `.ps1` e o `.txt` têm marca UTF-8 por causa dos acentos, e os `.bat` ficam só em ASCII.

## Regras de uso e segurança

- A API key fica só no `.env` (que está no `.gitignore`). Nunca no código nem no Git. Se vazar, revogar na hora.

## Classes

```
Imagem             → bytes + tipo de uma figura da questão (fórmulas viram texto, não Imagem)
Question           → enunciado + alternativas + imagens (dataclass imutável)
Suggestion         → índice sugerido + explicação curta

SolverError        → falha esperada de um solver (formato errado, cota, rede)
Solver (ABC)       → solve(question) -> Suggestion
 ├─ ApiSolver        → um provedor por API compatível com OpenAI (base_url, chave, modelo)
 └─ FallbackSolver   → lista de solvers; se um falha, tenta o próximo (com pausa)

PageReader         → SÓ LEITURA: ler_questao() -> Question | None
                     (LeituraIncompleta se uma imagem da questão não puder ser lida)

Presenter (ABC)    → mostrar(question, suggestion); opcionais: consultando(), avisar(msg)
 ├─ TerminalPresenter → imprime no terminal
 └─ JanelaPresenter   → janelinha tkinter, sempre por cima (janela.py)

chrome.py          → garantir_chrome(): abre o navegador do assistente (Chrome ou Edge) com a porta 9222
configurar.py      → janela (tkinter) para colar as chaves e escolher modelos; grava o .env

RoteiroDoCurso     → (curso.py) lógica pura, sem navegador: dado o menu das unidades e a unidade
                     aberta, diz o próximo passo (abrir unidade, abrir um dos 2 quizzes, concluído
                     ou PARAR e avisar). Confere os 2 quizzes de TODAS as unidades, em ordem.

AssistenteQuiz     → loop: observar → questão mudou? → solver → presenter
                     (no Automático também cuida do resumo, das tentativas e do curso)
main               → conecta ao navegador do assistente; o usuário loga e navega
```

## Setup

```
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Mac/Linux: source .venv/bin/activate
pip install playwright python-dotenv openai
```

**Estrutura de pastas:** na raiz ficam só `1-INSTALAR.bat`, `LEIA-ME.txt` e a pasta `programa/` (mais os arquivos de repositório: README, LICENSE, CLAUDE.md, `.gitignore`, `.gitattributes`). Dentro de `programa/` ficam `src/quizbot/`, `testes/`, `requirements.txt`, `.env.example`, `.env` (fora do Git), `instalar.ps1`, `iniciar.pyw` e `configurar.bat`.

**Testes** (`programa/testes/`): `teste_*.py` (um por assunto: leitura da revisão, curso e seções, envio, memória, janela…), `html/` (páginas de exemplo do Moodle: `revisao_icone_fora_e_dentro.html` com a estrutura real, textos resumidos, e `revisao_sem_icone.html` com o formato simples) e `rodar_todos.py`. Para rodar, na raiz: `.\.venv\Scripts\python.exe programa\testes\rodar_todos.py` (todos, ~3,5 min) ou `... rodar_todos.py revisao` (só os que têm esse trecho no nome). Precisam do Chrome ou do Edge; não usam a memória, a nuvem, o `.env` nem as chaves de verdade. Quando o Moodle mudar uma página, salve o HTML novo em `testes/html/` e rode `teste_revisao_html.py`: ele lê cada `revisao_*.html` sozinho. Rodar antes de dar o programa como pronto. Assim quem baixa o ZIP vê um único arquivo para abrir. A `.venv` de desenvolvimento continua na raiz (`..\.venv` para o `configurar.bat`).

Para quem não programa: `1-INSTALAR.bat` (uma vez) e depois o atalho `AssistenteQuiz`. O `LEIA-ME.txt` explica o passo a passo.

Para rodar: dois cliques no atalho `AssistenteQuiz` (ou em `programa\iniciar.pyw`, que abre sem janela preta). Ele abre a janelinha, que pergunta o modo (Automático ou Só sugerir), e o navegador do assistente (porta de depuração 9222, perfil `chrome-assistente`), se precisar. Faça login no site na janela do navegador.

Pelo terminal, na raiz do projeto: `$env:PYTHONPATH = "programa\src"; .\.venv\Scripts\python.exe -m quizbot.main`

Para instalar na mão: `pip install -r programa\requirements.txt`.

**ZIP para entregar a quem só vai usar** (sem `.env`, sem `.venv`, sem README/CLAUDE.md): contém `1-INSTALAR.bat`, `LEIA-ME.txt`, `LICENSE` e `programa/` (sem `.env`, sem `.env.example` e sem `testes/`), tudo dentro de uma pasta `AssistenteQuiz/`, com barra normal (`/`) nos nomes das entradas. Gerar de novo sempre que o código mudar.

## Progresso

Atualizar este checklist a cada passo concluído.

- [x] Estrutura de pastas e arquivos criada (com comentário de propósito em cada um)
- [x] `models.py`: Question, Suggestion
- [x] `solvers/`: Solver, SolverError
- [x] `page_reader.py`
- [x] `presenter.py`: TerminalPresenter
- [x] `assistente.py`: loop de polling
- [x] `config.py` e `main.py`
- [x] `ApiSolver` e `FallbackSolver` (provedores gratuitos, `.env.example`, testado no site real)
- [x] README completo (o que faz, como rodar, aviso educacional)
- [x] `JanelaPresenter` com tkinter e `programa\iniciar.pyw` (abre o navegador e a janela)
- [x] Instalador para leigos: `1-INSTALAR.bat`, `programa\instalar.ps1`, `configurar.py`, `LEIA-ME.txt` (testado numa cópia com Python instalado do zero; falta testar num Windows limpo)
- [x] Fórmulas (Wiris) como texto e questões com imagem (modelo de visão por provedor)
- [x] Curso (modo Automático): `curso.py` (`RoteiroDoCurso`) + `ler_menu/ler_unidade/ler_caminho` + `abrir_unidade/abrir_atividade`; confere "Atividade de Aprendizagem" e "Avaliação da Unidade" de todas as unidades (a barra de progresso mede conclusão, não nota); volta ao curso pelo botão ou pelo link do breadcrumb (sem passar pelas páginas); pausa de 5 s antes de voltar; algo fora do esperado: para e avisa com os pendentes (testado com um curso simulado e o HTML real do menu, da unidade e do breadcrumb; falta testar no site real)
- [x] Cursos com seções (`curso.py`, `page_reader.py`): a unidade tem "U1 - Seção 1/2/3" e os quizzes (Atividade Diagnóstica, Atividade de Aprendizagem e, na seção 3, Avaliação da Unidade) ficam dentro de cada seção; quais existem é lido da página. Só entra como unidade o item do menu cujo nome combina com `PADRAO_NOME_UNIDADE` (fora "Livro Didático", "Avalie sua disciplina"). A seção aberta é a marcada `li.active` no menu, conferida pelos nomes `U3S2 - …` da lista. O clique na seção é pelo DOM (o submenu fica escondido). O modo antigo (quizzes direto na unidade) continua. Testado com um curso simulado a partir do HTML real; falta testar no site real (principalmente: o endereço da seção, o que "Voltar ao curso" mostra e se "Atividade Diagnóstica" é mesmo um quiz a responder)
- [x] Revisão depois do envio: se em `ESPERA_PELA_REVISAO` (20 s) a revisão não for lida, o programa registra no log o que a página mostra (`PageReader.diagnosticar_pagina`) e avisa o usuário uma vez; questão da revisão pulada (imagem que não baixou) também vai para o log; gravação lenta da memória (> 3 s) é registrada. Motivo: num teste real a revisão não foi lida/guardada e o log não tinha nada para explicar (a causa não foi confirmada; no Moodle simulado o caminho completo funciona). A hipótese "revisão sem gabarito" foi descartada pelo usuário (a tela sempre mostra certo/errado), então o programa NUNCA termina a revisão sozinho sem ler: quando não consegue, só avisa e grava no log a estrutura da página (`[revisao] estrutura da pagina`, `PageReader.estrutura_da_revisao`) para achar o que o leitor não reconhece (esperado: seletores `.que .answer .correct/.incorrect` não batem com a revisão da "Avaliação da Unidade")
- [x] Memória conferida com dados reais (22:19–22:21): a mesma questão errada duas vezes foi com alternativas DIFERENTES ("III" depois "II"; a letra B coincidiu porque o Moodle embaralha alternativas e até a ordem das questões). A memória funcionou (tirou a errada conhecida, respondeu as certas sem IA). O registro agora mostra `| memoria: …` em cada `[resposta]` (`SolverComMemoria.nota`) e há `teste_memoria_embaralhada` (errada nunca repetida, certa vinda da memória, mesmo embaralhado). A memória só ELIMINA o que já se sabe errado; com 2 tentativas e 5 alternativas não garante acertar
- [x] Mais modelos nas chaves que o usuário já tem (12/11/2026, sem conta nova; cada modelo tem cota própria, conferido nas docs oficiais e com a chave dele): Gemini ganhou `gemini-3-flash-preview` (4 de 4 nas questões de teste, 2,8 s); os "lite" ficaram de fora (3 de 4 e ~6 s, mais que o tempo rápido, e falha lenta pausaria o Gemini inteiro); `pro`, `omni` e `gemini-4-*` têm limite 0/dia no plano gratuito e os `2.5` dão 404 ("no longer available to new users"). Groq ganhou `qwen/qwen3.8-27b` (11 de 12, enxerga imagem) e `openai/gpt-oss-20b` (6 de 8, só texto) via `Provedor.reservas_so_texto` (reserva só-texto nunca recebe imagem). 404 agora é erro permanente. Fila real: 12 modelos (Gemini 4, Groq 3, OpenRouter 5). Candidatos NÃO incluídos (docs oficiais): Cloudflare Workers AI = 10.000 neurons/dia grátis (estimativa ~100-250 questões/dia, precisa de conta, ID e token, URL com o ID da conta); Cohere = chave de teste grátis com 1.000 chamadas/mês e 20/min; Vercel AI Gateway = US$ 5/mês só em modelos "Free Tier eligible" (a lista pública de modelos não marca quais são). Testes: `teste_provedores`, `teste_reserva`, `teste_cotas`
- [x] Ollama Cloud e Mistral retirados (12/11/2026): o Ollama dá erro 402 (pede crédito) em todos os modelos; o Mistral eu havia incluído por listas de terceiros, mas a documentação OFICIAL (docs.mistral.ai/admin/billing-usage/usage-limits) diz que o modo gratuito "não inclui acesso à API" e que criar chave exige ativar cobrança (pay-as-you-go). `PROVEDORES_REMOVIDOS` guarda o motivo (um `.env` antigo com esses nomes só avisa e ignora; a janela de configuração tira da ordem e apaga as variáveis, e põe na ordem o provedor que ganhou chave). `ORDEM_PADRAO=gemini,groq,openrouter`. O usuário AUTORIZOU editar o `.env`: tirei o Ollama e o Mistral e deixei uma só `ORDEM_PROVEDORES` (havia duas, a última valia). Fontes OFICIAIS conferidas: Cerebras = sem plano gratuito permanente (US$ 5 de teste que exigem cartão e expiram em 30 dias); Vercel AI Gateway = US$ 5/mês de crédito grátis só em modelos "Free Tier eligible", API compatível com OpenAI em `https://ai-gateway.vercel.sh/v1`, aceita imagem (candidato, ainda não incluído: falta saber quais modelos são elegíveis); NVIDIA NIM = ~1.000 créditos de inscrição (fórum, não doc oficial). DeepSeek: API paga e barata (fontes divergem sobre crédito inicial). Testes: `teste_provedores`
- [x] Cotas e provedores (diagnóstico de 11/2026 com o log e testes reais): a Groq não "acabou", batia no limite de 8000 tokens POR MINUTO ("tente em 1,4 s") e o programa a deixava 2 min fora; o OpenRouter usava um modelo (gemma) saturado na origem (429 "temporarily rate-limited upstream"); o Ollama Cloud dá 402 (pede crédito) em todos os modelos para a chave gratuita. Correções: `espera_da_cota` lê o tempo real de Gemini/Groq/OpenRouter (sem teto; o vigia dorme no máximo 1 h), o modelo volta no instante pedido (`_volta_em`), erro 401/402/403 é `permanente` (fora da fila, sem vigia), `SolverError.motivo/permanente`, `Solver.apelido/fator_de_espera`; OpenRouter sugere nemotron-3-ultra (texto) e nemotron-3.5-super-vl (imagem) com reservas e `fator_de_espera=2` (levam ~10 s); quando NINGUÉM responde o aviso diz a situação de cada provedor e quanto falta ("volta em 5 h 56 min, às 04:31"), e se a espera for ≤ `ESPERA_CURTA_DA_IA` (20 s) o assistente espera e tenta de novo sozinho uma vez. Teste: `teste_cotas`. O `.env` do usuário NÃO foi alterado (ele precisa trocar `OPENROUTER_MODEL/_VISAO` e pode tirar `ollama-cloud` de `ORDEM_PROVEDORES`). Limites gratuitos (blogs de 10/2026, confirmar nos sites): Groq gpt-oss-120b 30 req/min, 1000/dia, 8K tokens/min, 200K tokens/dia; OpenRouter 20/min e 50/dia (1000/dia com US$ 10 de crédito); API da OpenAI e da Anthropic não têm plano gratuito (Haiku 5.5 ≈ US$ 0,10/0,50 por milhão de tokens)
- [x] Placar por origem: depois de ler a revisão o registro traz `[acerto] groq (openai/gpt-oss-120b): 2 de 3 | memória: 2 de 2` (uma vez por revisão, `_registrar_placar`), para medir qual provedor erra mais com dados reais. Medição de 11/2026 em 4 questões de gabarito conhecido: gpt-oss-120b 11 de 11 e qwen3.8-27b 11 de 12; nas tentativas reais só da Groq, 8 de 12 (os erros concentrados em questões de gabarito estranho, p. ex. sem a alternativa "II e III"). `teste_aviso_janela` falhou 1 vez em ~8 (corrida no fechamento da janela de teste, tkinter)
- [x] Pasta `programa/testes/` com os 27 testes, os HTML de exemplo da revisão (formato com ícone fora/dentro do texto e formato simples) e `rodar_todos.py` (26 de 26 passam; `teste_revisao_html` falha com 1 de 3 se a remoção do ícone for desfeita)
- [x] Revisão que guardava só algumas questões (causa achada na página real): o Moodle põe `img.questioncorrectnessicon` (SVG "Correto/Incorreto") ao lado da alternativa marcada, e em alternativas com texto em `<p>` o ícone cai DENTRO do `<label>`; virava `[imagem N]`, o SVG não é suportado e a questão inteira era descartada (e o texto da alternativa deixaria de bater com o da tentativa). `_JS_REVISAO` agora tira esse ícone da cópia. Teste: `teste_icone_revisao` (reproduz 1 de 3 sem a correção, 3 de 3 com ela, e confere que a questão da revisão é igual à da tentativa)
- [x] Começar de onde o usuário clicar: se ele abre uma unidade/seção por conta própria durante a análise (o endereço da página do curso muda e não foi o programa: `_o_usuario_escolheu`, `RoteiroDoCurso.ponto_de_partida/comecar_de`), o que vem antes é pulado e a análise segue dali (inclusive voltando para trás, que refaz dali). Cliques do próprio programa e a volta de um quiz não contam como escolha. Limite: clique feito nos ~1-2 s logo após um clique do programa é absorvido; e em curso com seções, clicar só no título da unidade apenas expande o menu (é preciso clicar numa seção). Testado no curso simulado; falta testar no site real
- [x] Imagens da questão hospedadas em outro endereço: o `fetch` da página falha por CORS ("Failed to fetch", reproduzido); `PageReader._baixar_da_rede` agora tenta de novo pelo contexto do navegador (`context.request`, mesmos cookies, sem CORS), registra `[imagem]` no log e o aviso passa a trazer o motivo real (ex.: "HTTP 404"). Falta ver no site real se era mesmo isso
- [x] Fim do curso e robustez: pergunta "Outra matéria" (espera abrir outro curso, reconhecido pelo `id` do endereço, e recomeça) ou "Encerrar"; o menu das unidades só conta em página sem `/mod/` (ele aparece também na prova, e o programa saía da prova); cliques sem falso erro em site lento (`no_wait_after`) e pelo DOM com a página oculta; flags do Chrome contra "soneca" quando minimizado; a janelinha volta à frente sozinha quando precisa do usuário (falta testar minimizado no PC real)
- [x] Cliques pelo DOM (`CLIQUE_PELO_DOM` no `config.py`; com o navegador minimizado o clique de mouse do Playwright funcionava mas a confirmação demorava e virava falso erro) e "Tentar de novo": se marcar, avançar, voltar ao curso ou obter a sugestão falhar, o programa tenta mais uma vez e, se falhar, a janelinha mantém a sugestão na tela e mostra um botão que repete a ação e segue o fluxo (falta testar minimizado no PC real)
- [x] Esperas que atendem o navegador: toda espera do programa (laço, pausas, contagens e a pergunta "Outra matéria") usa `_esperar`, que dorme em fatias de `FATIA_DE_ESPERA` chamando `PageReader.atender_navegador` (`wait_for_timeout`). `time.sleep`/`Event.wait` comum deixa o Playwright síncrono sem atender o navegador (medido: 0 mensagens em 1 s contra 19). Não confirmado que isso era a causa da página que não carregava durante a pergunta (falta testar no PC real)
- [x] Conferir o resumo antes de enviar: questão sem resposta é aberta pelo número, respondida, e só envia com todas respondidas; questão que já tem alternativa marcada não gasta IA, só avança (testado com um Moodle simulado; falta testar no site real)
