param([string]$Python='python',[int]$Port=8008,[switch]$Install,[switch]$SeedDemo)
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
if ($Install) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    & ./.venv/Scripts/python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
if (Test-Path ./.venv/Scripts/python.exe) { $Python=(Resolve-Path ./.venv/Scripts/python.exe).Path }
$env:DEBUG='1'
$env:PYTHONUTF8='1'
$env:PUBLIC_BASE_URL="http://127.0.0.1:$Port"
if (-not $env:SECRET_KEY) {
    $localConfig=Join-Path $PSScriptRoot '.local-secrets.json'
    if (Test-Path -LiteralPath $localConfig) { $localSecrets=Get-Content -LiteralPath $localConfig -Raw | ConvertFrom-Json }
    else {
        $generated=& $Python -c "import json,secrets;from cryptography.fernet import Fernet;print(json.dumps({'SECRET_KEY':secrets.token_urlsafe(48),'GATEWAY_ENCRYPTION_KEY':Fernet.generate_key().decode()}))"
        if ($LASTEXITCODE -ne 0) { throw 'Install the project dependencies first: ./start.ps1 -Install' }
        Set-Content -LiteralPath $localConfig -Value $generated
        $localSecrets=$generated | ConvertFrom-Json
    }
    $env:SECRET_KEY=$localSecrets.SECRET_KEY
    $env:GATEWAY_ENCRYPTION_KEY=$localSecrets.GATEWAY_ENCRYPTION_KEY
}
& $Python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
if ($SeedDemo) {
    if (-not $env:DEMO_PASSWORD) { throw 'Set DEMO_PASSWORD before using -SeedDemo.' }
    & $Python manage.py seed_demo
    if ($LASTEXITCODE -ne 0) { throw 'Demo setup failed.' }
}
$notificationWorker=Start-Process -FilePath $Python -ArgumentList @('manage.py','dispatch_notifications','--watch') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot '.notifications.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot '.notifications.stderr.log')
try { & $Python manage.py runserver "127.0.0.1:$Port" }
finally { if ($notificationWorker -and -not $notificationWorker.HasExited) { Stop-Process -Id $notificationWorker.Id } }
