# MODELS - os "dados" do projeto.
#
# Imagem     -> os bytes de uma imagem da questao (grafico, figura) e o tipo dela
#               (ex.: "image/png"). Formulas NAO viram Imagem: viram texto.
# Question   -> guarda o enunciado e as alternativas da questao lida na tela, mais as
#               imagens que ela tiver (no texto aparecem como [imagem 1], [imagem 2]...).
#               E um dataclass imutavel (frozen), entao nao muda depois de criado.
#               O __eq__ gerado e como o assistente percebe que a questao mudou.
# Suggestion -> guarda a resposta sugerida pela IA: o indice da alternativa
#               + uma explicacao curta + a origem (nome do provedor que respondeu).
from dataclasses import dataclass


@dataclass(frozen=True)
class Imagem:
    dados: bytes
    tipo: str


@dataclass(frozen=True)
class Question:
    enunciado: str
    alternativas: tuple[str, ...]
    imagens: tuple[Imagem, ...] = ()


@dataclass(frozen=True)
class Suggestion:
    indice: int
    explicacao: str
    origem: str = ""