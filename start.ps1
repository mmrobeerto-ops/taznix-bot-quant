$ErrorActionPreference = "SilentlyContinue"

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "   Iniciando SFA-IFA Pro HFT Motor..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[*] Comprobando disponibilidad del puerto 8080..." -ForegroundColor Yellow
$pid_to_kill = (Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue).OwningProcess

if ($pid_to_kill) {
    Write-Host "[!] Puerto 8080 ocupado por el proceso PID: $pid_to_kill." -ForegroundColor Red
    Write-Host "[*] Destruyendo proceso para liberar el puerto..." -ForegroundColor Yellow
    Stop-Process -Id $pid_to_kill -Force
    Start-Sleep -Seconds 2
    Write-Host "[+] Puerto liberado exitosamente." -ForegroundColor Green
} else {
    Write-Host "[+] El puerto 8080 está libre." -ForegroundColor Green
}

Write-Host "[*] Ejecutando el motor en Python..." -ForegroundColor Yellow
Write-Host "-----------------------------------------" -ForegroundColor Cyan
python run.py
