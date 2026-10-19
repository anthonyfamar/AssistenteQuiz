# CONFIGURAR - janela para colar as chaves de API e escolher os modelos (grava o .env).
#
# abrir_configuracao() -> abre a janela; devolve True se a pessoa clicou em Salvar.
#                         Tambem roda com: python -m quizbot.configurar (ou configurar.bat).
# So a chave de UM provedor e obrigatoria (o Gemini e o recomendado). Os modelos ja vem
# sugeridos e ficam escondidos em "Opcoes avancadas". Se o Chrome e o Edge nao forem
# achados, a janela pede o caminho do navegador.
# Ao salvar, o .env e reescrito: a ORDEM_PROVEDORES que ja existia e mantida.
import re
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, ttk

from dotenv import dotenv_values

from quizbot.chrome import achar_navegador
from quizbot.config import ARQUIVO_ENV, ORDEM_PADRAO, PROVEDORES, Provedor

LARGURA_TEXTO = 560


class JanelaConfiguracao:
    def __init__(self, caminho_env: Path = ARQUIVO_ENV) -> None:
        self._caminho = caminho_env
        self._salvou = False
        self._atuais = dotenv_values(caminho_env) if caminho_env.exists() else {}

        self._raiz = tk.Tk()
        self._raiz.title("AssistenteQuiz - Configuracao")
        self._raiz.resizable(False, False)
        self._raiz.protocol("WM_DELETE_WINDOW", self._raiz.destroy)

        corpo = ttk.Frame(self._raiz, padding=16)
        corpo.pack(fill="both", expand=True)
        ttk.Label(
            corpo, text="Cole a chave de pelo menos um provedor de IA", font=("Segoe UI", 12, "bold")
        ).pack(anchor="w")
        ttk.Label(
            corpo,
            text=(
                "O Gemini e o mais facil: e gratuito e a chave dele ja basta. Clique em "
                "'Como conseguir' para abrir a pagina onde a chave e criada, copie a chave "
                "e cole no campo."
            ),
            wraplength=LARGURA_TEXTO,
            justify="left",
        ).pack(anchor="w", pady=(2, 8))

        self._chaves: dict[str, tk.StringVar] = {}
        self._modelos: dict[str, tk.StringVar] = {}
        self._modelos_visao: dict[str, tk.StringVar] = {}
        self._entradas_chave: list[ttk.Entry] = []
        self._quadros_avancados: list[ttk.Frame] = []
        for provedor in PROVEDORES.values():
            self._criar_bloco(corpo, provedor)

        self._navegador = tk.StringVar(value=self._atuais.get("CAMINHO_NAVEGADOR") or "")
        self._criar_bloco_navegador(corpo)

        opcoes = ttk.Frame(corpo)
        opcoes.pack(fill="x", pady=(8, 0))
        self._mostrar_chaves = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opcoes, text="Mostrar as chaves", variable=self._mostrar_chaves, command=self._alternar_chaves
        ).pack(side="left")
        self._avancado = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opcoes, text="Opcoes avancadas (modelos)", variable=self._avancado, command=self._alternar_avancado
        ).pack(side="left", padx=16)

        self._mensagem = ttk.Label(corpo, foreground="#b91c1c", wraplength=LARGURA_TEXTO, justify="left")
        self._mensagem.pack(anchor="w", pady=(8, 0))

        botoes = ttk.Frame(corpo)
        botoes.pack(fill="x", pady=(8, 0))
        ttk.Button(botoes, text="Salvar", command=self._salvar).pack(side="right")
        ttk.Button(botoes, text="Cancelar", command=self._raiz.destroy).pack(side="right", padx=8)

        try:
            self._raiz.eval("tk::PlaceWindow . center")
        except tk.TclError:
            pass

    # --- montagem da janela ---

    def _criar_bloco(self, pai: ttk.Frame, provedor: Provedor) -> None:
        quadro = ttk.LabelFrame(pai, text=provedor.rotulo, padding=8)
        quadro.pack(fill="x", pady=4)
        ttk.Label(quadro, text=provedor.dica, wraplength=LARGURA_TEXTO - 20, justify="left").pack(anchor="w")

        linha = ttk.Frame(quadro)
        linha.pack(fill="x", pady=(4, 0))
        chave = tk.StringVar(value=self._atuais.get(provedor.chave_env) or "")
        entrada = ttk.Entry(linha, textvariable=chave, show="*", width=54)
        entrada.pack(side="left")
        ttk.Button(
            linha, text="Como conseguir", command=lambda url=provedor.url_chave: webbrowser.open(url)
        ).pack(side="left", padx=(8, 0))
        self._chaves[provedor.nome] = chave
        self._entradas_chave.append(entrada)

        modelo = tk.StringVar(value=self._atuais.get(provedor.modelo_env) or provedor.modelo_sugerido)
        if provedor.modelo_visao_env in self._atuais:
            visao = tk.StringVar(value=self._atuais[provedor.modelo_visao_env] or "")
        else:
            visao = tk.StringVar(value=provedor.modelo_visao_sugerido)
        self._modelos[provedor.nome] = modelo
        self._modelos_visao[provedor.nome] = visao

        avancado = ttk.Frame(quadro)
        ttk.Label(avancado, text="Modelo (so texto):").grid(row=0, column=0, sticky="w")
        ttk.Entry(avancado, textvariable=modelo, width=40).grid(row=0, column=1, padx=6, pady=2)
        ttk.Label(avancado, text="Modelo (com imagem):").grid(row=1, column=0, sticky="w")
        ttk.Entry(avancado, textvariable=visao, width=40).grid(row=1, column=1, padx=6, pady=2)
        self._quadros_avancados.append(avancado)

    def _criar_bloco_navegador(self, pai: ttk.Frame) -> None:
        manual = self._navegador.get().strip().strip('"')
        if achar_navegador() is not None or (manual and Path(manual).exists()):
            return
        quadro = ttk.LabelFrame(pai, text="Navegador", padding=8)
        quadro.pack(fill="x", pady=4)
        ttk.Label(
            quadro,
            text=(
                "Nao encontrei o Chrome nem o Edge neste computador. Indique onde o navegador "
                "esta (o arquivo chrome.exe ou msedge.exe)."
            ),
            wraplength=LARGURA_TEXTO - 20,
            justify="left",
        ).pack(anchor="w")
        linha = ttk.Frame(quadro)
        linha.pack(fill="x", pady=(4, 0))
        ttk.Entry(linha, textvariable=self._navegador, width=54).pack(side="left")
        ttk.Button(linha, text="Procurar...", command=self._procurar_navegador).pack(side="left", padx=(8, 0))

    def _procurar_navegador(self) -> None:
        caminho = filedialog.askopenfilename(title="Onde esta o navegador?", filetypes=[("Programa", "*.exe")])
        if caminho:
            self._navegador.set(caminho)

    def _alternar_chaves(self) -> None:
        for entrada in self._entradas_chave:
            entrada.config(show="" if self._mostrar_chaves.get() else "*")

    def _alternar_avancado(self) -> None:
        for quadro in self._quadros_avancados:
            if self._avancado.get():
                quadro.pack(fill="x", pady=(6, 0))
            else:
                quadro.pack_forget()

    # --- gravar o .env ---

    def _erro(self, texto: str) -> None:
        self._mensagem.config(text=texto)

    @staticmethod
    def _validar(provedor: Provedor, chave: str, modelo: str, visao: str) -> str | None:
        if re.search(r"[\s#'\"]", chave):
            return f"A chave de {provedor.rotulo} tem um caractere invalido (espaco, aspas ou #). Copie de novo, so a chave."
        for nome in (modelo, visao):
            if not re.fullmatch(r"[\w./:\-]*", nome):
                return f"O nome do modelo '{nome}' ({provedor.rotulo}) tem caracteres invalidos."
            if provedor.so_free and nome and not nome.endswith(":free"):
                return (
                    f"Em {provedor.rotulo}, os modelos precisam terminar em ':free' "
                    "(assim nada e cobrado). Corrija o nome nas opcoes avancadas."
                )
        return None

    def _salvar(self) -> None:
        ordem = self._atuais.get("ORDEM_PROVEDORES") or ORDEM_PADRAO
        linhas = [
            "# Gerado pela janela de configuracao do AssistenteQuiz. Pode editar na mao se quiser.",
            f"ORDEM_PROVEDORES={ordem}",
        ]
        ativos = 0
        for provedor in PROVEDORES.values():
            chave = self._chaves[provedor.nome].get().strip()
            modelo = self._modelos[provedor.nome].get().strip() or provedor.modelo_sugerido
            visao = self._modelos_visao[provedor.nome].get().strip()
            if chave:
                erro = self._validar(provedor, chave, modelo, visao)
                if erro:
                    self._erro(erro)
                    return
                ativos += 1
            linhas += [
                "",
                f"# {provedor.rotulo}",
                f"{provedor.chave_env}={chave}",
                f"{provedor.modelo_env}={modelo}",
                f"{provedor.modelo_visao_env}={visao}",
            ]
        if ativos == 0:
            self._erro("Cole a chave de pelo menos um provedor. O Gemini e o mais facil.")
            return

        navegador = self._navegador.get().strip().strip('"')
        if navegador:
            linhas += ["", "# Navegador (so se o Chrome e o Edge nao foram achados sozinhos)", f"CAMINHO_NAVEGADOR={navegador}"]

        self._caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        self._salvou = True
        self._raiz.destroy()

    def executar(self) -> bool:
        self._raiz.mainloop()
        return self._salvou


def abrir_configuracao(caminho_env: Path = ARQUIVO_ENV) -> bool:
    try:  # nitidez em telas de alta resolucao (Windows)
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    return JanelaConfiguracao(caminho_env).executar()


if __name__ == "__main__":
    raise SystemExit(0 if abrir_configuracao() else 1)
