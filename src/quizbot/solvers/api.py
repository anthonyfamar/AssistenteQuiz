# API - solver que usa uma IA por API compativel com OpenAI.
#
# ApiSolver -> um provedor (Gemini, Groq, OpenRouter ou Ollama): recebe o cliente
#              ja configurado (base_url + chave) e o modelo. Pede a resposta em JSON,
#              valida e devolve a Suggestion. Qualquer falha vira SolverError.
import json
from dataclasses import replace

from openai import OpenAI, OpenAIError

from quizbot.models import Question, Suggestion
from quizbot.solvers.base import Solver, SolverError

INSTRUCAO = (
    "Voce responde questoes de multipla escolha. "
    "Responda SOMENTE com um JSON neste formato: "
    '{"indice": <numero da alternativa, comecando em 0>, '
    '"explicacao": "<ate 2 frases>"}. '
    "Nao escreva mais nada alem do JSON."
)


def montar_prompt(question: Question) -> str:
    linhas = [question.enunciado, ""]
    for i, alternativa in enumerate(question.alternativas):
        linhas.append(f"{i}) {alternativa}")
    return "\n".join(linhas)


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
    def __init__(self, nome: str, client: OpenAI, modelo: str) -> None:
        self._nome = nome
        self._client = client
        self._modelo = modelo

    @property
    def nome(self) -> str:
        return self._nome

    def solve(self, question: Question) -> Suggestion:
        try:
            resposta = self._client.chat.completions.create(
                model=self._modelo,
                messages=[
                    {"role": "system", "content": INSTRUCAO},
                    {"role": "user", "content": montar_prompt(question)},
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
