# API - solver que usa uma IA por API compativel com OpenAI.
#
# ApiSolver -> um provedor (Gemini, Groq, OpenRouter ou Ollama): recebe o cliente
#              ja configurado (base_url + chave) e o modelo. Pede a resposta em JSON,
#              valida e devolve a Suggestion. Qualquer falha vira SolverError.
#              Questao com imagem usa o modelo_visao (um modelo que enxerga) e manda as
#              imagens no formato image_url; sem modelo_visao, o provedor nao as aceita.
import base64
import json
from dataclasses import replace

from openai import OpenAI, OpenAIError

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


class ApiSolver(Solver):
    def __init__(
        self,
        nome: str,
        client: OpenAI,
        modelo: str,
        modelo_visao: str | None = None,
        max_imagens: int = 5,
    ) -> None:
        self._nome = nome
        self._client = client
        self._modelo = modelo
        self._modelo_visao = modelo_visao
        self._max_imagens = max_imagens

    @property
    def nome(self) -> str:
        return self._nome

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

    def solve(self, question: Question) -> Suggestion:
        modelo = self._escolher_modelo(question)
        try:
            resposta = self._client.chat.completions.create(
                model=modelo,
                messages=[
                    {"role": "system", "content": INSTRUCAO},
                    {"role": "user", "content": montar_conteudo(question)},
                ],
            )
        except OpenAIError as erro:
            raise SolverError(f"{self.nome}: {erro}") from erro

        if not resposta.choices:
            raise SolverError(f"{self.nome}: resposta vazia")
        texto = resposta.choices[0].message.content or ""
        try:
            sugestao = ler_resposta(texto, len(question.alternativas))
        except SolverError as erro:
            raise SolverError(f"{self.nome}: {erro}") from erro
        return replace(sugestao, origem=self.nome)
