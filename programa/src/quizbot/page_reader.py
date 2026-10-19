# PAGE READER - os "olhos": le a questao que esta na pagina.
#
# PageReader -> usa o Playwright e seletores CSS para ler a pagina.
#               SO LEITURA: a classe nao tem nenhum metodo de clicar ou enviar, e a
#               pagina nunca e alterada (o HTML e copiado antes de ser lido).
#               Olha todas as abas e todos os iframes do navegador e usa o primeiro
#               que tiver uma questao.
#               - Formulas (imagens do Wiris) viram texto: x^2, (a)/(b)...
#               - Outras imagens (graficos, figuras) sao baixadas e vao junto da
#                 Question, e no texto aparecem como [imagem 1], [imagem 2]...
#               Tira o "a. " do comeco das alternativas (PADRAO_PREFIXO_ALTERNATIVA).
#               ler_questao() devolve uma Question, ou None se nao houver questao
#               (login, menu), e entao o assistente fica quieto.
#               So le quando ha exatamente 1 questao na tela: com varias, nao da
#               para saber de qual sao as alternativas, entao fica quieto.
#               Se a questao esta na tela mas uma imagem nao pode ser lida, levanta
#               LeituraIncompleta (melhor avisar do que a IA responder sem ver).
#
# Os seletores CSS de cada site ficam no config.py.
import base64
import hashlib
import re

from playwright.sync_api import BrowserContext, Frame
from playwright.sync_api import Error as PlaywrightError

from quizbot.config import (
    MAX_BYTES_IMAGEM,
    PADRAO_PREFIXO_ALTERNATIVA,
    SELETOR_ALTERNATIVAS,
    SELETOR_ENUNCIADO,
)
from quizbot.html_texto import ImagemRef, ResultadoHtml, converter_html
from quizbot.models import Imagem, Question

_PREFIXO = re.compile(PADRAO_PREFIXO_ALTERNATIVA)

# Copia o elemento para um documento "inerte" (que nunca carrega imagens nem roda nada;
# a pagina nao e tocada) e tira o src das imagens de formula, que ja trazem a formula
# escrita e so pesam na viagem.
_JS_COPIA = """
el => {
    const inerte = document.implementation.createHTMLDocument('');
    const copia = inerte.importNode(el, true);
    copia.querySelectorAll('img[data-mathml]').forEach(img => img.removeAttribute('src'));
    return copia.innerHTML;
}
"""
_JS_COPIA_LISTA = "els => els.map(" + _JS_COPIA.strip() + ")"

# Baixa uma imagem usando a sessao do proprio navegador (cookies). Nao rola a pagina.
_JS_BAIXAR = """
async src => {
    const resposta = await fetch(new URL(src, document.baseURI).href, {credentials: 'include'});
    if (!resposta.ok) throw new Error('HTTP ' + resposta.status);
    const blob = await resposta.blob();
    return await new Promise((ok, erro) => {
        const leitor = new FileReader();
        leitor.onload = () => ok(leitor.result);
        leitor.onerror = () => erro(leitor.error);
        leitor.readAsDataURL(blob);
    });
}
"""


class NavegadorFechado(Exception):
    """O navegador foi fechado ou desconectado."""


class LeituraIncompleta(Exception):
    """A questao esta na tela, mas nao deu para le-la por inteiro (ex.: uma imagem)."""


def _tipo_da_imagem(dados: bytes) -> str:
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if dados.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if dados.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("formato de imagem nao suportado")


def _imagem_de_data_url(url: str) -> Imagem:
    achou = re.fullmatch(r"data:[^,;]*;base64,(.+)", url, re.DOTALL)
    if achou is None:
        raise ValueError("imagem em formato inesperado")
    dados = base64.b64decode(achou.group(1))
    if len(dados) > MAX_BYTES_IMAGEM:
        raise ValueError("imagem grande demais")
    return Imagem(dados=dados, tipo=_tipo_da_imagem(dados))


class PageReader:
    def __init__(self, contexto: BrowserContext) -> None:
        self._contexto = contexto
        self._cache_imagens: dict[str, Imagem] = {}

    def _checar_conexao(self) -> None:
        navegador = self._contexto.browser
        if navegador is not None and not navegador.is_connected():
            raise NavegadorFechado("o navegador foi fechado")

    def _quadros(self) -> list[Frame]:
        self._checar_conexao()
        return [quadro for aba in self._contexto.pages for quadro in aba.frames]

    @staticmethod
    def _ler_enunciado(quadro: Frame) -> ResultadoHtml | None:
        elemento = quadro.locator(SELETOR_ENUNCIADO)
        if elemento.count() != 1:
            return None
        return converter_html(elemento.evaluate(_JS_COPIA, timeout=2000))

    @staticmethod
    def _ler_alternativas(quadro: Frame, primeiro: int) -> list[ResultadoHtml]:
        htmls = quadro.locator(SELETOR_ALTERNATIVAS).evaluate_all(_JS_COPIA_LISTA)
        resultados = []
        for html in htmls:
            resultado = converter_html(html, primeiro)
            primeiro += len(resultado.imagens)
            resultados.append(resultado)
        return resultados

    def _baixar(self, quadro: Frame, ref: ImagemRef) -> Imagem:
        chave = hashlib.sha1(ref.src.encode()).hexdigest()
        if chave in self._cache_imagens:
            return self._cache_imagens[chave]

        try:
            if not ref.src:
                raise ValueError("imagem sem endereco")
            url = ref.src if ref.src.startswith("data:") else quadro.evaluate(_JS_BAIXAR, ref.src)
            imagem = _imagem_de_data_url(url)
        except ValueError as erro:
            raise LeituraIncompleta(f"Nao consegui ler a imagem {ref.numero}: {erro}.") from erro
        except PlaywrightError as erro:
            self._checar_conexao()
            raise LeituraIncompleta(f"Nao consegui baixar a imagem {ref.numero} da questao.") from erro

        self._cache_imagens[chave] = imagem
        return imagem

    def _ler_quadro(self, quadro: Frame) -> Question | None:
        enunciado = self._ler_enunciado(quadro)
        if enunciado is None or not enunciado.texto:
            return None
        alternativas = self._ler_alternativas(quadro, primeiro=1 + len(enunciado.imagens))
        if not alternativas:
            return None

        refs = list(enunciado.imagens) + [ref for alt in alternativas for ref in alt.imagens]
        return Question(
            enunciado=enunciado.texto,
            alternativas=tuple(_PREFIXO.sub("", alt.texto) for alt in alternativas),
            imagens=tuple(self._baixar(quadro, ref) for ref in refs),
        )

    def ler_questao(self) -> Question | None:
        for quadro in self._quadros():
            try:
                questao = self._ler_quadro(quadro)
            except PlaywrightError:
                self._checar_conexao()
                continue
            if questao is not None:
                return questao
        return None
