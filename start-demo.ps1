function Wait-PostgresHealthy {
  param(
    [string]$ComposeFile,
    [int]$MaxAttempts = 25
  )

  for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    $status = docker compose -f $ComposeFile ps --format json 2>$null | ConvertFrom-Json
    if ($status) {
      $postgres = $status | Where-Object { $_.Service -eq "postgres" }
      if ($postgres -and $postgres.Health -eq "healthy") {
        return $true
      }
    }
    Start-Sleep -Seconds 2
  }
  return $false
}

function Wait-BackendReady {
  param(
    [int]$MaxAttempts = 20
  )

  for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8000/health" -TimeoutSec 2
      if ($r.StatusCode -eq 200) {
        return $true
      }
    } catch {}
    Start-Sleep -Seconds 1
  }

  return $false
}

function Wait-FrontendReady {
  param(
    [int]$MaxAttempts = 45
  )

  for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    foreach ($port in @(5173, 5174)) {
      foreach ($hostName in @("localhost", "127.0.0.1")) {
        try {
          $r = Invoke-WebRequest -UseBasicParsing "http://$hostName`:$port" -TimeoutSec 2
          if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) {
            return $true
          }
        } catch {}
      }
    }
    Start-Sleep -Seconds 1
  }

  return $false
}

function Stop-ProcessOnPort {
  param(
    [int]$Port,
    [string]$Label
  )

  $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if (-not $connections) {
    return
  }

  $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($procId in $pids) {
    try {
      $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
      if ($proc) {
        Write-Host "Stopping stale $Label process on port $Port (PID $procId)..." -ForegroundColor DarkYellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
      }
    } catch {}
  }

  Start-Sleep -Milliseconds 500
}

Set-Location $PSScriptRoot

$composeFile = Join-Path $PSScriptRoot "docker-compose.postgres.yml"
if (!(Test-Path $composeFile)) {
  Write-Error "docker-compose.postgres.yml not found in project root."
  exit 1
}

$pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (!(Test-Path $pythonExe)) {
  Write-Error "Virtual environment not found at .venv. Run setup first."
  exit 1
}

$nodeCmd = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $nodeCmd) {
  Write-Error "node was not found in PATH. Install Node.js and try again."
  exit 1
}

$viteCli = Join-Path $PSScriptRoot "frontend\node_modules\vite\bin\vite.js"
if (!(Test-Path $viteCli)) {
  Write-Error "Vite CLI not found. Run 'npm.cmd install' inside frontend folder first."
  exit 1
}

Write-Host "Starting PostgreSQL container..." -ForegroundColor Cyan
docker compose -f $composeFile up -d | Out-Null

Write-Host "Waiting for PostgreSQL health..." -ForegroundColor Cyan
if (-not (Wait-PostgresHealthy -ComposeFile $composeFile)) {
  Write-Error "PostgreSQL container did not become healthy in time."
  exit 1
}

Set-Location "$PSScriptRoot\backend"
Write-Host "Checking database state..." -ForegroundColor Cyan
$userCount = & $pythonExe -c "from app.database import SessionLocal; from app.models import User; db = SessionLocal(); print(db.query(User).count()); db.close()"
if ($LASTEXITCODE -ne 0) {
  Write-Error "Could not inspect database state."
  exit 1
}

$parsedCount = 0
if (-not [int]::TryParse(($userCount | Select-Object -Last 1).Trim(), [ref]$parsedCount)) {
  Write-Error "Could not parse user count from database check."
  exit 1
}

if ($parsedCount -eq 0) {
  Write-Host "Seeding demo data..." -ForegroundColor Cyan
  & $pythonExe -m app.seed_demo
  if ($LASTEXITCODE -ne 0) {
    Write-Error "Seeding failed."
    exit 1
  }
} else {
  Write-Host "Existing users detected. Skipping demo seed to preserve current data." -ForegroundColor Yellow
}

Write-Host "Ensuring default Admin authority account..." -ForegroundColor Cyan
& $pythonExe -m app.ensure_default_admin
if ($LASTEXITCODE -ne 0) {
  Write-Error "Could not ensure default admin account."
  exit 1
}

Stop-ProcessOnPort -Port 8000 -Label "backend"
Stop-ProcessOnPort -Port 5173 -Label "frontend"

Write-Host "Starting backend (http://127.0.0.1:8000)..." -ForegroundColor Green
Start-Process -FilePath $pythonExe -WorkingDirectory "$PSScriptRoot\backend" -ArgumentList @("-m", "uvicorn", "app.main:app", "--reload", "--port", "8000")

Write-Host "Starting frontend (http://localhost:5173)..." -ForegroundColor Green
$frontendProc = Start-Process -FilePath $nodeCmd -WorkingDirectory "$PSScriptRoot\frontend" -ArgumentList @(".\node_modules\vite\bin\vite.js") -PassThru

Write-Host "Waiting for backend readiness..." -ForegroundColor Cyan
if (-not (Wait-BackendReady)) {
  Write-Warning "Backend did not become ready within expected time. Running health check for details."
}

if ($frontendProc -and $frontendProc.HasExited) {
  Write-Warning "Frontend process exited early (exit code: $($frontendProc.ExitCode))."
}

Write-Host "Waiting for frontend readiness..." -ForegroundColor Cyan
if (-not (Wait-FrontendReady)) {
  Write-Warning "Frontend did not become ready within expected time. Running health check for details."
}

Write-Host "Running health check..." -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File "$PSScriptRoot\health-check.ps1"

Write-Host "Demo stack launched with PostgreSQL." -ForegroundColor Yellow
