function Test-PortOpen {
  param(
    [string]$HostName,
    [int]$Port
  )

  try {
    $client = New-Object System.Net.Sockets.TcpClient
    $iar = $client.BeginConnect($HostName, $Port, $null, $null)
    $connected = $iar.AsyncWaitHandle.WaitOne(1200, $false)
    if (-not $connected) {
      $client.Close()
      return $false
    }
    $client.EndConnect($iar)
    $client.Close()
    return $true
  } catch {
    return $false
  }
}

$backendPort = Test-PortOpen -HostName "127.0.0.1" -Port 8000
$postgresHealthy = $false
$composeFile = Join-Path $PSScriptRoot "docker-compose.postgres.yml"
if (Test-Path $composeFile) {
  try {
    $services = docker compose -f $composeFile ps --format json | ConvertFrom-Json
    $postgres = $services | Where-Object { $_.Service -eq "postgres" }
    if ($postgres -and $postgres.State -eq "running" -and $postgres.Health -eq "healthy") {
      $postgresHealthy = $true
    }
  } catch {}
}

$frontendUrl = "unavailable"
foreach ($port in @(5173, 5174)) {
  if ($frontendUrl -ne "unavailable") {
    break
  }

  foreach ($hostName in @("localhost", "127.0.0.1")) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing "http://$hostName`:$port" -TimeoutSec 2
      if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) {
        $frontendUrl = "http://$hostName`:$port"
        break
      }
    } catch {}
  }
}

$frontendPort = $frontendUrl -ne "unavailable"

Write-Host "Backend port 8000: $backendPort"
Write-Host "Frontend ready: $frontendPort ($frontendUrl)"
Write-Host "PostgreSQL healthy: $postgresHealthy"

try {
  $health = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8000/health" -TimeoutSec 3
  Write-Host "Backend /health: $($health.Content)"
} catch {
  Write-Host "Backend /health: unavailable"
}

if ($backendPort -and $frontendPort -and $postgresHealthy) {
  Write-Host "Status: READY FOR DEMO" -ForegroundColor Green
  exit 0
}

Write-Host "Status: NOT READY" -ForegroundColor Red
exit 1
