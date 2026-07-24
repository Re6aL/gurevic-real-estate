$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$port = 8768
$url = "http://localhost:$port/"

$python = Get-Command py -ErrorAction SilentlyContinue
$pythonPath = if ($python) { $python.Source } else { $null }
$pythonArgs = @("-3", "-m", "http.server", "$port", "--directory", $projectRoot)

if (-not $python) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    $pythonPath = if ($python) { $python.Source } else { $null }
    $pythonArgs = @("-m", "http.server", "$port", "--directory", $projectRoot)
}

if (-not $pythonPath) {
    $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $codexPython) {
        $pythonPath = $codexPython
        $pythonArgs = @("-m", "http.server", "$port", "--directory", $projectRoot)
    }
}

if (-not $pythonPath) {
    Write-Host "Python was not found." -ForegroundColor Red
    Write-Host "Install Python from python.org and enable Add Python to PATH."
    exit 1
}

try {
    $server = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList $pythonArgs `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru

    Start-Sleep -Seconds 1
    if ($server.HasExited) {
        throw "The local server did not start. Port $port may already be in use."
    }

    Start-Process $url
    Write-Host ""
    Write-Host "Site preview opened: $url" -ForegroundColor Green
    Write-Host "After editing files, refresh the browser page with Ctrl+R."
    Write-Host "Press Enter to stop the local server."
    Read-Host | Out-Null
}
finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id
    }
}
