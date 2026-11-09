# MEMORIA - o que o assistente lembra das questoes: as certas e as erradas.
#
# Memoria -> para cada questao guarda a alternativa CERTA (se ja acertou) ou as alternativas
#            ERRADAS que o Moodle ja marcou. A IA NAO aprende nada: quem lembra e este
#            programa.
#            - Acertou: guarda a certa e APAGA as erradas daquela questao (nao precisam mais).
#            - Errou:   guarda a errada, uma vez so (nunca repete).
#            - certa(questao) / erradas(questao): o que se sabe, juntando TODOS os PCs.
#            - registrar_revisao(resultados): guarda tudo da pagina de revisao de uma vez
#              e grava UMA vez (poupa as escritas do limite diario da nuvem).
#            - garantir_guardado(): True se o que se aprendeu esta em pelo menos um lugar
#              (arquivo local OU nuvem). O que ficou so no local sobe para a nuvem depois,
#              na proxima leitura (veja ArmazenamentoEspelhado).
#            Os dados vivem num Armazenamento (pasta local e/ou nuvem). Cada PC grava so o
#            seu, e a Memoria relê todos de tempos em tempos (INTERVALO_SINCRONIA), entao o
#            que um PC aprende aparece nos outros sem reiniciar.
#
# Como a questao e reconhecida (a "chave"): o enunciado + o codigo das imagens que estao
# no ENUNCIADO (no texto elas aparecem so como [imagem 1]). As imagens das alternativas
# ficam fora da chave, porque mudam de ordem quando o Moodle embaralha.
#
# Como a alternativa e reconhecida: pela "identidade" (Question.identidades), nunca pela
# posicao: o texto dela, e se for imagem, o codigo da imagem ([img:3f9a1c...]).
import hashlib
import re
import time
from collections.abc import Callable, Iterable

from quizbot.armazenamento import (
    Armazenamento,
    NuvemError,
    juntar_dados,
    juntar_entradas,
    nome_seguro,
)
from quizbot.config import INTERVALO_REGRAVAR, INTERVALO_SINCRONIA
from quizbot.models import Question, Resultado

_MARCA_IMAGEM = re.compile(r"\[imagem \d+\]")


def _chave(questao: Question) -> str:
    resumo = hashlib.sha1()
    resumo.update(questao.enunciado.encode())
    no_enunciado = len(_MARCA_IMAGEM.findall(questao.enunciado))
    for imagem in questao.imagens[:no_enunciado]:
        resumo.update(imagem.codigo.encode())
    return resumo.hexdigest()


class Memoria:
    def __init__(
        self,
        armazenamento: Armazenamento,
        nome: str,
        intervalo: float = INTERVALO_SINCRONIA,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._armazenamento = armazenamento
        self._nome = nome_seguro(nome)
        self._intervalo = intervalo
        self._relogio = relogio
        self._proprios: dict[str, dict] = {}  # o que ESTE PC aprendeu (e grava)
        self._outros: dict[str, dict] = {}  # o que os outros PCs aprenderam (so leitura)
        self._ultima_sincronia: float | None = None  # a 1a leitura acontece no 1o uso
        self._guardado = True  # False se a ultima gravacao nao chegou em lugar nenhum
        self._ultima_gravacao = 0.0

    def atualizar(self) -> None:
        todos = self._armazenamento.ler_todos()
        self._proprios = juntar_dados(todos.get(self._nome, {}), self._proprios)
        outros: dict[str, dict] = {}
        for nome, dados in todos.items():
            if nome != self._nome:
                outros = juntar_dados(outros, dados)
        self._outros = outros
        self._ultima_sincronia = self._relogio()
        if self._compactar():
            self._salvar()

    def _atualizar_se_preciso(self) -> None:
        agora = self._relogio()
        if self._ultima_sincronia is None or agora - self._ultima_sincronia >= self._intervalo:
            self.atualizar()

    def _compactar(self) -> bool:
        """Tira do arquivo deste PC o que ja nao serve: erradas de questoes com certa."""
        mudou = False
        for chave, entrada in list(self._proprios.items()):
            certa = entrada.get("certa") or self._outros.get(chave, {}).get("certa")
            if certa and entrada.get("erradas"):
                entrada["erradas"] = []
                mudou = True
            if not entrada.get("certa") and not entrada.get("erradas"):
                del self._proprios[chave]
                mudou = True
        return mudou

    def _entrada(self, chave: str) -> dict:
        return juntar_entradas(self._proprios.get(chave, {}), self._outros.get(chave, {}))

    def _salvar(self) -> None:
        self._ultima_gravacao = self._relogio()
        try:
            self._armazenamento.gravar(self._proprios)
            self._guardado = True
        except (OSError, NuvemError):  # nem o arquivo local nem a nuvem aceitaram
            self._guardado = False

    def garantir_guardado(self) -> bool:
        """True se o que se aprendeu esta guardado em PELO MENOS um lugar (local ou nuvem).

        Se estiver parcial (so no local), tudo bem: a nuvem recebe depois, sozinha. Se nao
        chegou em lugar nenhum, tenta de novo, no maximo uma vez a cada INTERVALO_REGRAVAR
        segundos."""
        if not self._guardado and self._relogio() - self._ultima_gravacao >= INTERVALO_REGRAVAR:
            self._salvar()
        return self._guardado

    def certa(self, questao: Question) -> str | None:
        self._atualizar_se_preciso()
        return self._entrada(_chave(questao)).get("certa")

    def erradas(self, questao: Question) -> frozenset[str]:
        self._atualizar_se_preciso()
        return frozenset(self._entrada(_chave(questao))["erradas"])

    def _aplicar(self, questao: Question, indice: int, acertou: bool) -> bool:
        if not 0 <= indice < len(questao.alternativas):
            return False
        identidade = questao.identidades[indice]
        chave = _chave(questao)
        conhecida = self._entrada(chave)

        if acertou and conhecida.get("certa") == identidade:
            return False
        if not acertou and (conhecida.get("certa") or identidade in conhecida["erradas"]):
            return False

        propria = self._proprios.setdefault(
            chave, {"enunciado": questao.enunciado[:100], "erradas": []}
        )
        if acertou:
            propria["certa"] = identidade
            propria["erradas"] = []
        else:
            propria["erradas"].append(identidade)
        return True

    def registrar(self, questao: Question, indice: int, acertou: bool) -> bool:
        """Guarda um resultado. Devolve True se era novidade."""
        self._atualizar_se_preciso()
        novo = self._aplicar(questao, indice, acertou)
        if novo:
            self._salvar()
        return novo

    def registrar_revisao(self, resultados: Iterable[Resultado]) -> tuple[int, int]:
        """Guarda os resultados da revisao e grava uma vez. Devolve (erradas, certas) novas."""
        self._atualizar_se_preciso()
        erradas = certas = 0
        for resultado in resultados:
            if self._aplicar(resultado.questao, resultado.indice, resultado.acertou):
                if resultado.acertou:
                    certas += 1
                else:
                    erradas += 1
        if erradas or certas:
            self._salvar()
        return erradas, certas
