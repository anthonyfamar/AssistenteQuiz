import sys
import threading
import time
from urllib.parse import parse_qs, urlparse

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

import quizbot.assistente as modulo
from quizbot.assistente import AssistenteQuiz
from quizbot.curso import AbrirAtividade, AbrirSecao, Concluido, Parar, RoteiroDoCurso, tipo_do_quiz
from quizbot.models import AtividadeDoCurso, Unidade, UnidadeAberta
from quizbot.page_reader import PageReader
from quizbot.presenter import Presenter
from quizbot.responder import Responder
from quizbot.solvers.base import Solver

modulo.PAUSA_APOS_ABRIR_CURSO = 0.3
modulo.PAUSA_APOS_CLICAR = 0.05

# ---------- 1) nomes ----------
assert tipo_do_quiz("U3S2 - Atividade Diagnóstica") == "diagnostica"
assert tipo_do_quiz("U3S2 - Atividade de Aprendizagem") == "aprendizagem"
assert tipo_do_quiz("U3 - Avaliação da Unidade") == "avaliacao"
assert tipo_do_quiz("U3 - Vídeo Aula Resumo") is None
assert tipo_do_quiz("U3S2 - Webaula") is None
assert tipo_do_quiz("Pré Aula 4 - U3S2 - Atividade de Aprendizagem") is None
print("nomes dos 3 quizzes ok")

# ---------- 2) o roteiro, so com dados ----------
SECOES = {n: tuple(f"U{n} - Seção {s}" for s in (1, 2, 3)) for n in (1, 2)}


def menu(ativa=None):
    return tuple(
        Unidade(f"Unidade de Ensino {n}", 50, False, SECOES[n], ativa if ativa in SECOES[n] else None)
        for n in (1, 2)
    )


def ativ(nome, icone="icon-library_books format_list_topics_default"):
    return AtividadeDoCurso(nome, False, icone)


def lista(n, s):
    itens = [ativ(f"U{n}S{s} - Webaula", "icon-book"), ativ(f"U{n}S{s} - Atividade Diagnóstica"),
             ativ(f"Unidade {n} - Aula presencial", "icon-add_box"), ativ(f"U{n}S{s} - Atividade de Aprendizagem")]
    if s == 3:
        itens += [ativ(f"U{n} - Vídeo Aula Resumo", "icon-ondemand_video"), ativ(f"U{n} - Avaliação da Unidade")]
    return UnidadeAberta("", tuple(itens))


r = RoteiroDoCurso()
a = r.proximo(menu(), None)
assert a == AbrirSecao("U1 - Seção 1", "Unidade de Ensino 1"), a
a = r.proximo(menu("U1 - Seção 1"), lista(1, 1))
assert a == AbrirAtividade("U1S1 - Atividade Diagnóstica", "U1 - Seção 1"), a
r.quiz_terminado()
a = r.proximo(menu("U1 - Seção 1"), lista(1, 1))
assert a == AbrirAtividade("U1S1 - Atividade de Aprendizagem", "U1 - Seção 1"), a
r.quiz_terminado()
# secao 1 pronta -> vai para a secao 2 (nao repete a 1)
a = r.proximo(menu("U1 - Seção 1"), lista(1, 1))
assert a == AbrirSecao("U1 - Seção 2", "Unidade de Ensino 1"), a
# a pagina ainda e a da secao 1 mas o menu ja marca a 2: nao confia na lista antiga
a = r.proximo(menu("U1 - Seção 2"), lista(1, 1))
assert isinstance(a, AbrirSecao) and a.nome == "U1 - Seção 2", a
a = r.proximo(menu("U1 - Seção 2"), lista(1, 2))
assert a == AbrirAtividade("U1S2 - Atividade Diagnóstica", "U1 - Seção 2"), a
print("roteiro: ordem das secoes, 2 quizzes por secao, nao confia em lista de outra pagina ok")

# secao 3 tem 3 quizzes, na ordem da pagina; depois vai para a unidade 2
r = RoteiroDoCurso()
for s in (1, 2):
    r._secoes_prontas.add(f"u1 - secao {s}")
