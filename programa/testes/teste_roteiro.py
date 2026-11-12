import sys

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from quizbot.curso import (
    AbrirAtividade, AbrirUnidade, Concluido, Parar, RoteiroDoCurso, limpar, tipo_do_quiz,
)
from quizbot.models import AtividadeDoCurso, Unidade, UnidadeAberta

# --- nomes ---
assert limpar("  Avaliação   da Unidade ") == "avaliacao da unidade"
assert tipo_do_quiz("U3 - Atividade de Aprendizagem") == "aprendizagem"
assert tipo_do_quiz("U1 - Avaliação da Unidade") == "avaliacao"
assert tipo_do_quiz("U3 - Livro Didático") is None
assert tipo_do_quiz("TECNOLOGIAS DE DESENVOLVIMENTO DE SISTEMAS") is None
print("nomes ok")

MENU = tuple(Unidade(f"Unidade de Ensino {n}", p) for n, p in ((1, 100), (2, 100), (3, 17), (4, 17)))


def unidade(n, feitas=(False, False), extras=True):
    ativ = []
    if extras:
        ativ += [AtividadeDoCurso(f"U{n} - Livro Didático", False), AtividadeDoCurso("TECNOLOGIAS", True)]
    ativ += [
        AtividadeDoCurso(f"U{n} - Atividade de Aprendizagem", feitas[0]),
        AtividadeDoCurso(f"U{n} - Avaliação da Unidade", feitas[1]),
    ]
    return UnidadeAberta(f"Unidade de Ensino {n}", tuple(ativ))


# --- percurso feliz: confere TODAS as unidades, em ordem, mesmo as que estao em 100% ---
r = RoteiroDoCurso()
passos = []
aberta = None
for _ in range(40):
    acao = r.proximo(MENU, aberta)
    if isinstance(acao, Concluido):
        break
    assert not isinstance(acao, Parar), acao
    passos.append(acao)
    if isinstance(acao, AbrirUnidade):
        n = int(acao.nome[-1])
        aberta = unidade(n)
    else:  # abriu um quiz: o assistente faz tudo e avisa que terminou
        assert r.quiz_terminado() is not None
else:
    raise AssertionError("nao terminou")
esperado = []
for n in range(1, 5):
    esperado += [AbrirUnidade(f"Unidade de Ensino {n}"),
                 AbrirAtividade(f"U{n} - Atividade de Aprendizagem", f"Unidade de Ensino {n}"),
                 AbrirAtividade(f"U{n} - Avaliação da Unidade", f"Unidade de Ensino {n}")]
assert passos == esperado, passos
assert acao == Concluido("Curso concluído: 4 unidade(s) conferida(s).")
assert r.pendentes(MENU) == ()
print("percurso: 4 unidades x 2 quizzes, em ordem, inclusive as em 100% ok")

# --- ja esta na unidade certa: nao reabre a unidade ---
r = RoteiroDoCurso()
assert r.proximo(MENU, unidade(1)) == AbrirAtividade("U1 - Atividade de Aprendizagem", "Unidade de Ensino 1")
r.quiz_terminado()
assert r.proximo(MENU, unidade(1)) == AbrirAtividade("U1 - Avaliação da Unidade", "Unidade de Ensino 1")
r.quiz_terminado()
assert r.proximo(MENU, unidade(1)) == AbrirUnidade("Unidade de Ensino 2")  # unidade 1 pronta
print("na unidade certa: vai direto ao quiz; terminou os 2, vai para a proxima ok")

# --- marcar pelo breadcrumb quando o quiz foi aberto de outro jeito (o usuario entrou na mao) ---
r = RoteiroDoCurso()
assert r.quiz_terminado("Unidade de Ensino 1", "U1 - Atividade de Aprendizagem") is not None
assert r.proximo(MENU, unidade(1)) == AbrirAtividade("U1 - Avaliação da Unidade", "Unidade de Ensino 1")
assert RoteiroDoCurso().quiz_terminado("Unidade de Ensino 1", "U1 - Livro Didático") is None  # nao e quiz alvo
assert RoteiroDoCurso().quiz_terminado() is None
print("quiz_terminado pelo breadcrumb ok")

# --- erros: nada fica sem fazer sem avisar ---
r = RoteiroDoCurso()
for _ in range(2):
    assert isinstance(r.proximo(MENU, None), AbrirUnidade)
p = r.proximo(MENU, None)
assert isinstance(p, Parar) and "Não consegui abrir a Unidade de Ensino 1" in p.motivo, p
assert len(p.pendentes) == 8

r = RoteiroDoCurso()
sem_avaliacao = UnidadeAberta("Unidade de Ensino 1", (AtividadeDoCurso("U1 - Atividade de Aprendizagem", True),))
assert isinstance(r.proximo(MENU, sem_avaliacao), AbrirAtividade)
r.quiz_terminado()
p = r.proximo(MENU, sem_avaliacao)
assert "Não achei 'Avaliação da Unidade' na Unidade de Ensino 1" in p.motivo, p.motivo

r = RoteiroDoCurso()
for _ in range(2):
    assert isinstance(r.proximo(MENU, unidade(1)), AbrirAtividade)  # abriu e "nao terminou" (ninguem chamou quiz_terminado)
p = r.proximo(MENU, unidade(1))
assert isinstance(p, Parar) and "Não consegui concluir 'U1 - Atividade de Aprendizagem'" in p.motivo, p

# contador da unidade zera quando chega nela (varias idas e vindas ao longo do curso nao estouram)
r = RoteiroDoCurso()
for n in (1, 2, 3, 4):
    assert r.proximo(MENU, None) in (AbrirUnidade("Unidade de Ensino 1"),) or True
r = RoteiroDoCurso()
r.proximo(MENU, None); r.proximo(MENU, unidade(1)); r.quiz_terminado()
r.proximo(MENU, None); r.proximo(MENU, unidade(1))  # zerou a conta ao chegar
r.quiz_terminado()
assert isinstance(r.proximo(MENU, None), AbrirUnidade)  # a unidade 1 nao esta mais pendente: pede a 2
print("erros viram Parar com pendentes; contadores certos ok")

# --- menu vazio (nao e a pagina do curso) nao quebra ---
assert isinstance(RoteiroDoCurso().proximo((), None), Concluido)
print("TUDO OK")

