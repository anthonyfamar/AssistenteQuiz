# FALLBACK - tenta um provedor; se falhar, passa para o proximo.
#
# FallbackSolver -> recebe uma LISTA de solvers e e, ele proprio, um Solver.
#                   A lista vem em ORDEM DE QUALIDADE (veja fabrica.py): o melhor modelo de
#                   cada provedor, depois os reserva dele, depois o proximo provedor.
#                   Questao com imagem so e tentada em quem aceita imagem.
#
#                   Rapido, sem prender a resposta:
#                   - cada tentativa espera pouco (timeout_rapido, ~5 s) se ainda ha outro modelo
#                     livre depois; so o ultimo da fila espera o tempo cheio (timeout_final).
#                     Modelo que pensa devagar tem um fator (Solver.fator_de_espera);
#                   - um modelo que falha fica PAUSADO e uma thread em segundo plano ("vigia")
#                     testa, de tempos em tempos, se ele voltou (um pedido minusculo, sondar()).
#                     So quando o teste passa ele volta para a fila. As respostas nunca esperam
#                     por esse teste. O intervalo dobra a cada teste que falha (ate um teto);
#                   - se o servidor disse QUANTO esperar (erro 429: "tente de novo em 1,4 s" ou
#                     "em 5 h 55 min"), vale esse tempo exato: o modelo volta para a fila no
#                     instante combinado, sem esperar o teste (quem pediu 1,4 s nao fica 30 s fora).
#                     O vigia dorme no maximo 1 h de cada vez, mas o tempo real fica guardado;
#                   - erro que esperar nao resolve (chave recusada, "pede credito pago") tira o
#                     modelo da fila ate o programa abrir de novo, sem testes em segundo plano;
#                   - se dois modelos do MESMO provedor falham DEMORANDO na mesma questao, o
#                     provedor inteiro e pausado e o programa vai direto ao proximo (falha
#                     rapida nao conta: o proximo modelo do provedor ainda e tentado).
#
#                   Quando NENHUM responde, o erro diz a situacao de cada provedor e quanto falta
#                   para ele voltar ("Gemini: volta em 5 h 56 min (as 04:31)"). O SolverError leva
#                   em espera_sugerida o menor desses tempos: o assistente espera sozinho se for
#                   curto (segundos); se for longo, o usuario ve o aviso e volta mais tarde.
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
from datetime import datetime, timedelta

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
# O vigia dorme no maximo isto (s) de cada vez, mesmo que o servidor peca mais (cota do dia).
TETO_ESPERA_DO_VIGIA = 3600.0


def formatar_espera(segundos: float) -> str:
    """'40 s', '12 min', '5 h 56 min' (minutos arredondados para cima: melhor sobrar que faltar)."""
    total = max(int(round(segundos)), 0)
    if total < 60:
        return f"{max(total, 1)} s"
    minutos = (total + 59) // 60
    if minutos < 60:
        return f"{minutos} min"
    horas, resto = divmod(minutos, 60)
    return f"{horas} h" if resto == 0 else f"{horas} h {resto:02d} min"


