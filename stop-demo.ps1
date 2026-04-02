[CmdletBinding()]
param(
  [switch]$IncludeDatabase
)

$targets = Get-CimInstance Win32_Process |
  Where-Object {
    ($_.Name -match 'python.exe' -and $_.CommandLine -match 'uvicorn app.main:app') -or
    ($_.Name -match 'node.exe' -and $_.CommandLine -match 'vite') -or
    ($_.Name -match 'powershell.exe' -and $_.CommandLine -match 'uvicorn app.main:app|vite\\.js|npm\.cmd run dev')
  }

$ids = $targets | Select-Object -ExpandProperty ProcessId -Unique

if (-not $ids -or $ids.Count -eq 0) {
  Write-Host "No demo processes were found running." -ForegroundColor Yellow
  exit 0
}

foreach ($id in $ids) {
  try {
    Stop-Process -Id $id -Force -ErrorAction Stop
    Write-Host "Stopped process $id" -ForegroundColor Yellow
  } catch {
    Write-Host "Process $id already exited." -ForegroundColor DarkYellow
  }
}

Write-Host "Demo processes stopped." -ForegroundColor Green

if ($IncludeDatabase) {
  $composeFile = Join-Path $PSScriptRoot "docker-compose.postgres.yml"
  if (Test-Path $composeFile) {
    docker compose -f $composeFile down | Out-Null
    Write-Host "PostgreSQL container stopped." -ForegroundColor Green
  } else {
    Write-Host "Compose file not found; database stop skipped." -ForegroundColor Yellow
  }
}

