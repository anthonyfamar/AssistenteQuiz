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
- **IA:** apenas APIs gratuitas e configuráveis (Gemini no AI Studio, Groq, OpenRouter ou Ollama Cloud). Planos gratuitos têm limite e mudam sem aviso: confirmar os valores atuais no site do provedor. A resposta deve ser estruturada (índice + explicação). Se a IA errar o formato ou a cota acabar, o assistente avisa em vez de inventar uma sugestão. Se um provedor falhar, o `FallbackSolver` tenta o próximo (com pausa de 60 s no que falhou). Nada de pagar: sem faturamento no Gemini, sem créditos no OpenRouter (só modelos `:free`, travado no código).
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

AssistenteQuiz     → loop: observar → questão mudou? → solver → presenter
main               → conecta ao navegador do assistente; o usuário loga e navega
```

## Setup

```
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Mac/Linux: source .venv/bin/activate
pip install playwright python-dotenv openai
```

**Estrutura de pastas:** na raiz ficam só `1-INSTALAR.bat`, `LEIA-ME.txt` e a pasta `programa/` (mais os arquivos de repositório: README, LICENSE, CLAUDE.md, `.gitignore`, `.gitattributes`). Dentro de `programa/` ficam `src/quizbot/`, `requirements.txt`, `.env.example`, `.env` (fora do Git), `instalar.ps1`, `iniciar.bat` e `configurar.bat`. Assim quem baixa o ZIP vê um único arquivo para abrir. A `.venv` de desenvolvimento continua na raiz (`..\.venv` para os `.bat`).

Para quem não programa: `1-INSTALAR.bat` (uma vez) e depois o atalho `AssistenteQuiz`. O `LEIA-ME.txt` explica o passo a passo.

Para rodar: dois cliques em `programa\iniciar.bat`. Ele abre o navegador do assistente (porta de depuração 9222, perfil `chrome-assistente`), se precisar, e a janelinha. Faça login no site na janela do navegador.

Pelo terminal, na raiz do projeto: `$env:PYTHONPATH = "programa\src"; .\.venv\Scripts\python.exe -m quizbot.main`

Para instalar na mão: `pip install -r programa\requirements.txt`.

**ZIP para entregar a quem só vai usar** (sem `.env`, sem `.venv`, sem README/CLAUDE.md): contém `1-INSTALAR.bat`, `LEIA-ME.txt`, `LICENSE` e `programa/` (sem `.env` e sem `.env.example`), tudo dentro de uma pasta `AssistenteQuiz/`, com barra normal (`/`) nos nomes das entradas. Gerar de novo sempre que o código mudar.

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
- [x] `JanelaPresenter` com tkinter e `programa\iniciar.bat` (abre o navegador e a janela)
- [x] Instalador para leigos: `1-INSTALAR.bat`, `programa\instalar.ps1`, `configurar.py`, `LEIA-ME.txt` (testado numa cópia com Python instalado do zero; falta testar num Windows limpo)
- [x] Fórmulas (Wiris) como texto e questões com imagem (modelo de visão por provedor)
