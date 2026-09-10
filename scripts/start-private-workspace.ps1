param(
    [string]$PythonExecutable = 'python',
    [string]$Warehouse = '',
    [int]$Port = 4789
)
$ErrorActionPreference = 'Stop'
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Open the existing service or choose another port."
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$privateRoot = Join-Path $projectRoot 'warehouse\private\workspace'
New-Item -ItemType Directory -Path $privateRoot -Force | Out-Null
if (-not $Warehouse) {
    $latest = Get-ChildItem -LiteralPath (Join-Path $projectRoot 'warehouse\nationwide\curated') -Filter '*.acceptance.json' |
        Sort-Object LastWriteTime -Descending | Where-Object { (Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json).status -eq 'VERIFIED' } | Select-Object -First 1
    if ($latest) { $Warehouse = $latest.FullName.Replace('.acceptance.json', '.duckdb') }
}
$serviceScript = Join-Path $PSScriptRoot 'private_workspace.py'
$env:PYTHONUTF8 = '1'
$runtimeFolder = Join-Path $projectRoot 'outputs\nationwide-runtime'
if (Test-Path -LiteralPath $runtimeFolder) { $env:PYTHONPATH = $runtimeFolder }
$serviceArguments = @('"' + $serviceScript + '"', '--port', $Port, '--data', '"' + $privateRoot + '"')
if ($Warehouse) { $serviceArguments += @('--warehouse', '"' + $Warehouse + '"') }
$process = Start-Process -FilePath $PythonExecutable -ArgumentList $serviceArguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $privateRoot 'service.log') -RedirectStandardError (Join-Path $privateRoot 'service.err')
$process.Id | Set-Content -LiteralPath (Join-Path $privateRoot 'service.pid')
Write-Output "Local workspace starting at http://127.0.0.1:$Port/ (process $($process.Id)). Set up your owner password in the browser."
