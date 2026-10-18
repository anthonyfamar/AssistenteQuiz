# FORMULAS - converte formulas (MathML) em texto linear que a IA entende.
#
# mathml_para_texto(mathml) -> "P(x)=1+x+x^2", "(x+1)/(x-1)", "sqrt(x^2+1)"...
#                              Entende o MathML do Wiris, que vem "escapado" no atributo
#                              data-mathml (« » ¨ § no lugar de < > " &).
#                              Levanta ValueError se o texto nao for um MathML valido.
# agrupar(texto)            -> poe parenteses quando preciso: "n+1" vira "(n+1)".
import re
import xml.etree.ElementTree as ET

_ESCAPES_WIRIS = {"«": "<", "»": ">", "¨": '"', "§": "&", "`": "'"}
# Caracteres invisiveis do MathML (funcao aplicada, vezes invisivel, separador, soma).
_INVISIVEIS = dict.fromkeys(range(0x2061, 0x2065))

_TOKENS = {"mn", "mi", "mo", "mtext", "ms"}
# Operadores que levam limites e pedem um espaco depois: "∑_(i=0)^n a_i".
_OPERADORES_GRANDES = {"∑", "∏", "∫", "∬", "∭", "∮", "⋃", "⋂", "lim", "max", "min"}


def mathml_para_texto(mathml: str) -> str:
    for escapado, normal in _ESCAPES_WIRIS.items():
        mathml = mathml.replace(escapado, normal)
    try:
        raiz = ET.fromstring(mathml)
    except ET.ParseError as erro:
        raise ValueError(f"MathML invalido: {erro}") from erro
    texto = _converter(raiz).translate(_INVISIVEIS)
    return re.sub(r"\s+", " ", texto).strip()


def agrupar(texto: str) -> str:
    if not texto or _simples(texto) or _ja_agrupado(texto):
        return texto
    return f"({texto})"


def _simples(texto: str) -> bool:
    return len(texto) == 1 or re.fullmatch(r"[\w.]+", texto) is not None


def _ja_agrupado(texto: str) -> bool:
    if len(texto) < 2 or texto[0] != "(" or texto[-1] != ")":
        return False
    profundidade = 0
    for i, caractere in enumerate(texto):
        if caractere == "(":
            profundidade += 1
        elif caractere == ")":
            profundidade -= 1
            if profundidade == 0 and i < len(texto) - 1:
                return False
    return profundidade == 0


def _depois(base: str) -> str:
    return " " if base.strip() in _OPERADORES_GRANDES else ""


def _tag(no: ET.Element) -> str:
    return no.tag.rsplit("}", 1)[-1]


def _converter(no: ET.Element) -> str:
    tag = _tag(no)
    if tag in _TOKENS:
        return no.text or ""
    if tag == "mspace":
        return " "
    if tag == "mphantom":
        return ""

    f = [_converter(filho) for filho in no]
    if tag == "msup" and len(f) >= 2:
        return f"{agrupar(f[0])}^{agrupar(f[1])}"
    if tag == "msub" and len(f) >= 2:
        return f"{agrupar(f[0])}_{agrupar(f[1])}"
    if tag == "msubsup" and len(f) >= 3:
        return f"{agrupar(f[0])}_{agrupar(f[1])}^{agrupar(f[2])}{_depois(f[0])}"
    if tag == "munder" and len(f) >= 2:
        return f"{agrupar(f[0])}_{agrupar(f[1])}{_depois(f[0])}"
    if tag == "mover" and len(f) >= 2:
        return f"{agrupar(f[0])}^{agrupar(f[1])}{_depois(f[0])}"
    if tag == "munderover" and len(f) >= 3:
        return f"{agrupar(f[0])}_{agrupar(f[1])}^{agrupar(f[2])}{_depois(f[0])}"
    if tag == "mfrac" and len(f) >= 2:
        return f"{agrupar(f[0])}/{agrupar(f[1])}"
    if tag == "msqrt":
        return "sqrt(" + "".join(f) + ")"
    if tag == "mroot" and len(f) >= 2:
        return f"root({f[1]}, {f[0]})"
    if tag == "mfenced":
        abre = no.get("open", "(")
        fecha = no.get("close", ")")
        separadores = no.get("separators", ",").strip()
        return abre + (separadores[:1] if separadores else "").join(f) + fecha
    if tag == "mtable":
        linhas = [", ".join(_converter(celula) for celula in linha) for linha in no]
        return "[" + "; ".join(linhas) + "]"
    if tag == "semantics":
        return f[0] if f else ""
    return "".join(f)
