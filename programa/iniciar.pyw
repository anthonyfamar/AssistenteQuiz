# INICIAR.PYW - abre o AssistenteQuiz SEM a janela preta.
#
# O atalho "AssistenteQuiz" abre este arquivo com o pythonw.exe (o Python sem terminal).
# O que o programa conta vai para o registro (assistente.log); veja quizbot/registro.py.
# Para ver as mensagens ao vivo num terminal, rode pelo terminal (veja o topo do main.py).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from quizbot.main import main  # noqa: E402

main()