abertos = []
while True:
    a = r.proximo(menu("U1 - Seção 3"), lista(1, 3))
    if not isinstance(a, AbrirAtividade):
        break
    abertos.append(a.nome)
    r.quiz_terminado()
assert abertos == ["U1S3 - Atividade Diagnóstica", "U1S3 - Atividade de Aprendizagem", "U1 - Avaliação da Unidade"], abertos
assert a == AbrirSecao("U2 - Seção 1", "Unidade de Ensino 2"), a
print("roteiro: secao 3 com Avaliacao da Unidade (3 quizzes), depois a proxima unidade ok")

# secao sem nenhum quiz: ok, segue (a lista so tem Webaula)
r = RoteiroDoCurso()
sem = UnidadeAberta("", (ativ("U1S1 - Webaula", "icon-book"),))
a = r.proximo(menu("U1 - Seção 1"), sem)
assert a == AbrirSecao("U1 - Seção 2", "Unidade de Ensino 1"), a
# pagina sem atividade nenhuma: nao conclui que a secao esta vazia; tenta abrir e, passando do limite, PARA
r = RoteiroDoCurso()
a1 = r.proximo(menu("U1 - Seção 1"), UnidadeAberta("", ()))
a2 = r.proximo(menu("U1 - Seção 1"), UnidadeAberta("", ()))
a3 = r.proximo(menu("U1 - Seção 1"), UnidadeAberta("", ()))
assert isinstance(a1, AbrirSecao) and isinstance(a2, AbrirSecao) and isinstance(a3, Parar), (a1, a2, a3)
assert "U1 - Seção 1" in a3.pendentes
# dois "Atividade de Aprendizagem" sem icone para desempatar: nao chuta
r = RoteiroDoCurso()
dup = UnidadeAberta("", (ativ("U1S1 - Webaula", "icon-book"), ativ("U1S1 - Atividade de Aprendizagem"),
                         ativ("U1S1 - Atividade de Aprendizagem")))
a = r.proximo(menu("U1 - Seção 1"), dup)
assert isinstance(a, Parar) and "mais de um" in a.motivo, a
print("roteiro: secao sem quiz segue; pagina vazia nao e dada como pronta; duplicado nao e chutado ok")

# ---------- 2b) comecar_de, so com dados (secoes e modo antigo) ----------
r = RoteiroDoCurso()
assert r.ponto_de_partida(menu("U2 - Seção 3"), lista(2, 3)) == ("Unidade de Ensino 2", "U2 - Seção 3")
assert r.ponto_de_partida(menu("U2 - Seção 3"), lista(2, 2)) is None  # lista de outra secao: nao confia
assert r.ponto_de_partida(menu(), None) is None
assert r.comecar_de(menu(), "Unidade de Ensino 2", "U2 - Seção 2") is True
a = r.proximo(menu("U2 - Seção 2"), lista(2, 2))
assert a == AbrirAtividade("U2S2 - Atividade Diagnóstica", "U2 - Seção 2"), a
assert r.comecar_de(menu(), "Unidade de Ensino 2", "U2 - Seção 2") is False  # ja era o proximo
antigo = tuple(Unidade(f"Unidade de Ensino {n}", 50) for n in (1, 2, 3))
ra = RoteiroDoCurso()
unid3 = UnidadeAberta("Unidade de Ensino 3", (ativ("U3 - Atividade de Aprendizagem"), ativ("U3 - Avaliação da Unidade")))
assert ra.ponto_de_partida(antigo, unid3) == ("Unidade de Ensino 3", None)
assert ra.comecar_de(antigo, "Unidade de Ensino 3", None) is True
assert ra.proximo(antigo, unid3) == AbrirAtividade("U3 - Atividade de Aprendizagem", "Unidade de Ensino 3")
# voltar para a unidade 2 refaz dali (2 e 3 voltam a ser pendentes)
ra.quiz_terminado()
assert ra.comecar_de(antigo, "Unidade de Ensino 2", None) is True
assert ra.pendentes(antigo)[0].startswith("Unidade de Ensino 2")
print("roteiro: ponto de partida e comecar_de (secoes e modo antigo) ok")

