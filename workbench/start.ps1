param([switch]$NoBrowser, [switch]$Rebuild)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskUrl = 'http://127.0.0.1:8765'

Push-Location -LiteralPath $taskRoot
try {
    if (-not (Test-Path -LiteralPath $taskPython)) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
    }
    $taskRequirementFiles = @('requirements.txt', 'requirements-manufacturing.txt', 'requirements-texture.txt')
    $taskDependencyHash = ($taskRequirementFiles | ForEach-Object { (Get-FileHash -LiteralPath (Join-Path $taskRoot $_) -Algorithm SHA256).Hash }) -join ':'
    $taskDependencyStamp = Join-Path $taskRoot '.venv\.seamheal-requirements.sha256'
    $taskSavedHash = if (Test-Path -LiteralPath $taskDependencyStamp) { (Get-Content -LiteralPath $taskDependencyStamp -Raw).Trim() } else { '' }
    if ($taskSavedHash -ne $taskDependencyHash) {
        & $taskPython -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Could not install Python dependencies.' }
        Set-Content -LiteralPath $taskDependencyStamp -Value $taskDependencyHash -Encoding Ascii
    }
    if ($Rebuild -or -not (Test-Path -LiteralPath (Join-Path $taskRoot 'web\dist\index.html'))) {
        Push-Location -LiteralPath (Join-Path $taskRoot 'web')
        try {
            npm.cmd ci
            if ($LASTEXITCODE -ne 0) { throw 'Could not install web dependencies.' }
            npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw 'Could not build the workbench.' }
        } finally { Pop-Location }
    }
    $taskHealth = $null
    try { $taskHealth = Invoke-RestMethod -Uri "$taskUrl/api/health" -TimeoutSec 2 } catch {}
    if ($taskHealth -and $taskHealth.engine -eq 'local-hole-fill') {
        Write-Output "Workbench is already running: $taskUrl"
    } else {
        $taskRuntime = Join-Path $taskRoot 'runtime'
        New-Item -ItemType Directory -Path $taskRuntime -Force | Out-Null
        $taskProcess = Start-Process -FilePath $taskPython -ArgumentList @('-m','uvicorn','server:app','--host','127.0.0.1','--port','8765') -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRuntime 'server.log') -RedirectStandardError (Join-Path $taskRuntime 'server-error.log') -PassThru
        $taskReady = $false
        for ($taskAttempt=0; $taskAttempt -lt 30; $taskAttempt++) {
            Start-Sleep -Milliseconds 500
            try {
                $taskHealth = Invoke-RestMethod -Uri "$taskUrl/api/health" -TimeoutSec 2
                if ($taskHealth.engine -eq 'local-hole-fill') { $taskReady = $true; break }
            } catch {}
            if ($taskProcess.HasExited) { break }
        }
        if (-not $taskReady) { throw 'The server did not start. See runtime/server-error.log.' }
        Write-Output "Workbench started: $taskUrl"
    }
    if (-not $NoBrowser) { Start-Process -FilePath $taskUrl }
} finally { Pop-Location }
