# PAGE READER - os "olhos": le a questao que esta na pagina.
#
# PageReader -> usa o Playwright e seletores CSS para ler o texto (DOM) da pagina.
#               SO LEITURA: a classe nao tem nenhum metodo de clicar ou enviar.
#               ler_questao() devolve uma Question, ou None se a pagina nao tiver
#               questao (login, menu), e entao o assistente fica quieto.
#
# TODO: os seletores CSS de cada site ficam no config.py.

from playwright.sync_api import Page
from quizbot.models import Question

SELETOR_ENUNCIADO = "#enunciado"
SELETOR_ALTERNATIVAS = "#alternativas .alternativa"


class PageReader:
    def __init__(self, page: Page) -> None:
        self._page = page

    def _ler_enunciado(self) -> str | None:
        elemento = self._page.locator(SELETOR_ENUNCIADO)
        if elemento.count() == 0:
            return None
        return elemento.inner_text().strip()

    def _ler_alternativas(self) -> tuple[str, ...]:
        elementos = self._page.locator(SELETOR_ALTERNATIVAS)
        textos = elementos.all_inner_texts()
        return tuple(texto.strip() for texto in textos)

    def ler_questao(self) -> Question | None:
        enunciado = self._ler_enunciado()
        alternativas = self._ler_alternativas()
        if not enunciado or not alternativas:
            return None
        return Question(enunciado=enunciado, alternativas=alternativas)