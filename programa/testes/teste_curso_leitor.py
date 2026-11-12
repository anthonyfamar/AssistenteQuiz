import sys

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

from quizbot.page_reader import PageReader
from quizbot.responder import Responder

# Marca o clique no titulo da pagina e nao navega (o href real iria para o site de verdade).
CLIQUE = "onclick=\"document.title += '[' + this.textContent.trim() + ']'; return false\""


def item(id_, pct, nome, ativo=False):
    if ativo:
        corpo = (f'<div class="timeline-item active"><a href="" aria-label="{nome} Item ativo" {CLIQUE}>\n'
                 f'                                    {nome}                                </a></div>')
    else:
        corpo = f'<div class="timeline-item"><a href="" {CLIQUE}>{nome}</a></div>'
    return (f'<li><div class="timeline-status"><i id="{id_}" class="material-icons" style="background-image: '
            f'linear-gradient(0deg, rgb(67, 74, 79) {pct}%, transparent {pct}%);">&nbsp;</i></div>{corpo}</li>')


MENU = ('<ul class="timeline">'
        + item(800398, 100, "Unidade de Ensino 1")
        + item(800399, 100, "Unidade de Ensino 2")
        + item(800400, 17, "Unidade de Ensino 3", ativo=True)
        + item(800401, 17, "Unidade de Ensino 4")
        + '<li><div class="timeline-status"><i class="material-icons last">&nbsp;</i></div></li></ul>')


def atividade(id_, icone, nome, feita, aviso=""):
    check = '<i class="icon-check_circle format_list_topics_complete"></i>' if feita else ""
    return (f'<div class="ct-list"><div class="ct-list-title"><h3><i id="{id_}" required="2" '
            f'completion="icon-new_releases" completion_rules="icon-check_circle" class="{icone} format_list_topics_default">'
            f'<i class="icon-new_releases format_list_topics_required"></i>{check}</i>'
            f'<a href="" {CLIQUE}>\n   {nome}   </a></h3></div>{aviso}</div>')


def rotulo(nome):
    return f'<div class="ct-list-label"><div class="ct-list-title"><h3 class="ct-list-title-label">{nome}</h3></div></div>'


AVISO = '<div class="no-overflow"><p>Atenção: Para sua tentativa ser contabilizada, você deve clicar no botão <strong>"Enviar Tudo e Terminar"</strong></p></div>'

UNIDADE = ('<div class="ct-resource-list"><div class="ct-section-active-topic"><h1>Unidade de Ensino 3</h1></div></div>'
           '<div class="ct-resource-list">'
           + atividade(5962657, "icon-book", "U3 - Livro Didático", False)
           + rotulo("Pré-Aula")
           + atividade(6080320, "icon-add_box", "TECNOLOGIAS DE DESENVOLVIMENTO DE SISTEMAS", True)
           + rotulo("Aula")
           + atividade(6080338, "icon-add_box", "TECNOLOGIAS DE DESENVOLVIMENTO DE SISTEMAS", False)
           + atividade(5962661, "icon-library_books", "U3 - Atividade de Aprendizagem", True, AVISO)
           + atividade(5962662, "icon-library_books", "U3 - Avaliação da Unidade", False, AVISO)
           + '</div>')

CAMINHO = ('<ol class="breadcrumb">'
           '<li class="breadcrumb-item"><a href="https://www.avaeduc.com.br/">Página inicial</a></li>'
           '<li class="breadcrumb-item">Meus cursos</li>'
           '<li class="breadcrumb-item"><a href="https://www.avaeduc.com.br/course/view.php?id=11336" '
           f'title="Desenvolvimento de Soluções Remotas" {CLIQUE}>Desenvolvimento de Soluções Remotas</a></li>'
           '<li class="breadcrumb-item">Unidade de Ensino 1</li>'
           '<li class="breadcrumb-item"><a href="https://www.avaeduc.com.br/mod/quiz/view.php?id=5959271" '
           'title="Questionário" aria-current="page">U1 - Atividade de Aprendizagem</a></li></ol>')

