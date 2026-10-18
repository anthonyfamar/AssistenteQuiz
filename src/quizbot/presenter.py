# PRESENTER - define ONDE a sugestao aparece para o usuario.
#
# Presenter (classe abstrata) -> contrato: mostrar(question, suggestion).
# TerminalPresenter           -> imprime no terminal do VS Code (primeiro).
# JanelaPresenter (depois)    -> janelinha sempre visivel com tkinter (opcional).
#                                Trocar de um para o outro e so trocar a classe.
from abc import ABC, abstractmethod
from string import ascii_uppercase
from quizbot.models import Question, Suggestion


class Presenter(ABC):
    @abstractmethod
    def mostrar(self, question: Question, suggestion: Suggestion) -> None:
        ...

class TerminalPresenter(Presenter):
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