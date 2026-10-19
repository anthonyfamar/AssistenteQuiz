# AssistenteQuiz

Programa em Python que acompanha um quiz web em tempo real. Quando a questão na tela muda, ele lê o enunciado e as alternativas, consulta uma IA gratuita e mostra numa janelinha (ou no terminal) uma **sugestão de resposta com uma explicação curta**.

Quem lê, decide e clica é sempre **você**: o programa só lê a página e nunca clica, envia ou navega por você.

```
============================================================
Qual é a capital do Brasil?

A. São Paulo
B. Rio de Janeiro
C. Brasília <-- sugestão
D. Salvador

Sugestão: alternativa C
Por quê: A capital oficial do Brasil é Brasília, fundada em 1960.
Respondido por: groq
============================================================
```

## Aviso importante

Este é um projeto **educacional**, feito para estudar Playwright, APIs de IA e programação orientada a objetos.

- Use em **atividades de treino**, ou onde o uso de IA for permitido pelo professor e pela instituição.
- **Não use em avaliações que valem nota** sem essa permissão. Isso pode violar as regras da instituição, e a responsabilidade é sua.
- O programa **não disfarça** a automação nem contorna proteções (CAPTCHA, detecção de robôs). Se um site bloquear, a solução é trocar de site.
- Em alguns planos gratuitos, o que você envia à IA **pode ser usado pelo provedor** para melhorar os produtos dele (é o caso do plano grátis do Gemini). Não envie dados pessoais.

## Como funciona

```
  Você                Chrome               AssistenteQuiz                 IA gratuita
   │  abre e loga       │                         │                            │
   │───────────────────▶│                         │                            │
   │                    │◀── lê o texto (DOM) ────│  a cada ~0,5 segundo       │
   │                    │                         │── questão nova? ──────────▶│
   │                    │                         │◀── índice + explicação ────│
   │◀─────────── sugestão na janelinha ───────────│                            │
```

1. Você abre o seu Chrome com uma porta de depuração, faz login e navega no seu ritmo.
2. O programa se conecta a esse Chrome e consulta a página a cada ~0,5 segundo, lendo o texto com seletores CSS. As fórmulas (imagens do Wiris) viram texto, e as imagens de verdade (gráficos, figuras) são baixadas e enviadas a uma IA que enxerga. Não tira print da tela.
3. Se o enunciado é diferente do último lido, é uma questão nova. A anterior fica guardada para não gastar a cota da IA com a mesma questão.
4. A questão vai para o `Solver`, que consulta a IA e devolve a sugestão.
5. Se a página não tiver questão (login, menu), os seletores não acham nada e o programa fica quieto.
6. Se a IA errar o formato da resposta ou a cota acabar, ele **avisa** em vez de inventar uma sugestão, e tenta o próximo provedor.

## Requisitos

