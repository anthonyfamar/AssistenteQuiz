# PRESENTER - define ONDE a sugestao aparece para o usuario.
#
# Presenter (classe abstrata) -> contrato: mostrar(question, suggestion).
#                                Opcionais: consultando() (a IA esta pensando) e
#                                avisar(mensagem) (erros e avisos; padrao: imprime) e
#                                erro_inesperado(pasta_log) (algo quebrou; os detalhes
#                                estao no registro, na pasta indicada) e
#                                problemas_nos_provedores(lista) (avisos das falhas da
#                                ultima consulta; a janela mostra e apaga sozinha) e
#                                perguntar_outra_materia() -> bool (terminou o curso:
#                                continuar com outra materia ou encerrar; espera a resposta),
#                                oferecer_tentar_de_novo(msg, tentar) (a acao falhou: mantem a
#                                sugestao na tela e oferece "Tentar de novo") e
#                                chamar_atencao() (traz a janela para a frente se minimizada).
# TerminalPresenter           -> imprime no terminal.
# JanelaPresenter (janela.py) -> janelinha sempre visivel com tkinter.
#                                Trocar de um para o outro e so trocar a classe.
from abc import ABC, abstractmethod
from collections.abc import Callable
from string import ascii_uppercase
from quizbot.models import Question, Suggestion


class Presenter(ABC):
    @abstractmethod
    def mostrar(self, question: Question, suggestion: Suggestion) -> None:
        ...

    def consultando(self) -> None:
        """Questao nova detectada, a IA esta sendo consultada. Opcional."""

    def avisar(self, mensagem: str) -> None:
        print(f"[aviso] {mensagem}")

    def erro_inesperado(self, pasta_log: str) -> None:
        self.avisar(f"Algo deu errado. Os detalhes estao em: {pasta_log}")

    def problemas_nos_provedores(self, problemas: list[str]) -> None:
        """Avisos curtos das falhas de IA da ultima consulta (lista vazia = nada a mostrar). Opcional."""

    def oferecer_tentar_de_novo(self, mensagem: str, tentar: Callable[[], None]) -> None:
        """Marcar/avancar/obter a sugestao falhou. Mostra a mensagem SEM apagar a sugestao que ja
        esta na tela, mais um botao "Tentar de novo" que chama tentar(). Opcional: o padrao so avisa."""
        self.avisar(mensagem)

    def chamar_atencao(self) -> None:
        """O programa precisa de quem esta usando agora (parou, pergunta): traz a janela para a
        frente se estiver minimizada. Opcional."""

    def perguntar_outra_materia(self, esperar: Callable[[float], bool] | None = None) -> bool:
        """Terminou o curso: quem esta usando quer conferir OUTRA materia? Espera a resposta.

        True = continuar (o programa espera a outra materia ser aberta e recomeca);
        False = encerrar. Opcional: sem como perguntar, o padrao e encerrar.
        `esperar(segundos)` e a espera do assistente, em que o navegador continua sendo atendido:
        use-a (em vez de dormir parado) enquanto aguarda a resposta.
        """
        return False


class TerminalPresenter(Presenter):
    def perguntar_outra_materia(self, esperar: Callable[[float], bool] | None = None) -> bool:
        return input("Curso concluído. Conferir outra matéria? (s/n): ").strip().lower().startswith("s")

    def mostrar(self, question: Question, suggestion: Suggestion) -> None:
        print("=" * 60)
        print(question.enunciado)
        print()
        for i, alternativa in enumerate(question.alternativas):
            marca = " <-- sugestão" if i == suggestion.indice else ""
            print(f"{ascii_uppercase[i]}. {alternativa}{marca}")
        print()
        print(f"Sugestão: alternativa {ascii_uppercase[suggestion.indice]}")
        print(f"Por quê: {suggestion.explicacao}")
        if suggestion.origem:
            print(f"Respondido por: {suggestion.origem}")
        print("=" * 60)