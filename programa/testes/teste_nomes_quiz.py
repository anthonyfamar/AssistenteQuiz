import sys

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from quizbot.curso import AbrirAtividade, Parar, RoteiroDoCurso, tipo_do_quiz
from quizbot.models import AtividadeDoCurso, Unidade, UnidadeAberta

# --- nomes da tela do Anthony (a unidade 1): so os 2 ultimos sao quizzes ---
assert tipo_do_quiz("U1 - Atividade de Aprendizagem") == "aprendizagem"
assert tipo_do_quiz("U1 - Avaliação da Unidade") == "avaliacao"
assert tipo_do_quiz("U12 – Avaliação da Unidade") == "avaliacao"  # travessao e unidade com 2 digitos
assert tipo_do_quiz("Pré Aula 4 - U1 - Atividade de Aprendizagem") is None
assert tipo_do_quiz("Pós Aula 4 - U1 - Avaliação da Unidade") is None
assert tipo_do_quiz("U1 - Atividade de Aprendizagem - Revisão") is None  # nada depois
assert tipo_do_quiz("Atividade de Aprendizagem") is None  # sem o "U<n> -"
for nome in ("Pré Aula 3 - Vídeo Resumo da U1S2", "Aula 4 - Revisão sobre Determinantes e Exercícios",
             "Pós Aula 1 - Leitura do Plano de Ensino e Principais Referências"):
    assert tipo_do_quiz(nome) is None, nome
print("nomes: so o nome inteiro conta ok")

MENU = (Unidade("Unidade de Ensino 1", 100),)
ARQ, QUIZ = "icon-add_box format_list_topics_default", "icon-library_books format_list_topics_default"


def unidade(*itens):
    return UnidadeAberta("Unidade de Ensino 1", tuple(AtividadeDoCurso(n, False, i) for n, i in itens))


# a lista da tela, na mesma ordem
TELA = unidade(
    ("Pré Aula 4 - U1 - Atividade de Aprendizagem", ARQ), ("Pré Aula 3 - Vídeo Resumo da U1S2", ARQ),
    ("Pré Aula 2 - Vídeo Resumo da U1S1", ARQ), ("Pré Aula 1 - Cronograma da disciplina", ARQ),
    ("Aula 4 - Revisão sobre Determinantes e Exercícios", ARQ), ("Aula 1 - Apresentação da Disciplina", ARQ),
    ("Pós Aula 4 - U1 - Avaliação da Unidade", ARQ), ("Pós Aula 1 - Leitura do Plano de Ensino", ARQ),
    ("U1 - Atividade de Aprendizagem", QUIZ), ("U1 - Avaliação da Unidade", QUIZ),
)
r = RoteiroDoCurso()
assert r.proximo(MENU, TELA) == AbrirAtividade("U1 - Atividade de Aprendizagem", "Unidade de Ensino 1")
r.quiz_terminado()
assert r.proximo(MENU, TELA) == AbrirAtividade("U1 - Avaliação da Unidade", "Unidade de Ensino 1")
print("tela do Anthony: escolhe os 2 ultimos (os quizzes), nunca os de Pre/Pos Aula ok")

# so armadilhas, sem os quizzes de verdade: PARA e avisa (nao entra em arquivo de apoio)
so_apoio = unidade(("Pré Aula 4 - U1 - Atividade de Aprendizagem", ARQ), ("Pós Aula 4 - U1 - Avaliação da Unidade", ARQ))
p = RoteiroDoCurso().proximo(MENU, so_apoio)
assert isinstance(p, Parar) and "Não achei 'Atividade de Aprendizagem' na Unidade de Ensino 1" in p.motivo, p
print("so arquivos de apoio: para e avisa ok")

# dois com o mesmo nome: o icone de quiz desempata; dois quizzes iguais: nao chuta
dois = unidade(("U1 - Atividade de Aprendizagem", ARQ), ("U1 - Atividade de Aprendizagem", QUIZ))
a = RoteiroDoCurso().proximo(MENU, dois)
assert a == AbrirAtividade("U1 - Atividade de Aprendizagem", "Unidade de Ensino 1")
dois_quizzes = unidade(("U1 - Atividade de Aprendizagem", QUIZ), ("U1 - Atividade de Aprendizagem", QUIZ))
p = RoteiroDoCurso().proximo(MENU, dois_quizzes)
assert isinstance(p, Parar) and "mais de um 'Atividade de Aprendizagem'" in p.motivo, p
nenhum_icone = unidade(("U1 - Atividade de Aprendizagem", ARQ), ("U1 - Atividade de Aprendizagem", ARQ))
assert isinstance(RoteiroDoCurso().proximo(MENU, nenhum_icone), Parar)
print("empate: icone de quiz desempata; ainda ambiguo: para e avisa ok")
print("TUDO OK")
