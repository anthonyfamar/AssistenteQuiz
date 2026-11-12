# TESTE - a memoria entre tentativas com as alternativas EMBARALHADAS (o Moodle muda a ordem).
#
# 1a tentativa: o programa marca uma alternativa que a revisao diz estar errada, outra certa.
# 2a tentativa: as mesmas questoes, alternativas em outra ordem. Confere que:
#   - a que ja era CERTA e devolvida da memoria (sem IA), na posicao nova;
#   - a que ja era ERRADA nunca e escolhida de novo, mesmo a IA querendo (a IA so ve as que sobram) e
#     o indice volta para a posicao certa da tela;
#   - o registro (nota) conta o que a memoria fez.
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from quizbot.armazenamento import ArmazenamentoLocal
from quizbot.memoria import Memoria
from quizbot.models import Question, Resultado, Suggestion
from quizbot.solvers.base import Solver
from quizbot.solvers.memoria import SolverComMemoria

ALTS = ("Só a afirmação I é correta.", "Só a afirmação II é correta.", "Só a afirmação III é correta.",
        "I e II são corretas.", "I, II e III são corretas.")


def questao(ordem, enunciado="Enunciado longo da questao de teste"):
    return Question(enunciado, tuple(ALTS[i] for i in ordem))


class IaQueSempreEscolheAPrimeira(Solver):
    """Escolhe sempre o indice 0 do que recebe (o pior caso: insistir na primeira alternativa)."""

    def __init__(self):
        self.recebidas = []

    def solve(self, question):
        self.recebidas.append(question.alternativas)
        return Suggestion(indice=0, explicacao="x", origem="falso")


memoria = Memoria(ArmazenamentoLocal(pathlib.Path(tempfile.mkdtemp()), "teste"), "teste")
ia = IaQueSempreEscolheAPrimeira()
solver = SolverComMemoria(ia, memoria)

# --- 1a tentativa (ordem normal): a revisao diz que a alternativa III estava ERRADA ---
q1 = questao((0, 1, 2, 3, 4))
memoria.registrar_revisao([Resultado(q1, 2, False)])
# e em outra questao, a "I, II e III" estava CERTA
outra = Question("Outra questao de teste", ALTS)
memoria.registrar_revisao([Resultado(outra, 4, True)])

# --- 2a tentativa, embaralhada: a III (errada) vem PRIMEIRA, e a IA insiste na primeira ---
q2 = questao((2, 0, 1, 3, 4))
s = solver.solve(q2)
escolhida = q2.alternativas[s.indice]
assert escolhida != ALTS[2], f"escolheu de novo a alternativa errada: {escolhida}"
assert ALTS[2] not in ia.recebidas[-1], "a IA nao devia ver a alternativa ja errada"
assert escolhida == ALTS[0] and s.indice == 1, (s.indice, escolhida)  # a 1a que sobrou, na posicao da tela
assert solver.nota == "1 errada(s) conhecida(s) tirada(s)", solver.nota
print("alternativa errada nao e escolhida de novo (IA so ve as outras; indice volta a posicao certa) ok")

# --- a certa conhecida volta da memoria, sem IA, na posicao nova ---
antes = len(ia.recebidas)
q3 = Question("Outra questao de teste", tuple(reversed(ALTS)))
s = solver.solve(q3)
assert s.origem == "memória" and q3.alternativas[s.indice] == ALTS[4], (s.origem, q3.alternativas[s.indice])
assert len(ia.recebidas) == antes and solver.nota == "certa conhecida"
print("alternativa certa vem da memoria, sem IA, mesmo embaralhada ok")

# --- 2 erradas conhecidas: a IA nao pode escolher nenhuma das duas ---
memoria.registrar_revisao([Resultado(q2, 1, False)])  # em q2 o indice 1 e "Só a afirmação I": 2a errada
q4 = questao((1, 2, 0, 3, 4))
erradas = memoria.erradas(q4)
assert len(erradas) == 2, erradas
s = solver.solve(q4)
assert q4.alternativas[s.indice] not in erradas, (q4.alternativas[s.indice], erradas)
print(f"com {len(erradas)} erradas conhecidas, nenhuma e escolhida ok")

# --- texto que nao bate: o registro avisa (era assim que um problema de identidade apareceria) ---
mudada = Question("Enunciado longo da questao de teste", tuple(a + " " for a in ALTS))
solver.solve(mudada)
assert "nenhuma bate" in solver.nota or solver.nota == "", solver.nota
print("registro avisa quando a memoria tem erradas mas o texto nao bate:", repr(solver.nota))
print("TUDO OK")
