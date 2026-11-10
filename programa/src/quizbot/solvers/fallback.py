# FALLBACK - tenta um provedor; se falhar, passa para o proximo.
#
# FallbackSolver -> recebe uma LISTA de solvers e e, ele proprio, um Solver.
#                   A lista vem em ORDEM DE QUALIDADE (veja fabrica.py): o melhor modelo de
#                   cada provedor, depois os reserva dele, depois o proximo provedor.
#                   Questao com imagem so e tentada em quem aceita imagem.
#
#                   Rapido, sem prender a resposta:
#                   - cada tentativa espera pouco (timeout_rapido, ~5 s) se ainda ha outro modelo
#                     livre depois; so o ultimo da fila espera o tempo cheio (timeout_final);
#                   - um modelo que falha fica PAUSADO e uma thread em segundo plano ("vigia")
#                     testa, de tempos em tempos, se ele voltou (um pedido minusculo, sondar()).
#                     So quando o teste passa ele volta para a fila. As respostas nunca esperam
#                     por esse teste. O intervalo dobra a cada teste que falha (ate um teto);
#                   - se a cota acabou (erro 429), o vigia espera o tempo que o servidor pediu
#                     (ate 1 h) antes de testar;
#                   - se dois modelos do MESMO provedor falham DEMORANDO na mesma questao, o
#                     provedor inteiro e pausado e o programa vai direto ao proximo (falha
#                     rapida nao conta: o proximo modelo do provedor ainda e tentado).
#
#                   Falha nunca passa em silencio:
#                   - o registro (log) recebe o erro COMPLETO: modelo, tempo, codigo HTTP,
#                     resposta do servidor e o rastro tecnico (para o desenvolvedor);
#                   - ao_mudar_problemas(lista) e chamado com os avisos das falhas DESTA consulta
#                     (frases diretas, ex.: "Algo deu errado: API do Gemini fora do ar."); a janela
#                     mostra por alguns segundos e apaga sozinha.
import threading
import time
import traceback
from collections.abc import Callable

from quizbot.models import Question, Suggestion
from quizbot.solvers.base import Solver, SolverError

# Quantos modelos do MESMO provedor podem falhar numa questao antes de pausar o provedor inteiro.
FALHAS_PARA_PAUSAR_PROVEDOR = 2
# O intervalo entre testes dobra a cada falha, mas nunca passa de cooldown x este numero.
TETO_PAUSA_VEZES = 6
# Questao com imagem leva mais tempo para enviar e ler: espera o dobro.
IMAGEM_VEZES = 2
# A falha so e "lenta" (conta contra o provedor) se demorou pelo menos esta fracao do limite.
FRACAO_LENTA = 0.8


