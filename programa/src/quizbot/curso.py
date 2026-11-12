# CURSO - decide o proximo passo no curso (sem navegador, so logica).
#
# RoteiroDoCurso -> recebe o que a pagina mostra (o menu das unidades e a unidade aberta) e
#                   responde "o que faco agora?" com uma Acao:
#                   - AbrirUnidade(nome)       clicar numa unidade do menu;
#                   - AbrirAtividade(nome)     clicar num dos 2 quizzes da unidade aberta;
#                   - Concluido(resumo)        todas as unidades conferidas;
#                   - Parar(motivo)            algo nao saiu como esperado: avisar o usuario.
#                   O quiz e achado pelo NOME INTEIRO ("U1 - Atividade de Aprendizagem"), nunca
#                   por um trecho: "Pre Aula 4 - U1 - Atividade de Aprendizagem" e arquivo de
#                   apoio. Com mais de um candidato, o icone de quiz desempata; sem certeza, Parar.
#                   Trabalha nas unidades EM ORDEM e confere os 2 quizzes de TODAS (a barra de
#                   progresso mede conclusao, nao nota: um quiz "feito" pode ter nota baixa e
#                   tentativa sobrando; quem decide refazer e o painel do quiz, no assistente).
#                   Um quiz so e dado como conferido quando o assistente avisa que terminou
#                   (quiz_terminado). Cada unidade/quiz tem poucas tentativas de abrir:
#                   passou disso, Parar (nada fica sem fazer sem o usuario saber).
#
# Fica separado do navegador de proposito: da para testar sozinho, so com dados.
import re
import unicodedata
from dataclasses import dataclass

from quizbot.config import (
    CLASSE_ICONE_QUIZ,
    MAX_TENTATIVAS_CURSO,
    QUIZZES_DO_CURSO,
    TIPOS_DE_QUIZ,
)
from quizbot.models import AtividadeDoCurso, Unidade, UnidadeAberta


