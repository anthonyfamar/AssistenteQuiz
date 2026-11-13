# RESPONDER - as "maos": executa acoes na pagina.
#
# Responder -> usa o Playwright para clicar nos botoes do quiz.
#              Fica separado do PageReader de proposito: quem le nao clica,
#              e quem clica nao le.
#              - clicar(indice): marca a alternativa de posicao "indice" (0 = primeira)
#                e confere que ficou marcada.
#              - avancar(): aperta o botao "Proxima pagina".
#              - abrir_questao(numero): na pagina de resumo, clica no numero de uma questao
#                (abre a pagina dela, para responder as que ficaram sem resposta).
#              - terminar(): na pagina de resumo, aperta "Enviar tudo e terminar" e
#                confirma na janelinha. Envia a tentativa e nao tem volta.
#              - terminar_revisao(): na pagina de revisao, aperta "Terminar revisao"
#                (volta para a pagina inicial do quiz).
#              - abrir_revisao(numero): na pagina inicial do quiz, clica no link "Revisao" da
#                linha da tentativa de numero N (para o programa ler e guardar as certas e erradas).
#              - iniciar_tentativa(): na pagina inicial do quiz, aperta o botao que houver
#                entre "Tentar responder o questionario agora", "Continuar a ultima
#                tentativa" e "Fazer uma outra tentativa".
#              - voltar_ao_curso(): aperta "Voltar ao curso" (quando acabaram as tentativas);
#                se o botao nao existe (nota maxima de primeira), clica no link do curso no
#                breadcrumb do topo; so em ultimo caso volta pelo historico do navegador.
#              - abrir_unidade(nome) / abrir_atividade(nome): no curso, clica numa unidade do
#                menu e, dentro dela, num dos quizzes.
#              Procura em todas as abas e iframes, como o PageReader.
#              Todos devolvem True se deu certo, False se nao deu (o assistente
#              so avanca depois de clicar() devolver True).
#
# Cliques: por padrao (CLIQUE_PELO_DOM, no config.py) clica DENTRO da pagina (el.click()), que
# funciona com a janela minimizada e nao espera confirmacao do navegador; _marcar() faz o mesmo
# para as alternativas e confere que ficou marcada. Com CLIQUE_PELO_DOM = False volta ao clique de
# mouse do Playwright. Os cliques que falham ficam no registro como "[clique]".
#
# Os seletores CSS ficam no config.py.
import re

from playwright.sync_api import BrowserContext, Locator
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from quizbot.config import (
    CLIQUE_PELO_DOM,
    FRAGMENTO_URL_CURSO,
    MAX_VOLTAS_NO_HISTORICO,
    SELETOR_BOTAO_PROXIMA,
    SELETOR_BOTAO_TERMINAR_REVISAO,
    SELETOR_CONFIRMAR_FINALIZAR,
    SELETOR_LINK_ATIVIDADE,
    SELETOR_LINK_CURSO,
    SELETOR_LINK_SECAO,
    SELETOR_LINK_UNIDADE,
    SELETOR_RADIOS,
    SELETOR_TABELA_RESUMO,
    SELETOR_TABELA_TENTATIVAS,
    TEXTO_BOTAO_COMECAR,
    TEXTO_BOTAO_CONTINUAR,
    TEXTO_BOTAO_FINALIZAR,
    TEXTO_BOTAO_OUTRA,
    TEXTO_BOTAO_TERMINAR_REVISAO,
    TEXTO_BOTAO_VOLTAR,
    TEXTO_LINK_REVISAO,
)


def _pagina_oculta(alvo: Locator) -> bool:
    # Janela minimizada (ou aba em segundo plano): o navegador marca a pagina como oculta.
    try:
        return alvo.evaluate("el => el.ownerDocument.visibilityState === 'hidden'", timeout=1000)
    except PlaywrightError:
        return False


# Clica DENTRO da pagina (el.click()), sem mouse simulado. Se o elemento estiver desabilitado, nao
# clica e devolve false (o programa trata como falha, em vez de achar que deu certo).
_JS_CLICAR = """
el => {
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
    el.click();
    return true;
}
"""
# Marca a bolinha (radio) so se ainda nao estiver marcada.
_JS_MARCAR = "el => { if (!el.checked) el.click(); return el.checked; }"


