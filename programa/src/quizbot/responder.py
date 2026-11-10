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
#              - terminar_revisao(): na pagina de revisao, aperta "Terminar revisao"
#                (volta para a pagina inicial do quiz).
#              - iniciar_tentativa(): na pagina inicial do quiz, aperta o botao que houver
#                entre "Tentar responder o questionario agora", "Continuar a ultima
#                tentativa" e "Fazer uma outra tentativa".
#              - voltar_ao_curso(): aperta "Voltar ao curso" (quando acabaram as tentativas);
#                se o botao nao existe (nota maxima de primeira), volta pelo historico do
#                navegador ate a pagina do curso.
#              Procura em todas as abas e iframes, como o PageReader.
#              Todos devolvem True se deu certo, False se nao deu (o assistente
#              so avanca depois de clicar() devolver True).
#
# Os seletores CSS ficam no config.py.
from playwright.sync_api import BrowserContext
from playwright.sync_api import Error as PlaywrightError

from quizbot.config import (
    FRAGMENTO_URL_CURSO,
    MAX_VOLTAS_NO_HISTORICO,
    SELETOR_BOTAO_PROXIMA,
    SELETOR_BOTAO_TERMINAR_REVISAO,
    SELETOR_CONFIRMAR_FINALIZAR,
    SELETOR_RADIOS,
    SELETOR_TABELA_TENTATIVAS,
    TEXTO_BOTAO_COMECAR,
    TEXTO_BOTAO_CONTINUAR,
    TEXTO_BOTAO_FINALIZAR,
    TEXTO_BOTAO_OUTRA,
    TEXTO_BOTAO_TERMINAR_REVISAO,
    TEXTO_BOTAO_VOLTAR,
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

    def _clicar_botao(self, texto: str) -> bool:
        for aba in self._contexto.pages:
            for quadro in aba.frames:
                try:
                    botao = quadro.locator("button", has_text=texto)
                    if botao.count() != 1:
                        continue
                    botao.click(timeout=2000)
                except PlaywrightError:
                    continue
                return True
        return False

    def iniciar_tentativa(self) -> bool:
        textos = (TEXTO_BOTAO_CONTINUAR, TEXTO_BOTAO_COMECAR, TEXTO_BOTAO_OUTRA)
        return any(self._clicar_botao(texto) for texto in textos)

    def voltar_ao_curso(self) -> bool:
        # Sem mais tentativas o Moodle mostra o botao "Voltar ao curso". Com tentativas
        # sobrando (nota maxima de primeira) o botao nao existe: volta pelo historico.
        if self._clicar_botao(TEXTO_BOTAO_VOLTAR):
            return True
        return self._voltar_pelo_historico()

    def _voltar_pelo_historico(self) -> bool:
        # Aperta a "seta de voltar" do navegador, na aba onde esta a pagina inicial do quiz,
        # ate chegar a pagina do curso. Paginas de questao ja enviadas e de revisao so
        # redirecionam, entao voltar por elas e seguro. go_back() devolve None quando nao
        # ha mais para onde voltar.
        for aba in self._contexto.pages:
            try:
                if not any(q.locator(SELETOR_TABELA_TENTATIVAS).count() == 1 for q in aba.frames):
                    continue
                inicio = aba.url
                for _ in range(MAX_VOLTAS_NO_HISTORICO):
                    if FRAGMENTO_URL_CURSO in aba.url:
                        return True
                    if aba.go_back(timeout=10000) is None:
                        break
                # Nao achou o curso: volta para a pagina do quiz em vez de largar o usuario
                # numa pagina qualquer do historico (ou numa aba em branco).
                aba.goto(inicio, timeout=10000)
                return False
            except PlaywrightError:
                continue
        return False

    def terminar_revisao(self) -> bool:
        for aba in self._contexto.pages:
            for quadro in aba.frames:
                try:
                    # So conta o link VISIVEL: o Moodle repete o link escondido no menu lateral
                    # do quiz (0x0 px), que o usuario nao ve e nao deve ser clicado.
                    link = quadro.locator(
                        SELETOR_BOTAO_TERMINAR_REVISAO, has_text=TEXTO_BOTAO_TERMINAR_REVISAO
                    ).locator("visible=true")
                    if link.count() != 1:
                        continue
                    link.click(timeout=2000)
                except PlaywrightError:
                    continue
                return True
        return False
