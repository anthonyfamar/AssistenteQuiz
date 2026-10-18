# ASSISTENTE - o "loop": junta tudo.
#
# AssistenteQuiz -> a cada ~1 segundo (polling):
#                   1. pede a questao ao PageReader;
#                   2. se for diferente da anterior (Question.__eq__), e questao nova;
#                   3. manda para o Solver, que devolve a Suggestion;
#                   4. entrega ao Presenter para mostrar.
#                   Guarda a ultima questao para nao consultar a IA duas vezes.
import time

from quizbot.models import Question
from quizbot.page_reader import PageReader
from quizbot.presenter import Presenter
from quizbot.solvers import Solver, SolverError


class AssistenteQuiz:
    def __init__(
        self,
        reader: PageReader,
        solver: Solver,
        presenter: Presenter,
        intervalo: float = 1.0,
    ) -> None:
        self._reader = reader
        self._solver = solver
        self._presenter = presenter
        self._intervalo = intervalo
        self._ultima: Question | None = None

    def _passo(self) -> None:
        questao = self._reader.ler_questao()
        if questao is None:
            self._ultima = None
            return
        if questao == self._ultima:
            return

        self._ultima = questao
        try:
            sugestao = self._solver.solve(questao)
        except SolverError as erro:
            print(f"[aviso] Não consegui uma sugestão: {erro}")
            return
        self._presenter.mostrar(questao, sugestao)

    def rodar(self) -> None:
        while True:
            self._passo()
            time.sleep(self._intervalo)
