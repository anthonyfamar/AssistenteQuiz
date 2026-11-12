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
#               ler_revisao() -> na pagina de REVISAO (depois de enviar), le todas as
#               questoes que o Moodle marcou como certas/erradas e devolve uma lista de
#               Resultado (questao + alternativa marcada + acertou). Lista vazia se a
#               pagina nao for uma revisao. Uma questao cuja imagem nao pode ser lida
#               e pulada (nao vale chutar a chave dela).
#               ler_resumo() -> na pagina de RESUMO (antes de enviar), le a tabela com cada
#               questao e se ja foi respondida (ResumoTentativa); None se nao for essa pagina.
#               ler_menu() / ler_unidade() / ler_caminho() -> o CURSO: o menu das unidades (nome e
#               barra de progresso), a unidade aberta (h1 e atividades feitas ou nao) e o
#               breadcrumb de uma pagina de quiz (unidade e nome do quiz). O menu so conta em
#               pagina que NAO e de atividade (endereco sem "/mod/"): ele aparece tambem na prova.
#               id_do_curso() -> o id do curso aberto (do endereco), para saber se mudou de materia.
#               questao_ja_respondida() / numero_da_questao() -> na tela de UMA questao, diz se ja
#               ha alternativa marcada e qual e o numero da questao ("Questao 8").
#               ler_painel() -> na pagina INICIAL do quiz, le em que pe estao as tentativas
#               (qual botao aparece, a tabela com as notas e a nota maxima) e devolve um
#               PainelQuiz; None se a pagina nao for essa. So olha, nao clica.
#
# Os seletores CSS de cada site ficam no config.py.
import base64
import hashlib
import re
from urllib.parse import parse_qs, urljoin, urlparse

from playwright.sync_api import BrowserContext, Frame
from playwright.sync_api import Error as PlaywrightError

from quizbot.config import (
    CLASSE_ATIVIDADE_CONCLUIDA,
    CLASSE_CORRETA,
    CLASSE_NAO_RESPONDIDA,
    FRAGMENTO_URL_ATIVIDADE,
    MAX_BYTES_IMAGEM,
    PADRAO_NOME_UNIDADE,
    PADRAO_PREFIXO_ALTERNATIVA,
    SELETOR_ALTERNATIVAS,
    SELETOR_ATIVIDADES,
    SELETOR_BOTAO_TERMINAR_REVISAO,
    SELETOR_CAMINHO,
    SELETOR_ENUNCIADO,
    SELETOR_MARCADAS,
    SELETOR_MENU_UNIDADES,
    SELETOR_NUMERO_DA_QUESTAO,
    SELETOR_QUESTAO,
    SELETOR_RADIO_MARCADO,
    SELETOR_TABELA_RESUMO,
    SELETOR_TABELA_TENTATIVAS,
    SELETOR_TITULO_UNIDADE,
    TEXTO_BOTAO_COMECAR,
    TEXTO_BOTAO_CONTINUAR,
    TEXTO_BOTAO_OUTRA,
    TEXTO_SEM_MAIS_TENTATIVAS,
)
from quizbot.curso import limpar
from quizbot.html_texto import ImagemRef, ResultadoHtml, converter_html
from quizbot.models import (
    AtividadeDoCurso,
    CaminhoDoQuiz,
    Imagem,
    PainelQuiz,
    QuestaoDoResumo,
    Question,
    Resultado,
    ResumoTentativa,
    Situacao,
    Tentativa,
    Unidade,
    UnidadeAberta,
)

_PADRAO_UNIDADE = re.compile(PADRAO_NOME_UNIDADE)
_PREFIXO = re.compile(PADRAO_PREFIXO_ALTERNATIVA)
_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")
_NOTA_MAXIMA = re.compile(r"/\s*(\d+(?:[.,]\d+)?)")

