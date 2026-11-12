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
#
# Situacao   -> em que pe esta a PAGINA INICIAL do quiz (a das tentativas):
#               SEM_TENTATIVA (botao de comecar), EM_ANDAMENTO (botao de continuar),
#               PODE_REFAZER (botao de outra tentativa) ou ESGOTADO (sem mais tentativas).
# Tentativa  -> uma linha da tabela de tentativas: numero, estado e nota (None se nao ha).
# PainelQuiz -> a pagina inicial lida: a situacao, as tentativas e a nota maxima (a do
#               cabecalho "Nota / 10,00"). Responde "acertou tudo?" e monta o resumo das
#               notas: a MAIOR nota e a que vale, mesmo que a ultima tentativa seja pior.
# Unidade / AtividadeDoCurso / UnidadeAberta / CaminhoDoQuiz -> o CURSO: o menu das unidades (nome e
#               barra de progresso), as atividades da unidade aberta (e se estao feitas) e o
#               breadcrumb de uma pagina de quiz (de qual unidade e quiz ela e).
# QuestaoDoResumo / ResumoTentativa -> a pagina de RESUMO (antes de enviar): cada questao com o
#               numero e se ja foi respondida. "faltam" lista os numeros sem resposta.
import hashlib
from dataclasses import dataclass
from enum import Enum
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


class Situacao(Enum):
    SEM_TENTATIVA = "sem_tentativa"
    EM_ANDAMENTO = "em_andamento"
    PODE_REFAZER = "pode_refazer"
    ESGOTADO = "esgotado"


@dataclass(frozen=True)
class Tentativa:
    numero: int | None
    estado: str
    nota: float | None


@dataclass(frozen=True)
class QuestaoDoResumo:
    numero: int
    respondida: bool


@dataclass(frozen=True)
class ResumoTentativa:
    questoes: tuple[QuestaoDoResumo, ...]

    @property
    def faltam(self) -> tuple[int, ...]:
        """Numeros das questoes ainda sem resposta, em ordem."""
        return tuple(q.numero for q in self.questoes if not q.respondida)


@dataclass(frozen=True)
class Unidade:
    """Um item do menu do curso: o nome, a barra de progresso (100 = cheia) e se esta aberta."""

    nome: str
    percentual: float | None
    aberta: bool = False
    secoes: tuple[str, ...] = ()  # "U1 - Seção 1"...: vazio nos cursos sem seções
    secao_ativa: str | None = None  # a seção marcada como ativa no menu (a que a página mostra)


@dataclass(frozen=True)
class AtividadeDoCurso:
    nome: str
    concluida: bool
    icone: str = ""  # as classes do icone (ex.: "icon-library_books ..."): o quiz tem um proprio


@dataclass(frozen=True)
class UnidadeAberta:
    """A unidade que a pagina mostra agora: o titulo (h1) e as atividades dela."""

    titulo: str
    atividades: tuple[AtividadeDoCurso, ...]


@dataclass(frozen=True)
class CaminhoDoQuiz:
    """O breadcrumb do topo de uma pagina de quiz: a unidade e o nome do quiz."""

    unidade: str | None
    quiz: str | None


def formatar_nota(nota: float) -> str:
    return f"{nota:.2f}".replace(".", ",")  # o Moodle em portugues usa virgula


@dataclass(frozen=True)
class PainelQuiz:
    situacao: Situacao
    tentativas: tuple[Tentativa, ...] = ()
    nota_maxima: float | None = None

    @property
    def _com_nota(self) -> tuple[Tentativa, ...]:
        return tuple(t for t in self.tentativas if t.nota is not None)

    @property
    def ultima(self) -> Tentativa | None:
        """A tentativa mais recente que ja tem nota (a ultima linha da tabela)."""
        return self._com_nota[-1] if self._com_nota else None

    @property
    def melhor(self) -> Tentativa | None:
        """A tentativa de maior nota (a primeira, se houver empate)."""
        return max(self._com_nota, key=lambda t: t.nota, default=None)

    @property
    def tudo_certo(self) -> bool:
        if self.nota_maxima is None or self.melhor is None:
            return False
        return self.melhor.nota >= self.nota_maxima - 1e-9

    def resumo_das_notas(self) -> str:
        ultima, melhor = self.ultima, self.melhor
        if ultima is None or melhor is None:
            return "Não consegui ler a nota."
        de = f" de {formatar_nota(self.nota_maxima)}" if self.nota_maxima is not None else ""
        if melhor.nota > ultima.nota:
            return (
                f"Nota da última tentativa: {formatar_nota(ultima.nota)}{de}. "
                f"Fica a maior nota: {formatar_nota(melhor.nota)}{de} (tentativa {melhor.numero})."
            )
        return f"Nota final: {formatar_nota(ultima.nota)}{de}."