# ---------- 3) navegador: o HTML real do menu + secoes ----------
TABELA = """<table class="generaltable quizattemptsummary"><thead><tr>
<th scope="col">Tentativa</th><th scope="col">Estado</th><th scope="col">Nota / 10,00</th></tr></thead>
<tbody><tr class="lastrow"><td>1</td><td>Finalizada</td><td>10,00</td></tr></tbody></table>"""


def item_lista(icone, nome, href):
    return ('<div class="ct-list"><div class="ct-list-title"><h3>'
            f'<i required="2" class="{icone} format_list_topics_default"><i class="icon-new_releases format_list_topics_required"></i></i>'
            f'                            <a href="{href}">\n   {nome}   </a></h3></div></div>')


class Curso:
    N = 2

    def __init__(self):
        self.visitas = []

    def menu(self, un=None, sec=None):
        html = ['<ul class="timeline">',
                '<li><div class="timeline-status"><i id="84883" class="material-icons complete">&nbsp;</i></div>'
                '<div class="timeline-item"><a href="/livro">Livro Didático</a></div></li>']
        for n in range(1, self.N + 1):
            abre = " open" if n == un else ""
            secoes = "".join(
                f'<li class="{"active" if (n, s) == (un, sec) else ""}"><a href="/course/view.php?id=1&u={n}&s={s}">U{n} - Seção {s}</a></li>'
                for s in (1, 2, 3))
            html.append(
                f'<li><div class="timeline-status"><i id="8488{n}" class="material-icons" style="background-image: linear-gradient(0deg, rgb(67, 74, 79) 9{n}%, transparent 9{n}%);">&nbsp;</i></div>'
                f'<div class="timeline-item group{abre}" data-ct-groupname="Unidade de Ensino {n}"><a href="#" aria-expanded="false" onclick="var m=this.closest(\'li\').querySelector(\'.timeline-menu\'); m.style.display = m.style.display==\'block\' ? \'none\' : \'block\'; window.cliquesUnidade=(window.cliquesUnidade||0)+1; return false">Unidade de Ensino {n}'
                f'<span class="timeline-arrow-container"><span class="icomoon icon-chevron-down"></span></span></a></div>'
                f'<div class="timeline-menu" style="display: {"block" if n == un else "none"};"><ul>{secoes}</ul></div></li>')
        html.append('<li><div class="timeline-status"><i id="784882" class="material-icons inactive">&nbsp;</i></div>'
                    '<div class="timeline-item group" data-ct-groupname="Avalie sua disciplina"><a href="#">Avalie sua disciplina</a></div>'
                    '<div class="timeline-menu"><ul><li><a href="/avalie">Avalie seu material</a></li></ul></div></li>')
        html.append('<li><div class="timeline-status"><i class="material-icons last">&nbsp;</i></div></li></ul>')
        return "".join(html)

    def pagina(self, un, sec):
        corpo = self.menu(un, sec)
        if un:
            q = lambda nome, t: item_lista("icon-library_books", nome, f"/mod/quiz/view.php?q={t}")
            itens = (item_lista("icon-book", f"U{un}S{sec} - Webaula", "#") + q(f"U{un}S{sec} - Atividade Diagnóstica", f"{un}{sec}d")
                     + item_lista("icon-add_box", f"Unidade {un} - Aula presencial", "/trap")
                     + q(f"U{un}S{sec} - Atividade de Aprendizagem", f"{un}{sec}a"))
            if sec == 3:
                itens += item_lista("icon-ondemand_video", f"U{un} - Vídeo Aula Resumo", "/trap")
                itens += q(f"U{un} - Avaliação da Unidade", f"{un}av")
            corpo += f'<div class="ct-resource-list">{itens}</div>'
        return f"<html><body>{corpo}</body></html>"

    def quiz(self, t):
        self.visitas.append(t)
        return (f'<html><body><ol class="breadcrumb"><li class="breadcrumb-item"><a href="/course/view.php?id=1">Curso</a></li>'
                f'<li class="breadcrumb-item"><a href="#">{t}</a></li></ol>{TABELA}'
                f'<div class="box quizattempt"><p>Não são permitidas outras tentativas</p>'
                f'<button type="button" onclick="location.href=\'/course/view.php?id=1\'">Voltar ao curso</button></div></body></html>')

    def atender(self, rota):
        url = urlparse(rota.request.url)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/course/view.php":
            # "Voltar ao curso" cai na pagina inicial do curso (sem secao): o programa tem que reabrir a secao
            corpo = self.pagina(int(q["u"]), int(q["s"])) if "u" in q else self.pagina(None, None)
        elif url.path == "/mod/quiz/view.php":
            corpo = self.quiz(q["q"])
        else:
            corpo = f"<html><body>{url.path} (nao devia ir)</body></html>"
            self.visitas.append("ERRO:" + url.path)
        rota.fulfill(status=200, content_type="text/html; charset=utf-8", body=corpo)


