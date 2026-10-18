# ASSISTENTE - o "loop": junta tudo.
#
# AssistenteQuiz -> a cada ~1 segundo (polling):
#                   1. pede a questao ao PageReader;
#                   2. se for diferente da anterior (Question.__eq__), e questao nova;
#                   3. manda para o Solver, que devolve a Suggestion;
#                   4. entrega ao Presenter para mostrar.
#                   Guarda a ultima questao para nao consultar a IA duas vezes.