def limpar(texto: str) -> str:
    """Minuscula, sem acento e com um espaco so entre as palavras (para comparar nomes)."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    sem_acento = sem_acento.replace("–", "-").replace("—", "-")  # travessoes viram "-"
    return " ".join(sem_acento.casefold().split())


# O nome INTEIRO tem que ser "U<numero> - <trecho>" (ou "U<numero>S<numero> - <trecho>", nos
# cursos com secoes). Assim "Pre Aula 4 - U1 - Atividade de Aprendizagem" (arquivo de apoio) nao
# e confundido com o quiz "U1 - Atividade de Aprendizagem".
_PADROES = tuple(
    (tipo, re.compile(rf"^u\d+(?:s\d+)?\s*-\s*{re.escape(trecho)}$")) for tipo, trecho, _ in TIPOS_DE_QUIZ
)
_SECAO = re.compile(r"^u(\d+)\s*-\s*secao\s*(\d+)$")  # "U3 - Seção 2" (ja sem acento)


def tipo_do_quiz(nome: str) -> str | None:
    """'diagnostica', 'aprendizagem' ou 'avaliacao' se o nome for, por inteiro, o de um quiz."""
    limpo = limpar(nome)
    for tipo, padrao in _PADROES:
        if padrao.match(limpo):
            return tipo
    return None


def _quiz_e_desta_secao(nome: str, tipo: str, codigo: tuple[str, str] | None) -> bool:
    # "U3S2 - ..." so vale na "U3 - Secao 2"; a "Avaliacao da Unidade" ("U3 - ...") na unidade 3.
    # Sem o codigo da secao (nome fora do padrao), nao da para conferir: aceita.
    if codigo is None:
        return True
    unidade, secao = codigo
    inicio = rf"^u{unidade}\s*-" if tipo == "avaliacao" else rf"^u{unidade}s{secao}\s*-"
    return re.match(inicio, limpar(nome)) is not None


@dataclass(frozen=True)
class AbrirUnidade:
    nome: str


@dataclass(frozen=True)
class AbrirSecao:
    nome: str
    unidade: str


@dataclass(frozen=True)
class AbrirAtividade:
    nome: str
    unidade: str


@dataclass(frozen=True)
class Concluido:
    resumo: str


@dataclass(frozen=True)
class Parar:
    motivo: str
    pendentes: tuple[str, ...] = ()


Acao = AbrirUnidade | AbrirSecao | AbrirAtividade | Concluido | Parar


class RoteiroDoCurso:
    def __init__(self, max_tentativas: int = MAX_TENTATIVAS_CURSO) -> None:
        self._max = max_tentativas
        self._conferidos: set[tuple[str, str]] = set()  # (unidade, tipo) ja conferidos
        self._tentativas: dict[tuple, int] = {}  # quantas vezes tentou abrir cada coisa
        self._atual: tuple[str, str] | None = None  # o quiz que o roteiro mandou abrir
        self._secoes_prontas: set[str] = set()  # secoes cujos quizzes (todos) ja foram conferidos
        self._quizzes_da_secao: dict[str, list[str]] = {}  # tipos de quiz vistos na pagina de cada secao

    # --- o que o assistente avisa ---

    def quiz_terminado(self, unidade: str | None = None, quiz: str | None = None) -> str | None:
        """O assistente terminou um quiz (nota 10 ou tentativas esgotadas) e vai voltar ao curso.

        Marca como conferido o quiz que o proprio roteiro abriu; se foi aberto de outro jeito,
        usa o nome da unidade e do quiz lidos no topo da pagina. Devolve o que marcou (ou None).
        """
        chave = self._atual
        if chave is None and unidade and quiz:
            tipo = tipo_do_quiz(quiz)
            if tipo is not None:
                chave = (limpar(unidade), tipo)
        self._atual = None
        if chave is None:
            return None
        self._conferidos.add(chave)
        return f"{chave[0]} / {chave[1]}"

    # --- o usuario abriu uma unidade/secao por conta propria: comecar de la ---

    def ponto_de_partida(
        self, menu: tuple[Unidade, ...], aberta: UnidadeAberta | None
    ) -> tuple[str, str | None] | None:
        """Onde a pagina esta: (unidade, secao) ou (unidade, None) nos cursos sem secoes.

        None se nao da para saber (pagina carregando, ou sem unidade/secao aberta).
        """
        atividades = aberta.atividades if aberta else ()
        for unidade in menu:
            if unidade.secoes:
                secao = unidade.secao_ativa
                if secao is None:
                    continue
                achado = _SECAO.match(limpar(secao))
                # So vale se a lista da pagina e dessa secao (nomes "U3S2 - ...").
                if achado is None or any(
                    re.match(rf"^u{achado.group(1)}s{achado.group(2)}\b", limpar(a.nome))
                    for a in atividades
                ):
                    return unidade.nome, secao
            elif aberta is not None and limpar(aberta.titulo) == limpar(unidade.nome):
                return unidade.nome, None
        return None

    def comecar_de(self, menu: tuple[Unidade, ...], unidade: str, secao: str | None) -> bool:
        """Tudo que vem ANTES do ponto escolhido e pulado; dali em diante, volta a ser conferido.

        Devolve False se nada mudou (o ponto ja era o proximo do roteiro).
        """
        antes = (frozenset(self._secoes_prontas), frozenset(self._conferidos))
        passou = False  # ja chegou no ponto escolhido?
        for item in menu:
            chave_unidade = limpar(item.nome)
            if item.secoes:
                for nome_secao in item.secoes:
                    chave = limpar(nome_secao)
                    if not passou and chave_unidade == limpar(unidade) and (
                        secao is None or chave == limpar(secao)
                    ):
                        passou = True
                    if passou:
                        self._secoes_prontas.discard(chave)
                        self._quizzes_da_secao.pop(chave, None)
                        self._conferidos = {c for c in self._conferidos if c[0] != chave}
                    else:
                        self._secoes_prontas.add(chave)
                continue
            if not passou and chave_unidade == limpar(unidade):
                passou = True
            for tipo, _, _ in QUIZZES_DO_CURSO:
                if passou:
                    self._conferidos.discard((chave_unidade, tipo))
                else:
                    self._conferidos.add((chave_unidade, tipo))
        self._tentativas.clear()
        self._atual = None
        return antes != (frozenset(self._secoes_prontas), frozenset(self._conferidos))

    # --- o que o assistente pergunta ---

    def proximo(self, menu: tuple[Unidade, ...], aberta: UnidadeAberta | None) -> Acao:
        for unidade in menu:
            if unidade.secoes:  # curso com secoes: os quizzes estao dentro de cada secao
                for secao in unidade.secoes:
                    chave_secao = limpar(secao)
                    if chave_secao in self._secoes_prontas:
                        continue
                    vistos = self._quizzes_da_secao.get(chave_secao)
                    if vistos is not None and all((chave_secao, t) in self._conferidos for t in vistos):
                        self._secoes_prontas.add(chave_secao)  # ja viu a lista: nao reabre so para conferir
                        continue
                    acao = self._trabalhar_na_secao(unidade, secao, aberta, menu)
                    if acao is not None:
                        return acao
                continue
            chave = limpar(unidade.nome)
            if all((chave, tipo) in self._conferidos for tipo, _, _ in QUIZZES_DO_CURSO):
                continue
            return self._trabalhar_na(unidade, chave, aberta, menu)
        return Concluido(f"Curso concluído: {len(menu)} unidade(s) conferida(s).")

    def pendentes(self, menu: tuple[Unidade, ...]) -> tuple[str, ...]:
        faltam: list[str] = []
        for unidade in menu:
            if unidade.secoes:
                faltam += [s for s in unidade.secoes if limpar(s) not in self._secoes_prontas]
                continue
            faltam += [
                f"{unidade.nome} ({rotulo})"
                for tipo, _, rotulo in QUIZZES_DO_CURSO
                if (limpar(unidade.nome), tipo) not in self._conferidos
            ]
        return tuple(faltam)

    # --- por dentro ---

    def _tentar(self, chave: tuple) -> bool:
        """Conta uma tentativa; False se ja passou do limite."""
        self._tentativas[chave] = self._tentativas.get(chave, 0) + 1
        return self._tentativas[chave] <= self._max

    def _trabalhar_na_secao(
        self, unidade: Unidade, secao: str, aberta: UnidadeAberta | None, menu: tuple[Unidade, ...]
    ) -> Acao | None:
        """Uma secao: abre, confere cada quiz que ela tem e a marca como pronta (devolve None)."""
        chave = limpar(secao)
        achado = _SECAO.match(chave)
        codigo = (achado.group(1), achado.group(2)) if achado else None
        atividades = aberta.atividades if aberta else ()
        # A pagina e a da secao se o menu a marca como ativa E as atividades listadas sao dela
        # (os nomes comecam com "U3S2"): protege contra ler a lista de outra pagina.
        ativa = unidade.secao_ativa is not None and limpar(unidade.secao_ativa) == chave
        dela = codigo is None or any(
            re.match(rf"^u{codigo[0]}s{codigo[1]}\b", limpar(a.nome)) for a in atividades
        )
        if not (ativa and atividades and dela):
            if not self._tentar(("secao", chave)):
                return Parar(f"Não consegui abrir a {secao}.", self.pendentes(menu))
            return AbrirSecao(secao, unidade.nome)
        self._tentativas.pop(("secao", chave), None)

        por_tipo: dict[str, list[AtividadeDoCurso]] = {}  # na ordem em que aparecem na pagina
        for atividade in atividades:
            tipo = tipo_do_quiz(atividade.nome)
            if tipo is not None and _quiz_e_desta_secao(atividade.nome, tipo, codigo):
                por_tipo.setdefault(tipo, []).append(atividade)
        self._quizzes_da_secao[chave] = list(por_tipo)
        rotulos = {tipo: rotulo for tipo, _, rotulo in TIPOS_DE_QUIZ}
        for tipo, candidatos in por_tipo.items():
            if (chave, tipo) in self._conferidos:
                continue
            if len(candidatos) > 1:  # desempata pelo icone do quiz
                candidatos = [a for a in candidatos if CLASSE_ICONE_QUIZ in a.icone.split()]
            if not candidatos:
                return Parar(f"Não achei '{rotulos[tipo]}' na {secao}.", self.pendentes(menu))
            if len(candidatos) > 1:
                return Parar(
                    f"Achei mais de um '{rotulos[tipo]}' na {secao} e não sei qual é o quiz.",
                    self.pendentes(menu),
                )
            nome = candidatos[0].nome
            if not self._tentar(("quiz", chave, tipo)):
                return Parar(f"Não consegui concluir '{nome}'.", self.pendentes(menu))
            self._atual = (chave, tipo)
            return AbrirAtividade(nome, secao)
        self._secoes_prontas.add(chave)
        return None

    def _trabalhar_na(
        self, unidade: Unidade, chave: str, aberta: UnidadeAberta | None, menu: tuple[Unidade, ...]
    ) -> Acao:
        if aberta is None or limpar(aberta.titulo) != chave:
            if not self._tentar(("unidade", chave)):
                return Parar(f"Não consegui abrir a {unidade.nome}.", self.pendentes(menu))
            return AbrirUnidade(unidade.nome)
        self._tentativas.pop(("unidade", chave), None)  # esta na unidade certa: zera a conta

        for tipo, _, rotulo in QUIZZES_DO_CURSO:
            if (chave, tipo) in self._conferidos:
                continue
            candidatos = [a for a in aberta.atividades if tipo_do_quiz(a.nome) == tipo]
            if len(candidatos) > 1:  # desempata pelo icone do quiz
                candidatos = [a for a in candidatos if CLASSE_ICONE_QUIZ in a.icone.split()]
            if not candidatos:
                return Parar(
                    f"Não achei '{rotulo}' na {unidade.nome}.", self.pendentes(menu)
                )
            if len(candidatos) > 1:  # nao sabe qual e: nao chuta
                return Parar(
                    f"Achei mais de um '{rotulo}' na {unidade.nome} e não sei qual é o quiz.",
                    self.pendentes(menu),
                )
            nome = candidatos[0].nome
            if not self._tentar(("quiz", chave, tipo)):
                return Parar(f"Não consegui concluir '{nome}'.", self.pendentes(menu))
            self._atual = (chave, tipo)
            return AbrirAtividade(nome, unidade.nome)
        # Nao deveria chegar aqui (a unidade so entra aqui se faltar algum quiz). Se chegar, para.
        return Parar(f"Estado inesperado na {unidade.nome}.", self.pendentes(menu))