- Python **3.10 ou superior** (testado no 3.11)
- Google Chrome
- Pelo menos uma chave de API gratuita (veja [Provedores de IA](#provedores-de-ia))

## Instalação

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

No Mac/Linux, ative com `source .venv/bin/activate`.

## Configuração

Copie o modelo e preencha:

```powershell
Copy-Item .env.example .env
```

O arquivo `.env` **nunca** vai para o Git (está no `.gitignore`). Se uma chave vazar, revogue-a na hora no painel do provedor.

### Provedores de IA

Todos têm plano gratuito e usam a API no formato compatível com OpenAI, então a mesma classe atende os quatro. Provedor sem chave ou sem modelo é **pulado sozinho**, e você pode configurar só um.

| Provedor | Onde criar a chave | Variáveis no `.env` |
|---|---|---|
| Gemini (Google AI Studio) | [aistudio.google.com](https://aistudio.google.com) | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| Groq | [console.groq.com](https://console.groq.com) | `GROQ_API_KEY`, `GROQ_MODEL` |
| OpenRouter | [openrouter.ai](https://openrouter.ai) | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` |
| Ollama Cloud | [ollama.com/settings/keys](https://ollama.com/settings/keys) | `OLLAMA_API_KEY`, `OLLAMA_CLOUD_MODEL` |

`ORDEM_PROVEDORES` define a ordem de tentativa, por exemplo `gemini,groq,openrouter,ollama-cloud`. Se um provedor falhar (cota, erro, formato errado), o programa passa para o próximo e deixa o que falhou **em pausa por 60 segundos**.

**Questões com imagem:** cada provedor tem uma variável `..._MODEL_VISAO` (por exemplo `GEMINI_MODEL_VISAO`) com o nome de um modelo **que enxerga**. Questão com imagem só é tentada nos provedores que a têm preenchida, e os que não têm continuam respondendo as questões só de texto. Imagem gasta mais da cota gratuita que texto, então só é enviada quando existe. Fórmulas **não** contam como imagem: viram texto.

**Para não gastar nada:**
- Gemini: não ative faturamento no projeto.
- OpenRouter: não compre créditos. O programa só aceita modelo cujo nome termina em `:free`.
- Ollama Cloud: não adicione créditos.

Os planos gratuitos têm limites e **mudam sem aviso**. Confirme os valores atuais no site de cada provedor. Os nomes de modelo também mudam, então use os que aparecem na documentação deles (por exemplo `gemini-3.5-flash-lite` ou `openai/gpt-oss-120b`).

## Como usar

**Dê dois cliques em `iniciar.bat`**, na pasta do projeto. Ele:

1. abre o Chrome do assistente, se ainda não estiver aberto (com a porta de depuração 9222 e um perfil próprio, `chrome-assistente`, na sua pasta de usuário, fora do projeto);
2. abre uma janelinha no canto inferior direito da tela, sempre por cima das outras;
3. conecta ao Chrome e começa a ler.

Faça login no site **na janela do Chrome que abriu** (nenhuma senha vai em código ou `.env`) e abra uma questão. A janelinha mostra:

```
SUGESTÃO
C - Brasília
A capital oficial do Brasil é Brasília, fundada em 1960.
Respondido por: groq
```

Ela também mostra `Aguardando questão…`, `Consultando a IA…` (assim você nunca vê a resposta da questão anterior) e os avisos em laranja. Para encerrar, feche a janelinha. O Chrome continua aberto.

> Enquanto o Chrome do assistente estiver aberto, qualquer programa do seu computador pode controlá-lo pela porta 9222 (ela só aceita conexões locais). Use só para o quiz e feche depois.

**Pelo terminal**, na raiz do projeto, dá o mesmo resultado:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m quizbot.main
```

Em outro sistema operacional, só o caminho do Chrome (`CAMINHOS_CHROME`, no `config.py`) precisa mudar.

## Adaptar a outro site

Os seletores do site ficam em `src/quizbot/config.py`. O padrão atual serve para quizzes do **Moodle**.

1. Abra uma questão no Chrome e aperte `F12`.
2. Use a setinha do painel para clicar no enunciado e suba até o bloco que contém o enunciado e as alternativas.
3. Escolha seletores com **classes estáveis** (como `.qtext`). Evite `id`s gerados a cada acesso e seletores como `div:nth-child(3)`, que quebram quando o site muda um detalhe.
4. O seletor do enunciado deve achar **exatamente um** elemento na tela de questão e **nenhum** em login e menus. O das alternativas deve achar um elemento por opção.

## Estrutura do projeto

```
AssistenteQuiz/
├── src/quizbot/
│   ├── models.py          Question, Imagem e Suggestion (dataclasses imutáveis)
│   ├── config.py          seletores CSS, intervalo, provedores de IA
│   ├── page_reader.py     SÓ LEITURA: lê a questão de todas as abas e iframes
│   ├── html_texto.py      HTML da questão → texto (fórmulas e marcadores de imagem)
│   ├── formulas.py        MathML → texto linear (x^2, (a)/(b), sqrt(x))
│   ├── presenter.py       contrato Presenter e TerminalPresenter
│   ├── janela.py          JanelaPresenter: a janelinha (tkinter)
│   ├── chrome.py          abre o Chrome do assistente com a porta de depuração
│   ├── assistente.py      o laço: observar → mudou? → solver → presenter
│   ├── main.py            conecta ao Chrome e monta as peças
│   └── solvers/
│       ├── base.py        Solver (classe abstrata) e SolverError
│       ├── api.py         ApiSolver: um provedor de IA
│       ├── fallback.py    FallbackSolver: tenta um, depois o próximo
│       └── fabrica.py     monta os solvers a partir do .env
├── iniciar.bat            duplo clique: abre o Chrome e a janelinha
├── .env.example           modelo do .env
└── requirements.txt
```

## Decisões de projeto

- **Só leitura por desenho.** O `PageReader` não tem nenhum método de clicar ou enviar. O limite vem do código, não de uma promessa.
- **Classes abstratas.** `Solver` e `Presenter` são contratos. O `AssistenteQuiz` recebe "um solver" e "um presenter" sem saber quais, então trocar de IA ou de terminal para janela é trocar uma classe.
- **Composição.** O `FallbackSolver` também é um `Solver`: recebe uma lista deles e tenta em ordem. Para o resto do programa, é como se fosse um só.
- **Erros esperados têm nome.** Falhas previstas (cota, formato, rede) viram `SolverError`. Um bug de verdade não é engolido: aparece.
- **A resposta da IA é validada.** O programa pede um JSON (`indice` + `explicacao`), confere o formato e rejeita índice fora das alternativas.
- **Chaves só no `.env`.** Nunca no código nem no Git.

## Limitações

- As fórmulas são lidas pelo MathML do **Wiris**. Outros formatos de fórmula (MathJax, LaTeX) ainda não têm tratamento próprio.
- Questão **com imagem** só é respondida se algum provedor tiver modelo de visão. Se nenhum tiver, ou se a imagem não puder ser baixada, a janelinha avisa em vez de adivinhar.
- Tabelas e figuras muito detalhadas podem ser mal interpretadas pela IA, mesmo vendo a imagem.
- Só lê quando há **exatamente uma questão** na tela. Com várias na mesma página, o programa fica quieto em vez de misturar alternativas.
- A sugestão da IA pode estar **errada**. Quem decide é você.
- As cotas gratuitas são limitadas. Se todos os provedores estiverem esgotados, o programa avisa e tenta de novo na próxima questão.

## Status

- [x] Leitura da página (Playwright, só leitura)
- [x] Quatro provedores de IA gratuitos, com troca automática
- [x] Sugestão no terminal ou na janelinha
- [x] Fórmulas (Wiris) lidas como texto e questões com imagem (modelo de visão)
- [x] Janela flutuante (tkinter), sempre por cima

## Licença

[MIT](LICENSE)
