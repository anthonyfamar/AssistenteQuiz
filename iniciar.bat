@echo off
rem Inicia o AssistenteQuiz: abre o navegador do assistente (se precisar) e a janelinha.
cd /d "%~dp0"
rem Usa a .venv da pasta (quem instalou na mao) ou o ambiente criado pelo 1-INSTALAR.bat.
set "PY=%LOCALAPPDATA%\AssistenteQuiz\venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" echo O AssistenteQuiz ainda nao foi instalado. De dois cliques em 1-INSTALAR.bat primeiro.
if not exist "%PY%" pause
if not exist "%PY%" exit /b 1
set PYTHONPATH=src
if not exist ".env" echo Primeira vez: vamos configurar a sua chave.
if not exist ".env" "%PY%" -m quizbot.configurar
"%PY%" -m quizbot.main
if errorlevel 1 pause