# Le so o TEXTO da tabela de tentativas: os cabecalhos e, para cada linha, o texto das celulas.
# Do "Estado" tira o trecho dos detalhes (a data de envio), numa copia solta na memoria.
_JS_TABELA = """
tabela => {
    const texto = el => {
        const copia = el.cloneNode(true);
        copia.querySelectorAll('.statedetails').forEach(e => e.remove());
        return copia.textContent.trim();
    };
    return {
        cabecalhos: Array.from(tabela.querySelectorAll('thead th')).map(texto),
        linhas: Array.from(tabela.querySelectorAll('tbody tr')).map(
            tr => Array.from(tr.querySelectorAll('td')).map(texto)
        ),
    };
}
"""

# Le so o numero e as classes de cada linha da tabela de resumo (nada na pagina e alterado).
_JS_RESUMO = """
tabela => Array.from(tabela.querySelectorAll('tbody tr')).map(tr => ({
    numero: (tr.querySelector('td') || {textContent: ''}).textContent.trim(),
    classes: tr.className,
}))
"""

# Le o menu das unidades: nome, a barra de progresso (o PRIMEIRO numero do linear-gradient do
# icone: 100 = cheia) e se o item e o ativo. Os itens sem link (o ultimo, so decorativo) saem.
_JS_MENU = r"""
lista => Array.from(lista.querySelectorAll('li')).map(li => {
    if (li.closest('.timeline-menu')) return null;  // as secoes sao lidas junto da unidade
    const item = li.querySelector('.timeline-item');
    const link = item ? item.querySelector('a') : null;
    if (!link) return null;
    const icone = li.querySelector('.timeline-status i');
    const estilo = icone ? (icone.getAttribute('style') || '') : '';
    const achado = estilo.match(/linear-gradient\(\s*0deg\s*,\s*rgb\([^)]*\)\s*(\d+(?:\.\d+)?)%/);
    let percentual = achado ? parseFloat(achado[1]) : null;
    if (percentual === null && icone) {  // sem barra: "complete" = cheia, "inactive" = vazia
        if (icone.classList.contains('complete')) percentual = 100;
        else if (icone.classList.contains('inactive')) percentual = 0;
    }
    const secoes = Array.from(li.querySelectorAll('.timeline-menu li')).map(s => {
        const a = s.querySelector('a');
        return a ? {nome: a.textContent.replace(/\s+/g, ' ').trim(), ativa: s.classList.contains('active')} : null;
    }).filter(x => x !== null && x.nome);
    return {
        nome: link.textContent.replace(/\s+/g, ' ').trim(),
        percentual: percentual,
        aberta: item.classList.contains('active') || item.classList.contains('open'),
        secoes: secoes,
    };
}).filter(x => x !== null)
"""

# Le as atividades da unidade: o nome do link, se tem o icone de "concluida" dentro e as classes
# do icone da atividade (o quiz tem um icone proprio, diferente dos arquivos de apoio).
_JS_ATIVIDADES = r"""
(blocos, classeConcluida) => blocos.map(el => {
    const link = el.querySelector('h3 a');
    const icone = el.querySelector('h3 > i');
    return {
        nome: link ? link.textContent.replace(/\s+/g, ' ').trim() : '',
        concluida: !!el.querySelector('.' + classeConcluida),
        icone: icone ? icone.className : '',
    };
})
"""

# Qual botao (ou aviso) a pagina inicial mostra decide a situacao. So um aparece por vez.
_BOTOES_DO_PAINEL = (
    (TEXTO_BOTAO_CONTINUAR, Situacao.EM_ANDAMENTO),
    (TEXTO_BOTAO_COMECAR, Situacao.SEM_TENTATIVA),
    (TEXTO_BOTAO_OUTRA, Situacao.PODE_REFAZER),
)


def _numero(texto: str) -> float | None:
    achado = _NUMERO.search(texto)
    return float(achado.group().replace(",", ".")) if achado else None


def _coluna(cabecalhos: list[str], comeco: str) -> int | None:
    for i, cabecalho in enumerate(cabecalhos):
        if cabecalho.lower().startswith(comeco):
            return i
    return None


