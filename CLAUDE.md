# AssistenteQuiz

Programa em Python que acompanha um quiz web em tempo real. Quando a questão na tela muda, ele lê o enunciado e as alternativas, consulta uma IA e mostra uma sugestão de resposta com uma explicação curta. Quem lê, decide e clica é sempre o usuário.

## Regras de trabalho (valem sempre)

1. **Confirmar antes de mudar a estrutura.** Antes de criar ou mudar qualquer arquivo ou pasta, eu mostro o que vai ser criado e como vai ficar, e espero seu "pode".
Um pedido genérico como "crie" não conta como OK para um conteúdo que você ainda não viu.
2. **Responder em português** e ensinar: o Anthony quer aprender Playwright, APIs de IA e POO.
3. **Código em pequenos passos**, com cada conceito e cada linha explicados. Um passo por vez.
4. Projeto pensado para ser bonito e digno de GitHub: código limpo, README claro.

## Como funciona

- O Playwright abre um navegador visível. O usuário faz login e navega sozinho, no ritmo dele.
- Um laço (polling) consulta a página a cada ~1 segundo e lê o texto (DOM) com seletores CSS. Não usa captura de tela.
- Se o enunciado é diferente do último lido, é uma questão nova (guarda a anterior para não repetir a consulta).
- A questão vai para o `Solver`, que consulta a IA e devolve a sugestão (alternativa + explicação).
- A sugestão aparece no terminal do VS Code. Depois, opcionalmente, numa janelinha tkinter (trocando só uma classe).
- Se a página não tiver questão (login, menu), os seletores não acham nada e o assistente fica quieto.

## Decisões

- **Só leitura:** a classe que acessa a página não tem método de clicar ou enviar. O limite vem do desenho do código.
- **IA:** apenas APIs gratuitas e configuráveis (Gemini no AI Studio, Groq, OpenRouter ou Ollama local). Planos gratuitos têm limite e mudam sem aviso: confirmar os valores atuais no site do provedor. A resposta deve ser estruturada (índice + explicação). Se a IA errar o formato ou a cota acabar, o assistente avisa em vez de inventar uma sugestão.
- **Login:** manual, no navegador do Playwright. Nenhuma senha em código ou `.env`. Sessão salva é opcional e fica no `.gitignore`.

## Regras de uso e segurança

- Nada de disfarçar o programa ou contornar proteções (CAPTCHA, detecção). Se o site bloquear, troca-se de site.
- A API key fica só no `.env` (que está no `.gitignore`). Nunca no código nem no Git. Se vazar, revogar na hora.

## Classes

```
Question           → enunciado + alternativas (dataclass imutável)
Suggestion         → índice sugerido + explicação curta

Solver (ABC)       → solve(question) -> Suggestion
 ├─ FakeSolver       → resposta fixa, para testes
 └─ ApiSolver        → API gratuita configurável (base_url, chave, modelo)

PageReader         → SÓ LEITURA: ler_questao() -> Question | None

Presenter (ABC)    → mostrar(question, suggestion)
 ├─ TerminalPresenter → imprime no terminal (primeiro)
 └─ JanelaPresenter   → janelinha tkinter (opcional, depois)

AssistenteQuiz     → loop: observar → questão mudou? → solver → presenter
main               → abre o navegador; o usuário loga e navega
```

## Setup

```
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Mac/Linux: source .venv/bin/activate
pip install playwright python-dotenv
playwright install chromium
```

Mais o SDK do provedor de IA escolhido, quando chegarmos nele.

## Progresso

Atualizar este checklist a cada passo concluído.

- [x] Estrutura de pastas e arquivos criada (com comentário de propósito em cada um)
- [ ] `models.py`: Question, Suggestion
- [ ] `solver.py`: Solver, FakeSolver
- [ ] `demo/quiz_local.html`
- [ ] `page_reader.py`
- [ ] `presenter.py`: TerminalPresenter
- [ ] `assistente.py`: loop de polling
- [ ] `config.py` e `main.py`
- [ ] `ApiSolver` (escolher provedor, `.env.example`)
- [ ] Testes (`test_models.py`, `test_solver.py`)
- [ ] README completo (o que faz, como rodar a demo, aviso educacional)
- [ ] `JanelaPresenter` com tkinter (opcional)
