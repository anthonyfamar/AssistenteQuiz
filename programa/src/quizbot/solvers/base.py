# BASE - o contrato dos solvers e o erro que eles levantam.
#
# Solver (classe abstrata) -> todo solver tem solve(question) -> Suggestion.
#                             O AssistenteQuiz recebe "um Solver" sem saber qual e.
# SolverError              -> falha ESPERADA de um solver: formato errado da IA,
#                             cota acabou, sem rede. O assistente avisa e segue.
from abc import ABC, abstractmethod

from quizbot.models import Question, Suggestion


class SolverError(Exception):
    """Falha esperada ao pedir uma sugestao."""


class Solver(ABC):
    @abstractmethod
    def solve(self, question: Question) -> Suggestion:
        ...

    @property
    def nome(self) -> str:
        return type(self).__name__

    @property
    def aceita_imagens(self) -> bool:
        return True