class Falso(Solver):
    def solve(self, question):
        raise AssertionError("sem IA")


class Tela(Presenter):
    def __init__(self):
        self.avisos = []

    def mostrar(self, question, suggestion):
        pass

    def avisar(self, mensagem):
        self.avisos.append(mensagem)


with sync_playwright() as p:
    navegador = None
    for canal in ("chrome", "msedge"):
        try:
            navegador = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception:
            pass
    assert navegador
    ctx = navegador.new_context()
    curso = Curso()
    ctx.route("http://quiz.test/**", curso.atender)
    pag = ctx.new_page()
    pag.goto("http://quiz.test/course/view.php?id=1")
    leitor = PageReader(ctx)

    # leitura do menu: so as unidades (nao "Livro Didatico" nem "Avalie sua disciplina"), com secoes
    m = leitor.ler_menu()
    assert [u.nome for u in m] == ["Unidade de Ensino 1", "Unidade de Ensino 2"], m
    assert m[0].secoes == ("U1 - Seção 1", "U1 - Seção 2", "U1 - Seção 3") and m[0].secao_ativa is None, m
    assert m[0].percentual == 91 and m[1].percentual == 92, m
    pag.goto("http://quiz.test/course/view.php?id=1&u=1&s=2")
    m = leitor.ler_menu()
    assert m[0].secao_ativa == "U1 - Seção 2" and m[0].aberta and m[1].secao_ativa is None, m
    un = leitor.ler_unidade()
    assert un is not None and [a.nome for a in un.atividades][1] == "U1S2 - Atividade Diagnóstica", un
    print("leitor: menu so com unidades, secoes e secao ativa; atividades lidas sem depender do h1 ok")

    # clique na secao com o submenu FECHADO (link escondido): pelo DOM
    pag.goto("http://quiz.test/course/view.php?id=1")
    assert Responder(ctx).abrir_secao("U2 - Seção 3")  # sem o nome da unidade: so o clique no link escondido
    pag.wait_for_url("**u=2&s=3")
    # com a unidade: abre a unidade (1 clique no titulo) e depois a secao
    pag.goto("http://quiz.test/course/view.php?id=1")
    assert Responder(ctx).abrir_secao("U2 - Seção 2", "Unidade de Ensino 2")
    pag.wait_for_url("**u=2&s=2")
    # secao ja visivel (unidade aberta): NAO clica no titulo da unidade (fecharia o submenu)
    pag.evaluate("window.cliquesUnidade = 0")
    assert Responder(ctx).abrir_secao("U2 - Seção 3", "Unidade de Ensino 2")
    pag.wait_for_url("**u=2&s=3")
    pag.goto("http://quiz.test/course/view.php?id=1")
    pag.evaluate("window.cliquesUnidade = 0")
    r_ = Responder(ctx)
    assert r_._link_visivel("ul.timeline .timeline-menu li a", "U1 - Seção 1") is False
    r_.abrir_secao("U1 - Seção 1", "Unidade de Ensino 1")
    pag.wait_for_url("**u=1&s=1")
    print("responder: abre a unidade e depois a secao; nao fecha unidade ja aberta ok")

    # fluxo completo: 2 unidades x (S1: 2 quizzes, S2: 2, S3: 3) = 14 quizzes, em ordem
    pag.goto("http://quiz.test/course/view.php?id=1")
    tela = Tela()
    ass = AssistenteQuiz(leitor, Falso(), tela, intervalo=0.05, parar=threading.Event(), responder=Responder(ctx),
                         finalizar=True, tentativas=True, curso=True, pausa_voltar=0.3, pausa_curso=1)
    fim = time.monotonic() + 90
    while time.monotonic() < fim and not ass._curso_parado:
        ass._passo()
        time.sleep(0.05)
    for _ in range(6):
        ass._passo()
        time.sleep(0.05)
    esperado = []
    for n in (1, 2):
        for s in (1, 2, 3):
            esperado += [f"{n}{s}d", f"{n}{s}a"]
            if s == 3:
                esperado.append(f"{n}av")
    assert curso.visitas == esperado, curso.visitas
    assert "Curso concluído: 2 unidade(s) conferida(s)." in tela.avisos, tela.avisos
    assert not any("Parei" in a for a in tela.avisos), tela.avisos
    print("fluxo: 2 unidades x 3 secoes = 14 quizzes em ordem; sem ir a 'Aula presencial' nem video; concluido ok")

    # ---------- o USUARIO abre uma secao: comeca dali ----------
    def rodar_com_usuario(gancho_aviso=None, gancho_tick=None, segundos=90, pausa_voltar=0.3):
        curso2 = Curso()
        ctx2 = navegador.new_context()
        ctx2.route("http://quiz.test/**", curso2.atender)
        pag2 = ctx2.new_page()
        pag2.goto("http://quiz.test/course/view.php?id=1")
        tela2 = Tela()
        if gancho_aviso:
            original = tela2.avisar

            def avisar(m):
                original(m)
                gancho_aviso(m, pag2)

            tela2.avisar = avisar
        ass2 = AssistenteQuiz(PageReader(ctx2), Falso(), tela2, intervalo=0.05, parar=threading.Event(),
                              responder=Responder(ctx2), finalizar=True, tentativas=True, curso=True,
                              pausa_voltar=pausa_voltar, pausa_curso=2)
        rodar_com_usuario.ultimo = ass2  # para os ganchos mexerem no estado do assistente
        fim = time.monotonic() + segundos
        while time.monotonic() < fim and not ass2._curso_parado:
            ass2._passo()
            if gancho_tick:
                gancho_tick(ass2, curso2, pag2)
            time.sleep(0.05)
        ctx2.close()
        return ass2, curso2, tela2

    # A) durante a contagem "Estou conferindo...": abre a U2 - Secao 3 -> so conferem U2S3 (3 quizzes)
    def abrir_u2s3(msg, pag2):
        if msg.startswith("Estou conferindo"):
            pag2.goto("http://quiz.test/course/view.php?id=1&u=2&s=3")

    ass2, curso2, tela2 = rodar_com_usuario(gancho_aviso=abrir_u2s3)
    assert curso2.visitas == ["23d", "23a", "2av"], curso2.visitas
    assert any("Começando de onde você abriu: U2 - Seção 3." == a for a in tela2.avisos), tela2.avisos
    assert "Curso concluído: 2 unidade(s) conferida(s)." in tela2.avisos
    print("usuario abre a U2 - Secao 3 durante a contagem: comeca dali (3 quizzes), pula o resto ok")

    # B) no meio da analise: o programa ja fez a 1a prova da U1S1; o usuario abre a U2 - Secao 1
    estado = {"feito": False}

    def abrir_u2s1(ass_, curso_, pag_):
        if (not estado["feito"] and curso_.visitas[:1] == ["11d"] and ass_._nossa_navegacao_ate == 0.0
                and "u=1&s=1" in pag_.url):
            estado["feito"] = True
            pag_.goto("http://quiz.test/course/view.php?id=1&u=2&s=1")

    ass2, curso2, tela2 = rodar_com_usuario(gancho_tick=abrir_u2s1)
    assert estado["feito"]
    esperado = ["11d"] + [f"{n}{s}{t}" for n in (2,) for s in (1, 2, 3) for t in ("d", "a")]
    esperado.insert(esperado.index("23a") + 1, "2av")
    assert curso2.visitas == esperado, curso2.visitas
    assert any("Começando de onde você abriu: U2 - Seção 1." == a for a in tela2.avisos), tela2.avisos
    print("usuario abre a U2 - Secao 1 no meio da analise: continua dali, sem voltar para a U1 ok")

    # C) o usuario volta para a U1 - Secao 2 depois de a analise ja estar na U2: refaz dali
    estado = {"feito": False}

    def voltar_u1s2(ass_, curso_, pag_):
        if not estado["feito"] and len(curso_.visitas) >= 7 and ass_._nossa_navegacao_ate == 0.0 and "u=2&s=" in pag_.url:
            estado["feito"] = True
            pag_.goto("http://quiz.test/course/view.php?id=1&u=1&s=2")

    ass2, curso2, tela2 = rodar_com_usuario(gancho_tick=voltar_u1s2)
    assert estado["feito"]
    apos = curso2.visitas[7:]  # o que veio depois da volta
    assert apos[0] == "12d" and apos[-1] == "2av" and apos.count("12d") == 1, curso2.visitas
    assert "Curso concluído: 2 unidade(s) conferida(s)." in tela2.avisos
    print("usuario volta para a U1 - Secao 2: a analise recomeca dali ok")

    # D) O CASO DO LOG (10:24): o usuario clica numa secao durante o "Voltando ao curso em 3 s".
    # O programa cancela a volta e NAO pode reabrir o quiz que estava (antes ele o reabria e o usuario
    # precisava clicar de novo, duas vezes); a analise segue de onde o usuario clicou.
    clique = {"feito": False}

    def clicar_na_contagem(msg, pag2):
        if not clique["feito"] and "Voltando ao curso em" in msg:
            clique["feito"] = True
            pag2.goto("http://quiz.test/course/view.php?id=1&u=2&s=2")

    ass2, curso2, tela2 = rodar_com_usuario(gancho_aviso=clicar_na_contagem, pausa_voltar=3)
    assert clique["feito"]
    assert curso2.visitas == ["11d", "22d", "22a", "23d", "23a", "2av"], curso2.visitas  # nada de 11d/11a de novo
    assert any("Começando de onde você abriu: U2 - Seção 2." == a for a in tela2.avisos), tela2.avisos
    print("clique do usuario durante 'Voltando ao curso': respeitado de primeira, sem reabrir o quiz anterior ok")

    # E) o usuario esta DENTRO do quiz (a analise ja estava trabalhando) e clica numa secao especifica
    # depois de mais de 3 s fora das paginas do curso: tambem conta como escolha dele
    clique = {"feito": False}

    def clicar_depois_de_ficar_na_prova(msg, pag2):
        if not clique["feito"] and "Voltando ao curso em" in msg:
            clique["feito"] = True
            # simula "ficou mais de TEMPO_FORA_DO_CURSO segundos numa prova": o programa ja esqueceu o
            # endereco do curso (e qualquer marca de "fui eu"); o usuario entao clica numa secao
            rodar_com_usuario.ultimo._url_curso = None
            rodar_com_usuario.ultimo._nossa_navegacao_ate = 0.0
            pag2.goto("http://quiz.test/course/view.php?id=1&u=2&s=3")

    ass2, curso2, tela2 = rodar_com_usuario(gancho_aviso=clicar_depois_de_ficar_na_prova, pausa_voltar=3)
    assert clique["feito"]
    assert curso2.visitas == ["11d", "23d", "23a", "2av"], curso2.visitas
    assert any("Começando de onde você abriu: U2 - Seção 3." == a for a in tela2.avisos), tela2.avisos
    print("chegou numa secao especifica sem clique do programa, depois de ficar fora do curso: foi o usuario ok")

    # F) a pagina INICIAL do curso (so o "id") depois de uma prova NAO conta como escolha do usuario:
    # e so "onde o programa esta" (ele volta de uma prova e nada muda no roteiro)
    from quizbot.assistente import _tem_alem_do_id
    assert _tem_alem_do_id("http://quiz.test/course/view.php?id=1&u=2&s=3")
    assert _tem_alem_do_id("https://www.avaeduc.com.br/course/view.php?id=5351&topic=84886")
    assert not _tem_alem_do_id("https://www.avaeduc.com.br/course/view.php?id=5351")
    print("pagina inicial do curso (so o id) nao conta como escolha; unidade/secao conta ok")
    navegador.close()
print("TUDO OK")
