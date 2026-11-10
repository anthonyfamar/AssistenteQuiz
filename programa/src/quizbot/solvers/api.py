# API - solver que usa uma IA por API compativel com OpenAI.
#
# ApiSolver -> um provedor (Gemini, Groq, OpenRouter ou Ollama): recebe o cliente
#              ja configurado (base_url + chave) e o modelo. Pede a resposta em JSON,
#              valida e devolve a Suggestion. Qualquer falha vira SolverError.
#              Questao com imagem usa o modelo_visao (um modelo que enxerga) e manda as
#              imagens no formato image_url; sem modelo_visao, o provedor nao as aceita.
import base64
import json
import re
import time
from dataclasses import replace

from openai import APIConnectionError, APITimeoutError, OpenAI, OpenAIError

from quizbot.models import Imagem, Question, Suggestion
from quizbot.solvers.base import Solver, SolverError

INSTRUCAO = (
    "Voce responde questoes de multipla escolha. "
    "Formulas aparecem em texto linear: x^2 e x ao quadrado, a/b e divisao, "
    "sqrt(x) e raiz quadrada. "
    "Responda SOMENTE com um JSON neste formato: "
    '{"indice": <numero da alternativa, comecando em 0>, '
    '"explicacao": "<ate 2 frases>"}. '
    "Nao escreva mais nada alem do JSON."
)


def montar_prompt(question: Question) -> str:
    linhas = [question.enunciado, ""]
    for i, alternativa in enumerate(question.alternativas):
        linhas.append(f"{i}) {alternativa}")
    if question.imagens:
        marcas = ", ".join(f"[imagem {n}]" for n in range(1, len(question.imagens) + 1))
        linhas.extend(["", f"As imagens anexas correspondem, na ordem, a {marcas}."])
    return "\n".join(linhas)


def montar_conteudo(question: Question) -> str | list[dict]:
    prompt = montar_prompt(question)
    if not question.imagens:
        return prompt
    partes: list[dict] = [{"type": "text", "text": prompt}]
    for imagem in question.imagens:
        partes.append({"type": "image_url", "image_url": {"url": _data_url(imagem)}})
    return partes


def _data_url(imagem: Imagem) -> str:
    return f"data:{imagem.tipo};base64,{base64.b64encode(imagem.dados).decode('ascii')}"


def ler_resposta(texto: str, total: int) -> Suggestion:
    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio == -1 or fim <= inicio:
        raise SolverError("a IA nao devolveu um JSON")
    try:
        dados = json.loads(texto[inicio : fim + 1])
    except json.JSONDecodeError as erro:
        raise SolverError(f"JSON invalido: {erro}") from erro

    indice = dados.get("indice")
    explicacao = dados.get("explicacao")
    if not isinstance(indice, int) or isinstance(indice, bool) or not 0 <= indice < total:
        raise SolverError(f"indice invalido: {indice!r}")
    if not isinstance(explicacao, str) or not explicacao.strip():
        raise SolverError("a IA nao deu explicacao")
    return Suggestion(indice=indice, explicacao=explicacao.strip())


def explicar_erro(erro: OpenAIError) -> str:
    """Frase curta e clara para o usuario (o que aconteceu, sem jargao)."""
    if isinstance(erro, APITimeoutError):  # subclasse de APIConnectionError: vem antes
        return "não respondeu a tempo"
    if isinstance(erro, APIConnectionError):
        return "sem conexão com o servidor"
    status = getattr(erro, "status_code", None)
    if status == 429:
        return "limite de uso (cota) atingido"
    if status in (401, 403):
        return "chave recusada"
    if status == 404:
        return "modelo não encontrado"
    if isinstance(status, int) and status >= 500:
        return f"servidor sobrecarregado ou fora do ar (erro {status})"
    if status is not None:
        return f"pedido recusado (erro {status})"
    return type(erro).__name__


def frase_curta(erro: OpenAIError) -> str:
    """O que deu errado, em poucas palavras, para completar "API do Gemini ..."."""
    if isinstance(erro, APITimeoutError):
        return "não está respondendo"
    if isinstance(erro, APIConnectionError):
        return "sem conexão"
    status = getattr(erro, "status_code", None)
    if status == 429:
        return "atingiu o limite de uso"
    if status in (401, 403):
        return "recusou a chave"
    if status == 404:
        return "não achou o modelo"
    if isinstance(status, int) and status >= 500:
        return "fora do ar"
    return "deu erro"


MAX_ESPERA_COTA = 3600.0  # mesmo que o servidor peca 8 h, o vigia olha de hora em hora


def espera_da_cota(erro: OpenAIError) -> float | None:
    """Erro 429: quantos segundos o servidor pediu para esperar (RetryInfo/retryDelay)."""
    if getattr(erro, "status_code", None) != 429:
        return None
    achado = re.search(r"retryDelay\W+(\d+(?:\.\d+)?)s", str(getattr(erro, "body", "")))
    segundos = float(achado.group(1)) if achado else 120.0  # sem informacao: 2 min
    return min(segundos, MAX_ESPERA_COTA)


