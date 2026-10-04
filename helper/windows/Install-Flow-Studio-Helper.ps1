$ErrorActionPreference = "Stop"

$installRoot = Join-Path $env:LOCALAPPDATA "FlowStudioWebHelper"
$processorRoot = Join-Path $installRoot "processor-v12"
$dataRoot = Join-Path $installRoot "data"
$logRoot = Join-Path $installRoot "logs"
$sourceRoot = Join-Path $PSScriptRoot "processor"
$exe = Join-Path $processorRoot "flow-local-processor.exe"
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "Flow Studio Helper.lnk"

if (-not (Test-Path (Join-Path $sourceRoot "flow-local-processor.exe"))) {
  throw "Khong tim thay Flow Studio Helper trong goi cai dat. Hay giai nen toan bo file ZIP roi chay lai."
}

Write-Host "Dang cai Flow Studio Helper cho Windows..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $installRoot, $dataRoot, $logRoot | Out-Null

# Stop only older Helper processes installed by this package. No admin rights
# are needed because the process belongs to the current Windows user.
Get-CimInstance Win32_Process -Filter "Name='flow-local-processor.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.ExecutablePath -like "$installRoot*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

if (Test-Path $processorRoot) { Remove-Item -Recurse -Force $processorRoot }
Copy-Item -Recurse -Force $sourceRoot $processorRoot
Get-ChildItem -Recurse $processorRoot | Unblock-File

$arguments = "--port 43127 --data-dir `"$dataRoot`""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exe
$shortcut.Arguments = $arguments
$shortcut.WorkingDirectory = $processorRoot
$shortcut.WindowStyle = 7
$shortcut.Description = "Flow Studio resize and Google Drive helper"
$shortcut.Save()

Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $processorRoot -WindowStyle Hidden

$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
  try {
    Invoke-RestMethod -Uri "http://127.0.0.1:43127/session" -Headers @{ Origin = "https://flow-studio-web-one.vercel.app" } -TimeoutSec 2 | Out-Null
    $ready = $true
    break
  } catch {
    Start-Sleep -Seconds 1
  }
}

if (-not $ready) {
  throw "Da cai Helper nhung chua khoi dong duoc. Hay khoi dong lai Windows va bam Kiem tra lai tren Studio Web."
}

Write-Host ""
Write-Host "Da cai xong Flow Studio Helper." -ForegroundColor Green
Write-Host "Quay lai Studio Web va bam Kiem tra lai."
Write-Host "Helper se tu chay khi ban dang nhap Windows."
Read-Host "Nhan Enter de dong"
