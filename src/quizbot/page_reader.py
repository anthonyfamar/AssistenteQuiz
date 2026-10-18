# PAGE READER - os "olhos": le a questao que esta na pagina.
#
# PageReader -> usa o Playwright e seletores CSS para ler o texto (DOM) da pagina.
#               SO LEITURA: a classe nao tem nenhum metodo de clicar ou enviar.
#               ler_questao() devolve uma Question, ou None se a pagina nao tiver
#               questao (login, menu), e entao o assistente fica quieto.
#
# TODO: os seletores CSS de cada site ficam no config.py.