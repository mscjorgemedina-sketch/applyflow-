# ApplyFlow v5 — Preparar sesión (v2)
# Abre Chrome en la pantalla de login de ChileTrabajos y en chrome://extensions.
# Uso: .\1-preparar-sesion.ps1 [-EsperarSeg 600]

param(
    [int]$EsperarSeg = 0    # >0: espera N s después de abrir (para automatizar)
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$extDir = Join-Path $root "extension_v2"
$loginUrl = "https://www.chiletrabajos.cl/chtlogin"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " ApplyFlow v5 - Preparar sesion" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path (Join-Path $extDir "manifest.json"))) {
    Write-Host "ERROR: no encuentro la extension en:" -ForegroundColor Red
    Write-Host "  $extDir"
    exit 1
}

$chromeCandidates = @(
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
    (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
) | Where-Object { $_ -and (Test-Path $_) }

$chrome = $chromeCandidates | Select-Object -First 1

if (-not $chrome) {
    Write-Host "No encontre Chrome. Abre manualmente:" -ForegroundColor Yellow
    Write-Host "  1) chrome://extensions"
    Write-Host "  2) $loginUrl"
} else {
    try {
        Start-Process -FilePath $chrome -ArgumentList "chrome://extensions/"
    } catch {
        Write-Host "Abre manualmente: chrome://extensions" -ForegroundColor Yellow
    }
    Start-Sleep -Milliseconds 700
    try {
        Start-Process -FilePath $chrome -ArgumentList $loginUrl
    } catch {
        Write-Host "Abre manualmente: $loginUrl" -ForegroundColor Yellow
    }
}

Write-Host "Checklist (una sola vez):" -ForegroundColor Green
Write-Host "  1. En chrome://extensions activa 'Modo de desarrollador'."
Write-Host "  2. Pulsa 'Cargar descomprimida' y elige esta carpeta:"
Write-Host "       $extDir" -ForegroundColor White
Write-Host "  3. Si ya estaba cargada y cambiamos archivos, pulsa el boton de recarga (flecha circular)."
Write-Host "  4. En ChileTrabajos inicia sesion. Cuando veas tu nombre, la sesion esta lista."
Write-Host ""
Write-Host "Luego ejecuta:" -ForegroundColor Green
Write-Host "  .\2-arrancar-postulaciones.ps1" -ForegroundColor White
Write-Host ""

if ($EsperarSeg -gt 0) {
    Write-Host "Esperando tu login (max $EsperarSeg s; Ctrl+C corta la espera)..." -ForegroundColor Cyan
    $fin = (Get-Date).AddSeconds($EsperarSeg)
    while ((Get-Date) -lt $fin) {
        Start-Sleep -Seconds 5
        $resta = [int]($fin - (Get-Date)).TotalSeconds
        Write-Host ("  ... esperando sesion ({0} s restantes). Al terminar, corre el comando 2." -f $resta) -ForegroundColor DarkGray
    }
    Write-Host "Tiempo de espera agotado. Continua cuando estes logueado corriendo el comando 2." -ForegroundColor Yellow
}
