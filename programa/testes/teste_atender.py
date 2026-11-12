import sys
import threading
import time

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

import quizbot.janela as jm
from quizbot.assistente import AssistenteQuiz
from quizbot.page_reader import PageReader

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
    aba = ctx.new_page()
    leitor = PageReader(ctx)
    a = AssistenteQuiz(leitor, None, None, parar=threading.Event())

    recebidas = []
    aba.on("console", lambda m: recebidas.append(time.monotonic()))
    aba.set_content("<script>setInterval(()=>console.log('x'), 100)</script>")

    # espera "parada" (o jeito antigo): o navegador manda mensagens e o Python nao as processa
    recebidas.clear()
    threading.Event().wait(1.0)
    paradas = len(recebidas)
    # espera do assistente: as mensagens sao atendidas DURANTE a espera
    recebidas.clear()
    ini = time.monotonic()
    assert a._esperar(1.0) is False
    dur = time.monotonic() - ini
    atendidas = len(recebidas)
    print(f"espera parada: {paradas} mensagem(ns) atendida(s) | espera do assistente: {atendidas} em {dur:.2f}s")
    assert 0.95 <= dur < 1.6, dur
    assert atendidas >= 6 and paradas == 0, (paradas, atendidas)

    # pedido de parar: sai na hora (True)
    a._parar.set()
    ini = time.monotonic()
    assert a._esperar(5) is True and time.monotonic() - ini < 0.3
    a._parar.clear()

    # sem nenhuma aba: cai na espera comum, sem erro
    aba.close()
    ini = time.monotonic()
    assert a._esperar(0.6) is False and 0.55 <= time.monotonic() - ini < 1.2
    navegador.close()
print("assistente: a espera atende o navegador, respeita parar e funciona sem aba ok")

# A pergunta "Outra materia" usa a espera do assistente enquanto aguarda o clique
jm.SEGUNDOS_ALERTA = 1
j = jm.JanelaPresenter(ao_fechar=lambda: None)
chamadas = []


def esperar(s):
    chamadas.append(s)
    time.sleep(s)
    return False


saida = {}
t = threading.Thread(target=lambda: saida.setdefault("v", j.perguntar_outra_materia(esperar)), daemon=True)
t.start()
fim = time.monotonic() + 4
while time.monotonic() < fim and not j._pergunta.winfo_ismapped():
    while not j._fila.empty():
        j._fila.get_nowait()()
    j._raiz.update()
    time.sleep(0.02)
assert j._pergunta.winfo_ismapped()
n = len(chamadas)
assert n >= 1, "nao usou a espera do assistente"
j._pergunta.winfo_children()[0].invoke()
t.join(2)
assert saida["v"] is True and len(chamadas) >= n
# a espera pede para parar: devolve False sem travar
j2 = jm.JanelaPresenter(ao_fechar=lambda: None)
saida2 = {}
t2 = threading.Thread(target=lambda: saida2.setdefault("v", j2.perguntar_outra_materia(lambda s: True)), daemon=True)
t2.start()
t2.join(3)
assert saida2.get("v") is False
j._raiz.destroy()
j2._raiz.destroy()
print("pergunta 'Outra materia': espera pelo assistente (navegador atendido) e responde ok")
print("TUDO OK")
