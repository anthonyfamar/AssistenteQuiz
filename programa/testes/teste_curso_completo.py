import sys
import threading
import time
from urllib.parse import parse_qs, urlparse

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

import quizbot.assistente as modulo
from quizbot.assistente import AssistenteQuiz
from quizbot.page_reader import PageReader
from quizbot.presenter import Presenter
from quizbot.responder import Responder
from quizbot.solvers.base import Solver

modulo.PAUSA_APOS_ABRIR_CURSO = 0.3
modulo.PAUSA_APOS_CLICAR = 0.05

PCT = {1: 100, 2: 100, 3: 17, 4: 17}
TABELA = """<table class="generaltable quizattemptsummary"><thead><tr>
<th class="header c0" scope="col">Tentativa</th><th class="header c1" scope="col">Estado</th>
<th class="header c2" scope="col">Nota / 10,00</th></tr></thead>
<tbody><tr class="lastrow"><td class="cell c0">1</td><td class="cell c1">Finalizada</td>
<td class="cell c2">{nota}</td></tr></tbody></table>"""


class Falso(Solver):
    def solve(self, question):
        raise AssertionError("nao devia consultar IA neste teste")


class Tela(Presenter):
    def __init__(self):
        self.avisos = []

    def mostrar(self, question, suggestion):
        pass

    def avisar(self, mensagem):
        self.avisos.append(mensagem)


class Curso:
    def __init__(self, cenarios=None, sem_avaliacao_na=(), quiz_quebrado=None, unidade_quebrada=None):
        # cenario de cada quiz: "esgotado" (tem botao Voltar), "dez" (10 de primeira, sem botao),
        # "refazer" (nota baixa, sobrou tentativa: o programa deve comecar outra tentativa)
        self.cenarios = {(n, t): "esgotado" for n in range(1, 5) for t in ("ap", "av")}
        self.cenarios.update(cenarios or {})
        self.sem_avaliacao_na = set(sem_avaliacao_na)
        self.quiz_quebrado = quiz_quebrado
        self.unidade_quebrada = unidade_quebrada
        self.feito = set()
        self.visitas = []
        self.inicios = []
        self.armadilhas = []
        self.na_prova = []

    def menu(self, aberta=None):
        itens = []
        for n in range(1, 5):
            href = "#" if n == self.unidade_quebrada else f"/course/view.php?id=1&u={n}"
            ativo = " active" if n == aberta else ""
            itens.append(
                f'<li><div class="timeline-status"><i id="80039{n}" class="material-icons" style="background-image: '
                f'linear-gradient(0deg, rgb(67, 74, 79) {PCT[n]}%, transparent {PCT[n]}%);">&nbsp;</i></div>'
                f'<div class="timeline-item{ativo}"><a href="{href}">Unidade de Ensino {n}</a></div></li>'
            )
        itens.append('<li><div class="timeline-status"><i class="material-icons last">&nbsp;</i></div></li>')
        return '<ul class="timeline">' + "".join(itens) + "</ul>"

    @staticmethod
    def ativ(icone, nome, feita, href):
        check = '<i class="icon-check_circle format_list_topics_complete"></i>' if feita else ""
        return (f'<div class="ct-list"><div class="ct-list-title"><h3><i required="2" class="{icone}">'
                f'<i class="icon-new_releases format_list_topics_required"></i>{check}</i>'
                f'<a href="{href}">\n  {nome}  </a></h3></div></div>')

    def pagina_curso(self, n=None):
        corpo = self.menu(n)
        if n is not None:
            lista = self.ativ("icon-book", f"U{n} - Livro Didático", False, "#")
            lista += self.ativ("icon-add_box", f"Pré Aula 4 - U{n} - Atividade de Aprendizagem", False, "/trap")
            lista += self.ativ("icon-add_box", f"Pós Aula 4 - U{n} - Avaliação da Unidade", False, "/trap")
            lista += '<div class="ct-list-label"><div class="ct-list-title"><h3 class="ct-list-title-label">Aula</h3></div></div>'
            lista += self.ativ("icon-library_books", f"U{n} - Atividade de Aprendizagem", (n, "ap") in self.feito,
                               "#" if self.quiz_quebrado == (n, "ap") else f"/mod/quiz/view.php?u={n}&t=ap")
            if n not in self.sem_avaliacao_na:
                lista += self.ativ("icon-library_books", f"U{n} - Avaliação da Unidade", (n, "av") in self.feito,
                                   "#" if self.quiz_quebrado == (n, "av") else f"/mod/quiz/view.php?u={n}&t=av")
            corpo += (f'<div class="ct-resource-list"><div class="ct-section-active-topic"><h1>Unidade de Ensino {n}</h1></div></div>'
                      f'<div class="ct-resource-list">{lista}</div>')
        return f"<html><body>{corpo}</body></html>"

    def pagina_quiz(self, n, t):
        nome = "Atividade de Aprendizagem" if t == "ap" else "Avaliação da Unidade"
        caminho = (
            '<ol class="breadcrumb"><li class="breadcrumb-item"><a href="/">Página inicial</a></li>'
            '<li class="breadcrumb-item">Meus cursos</li>'
            '<li class="breadcrumb-item"><a href="/course/view.php?id=1" title="Curso">Curso</a></li>'
            f'<li class="breadcrumb-item">Unidade de Ensino {n}</li>'
            f'<li class="breadcrumb-item"><a href="/mod/quiz/view.php?id={n}{t}" aria-current="page">U{n} - {nome}</a></li></ol>'
        )
        cenario = self.cenarios[(n, t)]
        if cenario == "esgotado":
            painel = (TABELA.format(nota="10,00") +
                      '<div class="box quizattempt"><p>Não são permitidas outras tentativas</p>'
                      f'<button type="button" onclick="location.href=\'/course/view.php?id=1&u={n}\'">Voltar ao curso</button></div>')
        elif cenario == "dez":
            painel = TABELA.format(nota="10,00") + '<button type="button" onclick="location.href=\'/mod/quiz/startattempt.php?u=%d&t=%s\'">Fazer uma outra tentativa</button>' % (n, t)
        else:  # refazer: nota baixa
            painel = TABELA.format(nota="6,00") + '<button type="button" onclick="location.href=\'/mod/quiz/startattempt.php?u=%d&t=%s\'">Fazer uma outra tentativa</button>' % (n, t)
        return f"<html><body>{caminho}<div class='box quizattempt'>{painel}</div></body></html>".replace(
            "<div class='box quizattempt'><div class=\"box quizattempt\">", "<div class='box quizattempt'>")

    def atender(self, rota):
        url = urlparse(rota.request.url)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/course/view.php":
            corpo = self.pagina_curso(int(q["u"]) if "u" in q else None)
        elif url.path == "/mod/quiz/view.php":
            n, t = int(q["u"]), q["t"]
            self.visitas.append((n, t))
            corpo = self.pagina_quiz(n, t)
            if self.cenarios[(n, t)] in ("esgotado", "dez"):
                self.feito.add((n, t))
        elif url.path == "/mod/quiz/attempt.php":
            self.na_prova.append(rota.request.url)
            corpo = f"<html><body>{self.menu()}<div role='main'>carregando a proxima questao</div></body></html>"
        elif url.path == "/trap":
            self.armadilhas.append(rota.request.url)
            corpo = "<html><body>ARMADILHA</body></html>"
        elif url.path == "/mod/quiz/startattempt.php":
            self.inicios.append((int(q["u"]), q["t"]))
            corpo = "<html><body><p>tentativa iniciada (fim do teste)</p></body></html>"
        else:
            corpo = "<html><body>?</body></html>"
        rota.fulfill(status=200, content_type="text/html; charset=utf-8", body=corpo)


