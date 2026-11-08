# MODELS - os "dados" do projeto.
#
# Imagem     -> os bytes de uma imagem da questao (grafico, figura) e o tipo dela
#               (ex.: "image/png"). Formulas NAO viram Imagem: viram texto.
#               "codigo" e a impressao digital da imagem (um hash curto dos bytes): a
#               mesma imagem tem sempre o mesmo codigo, em qualquer posicao ou PC.
# Question   -> guarda o enunciado e as alternativas da questao lida na tela, mais as
#               imagens que ela tiver (no texto aparecem como [imagem 1], [imagem 2]...).
#               "assinaturas" = a identidade ESTAVEL de cada alternativa: o mesmo texto,
#               mas com cada [imagem N] trocado por [img:codigo]. O N muda se a ordem for
#               embaralhada; o codigo nao. "identidades" devolve as assinaturas (ou, se
#               nao houver, as proprias alternativas) e e o que a memoria usa.
#               E um dataclass imutavel (frozen), entao nao muda depois de criado.
#               O __eq__ gerado e como o assistente percebe que a questao mudou.
# Suggestion -> guarda a resposta sugerida pela IA: o indice da alternativa
#               + uma explicacao curta + a origem (nome do provedor que respondeu).
# Resultado  -> uma questao lida na pagina de REVISAO: a questao, qual alternativa foi
#               marcada (indice, 0 = primeira) e se o Moodle a deu como certa.
import hashlib
from dataclasses import dataclass
from functools import cached_property


@dataclass(frozen=True)
class Imagem:
    dados: bytes
    tipo: str

    @cached_property
    def codigo(self) -> str:
        return hashlib.sha1(self.dados).hexdigest()[:10]


@dataclass(frozen=True)
class Question:
    enunciado: str
    alternativas: tuple[str, ...]
    imagens: tuple[Imagem, ...] = ()
    assinaturas: tuple[str, ...] = ()

    @property
    def identidades(self) -> tuple[str, ...]:
        return self.assinaturas or self.alternativas


@dataclass(frozen=True)
class Suggestion:
    indice: int
    explicacao: str
    origem: str = ""


@dataclass(frozen=True)
class Resultado:
    questao: Question
    indice: int
    acertou: bool