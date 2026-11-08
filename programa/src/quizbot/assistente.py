# ASSISTENTE - o "loop": junta tudo.
#
# AssistenteQuiz -> a cada ~0,5 segundo (polling, veja INTERVALO_POLLING no config.py):
#                   1. pede a questao ao PageReader;
#                   2. se for diferente da anterior (Question.__eq__), e questao nova;
#                   3. manda para o Solver, que devolve a Suggestion;
#                   4. entrega ao Presenter para mostrar;
#                   5. modo automatico (se houver um Responder): marca a alternativa
#                      sugerida e, so se a marca ficou, avanca para a proxima pagina.
#                      Sem questao na tela, tenta finalizar (so se "finalizar" estiver
#                      ligado; o Responder so acha o botao na pagina de resumo).
#                   6. na pagina de REVISAO (depois de enviar), le o que o Moodle deu como
#                      certo e errado e guarda na Memoria (certas e erradas). Isso vem
#                      ANTES de ler a questao, para uma revisao nunca ser tratada como
#                      questao.
#                   Guarda a ultima questao para nao consultar a IA duas vezes.
#                   Avisa o Presenter quando comeca a consultar a IA (para a tela nao
#                   mostrar a resposta da questao anterior) e quando a consulta falha.
#                   O laco para quando o Event "parar" e acionado.
import threading

from quizbot.config import PAUSA_APOS_CLICAR
from quizbot.memoria import Memoria
from quizbot.models import Question, Suggestion
from quizbot.page_reader import LeituraIncompleta, PageReader
from quizbot.presenter import Presenter
from quizbot.responder import Responder
from quizbot.solvers import Solver, SolverError


class AssistenteQuiz:
    def __init__(
        self,
        reader: PageReader,
        solver: Solver,
        presenter: Presenter,
        intervalo: float = 1.0,
        parar: threading.Event | None = None,
        responder: Responder | None = None,
        finalizar: bool = False,
        memoria: Memoria | None = None,
    ) -> None:
        self._reader = reader
        self._solver = solver
        self._presenter = presenter
        self._intervalo = intervalo
        self._parar = parar if parar is not None else threading.Event()
        self._responder = responder
        self._finalizar = finalizar
        self._memoria = memoria
        self._ultima: Question | None = None
        self._ultimo_aviso: str | None = None
        self._enviada = False

    def _agir(self, sugestao: Suggestion) -> None:
        if self._responder is None:
            return
        if not self._responder.clicar(sugestao.indice):
            self._presenter.avisar("Não consegui marcar a alternativa. Marque você mesmo.")
            return
        self._parar.wait(PAUSA_APOS_CLICAR)
        if not self._responder.avancar():
            self._presenter.avisar("Marquei a alternativa, mas não achei o botão de avançar.")

    def _tentar_finalizar(self) -> None:
        # "_enviada" evita enviar duas vezes se a pagina ainda nao trocou no tick seguinte.
        if self._responder is None or not self._finalizar or self._enviada:
            return
        if self._responder.terminar():
            self._enviada = True
            self._presenter.avisar("Tentativa enviada.")

    def _registrar_revisao(self) -> bool:
        if self._memoria is None:
            return False
        resultados = self._reader.ler_revisao()
        if not resultados:
            return False
        erradas, certas = self._memoria.registrar_revisao(resultados)
        if erradas or certas:
            total_erradas = sum(1 for r in resultados if not r.acertou)
            print(
                f"[revisao] {len(resultados)} questoes, {total_erradas} errada(s) | "
                f"guardado agora: {certas} certa(s), {erradas} errada(s)"
            )
            self._presenter.avisar(
                f"Revisão lida: guardei {certas} certa(s) e {erradas} errada(s) na memória."
            )
        return True

    def _passo(self) -> None:
        if self._registrar_revisao():
            self._ultima = None
            self._enviada = False
            return
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
            self._tentar_finalizar()
            return
        if questao == self._ultima:
            return

        self._ultima = questao
        self._enviada = False
        codigos = ", ".join(f"[img:{imagem.codigo}]" for imagem in questao.imagens)
        print(
            f"[leitura] {len(questao.alternativas)} alternativas, "
            f"{len(questao.imagens)} imagem(ns){' ' + codigos if codigos else ''} "
            f"| {questao.enunciado[:100]!r}"
        )
        self._presenter.consultando()
        try:
            sugestao = self._solver.solve(questao)
        except SolverError as erro:
            self._presenter.avisar(f"Não consegui uma sugestão: {erro}")
            return
        self._presenter.mostrar(questao, sugestao)
        self._agir(sugestao)

    def rodar(self) -> None:
        while not self._parar.is_set():
            self._passo()
            self._parar.wait(self._intervalo)
