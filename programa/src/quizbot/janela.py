# JANELA - presenter que mostra a sugestao numa janelinha (tkinter).
#
# JanelaPresenter -> janela pequena, sempre por cima, no canto inferior direito.
#                    Mostra "C - texto da alternativa" e a explicacao curta.
#                    Estados: aguardando, consultando a IA, sugestao, aviso e erro.
#                    Antes de tudo, escolher_modo() mostra a tela de escolha (Automatico ou
#                    So sugerir) e, se ninguem escolher, comeca no Automatico sozinha.
#                    No erro inesperado mostra a pasta do registro e um botao para abri-la.
#                    Se um provedor de IA falhar, mostra um alerta simples no rodape por alguns
#                    segundos (SEGUNDOS_ALERTA) e o apaga sozinho; os detalhes ficam so no
#                    registro, para o desenvolvedor.
#                    Se estiver minimizada, a janela volta sozinha para a frente quando precisa de
#                    quem esta usando (a pergunta do fim do curso, a parada por erro, uma acao que
#                    falhou). Se marcar ou avancar falhar, a sugestao CONTINUA na tela e aparece
#                    o botao "Tentar de novo" (oferecer_tentar_de_novo).
#                    Ao fim do curso, perguntar_outra_materia() mostra dois botoes ("Outra
#                    materia" e "Encerrar") e espera o clique de quem esta usando.
#                    Todo aviso fica pelo menos SEGUNDOS_ALERTA na tela para dar tempo de ler;
#                    a consulta nunca espera: o letreiro "Consultando a IA..." entra depois do
#                    aviso, mas uma linha sob o aviso ja diz que a IA esta trabalhando, e a
#                    sugestao aparece na hora.
#
# Threads: o tkinter so pode ser mexido pela thread principal, mas o assistente roda
# em outra. Por isso mostrar(), consultando() e avisar() so colocam o trabalho numa
# fila; a janela esvazia a fila de tempos em tempos (veja executar()).
import queue
import threading
import time
import tkinter as tk
from collections.abc import Callable
from string import ascii_uppercase

from pathlib import Path