class FallbackSolver(Solver):
    def __init__(
        self,
        solvers: list[Solver],
        cooldown: float = 30.0,
        ao_mudar_problemas: Callable[[list[str]], None] | None = None,
        timeout_rapido: float = 5.0,
        timeout_final: float = 15.0,
    ) -> None:
        if not solvers:
            raise ValueError("FallbackSolver precisa de pelo menos um solver")
        self._solvers = solvers
        self._cooldown = cooldown  # espera ate o 1o teste em segundo plano
        self._ao_mudar_problemas = ao_mudar_problemas
        self._timeout_rapido = timeout_rapido
        self._timeout_final = timeout_final

        self._trava = threading.Lock()  # a thread principal e os vigias mexem no mesmo estado
        self._pausados: set[int] = set()  # posicoes fora da fila ate o teste passar
        self._vigias: set[int] = set()  # posicoes que ja tem um vigia rodando
        self._espera_minima: dict[int, float] = {}  # posicao -> segundos pedidos pelo servidor (cota)
        self._falhas_seguidas: dict[int, int] = {}  # posicao -> falhas sem nenhum acerto no meio

    @property
    def nome(self) -> str:
        return "fallback(" + ", ".join(s.descricao for s in self._solvers) + ")"

    @property
    def aceita_imagens(self) -> bool:
        return any(s.aceita_imagens for s in self._solvers)

    # --- pausa e vigia (segundo plano) ---

    def _pausa_para(self, posicao: int) -> float:
        # Espera ate o proximo teste: dobra a cada falha seguida (30, 60, 120... ate o teto).
        falhas = max(self._falhas_seguidas.get(posicao, 1), 1)
        return min(self._cooldown * 2 ** (falhas - 1), self._cooldown * TETO_PAUSA_VEZES)

    def _pausar(self, posicao: int, espera_minima: float = 0.0) -> None:
        # espera_minima: o servidor pediu para esperar (cota do dia acabou): nao testa antes disso.
        with self._trava:
            self._pausados.add(posicao)
            self._espera_minima[posicao] = max(self._espera_minima.get(posicao, 0.0), espera_minima)
            if posicao in self._vigias:
                return
            self._vigias.add(posicao)
        threading.Thread(target=self._vigiar, args=(posicao,), daemon=True, name=f"vigia-{posicao}").start()

    def _vigiar(self, posicao: int) -> None:
        # Roda numa thread propria. Testa o modelo pausado ate ele responder; a thread principal
        # nem percebe. Qualquer erro aqui e so registrado: o vigia nunca derruba o programa.
        solver = self._solvers[posicao]
        while True:
            with self._trava:
                minima = self._espera_minima.pop(posicao, 0.0)
            time.sleep(max(self._pausa_para(posicao), minima))
            try:
                voltou = solver.sondar(self._timeout_rapido)
            except Exception as erro:  # noqa: BLE001 - o vigia precisa sobreviver a qualquer coisa
                print(f"[aviso] teste de {solver.descricao} deu erro inesperado: {erro!r}")
                voltou = False
            if voltou:
                with self._trava:
                    self._pausados.discard(posicao)
                    self._vigias.discard(posicao)
                    self._falhas_seguidas.pop(posicao, None)
                print(f"[aviso] {solver.descricao} voltou a funcionar e entrou de novo na fila.")
                return
            with self._trava:
                self._falhas_seguidas[posicao] = self._falhas_seguidas.get(posicao, 0) + 1
            print(
                f"[aviso] {solver.descricao} ainda não voltou; "
                f"próximo teste em {int(self._pausa_para(posicao))} s."
            )

    def _esta_pausado(self, posicao: int) -> bool:
        with self._trava:
            return posicao in self._pausados

    # --- registro e alerta ---

    def _avisar(self, avisos: list[str]) -> None:
        if self._ao_mudar_problemas is not None:
            # Sem repetir: dois modelos do mesmo provedor com o mesmo problema viram uma linha.
            self._ao_mudar_problemas(list(dict.fromkeys(avisos)))

    def _registrar_falha(
        self,
        solver: Solver,
        erro: SolverError,
        proximo: Solver | None,
        pausa: float,
        provedor_todo: bool,
    ) -> None:
        # Bloco delimitado e em ordem: primeiro o que um humano precisa (o que houve, o que o
        # programa fez), depois o rastro tecnico. Da para copiar o bloco inteiro e colar numa IA.
        alvo = f"todos os modelos de {solver.nome}" if provedor_todo else "este modelo"
        acao = f"tirou {alvo} da fila (teste em segundo plano daqui a {int(pausa)} s)"
        if proximo is not None:
            acao += f" e passou para {proximo.descricao}."
        else:
            acao += "; não há outro modelo livre agora."
        print(f"[aviso] {erro.resumo}")
        print("=============== PROBLEMA COM A IA ===============")
        print(f"O que aconteceu  : {erro.resumo}")
        if erro.detalhe:
            print(erro.detalhe)
        print(f"O programa fez   : {acao}")
        print("--- rastro técnico (para quem vai corrigir o código) ---")
        print("".join(traceback.format_exception(erro)).rstrip())
        print("=============== FIM DO PROBLEMA ===============")

    def _proximo_livre(self, candidatos: list[tuple[int, Solver]], depois_de: int) -> Solver | None:
        for i, solver in candidatos:
            if i > depois_de and not self._esta_pausado(i):
                return solver
        return None

    def _limite_de_espera(self, question: Question, ha_proximo: bool) -> float:
        # Com outro modelo livre depois, nao vale esperar muito; o ultimo da fila espera tudo.
        limite = self._timeout_rapido if ha_proximo else self._timeout_final
        return limite * IMAGEM_VEZES if question.imagens else limite

    # --- o trabalho de verdade ---

    def solve(self, question: Question) -> Suggestion:
        candidatos = [
            (i, solver)
            for i, solver in enumerate(self._solvers)
            if solver.aceita_imagens or not question.imagens
        ]
        if not candidatos:
            raise SolverError(
                "a questao tem imagem, mas nenhum provedor tem modelo de visao "
                "(preencha *_MODEL_VISAO no .env)"
            )

        erros: list[str] = []
        avisos: list[str] = []
        falhas_do_provedor: dict[str, int] = {}  # nesta questao: quantos modelos de cada provedor falharam
        for i, solver in candidatos:
            if self._esta_pausado(i):
                continue
            limite = self._limite_de_espera(question, self._proximo_livre(candidatos, i) is not None)
            inicio = time.monotonic()
            try:
                sugestao = solver.solve_com_limite(question, limite)
            except SolverError as erro:
                with self._trava:
                    self._falhas_seguidas[i] = self._falhas_seguidas.get(i, 0) + 1
                espera = erro.espera_sugerida or 0.0
                pausa = max(self._pausa_para(i), espera)
                # So falha LENTA (esperou quase o limite) conta contra o provedor: falha rapida
                # (cota, 503) nao custa nada e o proximo modelo dele pode estar funcionando.
                if time.monotonic() - inicio >= limite * FRACAO_LENTA:
                    falhas_do_provedor[solver.nome] = falhas_do_provedor.get(solver.nome, 0) + 1
                # Dois modelos do mesmo provedor demoraram e falharam: o provedor esta mal. Tira
                # todos os modelos dele da fila e segue para o proximo provedor.
                provedor_todo = falhas_do_provedor.get(solver.nome, 0) >= FALHAS_PARA_PAUSAR_PROVEDOR
                self._pausar(i, espera)
                if provedor_todo:
                    for j, outro in enumerate(self._solvers):
                        if outro.nome == solver.nome:
                            self._pausar(j)
                erros.append(erro.resumo)
                avisos.append(erro.aviso)
                self._registrar_falha(
                    solver, erro, self._proximo_livre(candidatos, i), pausa, provedor_todo
                )
                self._avisar(avisos)
                continue
            with self._trava:
                self._falhas_seguidas.pop(i, None)  # acertou: o proximo teste volta a ser o curto
            return sugestao
        if not erros:
            raise SolverError("todos os provedores estao em pausa, tente a proxima questao")
        raise SolverError(" | ".join(erros))
