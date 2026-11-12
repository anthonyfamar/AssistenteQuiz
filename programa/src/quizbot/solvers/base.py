# BASE - o contrato dos solvers e o erro que eles levantam.
#
# Solver (classe abstrata) -> todo solver tem solve(question) -> Suggestion.
#                             O AssistenteQuiz recebe "um Solver" sem saber qual e.
#                             Opcionais: solve_com_limite(question, timeout) e sondar(timeout),
#                             usados pelo FallbackSolver (tempo de espera e teste em segundo plano).
# SolverError              -> falha ESPERADA de um solver: formato errado da IA,
#                             cota acabou, sem rede. O assistente avisa e segue.
#                             Leva um resumo (para a janela) e um detalhe (para o log).
from abc import ABC, abstractmethod

from quizbot.models import Question, Suggestion


class SolverError(Exception):
    """Falha esperada ao pedir uma sugestao.

    mensagem -> o texto tecnico de sempre (str(erro)).
    resumo   -> uma frase clara com o modelo, para o registro e para o desenvolvedor.
    aviso    -> a frase DIRETA E SIMPLES que a janela mostra ao usuario
                (ex.: "Algo deu errado: API do Gemini fora do ar.").
    detalhe  -> tudo que ajuda o desenvolvedor (modelo, codigo HTTP, resposta do servidor...);
                vai so para o registro (log).
    espera_sugerida -> segundos que o servidor pediu para esperar (cota acabou), SEM limite
                (pode ser horas); o FallbackSolver nao testa o modelo antes disso e mostra ao
                usuario quanto falta. None = o servidor nao disse.
    motivo   -> o que aconteceu em poucas palavras ("limite de uso (cota) atingido"), para
                montar o aviso de "todas as IAs estao fora".
    permanente -> True quando esperar nao resolve (chave recusada, pede credito pago): o
                modelo sai da fila ate o programa ser aberto de novo, sem testes em segundo plano.
    """

    def __init__(
        self,
        mensagem: str,
        resumo: str | None = None,
        detalhe: str = "",
        aviso: str | None = None,
        espera_sugerida: float | None = None,
        motivo: str | None = None,
        permanente: bool = False,
    ) -> None:
        super().__init__(mensagem)
        self.resumo = resumo or mensagem
        self.aviso = aviso or self.resumo
        self.detalhe = detalhe
        self.espera_sugerida = espera_sugerida
        self.motivo = motivo
        self.permanente = permanente


class Solver(ABC):
    @abstractmethod
    def solve(self, question: Question) -> Suggestion:
        ...

    def solve_com_limite(self, question: Question, timeout: float) -> Suggestion:
        """Como solve(), mas desiste depois de 'timeout' segundos (so o ApiSolver respeita)."""
        return self.solve(question)

    def sondar(self, timeout: float) -> bool:
        """Teste barato para saber se o solver voltou a funcionar (usado em segundo plano)."""
        return True

    @property
    def nome(self) -> str:
        return type(self).__name__

    @property
    def descricao(self) -> str:
        """Nome para mensagens e registro (o ApiSolver acrescenta o modelo)."""
        return self.nome

    @property
    def apelido(self) -> str:
        """Nome curto para o usuario ("Gemini", "Groq"); o ApiSolver devolve o do provedor."""
        return self.nome

    @property
    def fator_de_espera(self) -> float:
        """Quantas vezes o tempo normal de espera este solver merece (modelo que pensa devagar)."""
        return 1.0

    @property
    def aceita_imagens(self) -> bool:
        return True
