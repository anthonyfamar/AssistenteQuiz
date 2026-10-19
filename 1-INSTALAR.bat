@echo off
rem Instala o AssistenteQuiz. Nao precisa ter Python nem nada instalado: o instalador cuida de tudo.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0programa\instalar.ps1"
echo.
pause
