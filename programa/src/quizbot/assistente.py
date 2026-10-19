# ASSISTENTE - o "loop": junta tudo.
#
# AssistenteQuiz -> a cada ~0,5 segundo (polling, veja INTERVALO_POLLING no config.py):
#                   1. pede a questao ao PageReader;
#                   2. se for diferente da anterior (Question.__eq__), e questao nova;
#                   3. manda para o Solver, que devolve a Suggestion;
#                   4. entrega ao Presenter para mostrar.
#                   Guarda a ultima questao para nao consultar a IA duas vezes.
#                   Avisa o Presenter quando comeca a consultar a IA (para a tela nao
#                   mostrar a resposta da questao anterior) e quando a consulta falha.
#                   O laco para quando o Event "parar" e acionado.
import threading

from quizbot.models import Question
from quizbot.page_reader import LeituraIncompleta, PageReader
from quizbot.presenter import Presenter
from quizbot.solvers import Solver, SolverError


class AssistenteQuiz:
    def __init__(
        self,
        reader: PageReader,
        solver: Solver,
        presenter: Presenter,
        intervalo: float = 1.0,
        parar: threading.Event | None = None,
    ) -> None:
        self._reader = reader
        self._solver = solver
        self._presenter = presenter
        self._intervalo = intervalo
        self._parar = parar if parar is not None else threading.Event()
        self._ultima: Question | None = None
        self._ultimo_aviso: str | None = None

    def _passo(self) -> None:
        try:
            questao = self._reader.ler_questao()
        except LeituraIncompleta as erro:
            aviso = str(erro)
            if aviso != self._ultimo_aviso:
                self._ultimo_aviso = aviso
                self._presenter.avisar(aviso)
            return
        self._ultimo_aviso = None
        if questao is None:
            self._ultima = None
            return
        if questao == self._ultima:
            return

        self._ultima = questao
        print(
            f"[leitura] {len(questao.alternativas)} alternativas, "
            f"{len(questao.imagens)} imagem(ns) | {questao.enunciado[:100]!r}"
        )
        self._presenter.consultando()
        try:
            sugestao = self._solver.solve(questao)
        except SolverError as erro:
            self._presenter.avisar(f"Não consegui uma sugestão: {erro}")
            return
        self._presenter.mostrar(questao, sugestao)

    def rodar(self) -> None:
        while not self._parar.is_set():
            self._passo()
            self._parar.wait(self._intervalo)
