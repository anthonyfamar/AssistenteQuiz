import sys
import threading
import time

import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import quizbot.janela as jm

jm.SEGUNDOS_ALERTA = 1


def nova():
    chamado = threading.Event()
    j = jm.JanelaPresenter(ao_fechar=chamado.set)
    return j, chamado


def roda(j, segundos, ate=None):
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        try:
            while not j._fila.empty():
                j._fila.get_nowait()()
            j._raiz.update()
        except Exception:  # a janela pode ter sido fechada
            return
        if ate is not None and ate():
            return
        time.sleep(0.02)


def perguntar(j):
    saida = {}
    t = threading.Thread(target=lambda: saida.setdefault("v", j.perguntar_outra_materia()), daemon=True)
    t.start()
    return t, saida


# 1) "Outra materia": mostra os botoes, espera o clique e devolve True; a janela continua aberta
j, chamado = nova()
t, saida = perguntar(j)
roda(j, 3, ate=lambda: j._pergunta.winfo_ismapped())
assert j._pergunta.winfo_ismapped() and j._legenda.cget("text") == "CURSO CONCLUÍDO"
assert j._principal.cget("text") == "Quer conferir outra matéria?"
assert j._raiz.winfo_height() >= j._conteudo.winfo_reqheight()
assert t.is_alive() and "v" not in saida  # esperando o clique
j._pergunta.winfo_children()[0].invoke()  # "Outra materia"
t.join(2)
assert saida["v"] is True
roda(j, 0.2)
assert not j._pergunta.winfo_ismapped() and j._legenda.cget("text") == "AGUARDANDO"
assert not chamado.is_set()
j._raiz.destroy()
print("'Outra materia': mostra os botoes, espera o clique, devolve True e segue aberta ok")

# 2) "Encerrar": devolve False e fecha a janela (chama ao_fechar)
j, chamado = nova()
t, saida = perguntar(j)
roda(j, 3, ate=lambda: j._pergunta.winfo_ismapped())
j._pergunta.winfo_children()[1].invoke()  # "Encerrar"
t.join(2)
assert saida["v"] is False
roda(j, 2.5, ate=lambda: chamado.is_set())
assert chamado.is_set() and j._fechada
print("'Encerrar': devolve False e fecha a janela ok")

# 3) o aviso do fim do curso fica na tela o tempo minimo ANTES da pergunta aparecer
j, chamado = nova()
j.avisar("Curso concluído: 4 unidade(s) conferida(s).")
t, saida = perguntar(j)
roda(j, 0.4)
assert j._legenda.cget("text") == "AVISO" and not j._pergunta.winfo_ismapped()
roda(j, 3, ate=lambda: j._pergunta.winfo_ismapped())
assert j._pergunta.winfo_ismapped()
j._pergunta.winfo_children()[0].invoke()
t.join(2)
j._raiz.destroy()
print("aviso 'Curso concluido' aparece primeiro; a pergunta entra depois ok")

# 4) janela fechada com a pergunta aberta: nao trava, devolve False
j, chamado = nova()
t, saida = perguntar(j)
roda(j, 3, ate=lambda: j._pergunta.winfo_ismapped())
j._fechar()
t.join(3)
assert saida.get("v") is False and chamado.is_set()
print("janela fechada durante a pergunta: devolve False sem travar ok")

# 6) JANELA MINIMIZADA: aviso comum nao restaura (nao atrapalha); a pergunta e o chamado restauram
j, chamado = nova()
j._raiz.iconify()
j._raiz.update()
assert j._raiz.state() == "iconic", j._raiz.state()
j.avisar("aviso comum com a janela minimizada")
roda(j, 0.4)
assert j._principal.cget("text") == "aviso comum com a janela minimizada"  # continua processando
assert j._raiz.state() == "iconic", j._raiz.state()  # e nao incomoda
j.chamar_atencao()
roda(j, 0.4)
assert j._raiz.state() == "normal", j._raiz.state()
j._raiz.iconify()
j._raiz.update()
t, saida = perguntar(j)
roda(j, 4, ate=lambda: j._pergunta.winfo_ismapped())
assert j._pergunta.winfo_ismapped() and j._raiz.state() == "normal", j._raiz.state()
j._pergunta.winfo_children()[0].invoke()
t.join(2)
assert saida["v"] is True
j._raiz.iconify()
j._raiz.update()
j._erro("C:/pasta")  # erro inesperado tambem restaura
assert j._raiz.state() == "normal", j._raiz.state()
j._raiz.destroy()
print("janela minimizada: avisos comuns nao restauram; pergunta, chamado e erro restauram ok")

# 7) falhou ao marcar/avancar: a SUGESTAO continua na tela, com a mensagem e o botao "Tentar de novo"
from quizbot.models import Question, Suggestion

j, chamado = nova()
j.mostrar(Question("e", ("a", "b", "c")), Suggestion(indice=1, explicacao="porque sim", origem="groq"))
roda(j, 0.3)
assert j._legenda.cget("text") == "SUGESTÃO"
chamadas = []
j.oferecer_tentar_de_novo("Não consegui marcar a alternativa B. Marque você mesmo ou tente de novo.",
                          lambda: chamadas.append(1))
roda(j, 0.3)
assert j._botao_repetir.winfo_ismapped() and j._aviso_acao.winfo_ismapped()
# a resposta NAO foi apagada pelo aviso de falha
assert j._legenda.cget("text") == "SUGESTÃO", j._legenda.cget("text")
assert j._principal.cget("text").startswith("B - ") and "porque sim" in j._explicacao.cget("text")
assert "Não consegui marcar a alternativa B" in j._aviso_acao.cget("text")
assert j._raiz.winfo_height() >= j._conteudo.winfo_reqheight()
j._botao_repetir.invoke()
assert chamadas == [1] and not j._botao_repetir.winfo_ismapped()
j._botao_repetir.invoke()  # clique repetido: nao chama de novo
assert chamadas == [1]
assert j._principal.cget("text").startswith("B - ")  # a sugestao segue la
# a oferta some quando a questao muda
j.oferecer_tentar_de_novo("falha 2", lambda: None)
roda(j, 0.3)
assert j._botao_repetir.winfo_ismapped()
j.consultando()
roda(j, 0.3)
assert not j._botao_repetir.winfo_ismapped() and not j._aviso_acao.winfo_ismapped()
# com a janela minimizada, a falha traz a janela para a frente (o usuario precisa agir)
j._raiz.iconify()
j._raiz.update()
j.oferecer_tentar_de_novo("falha 3", lambda: None)
roda(j, 0.4)
assert j._raiz.state() == "normal", j._raiz.state()
j._raiz.destroy()
print("acao que falhou: a sugestao continua na tela + 'Tentar de novo' (e traz a janela se minimizada) ok")

# 5) clique repetido nao quebra
j, chamado = nova()
t, saida = perguntar(j)
roda(j, 3, ate=lambda: j._pergunta.winfo_ismapped())
botao = j._pergunta.winfo_children()[0]
botao.invoke()
botao.invoke()
t.join(2)
assert saida["v"] is True
j._raiz.destroy()
print("TUDO OK")
