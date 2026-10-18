# FALLBACK - tenta um provedor; se falhar, passa para o proximo.
#
# FallbackSolver -> recebe uma LISTA de solvers e e, ele proprio, um Solver.
#                   Quando um falha (SolverError), fica em "pausa" por um tempo
#                   (cooldown) para nao gastar a cota gratis a cada questao.
import time

from quizbot.models import Question, Suggestion
from quizbot.solvers.base import Solver, SolverError


class FallbackSolver(Solver):
    def __init__(self, solvers: list[Solver], cooldown: float = 60.0) -> None:
        if not solvers:
            raise ValueError("FallbackSolver precisa de pelo menos um solver")
        self._solvers = solvers
        self._cooldown = cooldown
        self._livre_em: dict[int, float] = {}

    @property
    def nome(self) -> str:
        return "fallback(" + ", ".join(s.nome for s in self._solvers) + ")"

    def solve(self, question: Question) -> Suggestion:
        erros: list[str] = []
        for i, solver in enumerate(self._solvers):
            if self._livre_em.get(i, 0.0) > time.monotonic():
                continue
            try:
                return solver.solve(question)
            except SolverError as erro:
                self._livre_em[i] = time.monotonic() + self._cooldown
                erros.append(str(erro))
                print(f"[aviso] {erro}")
        if not erros:
            raise SolverError("todos os provedores estao em pausa, tente a proxima questao")
        raise SolverError(" | ".join(erros))