def _clicar(alvo: Locator, timeout: int = 2000) -> None:
    # Padrao (CLIQUE_PELO_DOM): clica dentro da pagina. O clique de mouse do Playwright depende de o
    # navegador desenhar a janela e confirmar o evento; com a janela MINIMIZADA a confirmacao
    # demora, o clique (que ja tinha dado certo) virava "tempo esgotado" e o programa achava
    # que tinha falhado. Clicar pelo DOM nao tem essa espera e acontece uma vez so.
    if CLIQUE_PELO_DOM:
        try:
            if not alvo.evaluate(_JS_CLICAR, timeout=timeout):
                raise PlaywrightError("o elemento esta desabilitado")
        except PlaywrightError as erro:
            print(f"[clique] nao consegui clicar pelo DOM: {str(erro).splitlines()[0]}")
            raise
        return
    _clicar_com_mouse(alvo, timeout)


def _marcar(alvo: Locator, timeout: int = 2000) -> None:
    # Marca uma bolinha (radio). Pelo DOM (padrao) e confere que ficou marcada.
    if CLIQUE_PELO_DOM:
        try:
            if not alvo.evaluate(_JS_MARCAR, timeout=timeout):
                raise PlaywrightError("a alternativa nao ficou marcada")
        except PlaywrightError as erro:
            print(f"[clique] nao consegui marcar pelo DOM: {str(erro).splitlines()[0]}")
            raise
        return
    _marcar_com_mouse(alvo, timeout)


def _clicar_com_mouse(alvo: Locator, timeout: int = 2000) -> None:
    # (CLIQUE_PELO_DOM = False) Clique de mouse do Playwright. no_wait_after: nao espera a pagina
    # nova carregar (site lento nao vira falso erro). Se esgotar o tempo com a pagina OCULTA,
    # clica pelo proprio DOM.
    try:
        alvo.click(timeout=timeout, no_wait_after=True)
    except PlaywrightTimeoutError as erro:
        if not _pagina_oculta(alvo):
            print(f"[clique] o clique nao terminou em {timeout / 1000:.0f} s: {str(erro).splitlines()[0]}")
            raise
        print("[clique] pagina oculta (janela minimizada?): cliquei pelo DOM.")
        alvo.evaluate("el => el.click()", timeout=timeout)