def _quando(segundos: float) -> str:
    """O tempo que falta e, a partir de 1 h, a hora do relogio em que acaba ("5 h 56 min, as 04:31")."""
    texto = formatar_espera(segundos)
    if segundos >= 3600:
        texto += f", às {(datetime.now() + timedelta(seconds=segundos)):%H:%M}"
    return texto


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
        self._permanentes: set[int] = set()  # fora da fila ate o programa abrir de novo
        self._vigias: set[int] = set()  # posicoes que ja tem um vigia rodando
        self._espera_minima: dict[int, float] = {}  # posicao -> segundos pedidos pelo servidor (cota)
        self._volta_em: dict[int, float] = {}  # posicao -> instante (monotonic) em que o servidor libera
        self._falhas_seguidas: dict[int, int] = {}  # posicao -> falhas sem nenhum acerto no meio
        self._ultimo_motivo: dict[str, str] = {}  # provedor -> por que falhou da ultima vez

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
        # espera_minima: o servidor disse quanto esperar (cota): nao testa nem tenta antes disso.
        with self._trava:
            self._pausados.add(posicao)
            self._espera_minima[posicao] = max(self._espera_minima.get(posicao, 0.0), espera_minima)
            if espera_minima > 0:
                self._volta_em[posicao] = time.monotonic() + espera_minima
            else:
                self._volta_em.pop(posicao, None)
            if posicao in self._vigias:
                return
            self._vigias.add(posicao)
        threading.Thread(target=self._vigiar, args=(posicao,), daemon=True, name=f"vigia-{posicao}").start()

    def _pausar_para_sempre(self, posicao: int) -> None:
        # Esperar nao resolve (chave recusada, pede credito pago): sem vigia, sem testes.
        with self._trava:
            self._pausados.add(posicao)
            self._permanentes.add(posicao)
            self._volta_em.pop(posicao, None)

    def _vigiar(self, posicao: int) -> None:
        # Roda numa thread propria. Testa o modelo pausado ate ele responder; a thread principal
        # nem percebe. Qualquer erro aqui e so registrado: o vigia nunca derruba o programa.
        solver = self._solvers[posicao]
        while True:
            with self._trava:
                minima = self._espera_minima.pop(posicao, 0.0)
            if minima > 0:  # o servidor disse quanto: dorme esse tempo (mais 1 s de folga), sem o cooldown
                time.sleep(min(minima, TETO_ESPERA_DO_VIGIA) + 1.0)
            else:
                time.sleep(self._pausa_para(posicao))
            try:
                voltou = solver.sondar(self._timeout_rapido)
            except Exception as erro:  # noqa: BLE001 - o vigia precisa sobreviver a qualquer coisa
                print(f"[aviso] teste de {solver.descricao} deu erro inesperado: {erro!r}")
                voltou = False
            if voltou:
                with self._trava:
                    self._pausados.discard(posicao)
                    self._vigias.discard(posicao)
                    self._volta_em.pop(posicao, None)
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
            if posicao not in self._pausados:
                return False
            if posicao in self._permanentes:
                return True
            # O servidor disse ate quando: passou da hora, o modelo ja pode ser tentado (nao precisa
            # esperar o vigia). Se falhar de novo, volta para a pausa com o novo tempo.
            volta = self._volta_em.get(posicao)
            return not (volta is not None and time.monotonic() >= volta)

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
        if erro.permanente:
            acao = f"tirou {alvo} da fila até o programa ser aberto de novo (esperar não resolve)"
        elif erro.espera_sugerida is not None:
            acao = f"tirou {alvo} da fila: o servidor pediu para esperar {_quando(erro.espera_sugerida)}"
        else:
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

    def _limite_de_espera(self, question: Question, ha_proximo: bool, solver: Solver) -> float:
        # Com outro modelo livre depois, nao vale esperar muito; o ultimo da fila espera tudo.
        # Modelo que pensa devagar (fator > 1) ganha mais tempo.
        limite = (self._timeout_rapido if ha_proximo else self._timeout_final) * solver.fator_de_espera
        return limite * IMAGEM_VEZES if question.imagens else limite

    # --- quando ninguem responde: a situacao de cada provedor ---

    def _situacao_dos_provedores(self) -> tuple[list[str], tuple[float, str] | None]:
        """Uma frase por provedor e (tempo em s, nome) de quem volta primeiro (None = ninguem sabe)."""
        agora = time.monotonic()
        grupos: dict[str, list[int]] = {}
        for i, solver in enumerate(self._solvers):
            grupos.setdefault(solver.nome, []).append(i)
        frases: list[str] = []
        menor: tuple[float, str] | None = None
        for nome, posicoes in grupos.items():
            apelido = self._solvers[posicoes[0]].apelido
            motivo = self._ultimo_motivo.get(nome, "sem resposta")
            vivos = [i for i in posicoes if i not in self._permanentes]
            if not vivos:
                frases.append(f"{apelido}: {motivo}, fora da fila")
                continue
            tempos = [max(self._volta_em[i] - agora, 0.0) for i in vivos if i in self._volta_em]
            if len(tempos) == len(vivos):  # o servidor disse quanto falta para todos os modelos dele
                falta = min(tempos)
                frases.append(f"{apelido}: {motivo}, volta em {_quando(falta)}")
                if menor is None or falta < menor[0]:
                    menor = (falta, apelido)
            else:
                frases.append(f"{apelido}: {motivo}, sem previsão (o programa testa de novo sozinho)")
        return frases, menor

    def _erro_de_ninguem_responde(self) -> SolverError:
        frases, primeiro = self._situacao_dos_provedores()
        if primeiro is not None:
            falta, quem = primeiro
            final = f"Volte mais tarde: a primeira a voltar é {quem}, em {_quando(falta)}."
        else:
            falta = None
            final = "Sem previsão: tente de novo daqui a alguns minutos."
        return SolverError(
            "nenhuma IA respondeu agora. " + " | ".join(frases) + ". " + final,
            espera_sugerida=falta,
        )

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

        avisos: list[str] = []
        falhas_do_provedor: dict[str, int] = {}  # nesta questao: quantos modelos de cada provedor falharam
        for i, solver in candidatos:
            if self._esta_pausado(i):
                continue
            limite = self._limite_de_espera(question, self._proximo_livre(candidatos, i) is not None, solver)
            inicio = time.monotonic()
            try:
                sugestao = solver.solve_com_limite(question, limite)
            except SolverError as erro:
                with self._trava:
                    self._falhas_seguidas[i] = self._falhas_seguidas.get(i, 0) + 1
                    self._ultimo_motivo[solver.nome] = erro.motivo or erro.resumo
                espera = erro.espera_sugerida or 0.0
                pausa = min(espera, TETO_ESPERA_DO_VIGIA) + 1.0 if espera > 0 else self._pausa_para(i)
                # So falha LENTA (esperou quase o limite) conta contra o provedor: falha rapida
                # (cota, 503) nao custa nada e o proximo modelo dele pode estar funcionando.
                if time.monotonic() - inicio >= limite * FRACAO_LENTA:
                    falhas_do_provedor[solver.nome] = falhas_do_provedor.get(solver.nome, 0) + 1
                # Dois modelos do mesmo provedor demoraram e falharam: o provedor esta mal. Tira
                # todos os modelos dele da fila e segue para o proximo provedor.
                provedor_todo = falhas_do_provedor.get(solver.nome, 0) >= FALHAS_PARA_PAUSAR_PROVEDOR
                if erro.permanente:
                    self._pausar_para_sempre(i)
                else:
                    self._pausar(i, espera)
                if provedor_todo:
                    for j, outro in enumerate(self._solvers):
                        if outro.nome == solver.nome:
                            self._pausar(j)
                avisos.append(erro.aviso)
                self._registrar_falha(
                    solver, erro, self._proximo_livre(candidatos, i), pausa, provedor_todo
                )
                self._avisar(avisos)
                continue
            with self._trava:
                self._falhas_seguidas.pop(i, None)  # acertou: o proximo teste volta a ser o curto
                self._pausados.discard(i)  # era um modelo liberado pelo relogio: voltou de vez
                self._volta_em.pop(i, None)
            return sugestao
        raise self._erro_de_ninguem_responde()
