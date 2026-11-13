# ASSISTENTE - o "loop": junta tudo.
#
# AssistenteQuiz -> a cada ~0,5 segundo (polling, veja INTERVALO_POLLING no config.py):
#                   1. pede a questao ao PageReader;
#                   2. se for diferente da anterior (Question.__eq__), e questao nova;
#                   3. manda para o Solver, que devolve a Suggestion;
#                   4. entrega ao Presenter para mostrar;
#                   5. modo automatico (se houver um Responder): marca a alternativa
#                      sugerida e, so se a marca ficou, avanca para a proxima pagina.
#                      Questao que JA tem alternativa marcada nao e respondida de novo: o
#                      programa mantem a resposta e so avanca.
#                      Sem questao na tela, tenta finalizar (so se "finalizar" estiver
#                      ligado; o Responder so acha o botao na pagina de resumo). ANTES de
#                      enviar, confere o resumo: se alguma questao ficou sem resposta, abre a
#                      primeira que falta, responde, e volta ao resumo; so envia com todas
#                      respondidas (se uma nao der, avisa e NAO envia).
#                   8. na pagina do CURSO (o menu das unidades), no Automatico, o RoteiroDoCurso
#                      (curso.py) manda abrir cada unidade e, nela, os 2 quizzes (Atividade de
#                      Aprendizagem e Avaliacao da Unidade); o resto e o que ja existe (painel,
#                      responder, enviar, revisao). Quiz terminado = marcado como conferido e
#                      volta ao curso. Algo fora do esperado: para e avisa o usuario.
#                      Ao concluir, pergunta: "Outra materia" (espera o usuario abrir OUTRO curso
#                      e recomeca) ou "Encerrar" (para o programa).
#                   6. na pagina de REVISAO (depois de enviar), le o que o Moodle deu como
#                      certo e errado e guarda na Memoria (certas e erradas). Isso vem
#                      ANTES de ler a questao, para uma revisao nunca ser tratada como
#                      questao. Com a revisao guardada em algum lugar (local ou nuvem),
#                      aperta "Terminar revisao" (modo automatico) SE a revisao foi aberta pelo
#                      programa (acabou de enviar, ou clicou em "Revisao" na tabela). Revisao que
#                      o USUARIO abriu: guarda e deixa aberta (ele pode estar lendo).
#                   9. na pagina INICIAL do quiz, antes de comecar outra tentativa (ou de voltar ao
#                      curso), le a revisao de cada tentativa finalizada que ainda nao leu: clica no
#                      link "Revisao" da tabela, guarda as certas e erradas e fecha. Assim a
#                      tentativa nova ja descarta as alternativas erradas. Quem decide o que ja foi
#                      lido e o attempt= do Moodle (ou o numero da linha, se o link nao o trouxer).
#                   7. na pagina INICIAL do quiz (sem questao na tela), se as tentativas
#                      automaticas estiverem ligadas, olha o painel: comeca ou continua a
#                      tentativa, faz outra se nao acertou tudo, para se acertou tudo e,
#                      sem mais tentativas, mostra a nota por 5 s e volta ao curso.
#                   Se marcar, avancar ou obter a sugestao falhar, tenta mais uma vez e, se ainda
#                   falhar, a janela MANTEM a sugestao na tela e mostra "Tentar de novo": o botao
#                   so avisa (a acao roda na thread do assistente) e o fluxo segue.
#                   Guarda a ultima questao para nao consultar a IA duas vezes.
#                   Avisa o Presenter quando comeca a consultar a IA (para a tela nao
#                   mostrar a resposta da questao anterior) e quando a consulta falha.
#                   O laco para quando o Event "parar" e acionado.
import threading
import time
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse
from string import ascii_uppercase

from quizbot.config import (
    ESPERA_CURTA_DA_IA,
    ESPERA_PELA_REVISAO,
    ESPERA_PELA_REVISAO_ANTIGA,
    FATIA_DE_ESPERA,
    MAX_VISITAS_POR_QUESTAO,
    PAUSA_ANTES_DE_COMECAR_CURSO,
    PAUSA_ANTES_DE_VOLTAR,
    PAUSA_APOS_ABRIR_CURSO,
    PAUSA_APOS_ABRIR_QUESTAO,
    PAUSA_APOS_CLICAR,
    PAUSA_ENTRE_TENTATIVAS,
    TEMPO_DA_NAVEGACAO_NOSSA,
    TEMPO_FORA_DO_CURSO,
    TEMPO_PARA_LER_ESCOLHA,
)
from quizbot.curso import AbrirSecao, AbrirUnidade, Concluido, Parar, RoteiroDoCurso
from quizbot.memoria import Memoria, RevisoesLidas
from quizbot.models import PainelQuiz, Question, Situacao, Suggestion, Unidade
from quizbot.page_reader import LeituraIncompleta, PageReader
from quizbot.presenter import Presenter
from quizbot.responder import Responder
from quizbot.solvers import Solver, SolverError


