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
#                      questao. Com a revisao guardada em algum lugar (local ou nuvem),
#                      aperta "Terminar revisao" (modo automatico).
#                   7. na pagina INICIAL do quiz (sem questao na tela), se as tentativas
#                      automaticas estiverem ligadas, olha o painel: comeca ou continua a
#                      tentativa, faz outra se nao acertou tudo, para se acertou tudo e,
#                      sem mais tentativas, mostra a nota por 20 s e volta ao curso.
#                   Guarda a ultima questao para nao consultar a IA duas vezes.
#                   Avisa o Presenter quando comeca a consultar a IA (para a tela nao
#                   mostrar a resposta da questao anterior) e quando a consulta falha.
#                   O laco para quando o Event "parar" e acionado.
import threading

from quizbot.config import PAUSA_ANTES_DE_VOLTAR, PAUSA_APOS_CLICAR
from quizbot.memoria import Memoria
from quizbot.models import PainelQuiz, Question, Situacao, Suggestion
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
        tentativas: bool = False,
        pausa_voltar: float = PAUSA_ANTES_DE_VOLTAR,
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
        self._revisao_fechada = False
        self._avisou_pendente = False
        self._tentativas = tentativas
        self._pausa_voltar = pausa_voltar
        self._painel_agido = False
        self._aviso_painel: str | None = None
        self._ultimo_painel: PainelQuiz | None = None

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

    def _tentar_terminar_revisao(self) -> None:
        # So depois de guardar em PELO MENOS um lugar (arquivo local ou nuvem). Se a nuvem
        # falhou mas o local gravou, clica mesmo assim: a nuvem recebe depois, sozinha.
        # So espera se nada gravou; a memoria tenta de novo e o proximo tick confere.
        # "_revisao_fechada" evita clicar de novo se a pagina ainda nao trocou no tick seguinte.
        if self._responder is None or self._memoria is None or self._revisao_fechada:
            return
        if not self._memoria.garantir_guardado():
            if not self._avisou_pendente:
                self._avisou_pendente = True
                self._presenter.avisar(
                    "Li a revisão, mas não consegui salvar nem no arquivo local nem na nuvem. "
                    "Só termino a revisão depois de salvar; tentando de novo."
                )
            return
        if self._responder.terminar_revisao():
            self._revisao_fechada = True
            self._presenter.avisar("Revisão terminada.")
        else:
            self._avisar_uma_vez('Não achei o botão "Terminar revisão". Clique você mesmo.')

    def _avisar_uma_vez(self, mensagem: str) -> None:
        if mensagem != self._aviso_painel:
            self._aviso_painel = mensagem
            self._presenter.avisar(mensagem)

    def _quiz_concluido(self, painel: PainelQuiz) -> None:
        # Tirou a nota maxima (ainda com tentativas sobrando): nao ha por que refazer.
        # Mostra a nota e volta ao curso, como quando as tentativas acabam.
        # ESPACO PARA O FUTURO: depois de voltar ao curso, aqui entra ir para o proximo quiz.
        self._voltar_ao_curso(painel, "Acertou tudo.")

    def _voltar_ao_curso(self, painel: PainelQuiz, motivo: str = "") -> None:
        # Mostra a nota, espera e volta ao curso. Se a pagina mudar durante a espera
        # (o usuario foi para outro lugar ou refez a tentativa), cancela e nao clica.
        segundos = int(self._pausa_voltar)
        resumo = f"{painel.resumo_das_notas()} {motivo}".strip()
        self._presenter.avisar(f"{resumo} Voltando ao curso em {segundos} s.")
        for passou in range(segundos):
            if self._parar.wait(1):
                return
            atual = self._reader.ler_painel()
            if atual is None or atual.situacao is not painel.situacao:
                return
            if passou + 1 == segundos // 2:
                self._presenter.avisar(f"{resumo} Voltando ao curso em {segundos - passou - 1} s.")
        self._painel_agido = True
        if not self._responder.voltar_ao_curso():
            self._presenter.avisar("Não consegui voltar ao curso. Volte você mesmo.")

    def _cuidar_do_painel(self) -> None:
        # Pagina inicial do quiz: decide pelo que a pagina mostra (veja a tabela no topo).
        if self._responder is None or not self._tentativas:
            return
        painel = self._reader.ler_painel()
        if painel is None:  # saiu da pagina inicial: o proximo painel conta como novo
            self._painel_agido = False
            self._aviso_painel = None
            self._ultimo_painel = None
            return
        if self._painel_agido:  # ja agiu nesta visita; espera a pagina trocar
            return
        if painel != self._ultimo_painel:  # imprime so quando muda, nao a cada 0,5 s
            self._ultimo_painel = painel
            notas = f", {painel.resumo_das_notas()}" if painel.tentativas else ""
            print(f"[painel] {painel.situacao.value}, {len(painel.tentativas)} tentativa(s){notas}")

        if painel.situacao is Situacao.ESGOTADO:
            self._voltar_ao_curso(painel)
            return
        if painel.situacao is Situacao.PODE_REFAZER:
            if painel.tudo_certo:
                self._quiz_concluido(painel)
                return
            if painel.ultima is None or painel.nota_maxima is None:
                self._avisar_uma_vez("Não consegui ler a nota na tabela; não vou começar outra tentativa.")
                return
        if self._responder.iniciar_tentativa():
            self._painel_agido = True
        else:
            self._avisar_uma_vez("Não achei o botão para começar a tentativa. Clique você mesmo.")

    def _passo(self) -> None:
        if self._registrar_revisao():
            self._ultima = None
            self._enviada = False
            self._tentar_terminar_revisao()
            return
        self._revisao_fechada = False
        self._avisou_pendente = False
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
            self._cuidar_do_painel()
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