def _ler_tabela(dados: dict) -> tuple[tuple[Tentativa, ...], float | None]:
    """Transforma o texto da tabela em tentativas e na nota maxima do cabecalho."""
    cabecalhos = dados["cabecalhos"]
    col_numero = _coluna(cabecalhos, "tentativa")
    col_estado = _coluna(cabecalhos, "estado")
    col_nota = _coluna(cabecalhos, "nota")
    nota_maxima = None
    if col_nota is not None:
        achado = _NOTA_MAXIMA.search(cabecalhos[col_nota])
        nota_maxima = float(achado.group(1).replace(",", ".")) if achado else None

    def celula(linha: list[str], coluna: int | None) -> str:
        return linha[coluna] if coluna is not None and coluna < len(linha) else ""

    tentativas = []
    for linha in dados["linhas"]:
        numero = _numero(celula(linha, col_numero))
        estado = celula(linha, col_estado).split("\n")[0].strip()  # "Finalizada" (sem a data)
        tentativas.append(
            Tentativa(int(numero) if numero is not None else None, estado, _numero(celula(linha, col_nota)))
        )
    return tuple(tentativas), nota_maxima

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

# Le UM bloco de questao da revisao (a copia e feita num documento inerte, como acima).
# Devolve o HTML do enunciado, o das alternativas, o indice da alternativa marcada e se o
# Moodle a deu como certa; ou null se o bloco nao tiver nada marcado.
_JS_REVISAO = """
(que, s) => {
    const inerte = document.implementation.createHTMLDocument('');
    const copiar = el => {
        const copia = inerte.importNode(el, true);
        copia.querySelectorAll('img[data-mathml]').forEach(i => i.removeAttribute('src'));
        // O Moodle poe o icone de certo/errado (img.questioncorrectnessicon, um SVG) ao lado da
        // alternativa marcada, as vezes DENTRO do texto dela. Nao e imagem da questao: sem tirar,
        // ele viraria "[imagem N]" (mudando o texto da alternativa) e a questao seria descartada.
        copia.querySelectorAll('.questioncorrectnessicon, img[src*="/i/grade_"]').forEach(i => i.remove());
        return copia.innerHTML;
    };
    const enunciado = que.querySelector(s.enunciado);
    const rotulos = Array.from(que.querySelectorAll(s.alternativas));
    const marcada = que.querySelector(s.marcadas);
    if (!enunciado || rotulos.length === 0 || !marcada) return null;
    const rotulo = marcada.matches('label') ? marcada : marcada.querySelector('label');
    const indice = rotulos.indexOf(rotulo);
    if (indice < 0) return null;
    return {
        enunciado: copiar(enunciado),
        alternativas: rotulos.map(copiar),
        indice: indice,
        acertou: marcada.classList.contains(s.classeCorreta),
    };
}
"""
_SELETORES_REVISAO = {
    "enunciado": SELETOR_ENUNCIADO,
    "alternativas": SELETOR_ALTERNATIVAS,
    "marcadas": SELETOR_MARCADAS,
    "classeCorreta": CLASSE_CORRETA,
}

# So para o registro (nao altera a pagina): o esqueleto de um bloco (tag#id.classes e o comeco do
# texto de cada elemento) e o caminho de um elemento ate o topo.
_JS_ESQUELETO = r"""
raiz => {
    const linhas = [];
    const desc = e => e.tagName.toLowerCase()
        + (e.id ? '#' + e.id.replace(/\d{3,}/g, 'N') : '')
        + (e.classList.length ? '.' + Array.from(e.classList).join('.') : '');
    const andar = (e, nivel) => {
        if (linhas.length >= 80 || nivel > 9) return;
        const texto = Array.from(e.childNodes).filter(n => n.nodeType === 3 && n.textContent.trim())
            .map(n => n.textContent.trim()).join(' ');
        linhas.push('  '.repeat(nivel) + desc(e) + (texto ? ` "${texto.slice(0, 16)}${texto.length > 16 ? '…' : ''}"` : ''));
        Array.from(e.children).forEach(f => andar(f, nivel + 1));
    };
    andar(raiz, 0);
    return linhas;
}
"""
_JS_CAMINHO = r"""
el => {
    const partes = [];
    for (let e = el; e && e.tagName && partes.length < 6; e = e.parentElement) {
        partes.push(e.tagName.toLowerCase() + (e.id ? '#' + e.id.replace(/\d{3,}/g, 'N') : '')
            + (e.classList.length ? '.' + Array.from(e.classList).join('.') : ''));
    }
    return partes.join(' < ');
}
"""

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


