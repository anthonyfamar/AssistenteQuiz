# MEMORIA - um Solver que "embrulha" outro e usa o que a Memoria ja sabe.
#
# SolverComMemoria -> antes de perguntar a IA:
#                     1. se a Memoria sabe a alternativa CERTA, devolve ela direto (sem IA);
#                     2. senao, tira da questao as alternativas que ja se sabe estarem
#                        ERRADAS e deixa a IA responder so entre as que sobraram. O indice
#                        dela e convertido de volta para a posicao original da tela;
#                        - sobrou 1 alternativa: devolve ela direto, sem consultar a IA;
#                        - nada conhecido (ou tudo descartado, o que indica texto mudado):
#                          pergunta a questao inteira, como sempre.
#                     Tirar as alternativas e mais seguro do que "avisar" a IA que elas
#                     estao erradas: ela nem consegue escolher uma delas.
#                     (Padrao Decorator: tem a mesma interface do Solver que embrulha.)
from quizbot.memoria import Memoria
from quizbot.models import Question, Suggestion
from quizbot.solvers.base import Solver


class SolverComMemoria(Solver):
    def __init__(self, interno: Solver, memoria: Memoria) -> None:
        self._interno = interno
        self._memoria = memoria

    @property
    def nome(self) -> str:
        return self._interno.nome

    @property
    def aceita_imagens(self) -> bool:
        return self._interno.aceita_imagens

    def solve(self, question: Question) -> Suggestion:
        identidades = question.identidades
        certa = self._memoria.certa(question)
        if certa in identidades:
            return Suggestion(
                indice=identidades.index(certa),
                explicacao="Você já acertou esta questão antes.",
                origem="memória",
            )

        erradas = self._memoria.erradas(question)
        restantes = [i for i, ident in enumerate(identidades) if ident not in erradas]
        if not erradas or not restantes:
            return self._interno.solve(question)
        if len(restantes) == 1:
            return Suggestion(
                indice=restantes[0],
                explicacao="Todas as outras alternativas já foram dadas como erradas.",
                origem="memória",
            )

        # As imagens seguem todas junto: os [imagem N] das alternativas que ficam
        # continuam apontando para as imagens certas.
        reduzida = Question(
            enunciado=question.enunciado,
            alternativas=tuple(question.alternativas[i] for i in restantes),
            imagens=question.imagens,
        )
        sugestao = self._interno.solve(reduzida)
        return Suggestion(
            indice=restantes[sugestao.indice],
            explicacao=sugestao.explicacao,
            origem=sugestao.origem,
        )