def rodar(p, curso, inicio="http://quiz.test/course/view.php?id=1", segundos=45):
    navegador = None
    for canal in ("chrome", "msedge"):
        try:
            navegador = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception:
            continue
    assert navegador
    ctx = navegador.new_context()
    ctx.route("http://quiz.test/**", curso.atender)
    pag = ctx.new_page()
    pag.goto(inicio)
    tela = Tela()
    ass = AssistenteQuiz(
        PageReader(ctx), Falso(), tela, intervalo=0.05, parar=threading.Event(),
        responder=Responder(ctx), finalizar=True, tentativas=True, curso=True,
        pausa_voltar=0.3, pausa_curso=1,
    )
    fim = time.monotonic() + segundos
    while time.monotonic() < fim and not ass._curso_parado and not curso.inicios:
        ass._passo()
        time.sleep(0.05)
    for _ in range(8):  # uns ticks a mais: nao pode fazer mais nada depois de parar
        ass._passo()
        time.sleep(0.05)
    navegador.close()
    return ass, tela


with sync_playwright() as p:
    # 1) curso inteiro: 4 unidades x 2 quizzes. Alguns saem pelo botao, outros pelo breadcrumb (10 de primeira)
    curso = Curso(cenarios={(2, "ap"): "dez", (3, "av"): "dez", (4, "ap"): "dez", (4, "av"): "dez"})
    ass, tela = rodar(p, curso)
    esperado = [(n, t) for n in range(1, 5) for t in ("ap", "av")]
    assert curso.visitas == esperado, curso.visitas
    assert ass._curso_parado and "Curso concluído: 4 unidade(s) conferida(s)." in tela.avisos, tela.avisos
    assert any("Estou conferindo as atividades…" in a for a in tela.avisos), tela.avisos
    assert not curso.inicios and not curso.armadilhas, curso.armadilhas
    print("curso inteiro: 8 quizzes em ordem (botao e breadcrumb), aviso de concluido ok")

    # 2) a unidade nao tem a Avaliacao: PARA e avisa com pendentes; nao pula
    curso = Curso(sem_avaliacao_na={2})
    ass, tela = rodar(p, curso)
    assert curso.visitas == [(1, "ap"), (1, "av"), (2, "ap")], curso.visitas
    assert ass._curso_parado
    ult = tela.avisos[-1]
    assert "Não achei 'Avaliação da Unidade' na Unidade de Ensino 2" in ult and "Pendentes" in ult, ult
    assert "Unidade de Ensino 2 (Avaliação da Unidade)" in ult and "Unidade de Ensino 4" in ult, ult
    print("faltou a Avaliacao: parou, avisou e listou os pendentes ok")

    # 3) o link do quiz nao abre: tenta 2 vezes e para (nao fica em laco, nao pula)
    curso = Curso(quiz_quebrado=(1, "ap"))
    ass, tela = rodar(p, curso)
    assert curso.visitas == [] and ass._curso_parado
    assert "Não consegui concluir" in tela.avisos[-1] and "Atividade de Aprendizagem" in tela.avisos[-1], tela.avisos
    print("link do quiz que nao abre: tentou, parou e avisou ok")

    # 4) a unidade nao abre pelo menu: para e avisa
    curso = Curso(unidade_quebrada=1)
    ass, tela = rodar(p, curso)
    assert ass._curso_parado and "Não consegui abrir a Unidade de Ensino 1" in tela.avisos[-1], tela.avisos
    print("unidade que nao abre: parou e avisou ok")

    # 5) unidade em 100% mas um quiz com nota baixa e tentativa sobrando: o programa REFAZ (nao dá como conferido)
    curso = Curso(cenarios={(1, "ap"): "refazer"})
    ass, tela = rodar(p, curso)
    assert curso.inicios == [(1, "ap")], curso.inicios  # clicou em "Fazer uma outra tentativa"
    assert curso.visitas == [(1, "ap")], curso.visitas  # e nao passou para o proximo quiz
    print("quiz 6/10 com tentativa sobrando (unidade em 100%): comecou outra tentativa ok")

    # 7) NO MEIO DE UMA PROVA: a pagina da prova tem o menu das unidades e, na troca de questao, fica um
    #    instante sem questao. O programa NAO pode sair da prova clicando numa unidade (bug do log de 16:07).
    curso = Curso()
    ass, tela = rodar(p, curso, inicio="http://quiz.test/mod/quiz/attempt.php?attempt=9&page=6", segundos=6)
    assert curso.visitas == [] and not ass._curso_parado, (curso.visitas, tela.avisos)
    assert not any("Estou conferindo" in a or "Parei" in a for a in tela.avisos), tela.avisos
    print("pagina de prova com o menu: o programa nao sai da prova clicando na unidade ok")

    # 6) terminou: PERGUNTA. "Outra materia": nao refaz em laco o mesmo curso; so recomeca quando abrir OUTRO.
    #    Na segunda vez, "Encerrar" para o programa.
    class TelaPergunta(Tela):
        def __init__(self, respostas):
            super().__init__()
            self.respostas, self.perguntas = list(respostas), 0

        def perguntar_outra_materia(self, esperar=None):
            self.perguntas += 1
            return self.respostas.pop(0)

    curso = Curso()
    navegador = None
    for canal in ("chrome", "msedge"):
        try:
            navegador = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception:
            continue
    ctx = navegador.new_context()
    ctx.route("http://quiz.test/**", curso.atender)
    pag = ctx.new_page()
    pag.goto("http://quiz.test/course/view.php?id=1")
    tela = TelaPergunta([True, False])
    ass = AssistenteQuiz(
        PageReader(ctx), Falso(), tela, intervalo=0.05, parar=threading.Event(),
        responder=Responder(ctx), finalizar=True, tentativas=True, curso=True,
        pausa_voltar=0.3, pausa_curso=1,
    )
    unidades = [(n, t) for n in range(1, 5) for t in ("ap", "av")]

    fim = time.monotonic() + 45
    while time.monotonic() < fim and tela.perguntas == 0:
        ass._passo()
        time.sleep(0.05)
    assert tela.perguntas == 1 and ass._aguardando_outra_materia and not ass._parar.is_set()
    assert curso.visitas == unidades, curso.visitas

    for _ in range(60):  # o mesmo curso continua na tela: nao pode refazer nada
        ass._passo()
        time.sleep(0.05)
    assert curso.visitas == unidades and tela.perguntas == 1, (curso.visitas, tela.perguntas)

    pag.goto("http://quiz.test/course/view.php?id=2")  # o usuario abriu OUTRA materia
    fim = time.monotonic() + 45
    while time.monotonic() < fim and tela.perguntas < 2:
        ass._passo()
        time.sleep(0.05)
    assert curso.visitas == unidades * 2, curso.visitas
    assert tela.perguntas == 2 and ass._parar.is_set()  # na 2a vez disse "Encerrar"
    navegador.close()
    print("fim do curso: 'Outra materia' espera abrir outro curso e recomeca; 'Encerrar' para ok")

print("TUDO OK")