_MARCA_IMAGEM = re.compile(r"\[imagem (\d+)\]")


def _assinatura(texto: str, por_numero: dict[int, Imagem]) -> str:
    # Troca cada "[imagem N]" por "[img:codigo]" (o codigo vem dos bytes da imagem).
    def trocar(achado: re.Match) -> str:
        imagem = por_numero.get(int(achado.group(1)))
        return f"[img:{imagem.codigo}]" if imagem else achado.group(0)

    return _MARCA_IMAGEM.sub(trocar, texto)


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
    return _imagem_de_bytes(base64.b64decode(achou.group(1)))


def _imagem_de_bytes(dados: bytes) -> Imagem:
    if len(dados) > MAX_BYTES_IMAGEM:
        raise ValueError("imagem grande demais")
    return Imagem(dados=dados, tipo=_tipo_da_imagem(dados))


def _motivo(erro: Exception) -> str:
    # A primeira linha da mensagem do navegador/Playwright, sem o prefixo ("Frame.evaluate: ").
    linha = (str(erro).strip().splitlines() or [type(erro).__name__])[0]
    return linha.split(": ", 1)[-1] if linha.startswith(("Frame.", "Error", "TypeError")) else linha


class PageReader:
    def __init__(self, contexto: BrowserContext) -> None:
        self._contexto = contexto
        self._cache_imagens: dict[str, Imagem] = {}
        self._imagens_avisadas: set[str] = set()  # para o registro nao repetir a mesma linha

    def _checar_conexao(self) -> None:
        navegador = self._contexto.browser
        if navegador is not None and not navegador.is_connected():
            raise NavegadorFechado("o navegador foi fechado")

    def atender_navegador(self, segundos: float) -> bool:
        # Espera `segundos` DEIXANDO o Playwright atender o navegador. No Playwright sincrono, um
        # time.sleep() ou Event.wait() comum deixa as mensagens do navegador paradas ate a proxima
        # chamada; wait_for_timeout() espera e as processa. False = nao deu (sem aba aberta ou
        # navegador fechado): quem chamou espera do jeito comum.
        try:
            abas = self._contexto.pages
            if not abas:
                return False
            abas[0].wait_for_timeout(segundos * 1000)
            return True
        except PlaywrightError:
            return False

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
            if ref.src.startswith("data:"):
                imagem = _imagem_de_data_url(ref.src)
            else:
                imagem = self._baixar_da_rede(quadro, ref)
        except ValueError as erro:
            raise LeituraIncompleta(f"Nao consegui ler a imagem {ref.numero}: {erro}.") from erro
        except PlaywrightError as erro:
            self._checar_conexao()
            raise LeituraIncompleta(
                f"Nao consegui baixar a imagem {ref.numero} da questao ({_motivo(erro)})."
            ) from erro

        self._cache_imagens[chave] = imagem
        return imagem

    def _baixar_da_rede(self, quadro: Frame, ref: ImagemRef) -> Imagem:
        # 1) Pela pagina (usa a sessao e os cookies do usuario). Imagem hospedada em OUTRO
        #    endereco (CDN, outro dominio) o navegador bloqueia (CORS: "Failed to fetch"), mesmo
        #    quando o servidor da imagem a libera; 2) entao baixa pelo contexto do navegador, que
        #    leva os mesmos cookies mas nao tem essa regra (e quem baixa e o programa, nao a pagina).
        try:
            return _imagem_de_data_url(quadro.evaluate(_JS_BAIXAR, ref.src))
        except PlaywrightError as erro_pagina:
            self._checar_conexao()
            url = urljoin(quadro.url, ref.src)
            if ref.src not in self._imagens_avisadas:
                self._imagens_avisadas.add(ref.src)
                print(f"[imagem] {ref.numero}: a pagina nao baixou ({_motivo(erro_pagina)}); tentando pelo navegador: {url}")
            resposta = self._contexto.request.get(url, timeout=15000)  # PlaywrightError se falhar
            if not resposta.ok:
                raise PlaywrightError(f"HTTP {resposta.status}") from erro_pagina
            return _imagem_de_bytes(resposta.body())

    def _montar(
        self, quadro: Frame, enunciado: ResultadoHtml, alternativas: list[ResultadoHtml]
    ) -> Question:
        refs = list(enunciado.imagens) + [ref for alt in alternativas for ref in alt.imagens]
        imagens = tuple(self._baixar(quadro, ref) for ref in refs)
        por_numero = {ref.numero: imagem for ref, imagem in zip(refs, imagens)}
        textos = tuple(_PREFIXO.sub("", alt.texto) for alt in alternativas)
        return Question(
            enunciado=enunciado.texto,
            alternativas=textos,
            imagens=imagens,
            assinaturas=tuple(_assinatura(texto, por_numero) for texto in textos),
        )

    def _ler_quadro(self, quadro: Frame) -> Question | None:
        enunciado = self._ler_enunciado(quadro)
        if enunciado is None or not enunciado.texto:
            return None
        alternativas = self._ler_alternativas(quadro, primeiro=1 + len(enunciado.imagens))
        if not alternativas:
            return None
        return self._montar(quadro, enunciado, alternativas)

    def _ler_revisao_quadro(self, quadro: Frame) -> list[Resultado]:
        # Conferencia barata antes de ler: sem nada marcado como certo/errado, nao e revisao.
        if quadro.locator(SELETOR_MARCADAS).count() == 0:
            return []
        blocos = quadro.locator(SELETOR_QUESTAO)
        resultados = []
        for i in range(blocos.count()):
            dados = blocos.nth(i).evaluate(_JS_REVISAO, _SELETORES_REVISAO, timeout=2000)
            if dados is None:
                continue
            enunciado = converter_html(dados["enunciado"])
            if not enunciado.texto:
                continue
            primeiro = 1 + len(enunciado.imagens)
            alternativas = []
            for html in dados["alternativas"]:
                alternativa = converter_html(html, primeiro)
                primeiro += len(alternativa.imagens)
                alternativas.append(alternativa)
            try:
                questao = self._montar(quadro, enunciado, alternativas)
            except LeituraIncompleta as erro:
                # Esta questao fica de fora da memoria: registra, para nao sumir em silencio.
                aviso = f"{i + 1}: {erro}"
                if aviso not in self._imagens_avisadas:
                    self._imagens_avisadas.add(aviso)
                    print(f"[revisao] questao {i + 1} da revisao pulada: {erro}")
                continue
            resultados.append(Resultado(questao, dados["indice"], dados["acertou"]))
        return resultados

    def estrutura_da_revisao(self) -> str:
        # Esqueleto da primeira questao da pagina (so tags, classes e o comeco dos textos), e o
        # caminho do link "Terminar revisao": o que preciso para ver como o Moodle montou a pagina
        # quando o programa nao consegue le-la.
        for quadro in self._quadros():
            try:
                if quadro.locator(SELETOR_QUESTAO).count() > 0:
                    linhas = quadro.locator(SELETOR_QUESTAO).first.evaluate(_JS_ESQUELETO)
                    caminho = quadro.locator(SELETOR_BOTAO_TERMINAR_REVISAO).first
                    cima = caminho.evaluate(_JS_CAMINHO) if caminho.count() else "(sem o link Terminar revisao)"
                    return "primeira questao:\n" + "\n".join(linhas) + f"\nlink Terminar revisao: {cima}"
            except PlaywrightError:
                self._checar_conexao()
        return "nenhuma questao (.que) na pagina"

    def diagnosticar_pagina(self) -> str:
        # Resumo curto do que a pagina mostra (para o registro quando algo nao anda): endereco e
        # quantos blocos de questao, marcados certo/errado, tabelas e links "Terminar revisao".
        partes = []
        for quadro in self._quadros():
            try:
                partes.append(
                    f"{quadro.url[:90]} [questoes={quadro.locator(SELETOR_QUESTAO).count()}, "
                    f"marcadas={quadro.locator(SELETOR_MARCADAS).count()}, "
                    f"resumo={quadro.locator(SELETOR_TABELA_RESUMO).count()}, "
                    f"terminar_revisao={quadro.locator(SELETOR_BOTAO_TERMINAR_REVISAO).count()}]"
                )
            except PlaywrightError:
                partes.append(f"{quadro.url[:90]} [nao deu para ler]")
        return " | ".join(partes) or "nenhuma pagina aberta"

    @staticmethod
    def _ler_painel_quadro(quadro: Frame) -> PainelQuiz | None:
        situacao = None
        for texto, candidata in _BOTOES_DO_PAINEL:
            if quadro.locator("button", has_text=texto).count() == 1:
                situacao = candidata
                break
        else:
            if quadro.locator(".quizattempt p", has_text=TEXTO_SEM_MAIS_TENTATIVAS).count() > 0:
                situacao = Situacao.ESGOTADO
        if situacao is None:
            return None
        tentativas: tuple[Tentativa, ...] = ()
        nota_maxima = None
        tabela = quadro.locator(SELETOR_TABELA_TENTATIVAS)
        if tabela.count() == 1:
            tentativas, nota_maxima = _ler_tabela(tabela.evaluate(_JS_TABELA, timeout=2000))
        return PainelQuiz(situacao, tentativas, nota_maxima)

    def ler_painel(self) -> PainelQuiz | None:
        for quadro in self._quadros():
            try:
                painel = self._ler_painel_quadro(quadro)
            except PlaywrightError:
                self._checar_conexao()
                continue
            if painel is not None:
                return painel
        return None

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

    def ler_resumo(self) -> ResumoTentativa | None:
        # Pagina de resumo (antes de enviar): None se nao for ela (ou se a tabela nao for achada).
        for quadro in self._quadros():
            try:
                resumo = self._ler_resumo_quadro(quadro)
            except PlaywrightError:
                self._checar_conexao()
                continue
            if resumo is not None:
                return resumo
        return None

    @staticmethod
    def _ler_resumo_quadro(quadro: Frame) -> ResumoTentativa | None:
        tabela = quadro.locator(SELETOR_TABELA_RESUMO)
        if tabela.count() != 1:
            return None
        questoes = []
        for linha in tabela.evaluate(_JS_RESUMO, timeout=2000):
            numero = _numero(linha["numero"])
            if numero is None:
                continue
            questoes.append(
                QuestaoDoResumo(int(numero), CLASSE_NAO_RESPONDIDA not in linha["classes"].split())
            )
        return ResumoTentativa(tuple(questoes)) if questoes else None

    def _quadro_da_questao(self) -> Frame | None:
        # O quadro com exatamente 1 questao na tela (o mesmo criterio do ler_questao).
        for quadro in self._quadros():
            try:
                if quadro.locator(SELETOR_ENUNCIADO).count() == 1:
                    return quadro
            except PlaywrightError:
                self._checar_conexao()
        return None

    def questao_ja_respondida(self) -> bool:
        """A questao na tela ja tem uma alternativa marcada (resposta guardada pelo Moodle)."""
        quadro = self._quadro_da_questao()
        if quadro is None:
            return False
        try:
            return quadro.locator(SELETOR_RADIO_MARCADO).count() > 0
        except PlaywrightError:
            self._checar_conexao()
            return False

    def numero_da_questao(self) -> int | None:
        """O numero da questao na tela ("Questao 8"), para o registro; None se nao achar."""
        quadro = self._quadro_da_questao()
        if quadro is None:
            return None
        try:
            texto = quadro.locator(SELETOR_NUMERO_DA_QUESTAO).first.text_content(timeout=1000)
        except PlaywrightError:
            self._checar_conexao()
            return None
        numero = _numero(texto or "")
        return int(numero) if numero is not None else None

    def ler_menu(self) -> tuple[Unidade, ...] | None:
        # O menu das unidades do curso; None se a pagina nao tiver esse menu. Pagina de atividade
        # (endereco com "/mod/": prova, resumo, painel do quiz) nao conta, mesmo com o menu na
        # lateral: ali o programa nao pode navegar pelo curso.
        for quadro in self._quadros():
            try:
                if FRAGMENTO_URL_ATIVIDADE in quadro.url:
                    continue
                menu = quadro.locator(SELETOR_MENU_UNIDADES).locator("visible=true")
                if menu.count() == 0:
                    continue
                itens = menu.first.evaluate(_JS_MENU, timeout=2000)
            except PlaywrightError:
                self._checar_conexao()
                continue
            unidades = tuple(
                Unidade(
                    i["nome"],
                    i["percentual"],
                    i["aberta"],
                    tuple(s["nome"] for s in i.get("secoes", ())),
                    next((s["nome"] for s in i.get("secoes", ()) if s["ativa"]), None),
                )
                for i in itens
                if i["nome"] and _PADRAO_UNIDADE.match(limpar(i["nome"]))
            )
            if unidades:
                return unidades
        return None

    def endereco_do_curso(self) -> str | None:
        # O endereco completo da pagina do CURSO (a que tem o menu das unidades, fora das paginas
        # de atividade). Muda quando alguem abre outra unidade/secao: serve para notar que o
        # USUARIO navegou por conta propria.
        for quadro in self._quadros():
            try:
                if FRAGMENTO_URL_ATIVIDADE in quadro.url:
                    continue
                if quadro.locator(SELETOR_MENU_UNIDADES).locator("visible=true").count() == 0:
                    continue
                return quadro.url
            except PlaywrightError:
                self._checar_conexao()
        return None

    def id_do_curso(self) -> str | None:
        # O "id" do curso, no endereco da pagina que tem o menu das unidades
        # (.../course/view.php?id=11336); None se nao achar. Serve para saber se o usuario abriu
        # OUTRA materia depois de o programa terminar uma.
        for quadro in self._quadros():
            try:
                url = quadro.url
                if FRAGMENTO_URL_ATIVIDADE in url:
                    continue
                if quadro.locator(SELETOR_MENU_UNIDADES).locator("visible=true").count() == 0:
                    continue
            except PlaywrightError:
                self._checar_conexao()
                continue
            achado = parse_qs(urlparse(url).query).get("id")
            if achado:
                return achado[0]
        return None

    def ler_unidade(self) -> UnidadeAberta | None:
        # A unidade que a pagina mostra: o titulo (h1) e as atividades com o "feito" de cada uma.
        for quadro in self._quadros():
            try:
                titulo = quadro.locator(SELETOR_TITULO_UNIDADE)
                nome = (
                    " ".join((titulo.first.text_content(timeout=1000) or "").split())
                    if titulo.count() > 0
                    else ""
                )
                itens = quadro.locator(SELETOR_ATIVIDADES).evaluate_all(
                    _JS_ATIVIDADES, CLASSE_ATIVIDADE_CONCLUIDA
                )
            except PlaywrightError:
                self._checar_conexao()
                continue
            # Numa pagina de secao o titulo pode nao ser o da unidade; as atividades bastam.
            if nome or any(i["nome"] for i in itens):
                return UnidadeAberta(
                    nome,
                    tuple(
                        AtividadeDoCurso(i["nome"], i["concluida"], i["icone"])
                        for i in itens
                        if i["nome"]
                    ),
                )
        return None

    def ler_caminho(self) -> CaminhoDoQuiz | None:
        # O breadcrumb do topo da pagina de quiz: o ultimo item e o quiz, o anterior e a unidade.
        for quadro in self._quadros():
            try:
                textos = quadro.locator(SELETOR_CAMINHO).all_text_contents()
            except PlaywrightError:
                self._checar_conexao()
                continue
            itens = [" ".join(t.split()) for t in textos if t.strip()]
            if len(itens) >= 2:
                return CaminhoDoQuiz(unidade=itens[-2], quiz=itens[-1])
        return None

    def ler_revisao(self) -> list[Resultado]:
        for quadro in self._quadros():
            try:
                resultados = self._ler_revisao_quadro(quadro)
            except PlaywrightError:
                self._checar_conexao()
                continue
            if resultados:
                return resultados
        return []