def _marcar_com_mouse(alvo: Locator, timeout: int = 2000) -> None:
    # (CLIQUE_PELO_DOM = False) Marca uma bolinha com o clique de mouse, com a mesma saida para
    # pagina oculta.
    try:
        alvo.check(timeout=timeout)
    except PlaywrightTimeoutError as erro:
        if not _pagina_oculta(alvo):
            print(f"[clique] a marcacao nao terminou em {timeout / 1000:.0f} s: {str(erro).splitlines()[0]}")
            raise
        print("[clique] pagina oculta (janela minimizada?): marquei pelo DOM.")
        alvo.evaluate("el => el.click()", timeout=timeout)


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
                    _marcar(alvo)
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
                    _clicar(botao)
                except PlaywrightError:
                    continue
                return True
        return False

    def abrir_questao(self, numero: int) -> bool:
        # Na pagina de resumo: clica no numero da questao (um link) e abre a pagina dela.
        # "tr.quizsummaryN": a classe e um item inteiro, entao o 1 nao pega o 10.
        seletor = f"{SELETOR_TABELA_RESUMO} tr.quizsummary{numero} a"
        for aba in self._contexto.pages:
            for quadro in aba.frames:
                try:
                    link = quadro.locator(seletor)
                    if link.count() != 1:
                        continue
                    _clicar(link)
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
                    _clicar(botao)
                    _clicar(quadro.locator(SELETOR_CONFIRMAR_FINALIZAR), 5000)
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
                    _clicar(botao)
                except PlaywrightError:
                    continue
                return True
        return False

    def iniciar_tentativa(self) -> bool:
        textos = (TEXTO_BOTAO_CONTINUAR, TEXTO_BOTAO_COMECAR, TEXTO_BOTAO_OUTRA)
        return any(self._clicar_botao(texto) for texto in textos)

    def abrir_revisao(self, numero: int) -> bool:
        # Acha a linha da tabela de tentativas cuja primeira celula e o numero pedido e clica no link
        # "Revisao" DELA (nunca no de outra linha). False se a tabela, a linha ou o link nao existirem.
        for aba in self._contexto.pages:
            for quadro in aba.frames:
                try:
                    linhas = quadro.locator(SELETOR_TABELA_TENTATIVAS).locator("tbody tr")
                    for i in range(linhas.count()):
                        linha = linhas.nth(i)
                        primeira = linha.locator("td").first.inner_text(timeout=2000)
                        if not re.fullmatch(rf"\s*{numero}\s*", primeira):
                            continue
                        link = linha.locator("a", has_text=re.compile(rf"^\s*{TEXTO_LINK_REVISAO}\s*$"))
                        if link.count() != 1:
                            return False
                        _clicar(link)
                        return True
                except PlaywrightError:
                    continue
        return False

    def voltar_ao_curso(self) -> bool:
        # Sem mais tentativas o Moodle mostra o botao "Voltar ao curso". Com tentativas
        # sobrando (nota maxima de primeira) o botao nao existe: clica no link do curso no
        # "caminho" do topo da pagina (breadcrumb). So se nem ele existir, volta pelo
        # historico do navegador (lento: passa por cada pagina de questao).
        if self._clicar_botao(TEXTO_BOTAO_VOLTAR):
            return True
        if self._clicar_link(SELETOR_LINK_CURSO):
            return True
        return self._voltar_pelo_historico()

    def abrir_unidade(self, nome: str) -> bool:
        # No curso: clica no nome da unidade no menu.
        return self._clicar_link(SELETOR_LINK_UNIDADE, nome)

    def abrir_secao(self, nome: str, unidade: str | None = None) -> bool:
        # Nos cursos com secoes: entra na unidade (abre o submenu, como o usuario faria) e clica
        # no nome da secao ("U3 - Secao 2"). So abre a unidade se a secao estiver escondida: clicar
        # no titulo de uma unidade ja aberta a fecharia. O clique na secao e pelo DOM, que
        # funciona mesmo se o submenu nao abrir a tempo (e um link comum, so navega).
        if unidade is not None and not self._link_visivel(SELETOR_LINK_SECAO, nome):
            if self._clicar_link(SELETOR_LINK_UNIDADE, unidade):
                self._esperar_submenu(nome)
        return self._clicar_link(SELETOR_LINK_SECAO, nome, so_visivel=False)

    def _link_visivel(self, seletor: str, nome: str) -> bool:
        padrao = re.compile(rf"^\s*{re.escape(nome)}\s*$")
        for aba in self._contexto.pages:
            for quadro in aba.frames:
                try:
                    if quadro.locator(seletor, has_text=padrao).locator("visible=true").count() > 0:
                        return True
                except PlaywrightError:
                    continue
        return False

    def _esperar_submenu(self, nome: str, segundos: float = 1.5) -> None:
        # Dá um instante para a animacao do submenu abrir (sem travar se nao abrir).
        for _ in range(int(segundos / 0.25)):
            if self._link_visivel(SELETOR_LINK_SECAO, nome):
                return
            for aba in self._contexto.pages[:1]:
                try:
                    aba.wait_for_timeout(250)
                except PlaywrightError:
                    return

    def abrir_atividade(self, nome: str) -> bool:
        # Na unidade (ou secao): clica no nome de uma atividade (um dos quizzes).
        return self._clicar_link(SELETOR_LINK_ATIVIDADE, nome)

    def _clicar_link(self, seletor: str, nome: str | None = None, so_visivel: bool = True) -> bool:
        # Clica num link VISIVEL (ou, com so_visivel=False, num link escondido tambem). Com
        # "nome", so no link cujo texto e exatamente esse (o Playwright ignora espacos a mais).
        # O primeiro vale se o menu aparecer repetido.
        padrao = re.compile(rf"^\s*{re.escape(nome)}\s*$") if nome is not None else None
        for aba in self._contexto.pages:
            for quadro in aba.frames:
                try:
                    links = quadro.locator(seletor, has_text=padrao)
                    if so_visivel:
                        links = links.locator("visible=true")
                    if links.count() == 0:
                        continue
                    _clicar(links.first)
                except PlaywrightError:
                    continue
                return True
        return False

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
                    _clicar(link)
                except PlaywrightError:
                    continue
                return True
        return False