def _tem_alem_do_id(endereco: str) -> bool:
    """O endereco do curso tem mais que o "id" (ex.: ...&topic=84886): e uma unidade/secao, nao a pagina inicial."""
    return bool(set(parse_qs(urlparse(endereco).query)) - {"id"})


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
        curso: bool = False,
        pausa_curso: float = PAUSA_ANTES_DE_COMECAR_CURSO,
        revisoes_lidas: RevisoesLidas | None = None,
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
        self._origens: dict[tuple, str] = {}  # (enunciado, alternativas) -> quem respondeu, p/ o placar
        self._enviada_em: float | None = None  # quando enviou a tentativa, ate a revisao ser lida
        self._avisou_revisao = False
        self._revisao_fechada = False
        self._avisou_pendente = False
        self._tentativas = tentativas
        self._pausa_voltar = pausa_voltar
        self._painel_agido = False
        self._aviso_painel: str | None = None
        self._ultimo_painel: PainelQuiz | None = None
        self._visitas: dict[int, int] = {}  # questao -> quantas vezes abriu do resumo por ela
        self._espera_ate = 0.0  # ate quando espera a pagina trocar depois de abrir uma questao
        # "Tentar de novo": a acao que falhou (e a questao dela) e o sinal do botao da janela.
        self._repeticao: tuple[Callable[[], None], Question] | None = None
        self._repetir = threading.Event()
        self._curso = curso
        self._pausa_curso = pausa_curso
        self._roteiro = RoteiroDoCurso()
        self._curso_iniciado = False  # ja passou pela contagem de antes de comecar?
        self._curso_parado = False  # concluiu ou parou por erro: nao mexe mais no curso
        self._aguardando_outra_materia = False  # concluiu e o usuario quer outra materia
        self._curso_concluido_id: str | None = None  # id do curso que acabou de concluir
        self._saiu_do_curso = False  # depois de concluir, o usuario saiu das paginas do curso?
        self._curso_espera_ate = 0.0  # ate quando espera a pagina trocar depois de clicar no curso
        # Para notar que o USUARIO abriu uma unidade/secao: o endereco da pagina do curso mudou e
        # nao foi o programa que causou (ele avisa em _nossa_navegacao_ate que vai navegar).
        self._url_curso: str | None = None
        self._nossa_navegacao_ate = 0.0
        self._mudanca_vista_em: float | None = None
        self._fora_desde: float | None = None  # desde quando nao esta numa pagina do curso
        # Revisoes de tentativas antigas (as que o programa nao fez ou nao guardou): so abre a
        # revisao de uma tentativa que ainda nao leu, e essa lista fica salva entre uma execucao e outra
        # (RevisoesLidas). As chaves sao o attempt= do Moodle (ou "id do quiz#numero" sem ele).
        self._revisoes_lidas = revisoes_lidas if revisoes_lidas is not None else RevisoesLidas()
        # Nao deu para abrir/ler: nao insiste ate fechar o programa; na proxima vez tenta de novo
        # (nao entra na lista das lidas, porque nada foi guardado).
        self._revisoes_puladas: set[str] = set()
        self._abrimos_revisao: str | None = None  # a chave da revisao que NOS abrimos e ainda nao foi lida
        self._abrimos_em = 0.0
        self._lendo_revisao = False  # a pagina atual e uma revisao ja lida (para decidir uma vez so)
        self._fechar_revisao = False  # quem abriu a revisao foi o programa? Entao ele a fecha
        # Durante a conferencia das revisoes antigas a janela mostra UMA mensagem fixa. Cada aviso fica
        # pelo menos SEGUNDOS_ALERTA na tela e os seguintes esperam na fila: um aviso por tentativa
        # (e por etapa) faria a janela ficar muito atras do que o programa ja fez. O detalhe vai so
        # para o registro.
        self._conferindo = False

    def _esperar(self, segundos: float) -> bool:
        # Espera ate `segundos` ou ate pedirem para parar (True = pediram). Em fatias curtas, em que
        # o Playwright atende o navegador: dormir "parado" deixa a pagina sem resposta do programa.
        fim = time.monotonic() + segundos
        while not self._parar.is_set():
            resta = fim - time.monotonic()
            if resta <= 0:
                return False
            fatia = min(resta, FATIA_DE_ESPERA)
            atender = getattr(self._reader, "atender_navegador", None)
            if atender is None or not atender(fatia):
                self._parar.wait(fatia)
        return True

    def _agir(self, sugestao: Suggestion, questao: Question) -> None:
        # Marca a alternativa sugerida e avanca. Cada passo tem 1 nova tentativa automatica; se
        # ainda assim falhar, a SUGESTAO continua na tela e aparece o botao "Tentar de novo"
        # (o usuario nunca fica sem a resposta nem sem o que fazer).
        if self._responder is None:
            return
        if not self._na_mesma_questao(questao):  # o usuario ja foi para outra: a vontade dele vale
            print("[usuario] a pagina mudou; nao marquei a resposta da questao anterior.")
            return
        letra = ascii_uppercase[sugestao.indice]
        repetir = lambda: self._agir(sugestao, questao)  # noqa: E731
        if not self._marcar_com_calma(sugestao.indice):
            self._oferecer_repeticao(
                f"Não consegui marcar a alternativa {letra}. Marque você mesmo ou tente de novo.",
                repetir,
                questao,
            )
            return
        self._esperar(PAUSA_APOS_CLICAR)
        if not self._na_mesma_questao(questao):  # mudou de questao no meio: nao empurra o usuario adiante
            print("[usuario] a pagina mudou depois de marcar; nao avancei.")
            return
        if not self._avancar_com_calma(questao):
            self._oferecer_repeticao(
                f"Marquei a alternativa {letra}, mas não consegui avançar. Avance você mesmo ou tente de novo.",
                repetir,
                questao,
            )

    def _na_mesma_questao(self, questao: Question) -> bool:
        # A IA demora (ate dezenas de segundos) e o usuario pode clicar em outra questao nesse tempo.
        # Antes de marcar ou avancar, confere se a pagina ainda mostra a questao da sugestao: marcar a
        # resposta velha na questao nova (e avancar) desfaria o clique dele.
        try:
            return self._reader.ler_questao() == questao
        except LeituraIncompleta:
            return True  # nao deu para ler agora: segue como antes

    def _marcar_com_calma(self, indice: int) -> bool:
        # Marcar e seguro de repetir: so clica se a alternativa ainda nao estiver marcada.
        if self._responder.clicar(indice):
            return True
        if self._esperar(PAUSA_ENTRE_TENTATIVAS):
            return False
        return self._responder.clicar(indice)

    def _avancar_com_calma(self, questao: Question) -> bool:
        # So repete o "avancar" se a pagina ainda mostra a mesma questao: se ja mudou, avancou.
        if self._responder.avancar():
            return True
        if self._esperar(PAUSA_ENTRE_TENTATIVAS):
            return False
        try:
            atual = self._reader.ler_questao()
        except LeituraIncompleta:
            atual = None
        if atual != questao:
            return True
        return self._responder.avancar()

    def _oferecer_repeticao(
        self, mensagem: str, acao: Callable[[], None], questao: Question | None
    ) -> None:
        # A janela mostra a mensagem SEM apagar a sugestao, mais o botao "Tentar de novo". O botao
        # roda na thread da janela, entao so avisa (_pedir_repeticao); quem repete e o proprio laco.
        print(f"[aviso] {mensagem}")
        self._repeticao = (acao, questao)
        self._presenter.oferecer_tentar_de_novo(mensagem, self._pedir_repeticao)

    def _pedir_repeticao(self) -> None:
        self._repetir.set()

    def _refazer(self) -> None:
        # O usuario tocou em "Tentar de novo". So repete se a pagina ainda mostra a mesma
        # questao (se ele seguiu sozinho, nao faz nada).
        pendente, self._repeticao = self._repeticao, None
        if pendente is None:
            return
        acao, questao = pendente
        if questao is not None:  # acao de uma questao: so vale se ela ainda esta na tela
            try:
                atual = self._reader.ler_questao()
            except LeituraIncompleta:
                atual = None
            if atual != questao:
                print("[aviso] a questao mudou; nao repeti a acao.")
                return
        print("[aviso] repetindo a acao a pedido do usuario.")
        acao()

    def _consultar_e_agir(self, questao: Question, ja_esperou: bool = False) -> None:
        # Consulta a IA e age. Se nenhuma IA conseguir, tambem oferece "Tentar de novo" (antes a
        # questao ficava parada, sem ninguem tentar de novo). Se a que volta primeiro pediu so
        # alguns segundos (limite por minuto), espera esse tempo e tenta de novo UMA vez sozinho.
        try:
            sugestao = self._solver.solve(questao)
        except SolverError as erro:
            espera = erro.espera_sugerida
            if not ja_esperou and espera is not None and espera <= ESPERA_CURTA_DA_IA:
                print(f"[ia] todas as IAs pediram para esperar; tento de novo em {espera:.0f} s")
                if not self._esperar(espera + 0.5):
                    self._consultar_e_agir(questao, ja_esperou=True)
                return
            self._oferecer_repeticao(
                f"Não consegui uma sugestão: {erro}",
                lambda: self._consultar_e_agir(questao),
                questao,
            )
            return
        if not self._na_mesma_questao(questao):  # o usuario foi para outra questao enquanto a IA pensava
            print("[usuario] voce mudou de questao enquanto a IA respondia; descartei a sugestao antiga.")
            return
        numero = self._reader.numero_da_questao()
        print(  # uma linha por questao: quem respondeu e o que escolheu (para conferir depois)
            f"[resposta] {f'questao {numero}: ' if numero is not None else ''}"
            f"alternativa {ascii_uppercase[sugestao.indice]} | {sugestao.origem}"
            f"{' | com imagem' if questao.imagens else ''}"
            f"{' | memoria: ' + nota if (nota := getattr(self._solver, 'nota', '')) else ''}"
        )
        self._origens[(questao.enunciado, questao.identidades)] = sugestao.origem  # para o placar da revisao
        self._presenter.mostrar(questao, sugestao)
        self._agir(sugestao, questao)

    def _tentar_finalizar(self) -> None:
        # "_enviada" evita enviar duas vezes se a pagina ainda nao trocou no tick seguinte.
        if self._responder is None or not self._finalizar or self._enviada:
            return
        if not self._resumo_completo():
            return
        if self._responder.terminar():
            self._enviada = True
            self._enviada_em = time.monotonic()  # daqui a pouco a revisao tem que aparecer
            self._avisou_revisao = False
            self._visitas.clear()
            self._presenter.avisar("Tentativa enviada.")

    def _vigiar_revisao(self) -> None:
        # Depois de enviar, a pagina de revisao deveria ser lida em segundos. Se passar do tempo,
        # nao deixa o usuario no escuro: registra o que a pagina mostra e avisa.
        self._vigiar_revisao_aberta()
        if self._enviada_em is None or self._avisou_revisao or self._memoria is None:
            return
        passou = time.monotonic() - self._enviada_em
        if passou < ESPERA_PELA_REVISAO:
            return
        self._avisou_revisao = True
        diagnostico = getattr(self._reader, "diagnosticar_pagina", lambda: "?")()
        print(f"[revisao] {int(passou)} s depois de enviar, a revisao nao foi lida. Pagina: {diagnostico}")
        estrutura = getattr(self._reader, "estrutura_da_revisao", lambda: "")()
        if estrutura:
            print(f"[revisao] estrutura da pagina (para o desenvolvedor):\n{estrutura}")
        self._presenter.avisar(
            "Enviei a tentativa, mas ainda não consegui ler a revisão para guardar as respostas. "
            'Se ela está na tela, aguarde um pouco ou clique em "Terminar revisão" você mesmo.'
        )
        chamar = getattr(self._presenter, "chamar_atencao", None)
        if chamar is not None:
            chamar()

    def _vigiar_revisao_aberta(self) -> None:
        # Clicamos em "Revisao" na tabela e, passado o tempo, a revisao nao foi lida (o clique nao abriu a
        # pagina ou o programa nao reconhece a estrutura). Em vez de ficar parado: registra o que a
        # pagina mostra, avisa, fecha a revisao (nada se perde: ela NAO conta como lida, entao e tentada
        # de novo quando o programa abrir outra vez) e deixa o processo seguir. Isso so vale para
        # revisoes de tentativas antigas; a revisao logo depois de ENVIAR continua nunca sendo fechada
        # sem ser lida (veja _vigiar_revisao).
        if self._abrimos_revisao is None or self._lendo_revisao:
            return
        passou = time.monotonic() - self._abrimos_em
        if passou < ESPERA_PELA_REVISAO_ANTIGA:
            return
        chave = self._abrimos_revisao
        self._revisoes_puladas.add(chave)
        self._abrimos_revisao = None
        diagnostico = getattr(self._reader, "diagnosticar_pagina", lambda: "?")()
        print(f"[revisao] abri a revisao da tentativa {chave}, mas {int(passou)} s depois nao foi lida. Pagina: {diagnostico}")
        estrutura = getattr(self._reader, "estrutura_da_revisao", lambda: "")()
        if estrutura:
            print(f"[revisao] estrutura da pagina (para o desenvolvedor):\n{estrutura}")
        if self._responder is not None and self._responder.terminar_revisao():
            self._presenter.avisar(
                "Não consegui ler a revisão de uma tentativa antiga. Fechei a revisão e sigo; "
                "tento ler de novo na próxima vez que o programa abrir."
            )
        else:
            self._presenter.avisar(
                "Não consegui ler a revisão de uma tentativa antiga e sigo sem ela. "
                'Se a revisão está na tela, clique em "Terminar revisão" você mesmo.'
            )

    def _chave_da_tentativa(self, painel: PainelQuiz, tentativa) -> str:
        # O numero que o Moodle da a tentativa (attempt=); sem ele, o id do quiz e o numero da linha.
        return tentativa.id_revisao or f"{painel.quiz_id}#{tentativa.numero}"

    def _ler_revisoes_pendentes(self, painel: PainelQuiz) -> bool:
        # Antes de comecar outra tentativa (ou de deixar o quiz), le a revisao das tentativas ja
        # finalizadas que este programa ainda nao leu: assim as certas e erradas ficam na memoria e a
        # proxima tentativa ja descarta as erradas. A leitura e a de sempre (_registrar_revisao); aqui
        # so se clica no link "Revisao" da tabela, uma tentativa por vez. True = esta agindo/esperando.
        if self._responder is None or self._memoria is None:
            return False
        if painel.situacao not in (Situacao.PODE_REFAZER, Situacao.ESGOTADO):
            self._conferindo = False
            return False  # sem tentativa feita, ou o usuario esta no meio de uma: nao mexe
        if self._abrimos_revisao is not None:
            return True  # ja clicamos; espera a revisao abrir e ser lida (ou o tempo esgotar)
        for tentativa in painel.tentativas:
            if not tentativa.tem_revisao or tentativa.numero is None:
                continue
            chave = self._chave_da_tentativa(painel, tentativa)
            if chave in self._revisoes_lidas or chave in self._revisoes_puladas:
                continue
            print(f"[revisao] tentativa {tentativa.numero} ainda nao lida por este programa: abrindo a revisao")
            if not self._conferindo:  # UMA mensagem para todo o processo, nao uma por tentativa
                self._conferindo = True
                self._presenter.avisar("Conferindo as revisões das tentativas anteriores…")
            if self._responder.abrir_revisao(tentativa.numero):
                self._abrimos_revisao = chave
                self._abrimos_em = time.monotonic()
            else:
                self._revisoes_puladas.add(chave)
                print(f"[revisao] nao achei o link Revisao da tentativa {tentativa.numero}; sigo sem ela.")
                self._avisar_uma_vez(
                    f"Não achei o link «Revisão» da tentativa {tentativa.numero}; sigo sem ler essa revisão."
                )
                continue
            return True
        self._conferindo = False  # nao sobrou nenhuma: a conferencia acabou
        return False

    def _resumo_completo(self) -> bool:
        # Antes de enviar (e o envio nao tem volta) confere a tabela do resumo: se alguma
        # questao ficou sem resposta, abre a primeira que falta (o loop responde, avanca e
        # volta ao resumo). So devolve True com TODAS respondidas. Se nao achar a tabela, nao
        # envia: melhor nao enviar do que enviar com questao em branco.
        resumo = self._reader.ler_resumo()
        if resumo is None:
            return False
        faltam = resumo.faltam
        if not faltam:
            return True
        if time.monotonic() < self._espera_ate:  # acabou de clicar; espera a pagina trocar
            return False
        numero = faltam[0]
        visitas = self._visitas[numero] = self._visitas.get(numero, 0) + 1
        if visitas > MAX_VISITAS_POR_QUESTAO:
            self._avisar_uma_vez(
                f"Não consegui responder a questão {numero}. Não vou enviar a tentativa: "
                "responda e envie você mesmo."
            )
            return False
        lista = ", ".join(str(n) for n in faltam)
        print(f"[resumo] sem resposta: {lista} | abrindo a questao {numero}")
        self._avisar_uma_vez(
            f"Faltam {len(faltam)} questão(ões) sem resposta ({lista}). "
            "Vou responder só as que faltam antes de enviar."
        )
        if self._responder.abrir_questao(numero):
            self._espera_ate = time.monotonic() + PAUSA_APOS_ABRIR_QUESTAO
        else:
            self._avisar_uma_vez(f"Não achei o link da questão {numero} no resumo. Responda você mesmo.")
        return False

    def _pular_respondida(self, questao: Question) -> None:
        # Questao que ja tem alternativa marcada: mantem a resposta e so avanca (nao gasta IA).
        numero = self._reader.numero_da_questao()
        nome = f"questao {numero}" if numero is not None else "questao"
        print(f"[pulo] {nome} ja estava respondida; mantive a resposta e avancei.")
        if not self._avancar_com_calma(questao):
            self._oferecer_repeticao(
                "Esta questão já estava respondida, mas não consegui avançar. "
                "Avance você mesmo ou tente de novo.",
                lambda: self._pular_respondida(questao),
                questao,
            )

    def _registrar_revisao(self) -> bool:
        if self._memoria is None:
            return False
        resultados = self._reader.ler_revisao()
        if not resultados:
            return False
        primeira = not self._lendo_revisao
        if primeira:
            # Primeira leitura desta revisao: decide UMA vez quem a abriu. Foi o programa (acabou de enviar
            # a tentativa ou clicou em "Revisao" na tabela)? Entao ele a fecha depois de guardar. Foi o
            # usuario? Entao so guarda e deixa a revisao aberta: ele pode estar lendo.
            self._lendo_revisao = True
            self._fechar_revisao = self._enviada_em is not None or self._abrimos_revisao is not None
            if not self._fechar_revisao:
                print("[revisao] revisao aberta pelo usuario: vou guardar e deixar aberta.")
        self._enviada_em = None  # a revisao foi lida: nada a vigiar
        self._registrar_placar(resultados)
        inicio = time.monotonic()
        erradas, certas = self._memoria.registrar_revisao(resultados)
        demorou = time.monotonic() - inicio
        if self._memoria.garantir_guardado():
            # So conta como LIDA depois de guardada em algum lugar (se nao gravou, e tentada de novo).
            numero_no_moodle = getattr(self._reader, "tentativa_em_revisao", lambda: None)()
            for chave in (self._abrimos_revisao, numero_no_moodle):
                if chave:
                    self._revisoes_lidas.add(chave)
        if demorou > 3:  # a nuvem pode demorar; o registro mostra quanto, para achar o gargalo
            print(f"[memoria] gravar a revisao levou {demorou:.1f} s")
        if erradas or certas:
            total_erradas = sum(1 for r in resultados if not r.acertou)
            print(
                f"[revisao] {len(resultados)} questoes, {total_erradas} errada(s) | "
                f"guardado agora: {certas} certa(s), {erradas} errada(s)"
            )
            if not self._conferindo:  # na conferencia, so a mensagem fixa (o resultado fica no registro)
                self._presenter.avisar(
                    f"Revisão lida: guardei {certas} certa(s) e {erradas} errada(s) na memória."
                )
        elif primeira:  # nada novo: a memoria ja sabia tudo (e nunca repete uma pergunta)
            print(f"[revisao] {len(resultados)} questoes, tudo isso ja estava salvo na memoria.")
            if not self._conferindo:
                self._presenter.avisar("Revisão conferida: tudo isso já estava salvo na memória.")
        return True

    def _registrar_placar(self, resultados: list) -> None:
        # Quantas cada origem (cada IA ou a memoria) acertou nesta tentativa: uma linha no registro,
        # so uma vez por revisao. Com o tempo mostra qual provedor erra mais, em dados reais.
        placar: dict[str, list[int]] = {}
        for resultado in resultados:
            origem = self._origens.get((resultado.questao.enunciado, resultado.questao.identidades))
            if origem is None:
                continue
            certas_e_total = placar.setdefault(origem, [0, 0])
            certas_e_total[0] += int(resultado.acertou)
            certas_e_total[1] += 1
        self._origens.clear()
        if placar:
            print("[acerto] " + " | ".join(f"{origem}: {a} de {t}" for origem, (a, t) in placar.items()))

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
            if not self._conferindo:
                self._presenter.avisar("Revisão terminada.")
        else:
            self._avisar_uma_vez('Não achei o botão "Terminar revisão". Clique você mesmo.')

    def _avisar_uma_vez(self, mensagem: str) -> None:
        if mensagem != self._aviso_painel:
            self._aviso_painel = mensagem
            self._presenter.avisar(mensagem)

    def _quiz_concluido(self, painel: PainelQuiz) -> None:
        # Tirou a nota maxima (ainda com tentativas sobrando): nao ha por que refazer.
        # Mostra a nota e volta ao curso, como quando as tentativas acabam. Na pagina do curso,
        # o _cuidar_do_curso escolhe o proximo quiz.
        self._voltar_ao_curso(painel, "Acertou tudo.")

    # --- o curso: unidades e os 2 quizzes de cada uma ---

    def _cuidar_do_curso(self) -> None:
        # Pagina do curso (tem o menu das unidades): o RoteiroDoCurso diz o que fazer agora.
        # So no Automatico. Nada fica sem fazer sem o usuario saber: se algo nao sair como o
        # esperado, o roteiro manda Parar e o usuario e avisado (aviso + bloco no registro).
        if self._responder is None or not self._curso:
            return
        if self._aguardando_outra_materia:
            if not self._chegou_outra_materia():
                return
        elif self._curso_parado:
            return
        menu = self._reader.ler_menu()
        if menu is None:
            # Fora das paginas do curso (numa prova, por exemplo). Depois de uns segundos, o proximo
            # endereco do curso e so "onde esta agora", nao uma escolha do usuario (ex.: ele voltou
            # do quiz sozinho).
            if self._fora_desde is None:
                self._fora_desde = time.monotonic()
            elif time.monotonic() - self._fora_desde >= TEMPO_FORA_DO_CURSO:
                # Esquece onde estava e qualquer "fui eu que cliquei" que sobrou: a chegada que
                # aconteceu enquanto estava na prova ja terminou, o proximo clique e do usuario.
                self._url_curso = None
                self._nossa_navegacao_ate = 0.0
            return
        self._fora_desde = None
        if self._o_usuario_escolheu(menu):  # abriu uma unidade/secao: ja recomecou de la
            self._curso_iniciado = True
            self._curso_espera_ate = 0.0
        if time.monotonic() < self._curso_espera_ate:  # acabou de clicar; espera a pagina trocar
            return
        if self._reader.ler_painel() is not None:  # e a pagina inicial de um quiz, nao a do curso
            return
        if not self._curso_iniciado and not self._contagem_do_curso():
            return
        acao = self._roteiro.proximo(menu, self._reader.ler_unidade())
        if isinstance(acao, Concluido):
            self._curso_parado = True
            print(f"[curso] {acao.resumo}")
            self._presenter.avisar(acao.resumo)
            self._perguntar_outra_materia()
        elif isinstance(acao, Parar):
            self._parar_o_curso(acao)
        elif isinstance(acao, AbrirUnidade):
            print(f"[curso] abrindo {acao.nome}")
            self._apos_clicar_no_curso(
                self._responder.abrir_unidade(acao.nome),
                f"Não achei a {acao.nome} no menu. Clique você mesmo.",
            )
        elif isinstance(acao, AbrirSecao):
            print(f"[curso] abrindo {acao.nome} ({acao.unidade})")
            self._apos_clicar_no_curso(
                self._responder.abrir_secao(acao.nome, acao.unidade),
                f"Não achei a {acao.nome} no menu. Clique você mesmo.",
            )
        else:
            print(f"[curso] abrindo '{acao.nome}' ({acao.unidade})")
            self._apos_clicar_no_curso(
                self._responder.abrir_atividade(acao.nome),
                f"Não achei '{acao.nome}' na {acao.unidade}. Clique você mesmo.",
                outra_pagina_do_curso=False,  # abre um quiz: sai do curso
            )

    def _perguntar_outra_materia(self) -> None:
        # Curso concluido: quem esta usando decide. "Encerrar" para o programa. "Outra materia"
        # zera o roteiro e espera a outra materia ser aberta (_chegou_outra_materia).
        if not self._presenter.perguntar_outra_materia(self._esperar):
            print("[curso] o usuario escolheu encerrar.")
            self._parar.set()
            return
        print("[curso] o usuario quer conferir outra materia: esperando abrir o outro curso.")
        self._aguardando_outra_materia = True
        self._curso_concluido_id = self._reader.id_do_curso()
        self._saiu_do_curso = False

    def _chegou_outra_materia(self) -> bool:
        # Depois de "Outra materia": so recomeca quando o usuario abrir um curso DIFERENTE do que
        # acabou (pelo id do endereco). Sem como saber o id, vale sair das paginas do curso e
        # voltar a uma. Enquanto isso (mesmo curso na tela) nao faz nada, para nao refazer em laco.
        menu = self._reader.ler_menu()
        if menu is None:
            self._saiu_do_curso = True
            return False
        atual = self._reader.id_do_curso()
        if atual is not None and self._curso_concluido_id is not None:
            nova = atual != self._curso_concluido_id
        else:
            nova = self._saiu_do_curso
        if not nova:
            return False
        print(f"[curso] outra materia aberta (id {atual}): recomecando.")
        self._aguardando_outra_materia = False
        self._curso_parado = False
        self._curso_iniciado = False  # volta a avisar "Estou conferindo..." e a esperar antes de comecar
        self._roteiro = RoteiroDoCurso()
        self._url_curso = None  # o endereco do outro curso e o novo ponto de comparacao
        return True

    def _o_usuario_escolheu(self, menu: tuple[Unidade, ...]) -> bool:
        # O usuario abriu uma unidade/secao por conta propria (o endereco da pagina do curso mudou
        # e nao foi o programa): a analise recomeca DALI. O que vem antes e pulado.
        # A mudanca causada pelo proprio programa (um clique dele, ou a volta de um quiz) e
        # avisada em _nossa_navegacao_ate e conta uma vez so.
        agora = self._reader.endereco_do_curso()
        if agora is None:
            return False
        if self._url_curso is None:
            # Primeira vez na pagina do curso (no comeco, ou depois de ficar numa prova): so guarda
            # onde esta. Excecao: o programa JA vinha trabalhando neste curso, nao clicou em nada
            # e chegou numa unidade/secao especifica (o endereco tem mais que o "id"): foi o usuario.
            especifica = _tem_alem_do_id(agora)
            if not (self._curso_iniciado and especifica and time.monotonic() >= self._nossa_navegacao_ate):
                self._url_curso = agora
                self._nossa_navegacao_ate = 0.0  # a chegada que o programa esperava aconteceu
                return False
        elif agora == self._url_curso:
            return False
        if time.monotonic() < self._nossa_navegacao_ate:  # fomos nos
            self._nossa_navegacao_ate = 0.0
            self._url_curso = agora
            self._mudanca_vista_em = None
            return False
        ponto = self._roteiro.ponto_de_partida(menu, self._reader.ler_unidade())
        if ponto is None:  # a pagina ainda carrega: tenta de novo por uns segundos
            if self._mudanca_vista_em is None:
                self._mudanca_vista_em = time.monotonic()
            elif time.monotonic() - self._mudanca_vista_em > TEMPO_PARA_LER_ESCOLHA:
                self._url_curso, self._mudanca_vista_em = agora, None
            return False
        self._url_curso, self._mudanca_vista_em = agora, None
        unidade, secao = ponto
        if not self._roteiro.comecar_de(menu, unidade, secao):
            return False
        onde = secao or unidade
        print(f"[curso] o usuario abriu {onde}: comecando dali (o que vem antes foi pulado).")
        self._presenter.avisar(f"Começando de onde você abriu: {onde}.")
        return True

    def _apos_clicar_no_curso(self, deu_certo: bool, aviso: str, outra_pagina_do_curso: bool = True) -> None:
        # Espera a pagina trocar antes de decidir de novo (evita clicar duas vezes). Se o clique
        # nao achou o link, avisa; o roteiro conta as tentativas e, passando do limite, para.
        # So marca "fui eu" quando o clique leva a OUTRA pagina do curso (unidade/secao): e la que o
        # _o_usuario_escolheu compara enderecos. Clique que abre um QUIZ sai do curso e nunca seria
        # "consumido": a marca ficava ativa e engolia o proximo clique do USUARIO (o bug do log).
        self._curso_espera_ate = time.monotonic() + PAUSA_APOS_ABRIR_CURSO
        if deu_certo and outra_pagina_do_curso:
            self._nossa_navegacao_ate = time.monotonic() + TEMPO_DA_NAVEGACAO_NOSSA
        if not deu_certo:
            self._avisar_uma_vez(aviso)

    def _contagem_do_curso(self) -> bool:
        # Ao chegar na pagina do curso pela primeira vez, avisa e espera antes de comecar:
        # mudar de pagina (ou fechar a janela) cancela. Guarda o menu (com as barras) no registro.
        segundos = int(self._pausa_curso)
        self._presenter.avisar("Estou conferindo as atividades…")
        for _ in range(segundos):
            if self._esperar(1):
                return False
            menu = self._reader.ler_menu()
            if menu is None:
                return False
            if self._o_usuario_escolheu(menu):  # o usuario ja escolheu por onde comecar: nao espera mais
                break
        menu = self._reader.ler_menu()
        if menu is None:
            return False
        barras = " | ".join(
            f"{u.nome} {f'{u.percentual:.0f}%' if u.percentual is not None else '?'}" for u in menu
        )
        print(f"[curso] menu: {barras}")
        self._curso_iniciado = True
        return True

    def _parar_o_curso(self, acao: Parar) -> None:
        self._curso_parado = True
        pendentes = ", ".join(acao.pendentes) or "nenhum"
        print("=============== PROBLEMA NO CURSO ===============")
        print(f"O que aconteceu : {acao.motivo}")
        print(f"Pendentes       : {pendentes}")
        print("O programa fez  : parou de navegar pelo curso e avisou o usuario.")
        print("=============== FIM DO PROBLEMA ===============")
        self._presenter.avisar(f"{acao.motivo} Parei de navegar pelo curso. Pendentes: {pendentes}.")
        self._presenter.chamar_atencao()  # com a janela minimizada, traz para a frente

    def _marcar_quiz_conferido(self) -> None:
        # O quiz acabou (nota maxima ou tentativas esgotadas) e o programa vai voltar ao curso:
        # avisa o roteiro (pelo que ele mesmo abriu ou, senao, pelo breadcrumb da pagina).
        caminho = self._reader.ler_caminho()
        marcado = self._roteiro.quiz_terminado(
            caminho.unidade if caminho else None, caminho.quiz if caminho else None
        )
        if marcado:
            print(f"[curso] quiz conferido: {marcado}")
        else:
            print("[curso] quiz terminado, mas nao deu para saber qual era (nao marquei).")

    def _voltar_ao_curso(self, painel: PainelQuiz, motivo: str = "") -> None:
        # Mostra a nota, espera e volta ao curso. Se a pagina mudar durante a espera
        # (o usuario foi para outro lugar ou refez a tentativa), cancela e nao clica.
        segundos = int(self._pausa_voltar)
        resumo = f"{painel.resumo_das_notas()} {motivo}".strip()
        self._presenter.avisar(f"{resumo} Voltando ao curso em {segundos} s.")
        for passou in range(segundos):
            if self._esperar(1):
                return
            atual = self._reader.ler_painel()
            if atual is None or atual.situacao is not painel.situacao:
                return
            if passou + 1 == segundos // 2:
                self._presenter.avisar(f"{resumo} Voltando ao curso em {segundos - passou - 1} s.")
        self._painel_agido = True
        if self._curso:
            self._marcar_quiz_conferido()
        self._voltar_ou_oferecer()

    def _voltar_ou_oferecer(self) -> None:
        self._nossa_navegacao_ate = time.monotonic() + TEMPO_DA_NAVEGACAO_NOSSA
        if not self._responder.voltar_ao_curso():
            self._oferecer_repeticao(
                "Não consegui voltar ao curso. Volte você mesmo ou tente de novo.",
                self._voltar_ou_oferecer,
                None,
            )

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

        if self._ler_revisoes_pendentes(painel):  # antes de outra tentativa ou de voltar ao curso
            return
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
        if self._repetir.is_set():  # o usuario tocou em "Tentar de novo"
            self._repetir.clear()
            self._refazer()
            return
        if self._registrar_revisao():
            self._ultima = None
            self._enviada = False
            self._visitas.clear()
            if self._fechar_revisao:
                self._tentar_terminar_revisao()
            return
        # Saiu da revisao? Confere pelo endereco (uma leitura que falha por um instante nao conta).
        if self._lendo_revisao and getattr(self._reader, "tentativa_em_revisao", lambda: None)() is None:
            self._lendo_revisao = False
            self._abrimos_revisao = None
        self._revisao_fechada = False
        self._avisou_pendente = False
        self._vigiar_revisao()
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
            self._cuidar_do_curso()
            return
        self._conferindo = False  # ha questao na tela: nao esta conferindo revisoes
        if questao == self._ultima:
            return

        self._ultima = questao
        self._enviada = False
        self._enviada_em = None  # voltou a ter questao: nao esta mais esperando a revisao
        self._repeticao = None  # questao nova: o "Tentar de novo" da anterior nao vale mais
        if self._responder is not None and self._reader.questao_ja_respondida():
            self._pular_respondida(questao)
            return
        numero = self._reader.numero_da_questao()
        codigos = ", ".join(f"[img:{imagem.codigo}]" for imagem in questao.imagens)
        print(
            f"[leitura] {f'questao {numero}: ' if numero is not None else ''}"
            f"{len(questao.alternativas)} alternativas, "
            f"{len(questao.imagens)} imagem(ns){' ' + codigos if codigos else ''} "
            f"| {questao.enunciado[:100]!r}"
        )
        self._presenter.consultando()
        self._consultar_e_agir(questao)

    def rodar(self) -> None:
        while not self._parar.is_set():
            self._passo()
            self._esperar(self._intervalo)
