import io
import os
import sys
import tempfile
import threading
from pathlib import Path

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from quizbot import registro

# ---------- REGISTRO ----------
pasta = Path(tempfile.mkdtemp())
log = pasta / "logs" / "assistente.log"
os.environ["GEMINI_API_KEY"] = "AIzaSyCHAVE-SECRETA-123"
os.environ["MEMORIA_SENHA"] = "minha-senha-forte"
os.environ["AUTOMATICO_X"] = "sim"  # curto e sem KEY/SENHA: nao some

terminal = io.StringIO()
orig_out, orig_err = sys.stdout, sys.stderr
sys.stdout = terminal
try:
    registro.iniciar(log)
    print("linha 1 com a chave AIzaSyCHAVE-SECRETA-123 e acentos: ação, revisão")
    print("sim", end=" ")
    print("continua na mesma linha")
    try:
        1 / 0
    except ZeroDivisionError:
        registro.registrar_erro("teste de erro")
    saida_final = sys.stdout
finally:
    sys.stdout, sys.stderr = orig_out, orig_err
texto = log.read_text(encoding="utf-8")
assert "AIzaSyCHAVE-SECRETA-123" not in texto and "***" in texto, texto
assert "ação, revisão" in texto
assert "minha-senha-forte" not in texto
assert "ZeroDivisionError" in texto and "teste de erro" in texto  # traceback completo
assert all(l[2] == ":" and l[5] == ":" for l in texto.splitlines() if l[:1].isdigit()), texto  # hora no comeco
assert "sim continua na mesma linha" in texto  # hora so no comeco da linha, nao no meio
assert "AIzaSyCHAVE-SECRETA-123" in terminal.getvalue()  # o terminal ainda mostra tudo (so o arquivo e protegido)
print("registro: hora, acentos, traceback e segredos escondidos ok")

# recomeca a cada execucao e guarda a anterior como .1
# (no uso real cada execucao e um processo novo; aqui fecho o arquivo da execucao anterior)
saida_final._arquivo.close()
sys.stdout = io.StringIO()
try:
    registro.iniciar(log)
finally:
    sys.stdout, sys.stderr = orig_out, orig_err
assert (log.parent / "assistente.log.1").exists()
assert "linha 1" in (log.parent / "assistente.log.1").read_text(encoding="utf-8")
assert "linha 1" not in log.read_text(encoding="utf-8")
print("registro: rotacao ok")

# sem terminal (como no pythonw: sys.stdout None) nao quebra
sys.stdout.flush()
sys.stdout = sys.stderr = None
try:
    registro.iniciar(log)
    print("funciona sem terminal")
finally:
    sys.stdout, sys.stderr = orig_out, orig_err
assert "funciona sem terminal" in log.read_text(encoding="utf-8")
print("registro: sem terminal ok")

# ---------- JANELA: escolha de modo e erro ----------
import quizbot.janela as J

try:
    janela = J.JanelaPresenter()
except Exception as erro:
    print("janela nao testada (sem tela):", type(erro).__name__)
    print("TUDO OK (parcial)")
    raise SystemExit

def botoes_da_escolha(j):
    # procura os dois botoes da tela de escolha
    achados = []
    def varrer(w):
        for f in w.winfo_children():
            if f.winfo_class() == "Button":
                achados.append(f)
            varrer(f)
    varrer(j._raiz)
    return achados

escolhas = []
janela.escolher_modo(escolhas.append, segundos=30)
janela._raiz.update()
bts = [b for b in botoes_da_escolha(janela) if b["text"] in ("Automático", "Só sugerir")]
assert [b["text"] for b in bts] == ["Automático", "Só sugerir"]
altura = janela._raiz.winfo_height()
assert altura > 250, altura  # a tela de escolha e mais alta que a janelinha normal
bts[1].invoke(); janela._raiz.update()
assert escolhas == [False], escolhas
assert janela._raiz.winfo_height() <= 260  # voltou ao tamanho normal
janela._raiz.destroy()

# Automatico pelo botao, e pelo tempo (1 s no teste em vez de 15)
j2 = J.JanelaPresenter(); escolhas2 = []
j2.escolher_modo(escolhas2.append, segundos=30); j2._raiz.update()
[b for b in botoes_da_escolha(j2) if b["text"] == "Automático"][0].invoke()
assert escolhas2 == [True]
j2._raiz.destroy()

j3 = J.JanelaPresenter(); escolhas3 = []
j3.escolher_modo(escolhas3.append, segundos=1)
j3._raiz.after(2500, j3._raiz.quit)  # sai do mainloop depois de 2,5 s
j3.executar()
assert escolhas3 == [True], escolhas3  # ninguem escolheu: comecou no Automatico
j3._raiz.destroy()
print("janela: escolha por botao e por tempo ok (altura da escolha:", altura, ")")

# erro inesperado: mostra a pasta e o botao abre a pasta
abertas = []
J.abrir_pasta = abertas.append
j4 = J.JanelaPresenter()
j4.erro_inesperado(r"C:\Users\x\AppData\Local\AssistenteQuiz\logs")
j4._processar_fila(); j4._raiz.update()
assert j4._legenda["text"] == "ERRO" and "AssistenteQuiz\\logs" in j4._explicacao["text"]
assert j4._botao_pasta.winfo_ismapped()
j4._botao_pasta.invoke()
assert abertas == [Path(r"C:\Users\x\AppData\Local\AssistenteQuiz\logs")], abertas
j4.avisar("aviso comum"); j4._processar_fila(); j4._raiz.update()
assert not j4._botao_pasta.winfo_ismapped()  # o botao so aparece no erro
j4._raiz.destroy()
print("janela: erro com botao de abrir pasta ok")

# ---------- MAIN: erro inesperado na thread e erro ao abrir ----------
import quizbot.main as M

class JanFalsa:
    def __init__(self): self.pasta = None
    def erro_inesperado(self, p): self.pasta = p

def quebra(*a, **k):
    raise RuntimeError("boom de teste")

M.trabalhar = quebra
sys.stdout = io.StringIO()
try:
    registro.iniciar(log)
    jf = JanFalsa()
    M._trabalhar_com_registro(jf, None, threading.Event(), True, None)
finally:
    sys.stdout, sys.stderr = orig_out, orig_err
assert jf.pasta == str(M.PASTA_LOGS)
assert "RuntimeError: boom de teste" in log.read_text(encoding="utf-8")
print("main: erro na thread vai para o log e a janela avisa ok")

mostradas = []
M._erro_ao_abrir = lambda: mostradas.append(1)
M._executar = quebra
M.registro.iniciar = lambda *a, **k: None  # nao trocar o stdout de novo
try:
    M.main(); raise AssertionError("devia sair com erro")
except SystemExit as s:
    assert s.code == 1
assert mostradas == [1]
print("main: erro ao abrir avisa e sai com codigo 1 ok")
print("TUDO OK")
