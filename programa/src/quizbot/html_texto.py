# HTML_TEXTO - transforma o HTML de um trecho da questao em texto simples.
#
# converter_html(html, primeiro) -> ResultadoHtml(texto, imagens)
#   - paragrafos e quebras de linha viram quebras de linha;
#   - <sup>/<sub> viram ^ e _ ("x<sup>2</sup>" -> "x^2");
#   - imagem de formula (Wiris: tem data-mathml) vira a formula em texto linear;
#   - qualquer outra imagem (grafico, figura) vira o marcador [imagem N] no texto e
#     entra na lista de imagens, para o PageReader baixar e mandar a IA que enxerga.
#     "primeiro" e o numero da primeira imagem deste trecho (a numeracao e da questao
#     inteira: enunciado e alternativas).
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from quizbot.formulas import agrupar, mathml_para_texto

_BLOCOS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "blockquote", "pre",
    "h1", "h2", "h3", "h4", "h5", "h6",
}
_IGNORAR = {"script", "style"}


@dataclass(frozen=True)
class ImagemRef:
    numero: int
    src: str
    alt: str


@dataclass(frozen=True)
class ResultadoHtml:
    texto: str
    imagens: tuple[ImagemRef, ...]


class _Conversor(HTMLParser):
    def __init__(self, primeiro: int) -> None:
        super().__init__(convert_charrefs=True)
        self._primeiro = primeiro
        self.partes: list[str] = []
        self.imagens: list[ImagemRef] = []
        self._ignorando = 0
        self._scripts: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _IGNORAR:
            self._ignorando += 1
            return
        if tag in _BLOCOS:
            self.partes.append("\n")
        if tag in ("sup", "sub"):
            self._scripts.append((tag, len(self.partes)))
        if tag == "img":
            self._imagem(dict(attrs))

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORAR:
            self._ignorando = max(0, self._ignorando - 1)
            return
        if tag in _BLOCOS and tag != "br":
            self.partes.append("\n")
        if tag in ("sup", "sub") and self._scripts and self._scripts[-1][0] == tag:
            _, inicio = self._scripts.pop()
            conteudo = "".join(self.partes[inicio:]).strip()
            del self.partes[inicio:]
            marca = "^" if tag == "sup" else "_"
            self.partes.append(f"{marca}{agrupar(conteudo)}")

    def handle_data(self, data: str) -> None:
        if not self._ignorando:
            self.partes.append(re.sub(r"\s+", " ", data))

    def _imagem(self, attrs: dict) -> None:
        alt = (attrs.get("alt") or "").strip()
        mathml = attrs.get("data-mathml")
        classes = (attrs.get("class") or "").lower()

        if mathml:
            try:
                self.partes.append(f" {mathml_para_texto(mathml)} ")
                return
            except ValueError:
                pass
        if (mathml or "wirisformula" in classes) and alt:
            self.partes.append(f" {alt} ")
            return

        numero = self._primeiro + len(self.imagens)
        self.imagens.append(ImagemRef(numero=numero, src=attrs.get("src") or "", alt=alt))
        self.partes.append(f" [imagem {numero}] ")


def converter_html(html: str, primeiro: int = 1) -> ResultadoHtml:
    conversor = _Conversor(primeiro)
    conversor.feed(html)
    conversor.close()

    linhas = [re.sub(r" {2,}", " ", linha).strip() for linha in "".join(conversor.partes).split("\n")]
    texto = re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()
    return ResultadoHtml(texto=texto, imagens=tuple(conversor.imagens))