from quizbot.config import PASTA_LOGS, PAUSA_ESCOLHA, SEGUNDOS_ALERTA
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
        self._pasta_log: Path = PASTA_LOGS

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
        # Alerta (provedor de IA com problema): nao e apagado quando a sugestao muda; some sozinho.
        # O botao da pasta do registro so aparece na tela de erro inesperado.
        self._alerta = self._criar_rotulo(("Segoe UI", 9, "bold"), cor=AVISO)
        self._botao_pasta = self._criar_botao(
            self._conteudo, "Abrir a pasta", self._abrir_pasta_do_log, DESTAQUE, FUNDO
        )
        # Pergunta do fim do curso ("Outra materia" ou "Encerrar"): os dois botoes ficam num quadro
        # que so aparece quando o assistente pergunta (veja perguntar_outra_materia).
        self._pergunta = tk.Frame(self._conteudo, bg=FUNDO)
        self._criar_botao(
            self._pergunta, "Outra matéria", lambda: self._responder_pergunta(True), DESTAQUE, FUNDO
        ).pack(side="left")
        self._criar_botao(
            self._pergunta, "Encerrar", lambda: self._responder_pergunta(False), "#374151", TEXTO
        ).pack(side="left", padx=(MARGEM // 2, 0))
        self._pergunta_visivel = False
        self._entregar_resposta: Callable[[bool], None] | None = None
        self._fechada = False
        # Falha ao marcar/avancar: a mensagem e o botao "Tentar de novo" ficam abaixo da sugestao
        # (que NAO e apagada). Somem quando a questao muda.
        self._aviso_acao = self._criar_rotulo(("Segoe UI", 9, "bold"), cor=AVISO)
        self._botao_repetir = self._criar_botao(
            self._conteudo, "Tentar de novo", self._clicou_repetir, DESTAQUE, FUNDO
        )
        self._repetir_visivel = False
        self._tentar_de_novo: Callable[[], None] | None = None
        self._alerta_visivel = False
        self._timer_alerta: str | None = None  # id do after() que apaga o alerta
        self._livre_em = 0.0  # ate quando o aviso atual fica na tela (time.monotonic)
        self._pendentes: list[tuple[Callable[[], None], bool]] = []  # esperando a vez
        self._timer_pendentes: str | None = None
        self._em_erro = False
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
        self._em_erro = False
        self._pergunta_visivel = False
        self._repetir_visivel = False
        self._atualizar_rodape()

    def _atualizar_rodape(self) -> None:
        # A pergunta, a falha da acao (com "Tentar de novo"), o alerta e o botao ficam sempre no
        # fim, nesta ordem. So aparecem quando ha motivo: a pergunta, ao fim do curso; a falha, se
        # nao deu para marcar/avancar; o alerta, se algum provedor de IA falhou; o botao da pasta,
        # so no erro inesperado.
        self._pergunta.pack_forget()
        self._aviso_acao.pack_forget()
        self._botao_repetir.pack_forget()
        self._alerta.pack_forget()
        self._botao_pasta.pack_forget()
        if self._pergunta_visivel:
            self._pergunta.pack(anchor="w", padx=MARGEM, pady=(MARGEM // 2, 0))
        if self._repetir_visivel:
            self._aviso_acao.pack(fill="x", padx=MARGEM, pady=(MARGEM // 2, 0))
            self._botao_repetir.pack(anchor="w", padx=MARGEM, pady=(MARGEM // 2, 0))
        if self._alerta_visivel:
            self._alerta.pack(fill="x", padx=MARGEM, pady=(MARGEM // 2, 0))
        if self._em_erro:
            self._botao_pasta.pack(anchor="w", padx=MARGEM, pady=(MARGEM // 2, 0))
        self._ajustar_altura()

    def _ajustar_altura(self) -> None:
        # A janela tem altura fixa (ALTURA), mas cresce o necessario se o conteudo (sugestao
        # longa mais o alerta de provedor) nao couber, para nada ficar cortado.
        if not self._conteudo.winfo_manager():  # tela de escolha do modo no lugar
            return
        self._raiz.update_idletasks()
        self._posicionar(max(ALTURA, self._conteudo.winfo_reqheight() + MARGEM // 2))

    # --- estados (rodam sempre na thread principal) ---

    def _esperando(self) -> None:
        self._definir("AGUARDANDO", "Aguardando questão…", SUAVE)

    def _consultando(self) -> None:
        self._definir("CONSULTANDO", "Consultando a IA…", SUAVE)

    def _exibir(self, question: Question, suggestion: Suggestion) -> None:
        self._furar_a_fila()
        letra = ascii_uppercase[suggestion.indice]
        if 0 <= suggestion.indice < len(question.alternativas):
            principal = f"{letra} - {question.alternativas[suggestion.indice]}"
        else:
            principal = letra
        rodape = f"Respondido por: {suggestion.origem}" if suggestion.origem else ""
        self._definir("SUGESTÃO", principal, DESTAQUE, suggestion.explicacao, rodape)

    def _aviso(self, mensagem: str) -> None:
        self._definir("AVISO", mensagem, AVISO)

    # --- tempo minimo dos avisos (para dar tempo de ler) ---
    # Um aviso fica SEGUNDOS_ALERTA na tela. Estados "sem pressa" (o letreiro "Consultando a
    # IA...") e outros avisos esperam a vez numa fila e entram depois. A sugestao e o erro
    # inesperado furam a fila: aparecem na hora (a consulta em si nunca espera por isso).

    def _pedir_consultando(self) -> None:
        # A consulta ja comecou. Se ha um aviso na tela, o letreiro grande espera a vez, mas
        # uma linha pequena sob o aviso ja diz que a IA esta trabalhando (os dois ficam visiveis).
        if time.monotonic() < self._livre_em or self._pendentes:
            self._explicacao.config(text="Consultando a IA…")
            self._ajustar_altura()
        self._segurar(self._consultando)

    def _segurar(self, tarefa: Callable[[], None], e_aviso: bool = False) -> None:
        if time.monotonic() >= self._livre_em and not self._pendentes:
            self._executar(tarefa, e_aviso)
        else:
            self._pendentes.append((tarefa, e_aviso))
            self._agendar_pendentes()

    def _executar(self, tarefa: Callable[[], None], e_aviso: bool) -> None:
        tarefa()
        if e_aviso:
            self._livre_em = time.monotonic() + SEGUNDOS_ALERTA

    def _agendar_pendentes(self) -> None:
        if self._timer_pendentes is None:
            falta = max(0.0, self._livre_em - time.monotonic())
            self._timer_pendentes = self._raiz.after(int(falta * 1000) + 20, self._soltar_pendente)

    def _soltar_pendente(self) -> None:
        self._timer_pendentes = None
        if self._pendentes:
            tarefa, e_aviso = self._pendentes.pop(0)
            self._executar(tarefa, e_aviso)
        if self._pendentes:
            self._agendar_pendentes()

    def _trazer_para_a_frente(self) -> None:
        # Com a janela minimizada ninguem veria a pergunta nem o aviso de parada: restaura.
        try:
            if self._raiz.state() == "iconic":
                self._raiz.deiconify()
            self._raiz.lift()
        except tk.TclError:  # a janela ja foi fechada
            pass

    def _mostrar_repeticao(self, mensagem: str, tentar: Callable[[], None]) -> None:
        # NAO usa _definir: a sugestao que ja esta na tela continua la. So acrescenta a mensagem e o
        # botao, e traz a janela para a frente (se estiver minimizada, e quando o usuario precisa).
        self._aviso_acao.config(text="⚠ " + mensagem)
        self._tentar_de_novo = tentar
        self._repetir_visivel = True
        self._atualizar_rodape()
        self._trazer_para_a_frente()

    def _clicou_repetir(self) -> None:
        tentar, self._tentar_de_novo = self._tentar_de_novo, None
        if tentar is None:  # clique repetido
            return
        self._repetir_visivel = False
        self._atualizar_rodape()
        tentar()  # so avisa o assistente; quem repete e a thread dele

    def _mostrar_pergunta(self, entregar: Callable[[bool], None]) -> None:
        self._trazer_para_a_frente()
        self._entregar_resposta = entregar
        self._definir(
            "CURSO CONCLUÍDO",
            "Quer conferir outra matéria?",
            DESTAQUE,
            "Outra matéria: abra a matéria no navegador e eu confiro de novo. "
            "Encerrar: fecho o programa.",
        )
        self._pergunta_visivel = True
        self._atualizar_rodape()

    def _responder_pergunta(self, outra_materia: bool) -> None:
        entregar, self._entregar_resposta = self._entregar_resposta, None
        if entregar is None:  # clique repetido
            return
        if outra_materia:
            self._definir("AGUARDANDO", "Abra a outra matéria no navegador.", SUAVE)
        else:
            self._definir("ENCERRANDO", "Até a próxima!", SUAVE)
            self._raiz.after(1200, self._fechar)
        entregar(outra_materia)

    def _furar_a_fila(self) -> None:
        # A sugestao (ou o erro) aparece agora: esquece o que esperava a vez.
        if self._timer_pendentes is not None:
            self._raiz.after_cancel(self._timer_pendentes)
            self._timer_pendentes = None
        self._pendentes.clear()
        self._livre_em = 0.0

    def _erro(self, pasta_log: str) -> None:
        self._furar_a_fila()
        self._trazer_para_a_frente()
        self._pasta_log = Path(pasta_log)
        self._definir(
            "ERRO",
            "Algo deu errado. O programa guardou os detalhes.",
            ERRO,
            f"Pasta: {pasta_log}",
        )
        self._em_erro = True
        self._atualizar_rodape()

    def _mostrar_problemas(self, problemas: list[str]) -> None:
        # O alerta aparece quando uma consulta falha e some sozinho depois de alguns segundos.
        if self._timer_alerta is not None:
            self._raiz.after_cancel(self._timer_alerta)
            self._timer_alerta = None
        self._alerta_visivel = bool(problemas)
        if problemas:
            self._alerta.config(text="⚠ " + "\n⚠ ".join(problemas))
            self._timer_alerta = self._raiz.after(
                SEGUNDOS_ALERTA * 1000, lambda: self._mostrar_problemas([])
            )
        self._atualizar_rodape()

    def _abrir_pasta_do_log(self) -> None:
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
            "confere o que errou, tenta de novo se não tirar a nota máxima e percorre "
            "as unidades do curso, fazendo os quizzes de cada uma."
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
        self._fila.put(self._pedir_consultando)

    def avisar(self, mensagem: str) -> None:
        # Tambem vai para o registro: o aviso fica poucos segundos na janela, o log guarda o que foi.
        print(f"[aviso] {mensagem}")
        self._fila.put(lambda: self._segurar(lambda: self._aviso(mensagem), True))

    def erro_inesperado(self, pasta_log: str) -> None:
        self._fila.put(lambda: self._erro(pasta_log))

    def problemas_nos_provedores(self, problemas: list[str]) -> None:
        self._fila.put(lambda: self._mostrar_problemas(problemas))

    def oferecer_tentar_de_novo(self, mensagem: str, tentar: Callable[[], None]) -> None:
        print(f"[aviso] {mensagem}")
        self._fila.put(lambda: self._mostrar_repeticao(mensagem, tentar))

    def chamar_atencao(self) -> None:
        self._fila.put(self._trazer_para_a_frente)

    def perguntar_outra_materia(self, esperar: Callable[[float], bool] | None = None) -> bool:
        # Roda na thread do assistente: mostra a pergunta (depois do aviso que estiver na tela)
        # e espera o clique. Se a janela for fechada enquanto espera, devolve False (encerrar).
        # `esperar` mantem o navegador sendo atendido enquanto isso (a pagina nao pode ficar parada).
        resposta: dict[str, bool] = {}
        pronta = threading.Event()

        def entregar(valor: bool) -> None:
            resposta["valor"] = valor
            pronta.set()

        self._fila.put(lambda: self._segurar(lambda: self._mostrar_pergunta(entregar)))
        while not pronta.is_set():
            if self._fechada:
                return False
            if esperar is None:
                pronta.wait(0.2)
            elif esperar(0.2):  # pediram para parar (ex.: o programa esta sendo encerrado)
                return False
        return resposta["valor"]

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
        if self._fechada:
            return
        self._fechada = True
        if self._ao_fechar is not None:
            self._ao_fechar()
        self._raiz.destroy()
