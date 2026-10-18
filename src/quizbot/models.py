# MODELS - os "dados" do projeto.
#
# Question   -> guarda o enunciado e as alternativas da questao lida na tela.
#               E um dataclass imutavel (frozen), entao nao muda depois de criado.
#               O __eq__ gerado e como o assistente percebe que a questao mudou.
# Suggestion -> guarda a resposta sugerida pela IA: o indice da alternativa
#               + uma explicacao curta.

@dataclass(frozen=True)
class Question:
    enunciado: str
    alternativas: tuple[str, str, str, str, str]

@dataclass(frozen=True)
class Suggestion:
    indice: int
    explicacao: str