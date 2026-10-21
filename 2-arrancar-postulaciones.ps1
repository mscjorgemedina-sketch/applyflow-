param(
    [string]$Perfil = "",
    [int]$Objetivo = 100,
    [int]$Dias = 14,
    [int]$MinScore = 70,
    [switch]$DryRun,
    [switch]$NoBuscar,
    [switch]$Refill,
    [switch]$SinLLM,
    [switch]$Rapido,
    [switch]$Entrenar,
    [switch]$AbrirDashboard
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$orch = Join-Path $root "orquestador.py"
$profilesDir = Join-Path $root "perfiles"

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = "utf-8"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " ApplyFlow v5 - Arrancar postulaciones" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $orch)) {
    Write-Host "ERROR: no encuentro $orch" -ForegroundColor Red
    exit 1
}

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) {
    Write-Host "ERROR: Python no esta instalado o no esta en el PATH." -ForegroundColor Red
    exit 1
}

# --- Guardian: el receiver v5 debe estar en 8766 (la extension lo usa).
# Se levanta en background si no responde; cero preguntar, cero detenerse.
$receiverScript = Join-Path $root "tools\receiver.py"
try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:8766/health" -TimeoutSec 2
    Write-Host "Receiver v5: activo (127.0.0.1:8766)" -ForegroundColor DarkGray
} catch {
    if (-not (Test-Path $receiverScript)) {
        Write-Host "AVISO: no existe tools\receiver.py; la extension no tendra respuestas." -ForegroundColor Yellow
    } else {
        Write-Host "Receiver no responde; levantandolo en background..." -ForegroundColor Yellow
        try {
            Start-Process -FilePath $py.Source -ArgumentList "`"$receiverScript`"" -WindowStyle Hidden -WorkingDirectory $root | Out-Null
            Start-Sleep -Seconds 2
            $null = Invoke-RestMethod -Uri "http://127.0.0.1:8766/health" -TimeoutSec 3
            Write-Host "Receiver v5: levantado OK" -ForegroundColor Green
        } catch {
            Write-Host "AVISO: no pude levantar el receiver (se seguira sin el; revisar a mano luego): $_" -ForegroundColor Yellow
        }
    }
}

if (-not $Perfil) {
    $available = @()
    if (Test-Path $profilesDir) {
        $available = Get-ChildItem $profilesDir -Directory | Select-Object -ExpandProperty Name
    }
    if ($available.Count -gt 0) {
        Write-Host "Perfiles disponibles: $($available -join ', ')"
    } else {
        Write-Host "No hay perfiles en $profilesDir" -ForegroundColor Yellow
    }
    $default = if ($available -contains "Jorge") { "Jorge" } elseif ($available.Count -gt 0) { $available[0] } else { "Jorge" }
    try {
        $entry = Read-Host "Nombre del perfil [$default]"
    } catch {
        # Modo no interactivo (automatizado): usa el perfil por defecto.
        Write-Host "Modo no interactivo: uso el perfil '$default'." -ForegroundColor Yellow
        $entry = ""
    }
    if ([string]::IsNullOrWhiteSpace($entry)) { $Perfil = $default } else { $Perfil = $entry.Trim() }
}

$profileDir = Join-Path $profilesDir $Perfil
if (-not (Test-Path $profileDir)) {
    Write-Host "ERROR: no existe el perfil '$Perfil' en $profilesDir" -ForegroundColor Red
    Write-Host "Crea la carpeta con tu CV o ejecuta con -Entrenar." -ForegroundColor Yellow
    exit 1
}

$cv = Get-ChildItem $profileDir -Filter *.pdf -File -ErrorAction SilentlyContinue | Select-Object -First 1
if ($cv) {
    Write-Host "Perfil: $Perfil" -ForegroundColor Green
    Write-Host "CV:     $($cv.FullName)" -ForegroundColor Green
} else {
    Write-Host "Perfil: $Perfil" -ForegroundColor Green
    Write-Host "AVISO: no hay PDF en $profileDir. Podras adjuntarlo manualmente al enviar." -ForegroundColor Yellow
}
Write-Host ""

$argsList = @(
    $orch,
    "--perfil", $Perfil,
    "--objetivo", "$Objetivo",
    "--dias", "$Dias",
    "--min-score", "$MinScore"
)
if ($DryRun) { $argsList += "--dry-run" }
if ($NoBuscar) { $argsList += "--no-buscar" }
if ($Refill) { $argsList += "--refill" }
if ($SinLLM) { $argsList += "--sin-llm" }
if ($Rapido) { $argsList += "--rapido" }
if ($Entrenar) { $argsList += "--entrenar" }
if ($AbrirDashboard) { $argsList += "--abrir-dashboard" }

& $py.Source @argsList
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 3) {
    Write-Host "La sesion expiro. Ejecuta .\1-preparar-sesion.ps1 y vuelve a intentar." -ForegroundColor Yellow
} elseif ($code -eq 2) {
    Write-Host "No hubo ofertas para el filtro actual. Prueba:" -ForegroundColor Yellow
    Write-Host "  .\2-arrancar-postulaciones.ps1 -Dias 21 -MinScore 60"
} elseif ($code -ne 0) {
    Write-Host "El flujo termino con codigo $code. Revisa los mensajes de arriba." -ForegroundColor Yellow
}

exit $code
