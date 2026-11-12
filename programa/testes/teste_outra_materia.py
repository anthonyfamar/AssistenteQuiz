import sys
import threading
import time

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import quizbot.assistente as A
from quizbot.curso import RoteiroDoCurso
from quizbot.models import Unidade

MENU = (Unidade("Unidade de Ensino 1", 100),)


class Leitor:
    def __init__(self):
        self.menu, self.id_ = MENU, "100"

    def ler_menu(self): return self.menu
    def id_do_curso(self): return self.id_
    def endereco_do_curso(self): return f"http://quiz.test/course/view.php?id={self.id_}"
    def ler_questao(self): return None
    def ler_painel(self): return None
    def ler_unidade(self): return None
    def ler_resumo(self): return None
    def questao_ja_respondida(self): return False
    def numero_da_questao(self): return None


class Tela:
    def __init__(self, resposta): self.resposta, self.avisos = resposta, []
    def avisar(self, m): self.avisos.append(m)
    def consultando(self): pass
    def mostrar(self, q, s): pass
    def perguntar_outra_materia(self, esperar=None): return self.resposta


class Resp:
    def abrir_unidade(self, n): return True
    def abrir_atividade(self, n): return True


def assistente(resposta=True):
    leitor, tela = Leitor(), Tela(resposta)
    a = A.AssistenteQuiz(leitor, None, tela, parar=threading.Event(), responder=Resp(), curso=True, pausa_curso=0)
    return a, leitor, tela


# --- "Encerrar": para o programa ---
a, _, _ = assistente(resposta=False)
a._curso_parado = True
a._perguntar_outra_materia()
assert a._parar.is_set() and not a._aguardando_outra_materia
print("encerrar: para o programa ok")

# --- "Outra materia" com id: so recomeca quando o id MUDA ---
a, leitor, _ = assistente()
velho = a._roteiro
a._curso_parado = True
a._perguntar_outra_materia()
assert a._aguardando_outra_materia and a._curso_concluido_id == "100" and not a._parar.is_set()
for _ in range(5):  # o mesmo curso na tela: nada acontece
    a._cuidar_do_curso()
    assert a._aguardando_outra_materia and a._curso_parado and a._roteiro is velho
leitor.id_ = "200"  # abriu outra materia
A.PAUSA_APOS_ABRIR_CURSO = 0
a._cuidar_do_curso()
assert not a._aguardando_outra_materia and a._roteiro is not velho
print("outra materia (id muda): ignora o mesmo curso e recomeca no outro, com roteiro zerado ok")

# --- id desconhecido: vale sair das paginas do curso e voltar a uma ---
a, leitor, _ = assistente()
leitor.id_ = None
a._curso_parado = True
a._perguntar_outra_materia()
assert a._curso_concluido_id is None
assert a._chegou_outra_materia() is False  # ainda na mesma pagina
leitor.menu = None  # saiu do curso
assert a._chegou_outra_materia() is False
leitor.menu = MENU  # abriu uma pagina de curso
assert a._chegou_outra_materia() is True
print("outra materia (sem id): sair do curso e abrir um curso conta como outra materia ok")

# --- mesmo id, mesmo saindo e voltando: e o MESMO curso, nao refaz ---
a, leitor, _ = assistente()
a._curso_parado = True
a._perguntar_outra_materia()
leitor.menu = None
a._chegou_outra_materia()
leitor.menu = MENU  # voltou ao mesmo curso (id 100)
assert a._chegou_outra_materia() is False
print("mesmo curso (mesmo id) nao e refeito ok")
print("TUDO OK")
