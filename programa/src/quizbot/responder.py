# RESPONDER - as "maos": executa acoes na pagina.
#
# Responder -> usa o Playwright para clicar nos botoes do quiz.
#              Fica separado do PageReader de proposito: quem le nao clica,
#              e quem clica nao le.
#              - clicar(indice): marca a alternativa de posicao "indice" (0 = primeira)
#                e confere que ficou marcada.
#              - avancar(): aperta o botao "Proxima pagina".
#              - terminar(): na pagina de resumo, aperta "Enviar tudo e terminar" e
#                confirma na janelinha. Envia a tentativa e nao tem volta.
#              Procura em todas as abas e iframes, como o PageReader.
#              Todos devolvem True se deu certo, False se nao deu (o assistente
#              so avanca depois de clicar() devolver True).
#
# Os seletores CSS ficam no config.py.
from playwright.sync_api import BrowserContext
from playwright.sync_api import Error as PlaywrightError

from quizbot.config import (
    SELETOR_BOTAO_PROXIMA,
    SELETOR_CONFIRMAR_FINALIZAR,
    SELETOR_RADIOS,
    TEXTO_BOTAO_FINALIZAR,
)


class Responder:
    def __init__(self, contexto: BrowserContext) -> None:
        self._contexto = contexto

    def clicar(self, indice: int) -> bool:
        for aba in self._contexto.pages:
            for quadro in aba.frames:
                try:
                    radios = quadro.locator(SELETOR_RADIOS)
                    if not 0 <= indice < radios.count():
                        continue
                    alvo = radios.nth(indice)
                    alvo.check(timeout=2000)
                    return alvo.is_checked()
                except PlaywrightError:
                    continue
        return False

    def avancar(self) -> bool:
        for aba in self._contexto.pages:
            for quadro in aba.frames:
                try:
                    botao = quadro.locator(SELETOR_BOTAO_PROXIMA)
                    if botao.count() != 1:
                        continue
                    botao.click(timeout=2000)
                except PlaywrightError:
                    continue
                return True
        return False

    def terminar(self) -> bool:
        for aba in self._contexto.pages:
            for quadro in aba.frames:
                try:
                    botao = quadro.locator("button", has_text=TEXTO_BOTAO_FINALIZAR)
                    if botao.count() != 1:
                        continue
                    botao.click(timeout=2000)
                    quadro.locator(SELETOR_CONFIRMAR_FINALIZAR).click(timeout=5000)
                except PlaywrightError:
                    continue
                return True
        return False