BOTAO_VOLTAR = f'<button type="submit" class="btn btn-secondary" {CLIQUE}>Voltar ao curso</button>'

with sync_playwright() as p:
    navegador = None
    for canal in ("chrome", "msedge"):
        try:
            navegador = p.chromium.launch(channel=canal, headless=True)
            break
        except Exception:
            continue
    assert navegador
    ctx = navegador.new_context()
    pag = ctx.new_page()
    leitor, resp = PageReader(ctx), Responder(ctx)

    # --- ler_menu ---
    pag.set_content("<html><body><p>sem menu</p></body></html>")
    assert leitor.ler_menu() is None and leitor.ler_unidade() is None and leitor.ler_caminho() is None
    pag.set_content(f"<html><body><title></title>{MENU}</body></html>")
    menu = leitor.ler_menu()
    assert [(u.nome, u.percentual, u.aberta) for u in menu] == [
        ("Unidade de Ensino 1", 100.0, False), ("Unidade de Ensino 2", 100.0, False),
        ("Unidade de Ensino 3", 17.0, True), ("Unidade de Ensino 4", 17.0, False),
    ], menu
    print("ler_menu: 4 unidades, barras 100/100/17/17, a 3 aberta, o <li> decorativo ignorado ok")

    # --- ler_unidade ---
    pag.set_content(f"<html><body>{MENU}{UNIDADE}</body></html>")
    u = leitor.ler_unidade()
    assert u.titulo == "Unidade de Ensino 3", u.titulo
    nomes = [(a.nome, a.concluida) for a in u.atividades]
    assert ("U3 - Atividade de Aprendizagem", True) in nomes and ("U3 - Avaliação da Unidade", False) in nomes, nomes
    assert ("U3 - Livro Didático", False) in nomes and len(nomes) == 5, nomes  # os rotulos "Aula"/"Pre-Aula" nao entram
    print("ler_unidade: h1, atividades e o 'feito' de cada uma ok")

    # --- ler_caminho (breadcrumb) ---
    pag.set_content(f"<html><body>{CAMINHO}</body></html>")
    c = leitor.ler_caminho()
    assert (c.unidade, c.quiz) == ("Unidade de Ensino 1", "U1 - Atividade de Aprendizagem"), c
    print("ler_caminho: unidade e quiz do breadcrumb ok")

    # --- Responder: abrir unidade / atividade (texto exato) ---
    pag.set_content(f"<html><head><title></title></head><body>{MENU}{UNIDADE}</body></html>")
    assert resp.abrir_unidade("Unidade de Ensino 3")  # o ativo tem espacos/quebras no texto
    assert resp.abrir_unidade("Unidade de Ensino 1")
    assert not resp.abrir_unidade("Unidade de Ensino 9")
    assert not resp.abrir_unidade("Unidade de Ensino")  # nome incompleto nao vale
    assert resp.abrir_atividade("U3 - Avaliação da Unidade")
    assert not resp.abrir_atividade("U3 - Avaliação")
    assert pag.title() == "[Unidade de Ensino 3][Unidade de Ensino 1][U3 - Avaliação da Unidade]", pag.title()
    print("abrir_unidade / abrir_atividade: clica so no nome exato ok")

    # --- voltar_ao_curso: botao primeiro, depois o breadcrumb ---
    pag.set_content(f"<html><head><title></title></head><body>{CAMINHO}{BOTAO_VOLTAR}</body></html>")
    assert resp.voltar_ao_curso() and pag.title() == "[Voltar ao curso]", pag.title()
    pag.set_content(f"<html><head><title></title></head><body>{CAMINHO}</body></html>")
    assert resp.voltar_ao_curso() and pag.title() == "[Desenvolvimento de Soluções Remotas]", pag.title()
    navegador.close()
    print("voltar_ao_curso: botao quando existe; senao o link do curso no breadcrumb ok")

print("TUDO OK")
