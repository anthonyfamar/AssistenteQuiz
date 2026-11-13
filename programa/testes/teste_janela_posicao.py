# TESTE - a janelinha so vai para o canto na PRIMEIRA vez; depois e do usuario.
#
# Confere: a posicao inicial (canto inferior direito); que depois de o usuario arrastar a janela, as
# trocas de tela (que mudam a altura) mantem x e y; e que ela so sobe se crescer para fora da tela.
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import quizbot.janela as jm
from quizbot.models import Question, Suggestion

jm.SEGUNDOS_ALERTA = 1


def posicao(j):
    j._raiz.update_idletasks()
    achado = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", j._raiz.geometry())
    return tuple(int(g) for g in achado.groups())  # largura, altura, x, y


def rodar(j, segundos):
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        while not j._fila.empty():
            j._fila.get_nowait()()
        j._raiz.update()
        time.sleep(0.02)


j = jm.JanelaPresenter(ao_fechar=lambda: None)
rodar(j, 0.2)
larg, alt, x, y = posicao(j)
tela_w, tela_h = j._raiz.winfo_screenwidth(), j._raiz.winfo_screenheight()
assert x == tela_w - jm.LARGURA - jm.MARGEM, (x, tela_w)
assert y == max(tela_h - alt - jm.ALTURA_BARRA_TAREFAS, 0), (y, tela_h, alt)
print(f"primeira vez: canto inferior direito ({x},{y}) ok")

# o usuario arrasta a janela para outro lugar
j._raiz.geometry("+137+91")
rodar(j, 0.2)
assert posicao(j)[2:] == (137, 91), posicao(j)

# as trocas de tela (sugestao, aviso longo, pergunta do fim do curso, falha com "Tentar de novo")
j.mostrar(Question("Enunciado", ("a", "b", "c")),
          Suggestion(indice=1, explicacao="Uma explicacao um pouco mais longa para a janela crescer. " * 4, origem="falso"))
rodar(j, 0.4)
assert posicao(j)[2:] == (137, 91), ("depois de mostrar a sugestao", posicao(j))
j.avisar("Um aviso comprido o bastante para mudar a altura da janela. " * 3)
rodar(j, 0.4)
assert posicao(j)[2:] == (137, 91), ("depois de um aviso", posicao(j))
j.oferecer_tentar_de_novo("Nao consegui marcar a alternativa B. Marque voce mesmo ou tente de novo.", lambda: None)
rodar(j, 0.4)
assert posicao(j)[2:] == (137, 91), ("depois de oferecer 'Tentar de novo'", posicao(j))
j.consultando()
rodar(j, 0.4)
assert posicao(j)[2:] == (137, 91), ("depois de consultar", posicao(j))
print("arrastada para (137,91): sugestao, aviso, 'Tentar de novo' e consulta NAO a movem ok")

# mudar so a altura mantem x e y
j._posicionar(420)
rodar(j, 0.2)
larg, alt, x, y = posicao(j)
assert (x, y) == (137, 91) and alt == 420, posicao(j)

# perto da borda de baixo: se crescer para fora da tela, sobe so o necessario (e continua visivel)
j._raiz.geometry(f"+300+{tela_h - 150}")
rodar(j, 0.2)
j._posicionar(300)
rodar(j, 0.2)
larg, alt, x, y = posicao(j)
assert x == 300 and y + alt <= tela_h - jm.ALTURA_BARRA_TAREFAS and y > 0, (x, y, alt, tela_h)
print(f"perto da borda de baixo: subiu so o necessario (y={y}) e a janela continua visivel ok")
j._raiz.destroy()
print("TUDO OK")
