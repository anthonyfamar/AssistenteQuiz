# AssistenteQuiz - instalador para Windows 10/11.
#
# Faz tudo sozinho, sem precisar de Python, IDE ou git no computador:
#   1. procura um Python (3.10 ou mais novo); se nao houver, baixa o instalador OFICIAL do
#      python.org, confere a assinatura digital e instala so para este programa
#      (sem administrador, sem mexer no PATH, numa pasta propria);
#   2. cria o ambiente do programa e instala os componentes. O ambiente fica numa pasta
#      CURTA (AppData\Local\AssistenteQuiz\venv) porque o Windows nao aceita caminhos
#      com mais de 260 caracteres e o Playwright tem pastas muito fundas: dentro de uma
#      pasta de projeto comprida (OneDrive, Downloads dentro de Downloads...) falharia;
#   3. abre a janela de configuracao (chaves de IA);
#   4. cria os atalhos na area de trabalho.
# Pode ser executado de novo sem problema.
#
# Parametros (so para testes): -PastaPython, -PastaVenv, -PastaAtalhos,
# -ForcarPythonPrivado, -SemConfig, -SemAtalhos.
param(
    [string]$PastaPython = (Join-Path $env:LOCALAPPDATA "AssistenteQuiz\python"),
    [string]$PastaVenv = (Join-Path $env:LOCALAPPDATA "AssistenteQuiz\venv"),
    [string]$PastaAtalhos = [Environment]::GetFolderPath("Desktop"),
    [switch]$ForcarPythonPrivado,
    [switch]$SemConfig,
    [switch]$SemAtalhos
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$VersaoPython = "3.13.16"
$UrlPython = "https://www.python.org/ftp/python/$VersaoPython/python-$VersaoPython-amd64.exe"
$Projeto = $PSScriptRoot

function Passo($texto) {
    Write-Host ""
    Write-Host "==> $texto" -ForegroundColor Cyan
}

function Falhar($texto) {
    Write-Host ""
    Write-Host "PROBLEMA: $texto" -ForegroundColor Red
    exit 1
}

function Test-Python($caminho) {
    try {
        & $caminho -c "import sys, tkinter, venv; sys.exit(0 if sys.version_info >= (3, 10) else 1)" | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Find-Python {
    $candidatos = @()
    $privado = Join-Path $PastaPython "python.exe"
    if (Test-Path $privado) { $candidatos += $privado }
    if (-not $ForcarPythonPrivado) {
        foreach ($nome in "python", "py") {
            $comando = Get-Command $nome -ErrorAction SilentlyContinue
            # O "python.exe" da pasta WindowsApps e so um atalho para a Microsoft Store.
            if ($comando -and $comando.Source -notmatch "WindowsApps") { $candidatos += $comando.Source }
        }
    }
    foreach ($c in $candidatos) {
        if (Test-Python $c) { return $c }
    }
    return $null
}

function Install-Python {
    if (-not [Environment]::Is64BitOperatingSystem) {
        Falhar "Este instalador precisa do Windows de 64 bits."
    }
    $instalador = Join-Path $env:TEMP "python-$VersaoPython-amd64.exe"

    Passo "Baixando o Python $VersaoPython (cerca de 25 MB)..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    try {
        Invoke-WebRequest -Uri $UrlPython -OutFile $instalador -UseBasicParsing
    } catch {
        Falhar "Não consegui baixar o Python. Confira a internet e tente de novo."
    }

    $assinatura = Get-AuthenticodeSignature $instalador
    $assinadoPelaPSF = $assinatura.Status -eq "Valid" -and $assinatura.SignerCertificate.Subject -match "Python Software Foundation"
    if (-not $assinadoPelaPSF) {
        Remove-Item $instalador -Force -ErrorAction SilentlyContinue
        Falhar "O arquivo baixado não tem a assinatura oficial do Python. Por segurança, a instalação foi cancelada."
    }
    Write-Host "Assinatura digital conferida (Python Software Foundation)."

    Passo "Instalando o Python só para este programa (não mexe no resto do computador)..."
    $argumentos = 'InstallAllUsers=0 PrependPath=0 Include_launcher=0 AssociateFiles=0 Shortcuts=0 ' +
        'Include_test=0 Include_doc=0 Include_tcltk=1 /quiet TargetDir="' + $PastaPython + '"'
    $processo = Start-Process -FilePath $instalador -ArgumentList $argumentos -Wait -PassThru
    if ($processo.ExitCode -ne 0 -or -not (Test-Path (Join-Path $PastaPython "python.exe"))) {
        Falhar "A instalação do Python não terminou (código $($processo.ExitCode))."
    }
}

function New-Atalho($nome, $alvo, $descricao) {
    $shell = New-Object -ComObject WScript.Shell
    $atalho = $shell.CreateShortcut((Join-Path $PastaAtalhos "$nome.lnk"))
    $atalho.TargetPath = $alvo
    $atalho.WorkingDirectory = $Projeto
    $atalho.Description = $descricao
    $atalho.WindowStyle = 7   # janela de texto minimizada (a janelinha do programa aparece normalmente)
    $atalho.Save()
    Write-Host "Atalho criado: $nome"
}

Write-Host "=== Instalador do AssistenteQuiz ===" -ForegroundColor Green
Write-Host "Pasta do programa: $Projeto"

# 1. Python
Passo "Procurando o Python..."
$python = Find-Python
if ($null -eq $python) {
    Write-Host "Nenhum Python utilizável foi encontrado. Vou instalar um só para este programa."
    Install-Python
    $python = Find-Python
    if ($null -eq $python) { Falhar "Instalei o Python, mas não consegui usá-lo." }
}
Write-Host "Usando: $python"

# 2. Ambiente e componentes
$pythonVenv = Join-Path $PastaVenv "Scripts\python.exe"
if ((Test-Path $pythonVenv) -and -not (Test-Python $pythonVenv)) {
    Write-Host "O ambiente anterior está quebrado. Vou recriá-lo."
    Remove-Item $PastaVenv -Recurse -Force
}
if (-not (Test-Path $pythonVenv)) {
    Passo "Criando o ambiente do programa..."
    & $python -m venv $PastaVenv
    if ($LASTEXITCODE -ne 0) { Falhar "Não consegui criar o ambiente do programa." }
}

Passo "Instalando os componentes (pode levar alguns minutos)..."
& $pythonVenv -m pip install --disable-pip-version-check -r (Join-Path $Projeto "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Falhar "Não consegui instalar os componentes. Confira a internet e tente de novo. A mensagem em vermelho acima diz o que aconteceu."
}

# 3. Configuracao
$env:PYTHONPATH = Join-Path $Projeto "src"
if (-not $SemConfig) {
    Passo "Abrindo a janela de configuração..."
    Write-Host "Cole a sua chave de IA na janela que vai abrir e clique em Salvar."
    & $pythonVenv -m quizbot.configurar
    if (-not (Test-Path (Join-Path $Projeto ".env"))) {
        Write-Host ""
        Write-Host "A configuração não foi salva. Depois de instalar, abra 'AssistenteQuiz - Configuração' para colar a chave." -ForegroundColor Yellow
    }
}

# 4. Atalhos
if (-not $SemAtalhos) {
    Passo "Criando os atalhos na área de trabalho..."
    New-Atalho "AssistenteQuiz" (Join-Path $Projeto "iniciar.bat") "Abre o AssistenteQuiz"
    New-Atalho "AssistenteQuiz - Configuracao" (Join-Path $Projeto "configurar.bat") "Colar ou trocar as chaves de IA"
}

Write-Host ""
Write-Host "Tudo pronto! Para usar, dê dois cliques no atalho 'AssistenteQuiz' na área de trabalho." -ForegroundColor Green
