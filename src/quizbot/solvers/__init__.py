# SOLVERS - quem responde as questoes.
#
# Reexporta as classes principais, para o resto do projeto escrever
# apenas: from quizbot.solvers import Solver, FakeSolver
from quizbot.solvers.base import Solver, SolverError
from quizbot.solvers.fake import FakeSolver

__all__ = ["Solver", "SolverError", "FakeSolver"]
