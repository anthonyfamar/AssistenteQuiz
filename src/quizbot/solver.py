# SOLVER - o "cerebro": define QUEM responde as questoes.
#
# Solver (classe abstrata) -> contrato: todo solver tem solve(question) -> Suggestion.
#                             O AssistenteQuiz recebe "um Solver" sem saber qual e.
# FakeSolver               -> devolve uma resposta fixa, serve para testar sem gastar API.
# ApiSolver (depois)       -> usa uma IA gratuita configuravel (Gemini, Groq, OpenRouter
#                             ou Ollama): base_url, chave e modelo.
#
# Quando o ApiSolver chegar, este arquivo pode virar a pasta solvers/ (base, fake, api).