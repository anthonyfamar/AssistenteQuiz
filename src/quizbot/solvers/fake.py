# FAKE - solver de mentira, para testar sem gastar API.
#
# FakeSolver -> devolve sempre a alternativa 0 com uma explicacao fixa.
from quizbot.models import Question, Suggestion
from quizbot.solvers.base import Solver


class FakeSolver(Solver):
    def solve(self, question: Question) -> Suggestion:
        return Suggestion(indice=0, explicacao="FakeSolver: resposta fixa para teste.")
