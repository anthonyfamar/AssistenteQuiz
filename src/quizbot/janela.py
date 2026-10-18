# JANELA - presenter que mostra a sugestao numa janelinha (tkinter).
#
# JanelaPresenter -> janela pequena, sempre por cima, no canto inferior direito.
#                    Mostra "C - texto da alternativa" e a explicacao curta.
#                    Estados: aguardando, consultando a IA, sugestao e aviso.
#
# Threads: o tkinter so pode ser mexido pela thread principal, mas o assistente roda
# em outra. Por isso mostrar(), consultando() e avisar() so colocam o trabalho numa
# fila; a janela esvazia a fila de tempos em tempos (veja executar()).
import queue
import tkinter as tk
from collections.abc import Callable
from string import ascii_uppercase

from quizbot.models import Question, Suggestion
from quizbot.presenter import Presenter

LARGURA = 400
ALTURA = 250
MARGEM = 16
ALTURA_BARRA_TAREFAS = 64
INTERVALO_FILA_MS = 100

FUNDO = "#1f2937"
TEXTO = "#f3f4f6"
SUAVE = "#9ca3af"
DESTAQUE = "#60a5fa"
AVISO = "#fbbf24"


class JanelaPresenter(Presenter):
    def __init__(self, ao_fechar: Callable[[], None] | None = None) -> None:
        self._ao_fechar = ao_fechar
        self._fila: queue.Queue[Callable[[], None]] = queue.Queue()

        self._raiz = tk.Tk()
        self._raiz.title("AssistenteQuiz")
        self._raiz.configure(bg=FUNDO)
        self._raiz.attributes("-topmost", True)
        self._raiz.resizable(False, False)
        self._raiz.protocol("WM_DELETE_WINDOW", self._fechar)
        self._posicionar()

        self._legenda = self._criar_rotulo(("Segoe UI", 9, "bold"))
        self._principal = self._criar_rotulo(("Segoe UI", 13, "bold"))
        self._explicacao = self._criar_rotulo(("Segoe UI", 11))
        self._rodape = self._criar_rotulo(("Segoe UI", 9))
        self._esperando()

    def _posicionar(self) -> None:
        x = self._raiz.winfo_screenwidth() - LARGURA - MARGEM
        y = self._raiz.winfo_screenheight() - ALTURA - ALTURA_BARRA_TAREFAS
        self._raiz.geometry(f"{LARGURA}x{ALTURA}+{x}+{y}")

    def _criar_rotulo(self, fonte: tuple) -> tk.Label:
        rotulo = tk.Label(
            self._raiz,
            font=fonte,
            bg=FUNDO,
            fg=TEXTO,
            wraplength=LARGURA - 2 * MARGEM,
            justify="left",
            anchor="w",
        )
        rotulo.pack(fill="x", padx=MARGEM, pady=(MARGEM // 2, 0))
        return rotulo

    def _definir(
        self,
        legenda: str,
        principal: str,
        cor: str,
        explicacao: str = "",
        rodape: str = "",
    ) -> None:
        self._legenda.config(text=legenda, fg=SUAVE)
        self._principal.config(text=principal, fg=cor)
        self._explicacao.config(text=explicacao)
        self._rodape.config(text=rodape, fg=SUAVE)

    # --- estados (rodam sempre na thread principal) ---

    def _esperando(self) -> None:
        self._definir("AGUARDANDO", "Aguardando questão…", SUAVE)

    def _consultando(self) -> None:
        self._definir("CONSULTANDO", "Consultando a IA…", SUAVE)

    def _exibir(self, question: Question, suggestion: Suggestion) -> None:
        letra = ascii_uppercase[suggestion.indice]
        if 0 <= suggestion.indice < len(question.alternativas):
            principal = f"{letra} - {question.alternativas[suggestion.indice]}"
        else:
            principal = letra
        rodape = f"Respondido por: {suggestion.origem}" if suggestion.origem else ""
        self._definir("SUGESTÃO", principal, DESTAQUE, suggestion.explicacao, rodape)

    def _aviso(self, mensagem: str) -> None:
        self._definir("AVISO", mensagem, AVISO)

    # --- interface do Presenter (podem ser chamadas de outra thread) ---

    def mostrar(self, question: Question, suggestion: Suggestion) -> None:
        self._fila.put(lambda: self._exibir(question, suggestion))

    def consultando(self) -> None:
        self._fila.put(self._consultando)

    def avisar(self, mensagem: str) -> None:
        self._fila.put(lambda: self._aviso(mensagem))

    # --- ciclo de vida ---

    def _processar_fila(self) -> None:
        while True:
            try:
                tarefa = self._fila.get_nowait()
            except queue.Empty:
                break
            tarefa()
        self._raiz.after(INTERVALO_FILA_MS, self._processar_fila)

    def executar(self) -> None:
        self._raiz.after(INTERVALO_FILA_MS, self._processar_fila)
        self._raiz.mainloop()

    def _fechar(self) -> None:
        if self._ao_fechar is not None:
            self._ao_fechar()
        self._raiz.destroy()
