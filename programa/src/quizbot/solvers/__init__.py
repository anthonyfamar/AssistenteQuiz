# SOLVERS - quem responde as questoes.
#
# Reexporta as classes principais, para o resto do projeto escrever
# apenas: from quizbot.solvers import Solver, ApiSolver
# (a fabrica.py fica de fora de proposito: depende do config e do .env)
from quizbot.solvers.api import ApiSolver
from quizbot.solvers.base import Solver, SolverError
from quizbot.solvers.fallback import FallbackSolver

__all__ = ["Solver", "SolverError", "ApiSolver", "FallbackSolver"]
