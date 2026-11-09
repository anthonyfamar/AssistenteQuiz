# JANELA - presenter que mostra a sugestao numa janelinha (tkinter).
#
# JanelaPresenter -> janela pequena, sempre por cima, no canto inferior direito.
#                    Mostra "C - texto da alternativa" e a explicacao curta.
#                    Estados: aguardando, consultando a IA, sugestao, aviso e erro.
#                    Antes de tudo, escolher_modo() mostra a tela de escolha (Automatico ou
#                    So sugerir) e, se ninguem escolher, comeca no Automatico sozinha.
#                    No erro inesperado mostra a pasta do registro e um botao para abri-la.
#
# Threads: o tkinter so pode ser mexido pela thread principal, mas o assistente roda
# em outra. Por isso mostrar(), consultando() e avisar() so colocam o trabalho numa
# fila; a janela esvazia a fila de tempos em tempos (veja executar()).
import queue
import tkinter as tk
from collections.abc import Callable
from string import ascii_uppercase

from pathlib import Path

from quizbot.config import PAUSA_ESCOLHA
from quizbot.models import Question, Suggestion
from quizbot.presenter import Presenter
from quizbot.registro import abrir_pasta

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
ERRO = "#f87171"


class JanelaPresenter(Presenter):
    def __init__(self, ao_fechar: Callable[[], None] | None = None) -> None:
        self._ao_fechar = ao_fechar
        self._fila: queue.Queue[Callable[[], None]] = queue.Queue()
        self._pasta_log: Path | None = None

        self._raiz = tk.Tk()
        self._raiz.title("AssistenteQuiz")
        self._raiz.configure(bg=FUNDO)
        self._raiz.attributes("-topmost", True)
        self._raiz.resizable(False, False)
        self._raiz.protocol("WM_DELETE_WINDOW", self._fechar)
        self._posicionar()

        # Os rotulos do dia a dia ficam num quadro proprio: assim a tela de escolha pode
        # esconder o quadro inteiro e devolve-lo depois.
        self._conteudo = tk.Frame(self._raiz, bg=FUNDO)
        self._conteudo.pack(fill="both", expand=True)
        self._legenda = self._criar_rotulo(("Segoe UI", 9, "bold"))
        self._principal = self._criar_rotulo(("Segoe UI", 13, "bold"))
        self._explicacao = self._criar_rotulo(("Segoe UI", 11))
        self._rodape = self._criar_rotulo(("Segoe UI", 9))
        self._botao_pasta = self._criar_botao(
            self._conteudo, "Abrir a pasta", self._abrir_pasta_do_log, DESTAQUE, FUNDO
        )
        self._esperando()

    def _posicionar(self, altura: int = ALTURA) -> None:
        x = self._raiz.winfo_screenwidth() - LARGURA - MARGEM
        y = self._raiz.winfo_screenheight() - altura - ALTURA_BARRA_TAREFAS
        self._raiz.geometry(f"{LARGURA}x{altura}+{x}+{max(y, 0)}")

    def _criar_rotulo(
        self, fonte: tuple, pai: tk.Misc | None = None, cor: str = TEXTO
    ) -> tk.Label:
        rotulo = tk.Label(
            pai if pai is not None else self._conteudo,
            font=fonte,
            bg=FUNDO,
            fg=cor,
            wraplength=LARGURA - 2 * MARGEM,
            justify="left",
            anchor="w",
        )
        rotulo.pack(fill="x", padx=MARGEM, pady=(MARGEM // 2, 0))
        return rotulo

    @staticmethod
    def _criar_botao(pai: tk.Misc, texto: str, comando: Callable[[], None], fundo: str, texto_cor: str) -> tk.Button:
        return tk.Button(
            pai,
            text=texto,
            command=comando,
            font=("Segoe UI", 10, "bold"),
            bg=fundo,
            fg=texto_cor,
            activebackground=fundo,
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=4,
        )

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
        self._botao_pasta.pack_forget()  # so o estado de erro mostra o botao

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

    def _erro(self, pasta_log: str) -> None:
        self._pasta_log = Path(pasta_log)
        self._definir(
            "ERRO",
            "Algo deu errado. O programa guardou os detalhes.",
            ERRO,
            f"Pasta: {pasta_log}",
        )
        self._botao_pasta.pack(anchor="w", padx=MARGEM, pady=(MARGEM // 2, 0))

    def _abrir_pasta_do_log(self) -> None:
        if self._pasta_log is not None:
            abrir_pasta(self._pasta_log)

    # --- tela de escolha do modo (roda na thread principal, antes do executar) ---

    def escolher_modo(
        self, ao_escolher: Callable[[bool], None], segundos: int = PAUSA_ESCOLHA
    ) -> None:
        """Mostra Automatico x So sugerir. Chama ao_escolher(True) para Automatico e
        ao_escolher(False) para So sugerir. Sem escolha em 'segundos', vale Automatico."""
        self._conteudo.pack_forget()
        tela = tk.Frame(self._raiz, bg=FUNDO)
        tela.pack(fill="both", expand=True, pady=(0, MARGEM))

        self._criar_rotulo(("Segoe UI", 13, "bold"), tela).config(text="Como você quer usar agora?")
        self._criar_rotulo(("Segoe UI", 10, "bold"), tela, DESTAQUE).config(text="AUTOMÁTICO")
        self._criar_rotulo(("Segoe UI", 10), tela).config(
            text="Faz tudo sozinho: lê cada questão, marca a resposta, avança, envia o quiz, "
            "confere o que errou e tenta de novo se não tirar a nota máxima."
        )
        self._criar_rotulo(("Segoe UI", 9, "bold"), tela, AVISO).config(
            text="Atenção: enviar o quiz não tem volta."
        )
        self._criar_rotulo(("Segoe UI", 10, "bold"), tela, DESTAQUE).config(text="SÓ SUGERIR")
        self._criar_rotulo(("Segoe UI", 10), tela).config(
            text="Mostra a sugestão de resposta. Você lê, decide e clica em tudo."
        )
        botoes = tk.Frame(tela, bg=FUNDO)
        botoes.pack(fill="x", padx=MARGEM, pady=(MARGEM, 0))
        contagem = self._criar_rotulo(("Segoe UI", 9), tela, SUAVE)

        estado = {"restante": segundos, "feito": False}

        def escolher(automatico: bool) -> None:
            if estado["feito"]:
                return
            estado["feito"] = True
            tela.destroy()
            self._conteudo.pack(fill="both", expand=True)
            self._posicionar()
            ao_escolher(automatico)

        def tique() -> None:
            if estado["feito"]:
                return
            if estado["restante"] <= 0:
                escolher(True)
                return
            contagem.config(text=f"Sem escolha, começa no Automático em {estado['restante']} s")
            estado["restante"] -= 1
            self._raiz.after(1000, tique)

        self._criar_botao(botoes, "Automático", lambda: escolher(True), DESTAQUE, FUNDO).pack(
            side="left"
        )
        self._criar_botao(botoes, "Só sugerir", lambda: escolher(False), "#374151", TEXTO).pack(
            side="left", padx=(MARGEM // 2, 0)
        )
        self._raiz.update_idletasks()
        self._posicionar(tela.winfo_reqheight() + MARGEM)
        tique()

    # --- interface do Presenter (podem ser chamadas de outra thread) ---

    def mostrar(self, question: Question, suggestion: Suggestion) -> None:
        self._fila.put(lambda: self._exibir(question, suggestion))

    def consultando(self) -> None:
        self._fila.put(self._consultando)

    def avisar(self, mensagem: str) -> None:
        self._fila.put(lambda: self._aviso(mensagem))

    def erro_inesperado(self, pasta_log: str) -> None:
        self._fila.put(lambda: self._erro(pasta_log))

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
