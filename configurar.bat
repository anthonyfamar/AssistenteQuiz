@echo off
rem Abre a janela para colar ou trocar as chaves de IA.
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\AssistenteQuiz\venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" echo O AssistenteQuiz ainda nao foi instalado. De dois cliques em 1-INSTALAR.bat primeiro.
if not exist "%PY%" pause
if not exist "%PY%" exit /b 1
set PYTHONPATH=src
"%PY%" -m quizbot.configurar
