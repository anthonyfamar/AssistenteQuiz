# PAGE READER - os "olhos": le a questao que esta na pagina.
#
# PageReader -> usa o Playwright e seletores CSS para ler o texto (DOM) da pagina.
#               SO LEITURA: a classe nao tem nenhum metodo de clicar ou enviar.
#               Olha todas as abas e todos os iframes do navegador e usa o primeiro
#               que tiver uma questao.
#               ler_questao() devolve uma Question, ou None se nao houver questao
#               (login, menu), e entao o assistente fica quieto.
#               So le quando ha exatamente 1 questao na tela: com varias, nao da
#               para saber de qual sao as alternativas, entao fica quieto.
#
# Os seletores CSS de cada site ficam no config.py.

from playwright.sync_api import BrowserContext, Frame
from playwright.sync_api import Error as PlaywrightError

from quizbot.config import SELETOR_ALTERNATIVAS, SELETOR_ENUNCIADO
from quizbot.models import Question


class NavegadorFechado(Exception):
    """O navegador foi fechado ou desconectado."""


class PageReader:
    def __init__(self, contexto: BrowserContext) -> None:
        self._contexto = contexto

    def _checar_conexao(self) -> None:
        navegador = self._contexto.browser
        if navegador is not None and not navegador.is_connected():
            raise NavegadorFechado("o navegador foi fechado")

    def _quadros(self) -> list[Frame]:
        self._checar_conexao()
        return [quadro for aba in self._contexto.pages for quadro in aba.frames]

    @staticmethod
    def _ler_enunciado(quadro: Frame) -> str | None:
        elemento = quadro.locator(SELETOR_ENUNCIADO)
        if elemento.count() != 1:
            return None
        return elemento.inner_text().strip()

    @staticmethod
    def _ler_alternativas(quadro: Frame) -> tuple[str, ...]:
        elementos = quadro.locator(SELETOR_ALTERNATIVAS)
        textos = elementos.all_inner_texts()
        return tuple(texto.strip() for texto in textos)

    def ler_questao(self) -> Question | None:
        for quadro in self._quadros():
            try:
                enunciado = self._ler_enunciado(quadro)
                alternativas = self._ler_alternativas(quadro)
            except PlaywrightError:
                self._checar_conexao()
                continue
            if enunciado and alternativas:
                return Question(enunciado=enunciado, alternativas=alternativas)
        return None
