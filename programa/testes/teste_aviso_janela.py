import sys
import time

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import quizbot.janela as jm
from quizbot.models import Question, Suggestion

jm.SEGUNDOS_ALERTA = 1  # no teste, 1 s em vez de 5 s
j = jm.JanelaPresenter()


def roda(segundos):
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        j._processar_fila_uma_vez() if hasattr(j, "_processar_fila_uma_vez") else None
        # esvazia a fila de tarefas (sem reagendar o after da janela)
        while not j._fila.empty():
            j._fila.get_nowait()()
        j._raiz.update()
        time.sleep(0.02)


def legenda():
    return j._legenda.cget("text")


def principal():
    return j._principal.cget("text")


# 1) aviso segura o "Consultando": ele entra so depois do tempo minimo
j.avisar("Tentativa enviada.")
j.consultando()
roda(0.3)
assert legenda() == "AVISO" and principal() == "Tentativa enviada.", (legenda(), principal())
# o usuario ja ve que a IA esta trabalhando, sob o aviso (sem esperar os 5 s)
assert j._explicacao.cget("text") == "Consultando a IA…", j._explicacao.cget("text")
assert j._raiz.winfo_height() >= j._conteudo.winfo_reqheight()
roda(1.2)
assert legenda() == "CONSULTANDO", legenda()
print("aviso fica o tempo minimo; o 'Consultando' espera a vez ok")

# 2) dois avisos seguidos: o segundo espera o primeiro ser lido (nenhum e engolido)
j.avisar("Revisão lida: guardei 10 certa(s).")
j.avisar("Revisão terminada.")
roda(0.3)
assert principal() == "Revisão lida: guardei 10 certa(s).", principal()
roda(1.2)
assert principal() == "Revisão terminada.", principal()
roda(1.3)
print("dois avisos seguidos aparecem um depois do outro ok")

# 3) a sugestao NUNCA espera: fura a fila na hora
j.avisar("Tentativa enviada.")
j.consultando()
roda(0.2)
assert legenda() == "AVISO"
j.mostrar(Question("e", ("a", "b")), Suggestion(indice=1, explicacao="porque sim", origem="groq"))
roda(0.1)
assert legenda() == "SUGESTÃO" and principal().startswith("B"), (legenda(), principal())
roda(1.5)
assert legenda() == "SUGESTÃO"  # o 'Consultando' que esperava foi descartado
print("a sugestao aparece na hora, por cima do aviso ok")

# 4) sem aviso nenhum, o 'Consultando' aparece na hora
roda(1.2)
j.consultando()
roda(0.1)
assert legenda() == "CONSULTANDO"
print("sem aviso, o 'Consultando' nao atrasa ok")

# 5) o alerta de falha da IA fica o tempo minimo e some sozinho
j.problemas_nos_provedores(["Algo deu errado: API do Gemini fora do ar."])
roda(0.3)
assert j._alerta.winfo_ismapped()
roda(1.3)
assert not j._alerta.winfo_ismapped()
print("alerta da IA fica e some sozinho ok")
j._raiz.destroy()
print("TUDO OK")