def detalhar_erro(nome: str, modelo: str, segundos: float, erro: OpenAIError) -> str:
    """Tudo que o desenvolvedor precisa para entender a falha (vai so para o registro)."""
    linhas = [
        f"Provedor         : {nome}",
        f"Modelo           : {modelo}",
        f"Tempo até falhar : {segundos:.1f} s",
        f"Tipo do erro     : {type(erro).__name__}",
    ]
    status = getattr(erro, "status_code", None)
    if status is not None:
        linhas.append(f"Código HTTP      : {status}")
    corpo = getattr(erro, "body", None)
    if corpo:
        linhas.append(f"Resposta servidor: {str(corpo)[:1500]}")
    linhas.append(f"Mensagem original: {erro}")
    return "\n".join(linhas)


class ApiSolver(Solver):
    def __init__(
        self,
        nome: str,
        client: OpenAI,
        modelo: str,
        modelo_visao: str | None = None,
        max_imagens: int = 5,
        apelido: str | None = None,
    ) -> None:
        self._nome = nome
        self._apelido = apelido or nome  # nome para a janela: "Gemini", "Groq"...
        self._client = client
        self._modelo = modelo
        self._modelo_visao = modelo_visao
        self._max_imagens = max_imagens

    @property
    def nome(self) -> str:
        return self._nome

    @property
    def descricao(self) -> str:
        return f"{self._nome} ({self._modelo})"

    @property
    def aceita_imagens(self) -> bool:
        return self._modelo_visao is not None

    def _escolher_modelo(self, question: Question) -> str:
        if not question.imagens:
            return self._modelo
        if self._modelo_visao is None:
            raise SolverError(f"{self.nome}: sem modelo de visao para a imagem da questao")
        if len(question.imagens) > self._max_imagens:
            raise SolverError(f"{self.nome}: aceita no maximo {self._max_imagens} imagens por questao")
        return self._modelo_visao

    def _aviso(self, frase: str) -> str:
        return f"Algo deu errado: API do {self._apelido} {frase}."

    def sondar(self, timeout: float) -> bool:
        # Pedido minusculo so para saber se o modelo responde de novo (a lista de modelos do
        # Gemini responde mesmo quando o chat esta travado, entao tem que ser um chat de verdade).
        try:
            self._client.chat.completions.create(
                model=self._modelo,
                messages=[{"role": "user", "content": "Responda apenas: ok"}],
                timeout=timeout,
            )
        except OpenAIError:
            return False
        return True

    def solve(self, question: Question) -> Suggestion:
        return self._consultar(question, None)

    def solve_com_limite(self, question: Question, timeout: float) -> Suggestion:
        return self._consultar(question, timeout)

    def _consultar(self, question: Question, timeout: float | None) -> Suggestion:
        modelo = self._escolher_modelo(question)
        inicio = time.monotonic()
        # Sem limite proprio, vale o do cliente (TIMEOUT_API, definido na fabrica).
        extra = {} if timeout is None else {"timeout": timeout}
        try:
            resposta = self._client.chat.completions.create(
                model=modelo,
                messages=[
                    {"role": "system", "content": INSTRUCAO},
                    {"role": "user", "content": montar_conteudo(question)},
                ],
                **extra,
            )
        except OpenAIError as erro:
            raise SolverError(
                f"{self.nome}: {erro}",
                resumo=f"{self.nome} ({modelo}): {explicar_erro(erro)}.",
                detalhe=detalhar_erro(self.nome, modelo, time.monotonic() - inicio, erro),
                aviso=self._aviso(frase_curta(erro)),
                espera_sugerida=espera_da_cota(erro),
            ) from erro

        if not resposta.choices:
            raise SolverError(
                f"{self.nome}: resposta vazia",
                resumo=f"{self.nome} ({modelo}): resposta vazia.",
                detalhe=(
                    f"Provedor         : {self.nome}\nModelo           : {modelo}\n"
                    f"Resposta recebida: {resposta!r}"
                )[:2000],
                aviso=self._aviso("não respondeu nada"),
            )
        texto = resposta.choices[0].message.content or ""
        try:
            sugestao = ler_resposta(texto, len(question.alternativas))
        except SolverError as erro:
            raise SolverError(
                f"{self.nome}: {erro}",
                resumo=f"{self.nome} ({modelo}): resposta fora do formato.",
                detalhe=(
                    f"Provedor         : {self.nome}\nModelo           : {modelo}\n"
                    f"Problema         : {erro}\n"
                    f"A IA devolveu    : {texto[:1500]!r}"
                ),
                aviso=self._aviso("respondeu num formato errado"),
            ) from erro
        return replace(sugestao, origem=f"{self.nome} ({modelo})")
