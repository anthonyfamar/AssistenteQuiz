@echo off
rem Inicia o AssistenteQuiz: abre o Chrome do assistente (se precisar) e a janelinha.
cd /d "%~dp0"
set PYTHONPATH=src
".venv\Scripts\python.exe" -m quizbot.main
pause
