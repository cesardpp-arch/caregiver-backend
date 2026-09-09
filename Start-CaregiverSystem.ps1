param(
    [switch]$DryRun
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPython = Join-Path $root '.venv\Scripts\python.exe'
$backendArgs = @('-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000')
$frontendWorkingDir = Join-Path (Split-Path -Parent $root) 'frontend'
$frontendArgs = @('run', 'dev', '--', '--port', '5174', '--strictPort')

if ($DryRun) {
    Write-Host "Backend: $backendPython $($backendArgs -join ' ')"
    Write-Host "Frontend: npm $($frontendArgs -join ' ')"
    exit 0
}

if (-not (Test-Path $backendPython)) {
    throw "Backend Python not found at $backendPython"
}

if (-not (Test-Path $frontendWorkingDir)) {
    throw "Frontend folder not found at $frontendWorkingDir"
}

Start-Process -FilePath $backendPython -WorkingDirectory $root -ArgumentList $backendArgs -WindowStyle Normal
Start-Process -FilePath 'npm.cmd' -WorkingDirectory $frontendWorkingDir -ArgumentList $frontendArgs -WindowStyle Normal