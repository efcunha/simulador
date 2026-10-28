#Requires -Version 7
<#
.SYNOPSIS
    Idempotent "ensure" for the CloudPilot <-> simulator integration.

.DESCRIPTION
    Re-applies the operational steps that do NOT survive a restart/recreate:
      1. podman machine up; emulator containers running
      2. DNS aliases on the CloudPilot bridge (management/login on azure-sim,
         GCP/AWS hostnames on the TLS front, emulator names for the front)
      3. CA trust present in the CloudPilot containers (env + /certs mount)
      4. azure-sim estate window reaches the current UTC day
      5. optional end-to-end smoke: "Verificar Conexão" on the three accounts
         and /costs/unified with stale=false

    Safe to run on a schedule: it only reconnects a network endpoint when an
    alias is missing, and only rebuilds the estate when the window is stale.
    It never edits code, credentials or the database.

.PARAMETER Smoke
    Also run the authenticated connection checks and the unified-costs read
    (mints a short-lived JWT inside the backend container; no secret is read
    from or written to disk).

.PARAMETER ForceRefresh
    Rebuild the azure-sim estate even when the window already covers today.

.PARAMETER SkipEstate
    Do not touch the estate window.

.PARAMETER Quiet
    Only write problems/summary to the console (the log file always gets all).

.EXAMPLE
    .\ensure-cloudpilot.ps1
    .\ensure-cloudpilot.ps1 -Smoke
#>
[CmdletBinding()]
param(
    [switch]$Smoke,
    [switch]$ForceRefresh,
    [switch]$SkipEstate,
    [switch]$Quiet,
    [string]$LogPath = (Join-Path $env:LOCALAPPDATA 'synthetic-clouds\integration.log')
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$DeployDir = Join-Path $RepoRoot 'deploy\synthetic-clouds'
$CaCrt = Join-Path $RepoRoot 'emulators\azure-sim\tls\ca.crt'
$CpRoot = 'D:\cloudpilot-deploy'
$CaBundle = Join-Path $CpRoot '.local\tls\ca-bundle.pem'

$CpNet = 'cloudpilot-deploy_cloudpilot_net'
$AzureSim = 'synthetic-clouds-azure-sim-1'
$TlsFront = 'synthetic-clouds-tls-front'
$GcpSim = 'synthetic-clouds-gcp-sim-1'
$AwsSim = 'synthetic-clouds-aws-sim-1'
$S3Mock = 'synthetic-clouds-s3mock-1'
$BqEmu = 'synthetic-clouds-bigquery-emulator-1'

$AzureHostAliases = @('management.azure.com', 'login.microsoftonline.com')
$FrontAliases = @(
    'bigquery.googleapis.com',
    'oauth2.googleapis.com',
    'cloudresourcemanager.googleapis.com',
    'compute.googleapis.com',
    'config.googleapis.com',
    'container.googleapis.com',
    'securitycenter.googleapis.com',
    'sts.amazonaws.com',
    'sts.us-east-1.amazonaws.com'
)

$script:Problems = [System.Collections.Generic.List[string]]::new()
$script:LogDir = Split-Path -Parent $LogPath
if (-not (Test-Path $script:LogDir)) { New-Item -ItemType Directory -Force $script:LogDir | Out-Null }

function Write-Log {
    param([string]$Level, [string]$Message)
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Add-Content -Path $LogPath -Value $line -Encoding utf8
    if (-not $Quiet -or $Level -ne 'INFO') { Write-Host $line }
}

function Add-Problem {
    param([string]$Message)
    $script:Problems.Add($Message) | Out-Null
    Write-Log 'FAIL' $Message
}

function Test-Podman {
    & podman info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Log 'WARN' 'podman machine is not responding; trying to start it'
        & podman machine start *> $null
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 3
            & podman info *> $null
            if ($LASTEXITCODE -eq 0) { return $true }
        }
        Add-Problem 'podman machine did not become ready'
        return $false
    }
    return $true
}

function Test-ContainerExists {
    param([string]$Name)
    & podman container exists $Name 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Test-ContainerRunning {
    param([string]$Name)
    $state = (& podman inspect $Name --format '{{.State.Status}}' 2>$null)
    return ($LASTEXITCODE -eq 0 -and "$state".Trim() -eq 'running')
}

function Wait-Healthy {
    param([string]$Name, [int]$TimeoutSeconds = 300)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $health = (& podman inspect $Name --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>$null)
        $value = "$health".Trim()
        if ($value -in @('healthy', 'running')) { return $true }
        Start-Sleep -Seconds 5
    }
    return $false
}

function Start-Container {
    param([string]$Name)
    if (-not (Test-ContainerExists $Name)) { return $false }
    if (-not (Test-ContainerRunning $Name)) {
        Write-Log 'INFO' "starting container $Name"
        & podman start $Name *> $null
    }
    return (Wait-Healthy $Name)
}

function Ensure-NetworkAliases {
    param([string]$Container, [string]$Network, [string[]]$Aliases)
    $raw = (& podman inspect $Container --format '{{json .NetworkSettings.Networks}}' 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
        Add-Problem "cannot inspect networks of $Container"
        return
    }
    $networks = $raw | ConvertFrom-Json
    $attached = $networks.PSObject.Properties.Name -contains $Network
    if (-not $attached) {
        Write-Log 'INFO' "connecting $Container to $Network with aliases $($Aliases -join ', ')"
        $args = [System.Collections.Generic.List[string]]::new()
        $args.Add('network'); $args.Add('connect')
        foreach ($alias in $Aliases) { $args.Add('--alias'); $args.Add($alias) }
        $args.Add($Network); $args.Add($Container)
        & podman @args *> $null
        if ($LASTEXITCODE -ne 0) { Add-Problem "podman network connect failed for $Container" }
        return
    }

    $current = @($networks.$Network.Aliases)
    $missing = @($Aliases | Where-Object { $_ -notin $current })
    if ($missing.Count -eq 0) {
        Write-Log 'INFO' "$Container aliases OK on $Network"
        return
    }

    Write-Log 'INFO' "$Container missing aliases ($($missing -join ', ')); reconnecting"
    & podman network disconnect $Network $Container *> $null
    $args = [System.Collections.Generic.List[string]]::new()
    $args.Add('network'); $args.Add('connect')
    foreach ($alias in $Aliases) { $args.Add('--alias'); $args.Add($alias) }
    $args.Add($Network); $args.Add($Container)
    & podman @args *> $null
    if ($LASTEXITCODE -ne 0) {
        Add-Problem "podman network reconnect failed for $Container"
    } else {
        Write-Log 'INFO' "$Container reconnected with aliases"
    }
}

function Get-CertBody {
    param([string]$Pem)
    return ((($Pem -replace '-----BEGIN CERTIFICATE-----', '') -replace '-----END CERTIFICATE-----', '') -replace '\s', '')
}

function Ensure-FrontCertificate {
    <#
      .SYNOPSIS
        Guarantees that the leaf the TLS front serves covers every hostname the front routes.

      .DESCRIPTION
        The client verifies the name it dialled, so a hostname the front routes but the
        leaf does not name fails the handshake -- the routing table and the certificate
        are one contract. The SAN list is therefore the generator's
        (gen_cloud_front_tls.DEFAULT_DNS_NAMES) PLUS the aliases this script routes, so
        a hostname added to the routing table cannot leave the certificate behind.

        The leaf is a local artifact (git-ignored) and the new one is signed by the SAME
        CA, so the CloudPilot trust bundle does not have to be rebuilt. Like the CA
        bundle, the running front keeps the OLD leaf until it is recreated, so this
        warns when it re-signs.
    #>
    $leaf = Join-Path $RepoRoot 'emulators\azure-sim\tls\server-clouds.crt'
    $generator = Join-Path $RepoRoot 'emulators\azure-sim\scripts\gen_cloud_front_tls.py'
    $python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) {
        Add-Problem "simulator venv python not found at $python (needed to re-sign the front leaf)"
        return $false
    }
    if (-not (Test-Path $generator)) {
        Add-Problem "leaf generator missing at $generator"
        return $false
    }
    $py = @'
import json
import sys
from pathlib import Path

generator_path = Path(sys.argv[1])
leaf_path = Path(sys.argv[2])
extra = tuple(sys.argv[3:])

sys.path.insert(0, str(generator_path.parent))
import gen_cloud_front_tls as generator
from cryptography import x509

required = tuple(dict.fromkeys(tuple(generator.DEFAULT_DNS_NAMES) + extra))
present = []
if leaf_path.is_file():
    cert = x509.load_pem_x509_certificate(leaf_path.read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    present = list(san.get_values_for_type(x509.DNSName))
missing = [name for name in required if name not in present]
regenerated = False
if missing:
    generator.generate(leaf_path.parent, days=3650, dns_names=required)
    regenerated = True
print(json.dumps({"missing": missing, "regenerated": regenerated, "names": len(required)}))
'@
    $raw = ($py | & $python - $generator $leaf @($FrontAliases) 2>&1)
    $line = $raw | Where-Object { "$_".StartsWith('{') } | Select-Object -Last 1
    if (-not $line) {
        Add-Problem "could not verify the front leaf: $($raw | Select-Object -Last 3)"
        return $false
    }
    $result = $line | ConvertFrom-Json
    if ($result.regenerated) {
        Write-Log 'WARN' ("front leaf re-signed (missing SANs: {0}); the tls-front must be recreated to pick it up" -f ($result.missing -join ', '))
        return $true
    }
    Write-Log 'INFO' ("front leaf covers the {0} names the front may serve" -f $result.names)
    return $true
}

function Repair-CaBundle {
    if (-not (Test-Path $CaCrt)) {
        Add-Problem "CA certificate missing at $CaCrt (run gen_dev_tls.py)"
        return $false
    }
    $caPem = (Get-Content -Path $CaCrt -Raw).Trim()
    $caBody = Get-CertBody $caPem
    if (Test-Path $CaBundle) {
        $bundleFlat = (Get-Content -Path $CaBundle -Raw) -replace '\s', ''
        if ($caBody -and $bundleFlat.Contains($caBody)) {
            Write-Log 'INFO' 'CA bundle contains the current CA'
            return $true
        }
    }
    if (-not (Test-ContainerRunning 'cloudpilot_backend')) {
        Add-Problem "CA bundle at $CaBundle is missing/stale and backend is not running to rebuild it"
        return $false
    }
    Write-Log 'INFO' "rebuilding CA bundle at $CaBundle from backend certifi + local CA"
    $certifi = (& podman exec cloudpilot_backend python -c "import certifi; print(certifi.where())" 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $certifi) {
        Add-Problem 'could not resolve certifi bundle inside cloudpilot_backend'
        return $false
    }
    $tmp = Join-Path $env:TEMP ("cp-ca-bundle-{0}.pem" -f ([guid]::NewGuid().ToString('N')))
    & podman exec cloudpilot_backend cat $certifi | Set-Content -Path $tmp -Encoding ascii
    Add-Content -Path $tmp -Value $caPem -Encoding ascii
    $targetDir = Split-Path -Parent $CaBundle
    if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Force $targetDir | Out-Null }
    Move-Item -Path $tmp -Destination $CaBundle -Force
    Write-Log 'WARN' 'CA bundle rebuilt; CloudPilot containers must be recreated to pick it up (mount is read at container creation)'
    return $true
}

function Test-CloudPilotTrust {
    $services = @(
        'cloudpilot_backend',
        'cloudpilot_celery_worker',
        'cloudpilot_celery_worker_drift',
        'cloudpilot-deploy-celery_worker_k8s-1',
        'cloudpilot_celery_beat'
    )
    $ok = 0
    foreach ($service in $services) {
        if (-not (Test-ContainerRunning $service)) {
            Write-Log 'WARN' "$service is not running; trust check skipped"
            continue
        }
        $envList = (& podman inspect $service --format '{{json .Config.Env}}' 2>$null | ConvertFrom-Json)
        $hasEnv = ($envList -contains 'REQUESTS_CA_BUNDLE=/certs/ca-bundle.pem')
        & podman exec $service sh -c 'test -f /certs/ca-bundle.pem' *> $null
        $hasMount = ($LASTEXITCODE -eq 0)
        if ($hasEnv -and $hasMount) {
            $ok++
        } else {
            Add-Problem "$service has no CA trust (env=$hasEnv mount=$hasMount); recreate with docker-compose.local.yml"
        }
    }
    if ($ok -gt 0) { Write-Log 'INFO' "CA trust present in $ok CloudPilot container(s)" }
    return $ok
}

function Get-EstateMaxDay {
    param([int]$ApiPort = 8080)
    $body = @{
        type      = 'ActualCost'
        timeframe = 'Custom'
        dataset   = @{
            granularity = 'Daily'
            aggregation = @{ CostInBillingCurrency = @{ name = 'Cost'; function = 'Sum' } }
            grouping    = @(@{ type = 'Dimension'; name = 'BillingPeriodStartDate' })
        }
    } | ConvertTo-Json -Depth 8
    $uri = "http://localhost:$ApiPort/subscriptions/00000000-0000-0000-0000-000000000000/providers/Microsoft.CostManagement/query?api-version=2025-03-01"
    $response = Invoke-RestMethod -Method Post -Uri $uri -ContentType 'application/json' -Body $body -TimeoutSec 180
    $days = @($response.properties.rows | ForEach-Object { [datetime]::ParseExact($_[1], 'yyyy-MM-dd', [Globalization.CultureInfo]::InvariantCulture) })
    if ($days.Count -eq 0) { return $null }
    return ($days | Sort-Object | Select-Object -Last 1)
}

function Ensure-Estate {
    param([int]$ApiPort = 8080, [switch]$Force)
    $today = (Get-Date).ToUniversalTime().Date
    $epoch = [datetime]::ParseExact('2026-01-01', 'yyyy-MM-dd', [Globalization.CultureInfo]::InvariantCulture)
    $days = ($today - $epoch).Days + 1

    $max = Get-EstateMaxDay -ApiPort $ApiPort
    if ($null -eq $max) {
        Add-Problem 'azure-sim returned no estate rows'
        return
    }
    if (-not $Force -and $max.Date -ge $today) {
        Write-Log 'INFO' ("estate window covers today (max {0:yyyy-MM-dd}, {1} days)" -f $max, $days)
        return
    }
    Write-Log 'INFO' ("estate window ends {0:yyyy-MM-dd}; refreshing to {1} days" -f $max, $days)
    Invoke-RestMethod -Method Post -Uri "http://localhost:$ApiPort/admin/estate/refresh?days=$days" -TimeoutSec 600 | Out-Null
    $maxAfter = Get-EstateMaxDay -ApiPort $ApiPort
    if ($null -eq $maxAfter -or $maxAfter.Date -lt $today) {
        Add-Problem ("estate refresh did not reach today (max {0})" -f $maxAfter)
    } else {
        Write-Log 'INFO' ("estate refreshed (max {0:yyyy-MM-dd})" -f $maxAfter)
    }
}

function Invoke-Smoke {
    $health = $null
    try { $health = (Invoke-WebRequest -UseBasicParsing 'http://localhost:8000/health' -TimeoutSec 10).StatusCode } catch { }
    if ($health -ne 200) {
        Add-Problem 'CloudPilot API is not healthy on :8000; smoke skipped'
        return
    }

    $python = @'
import json, time
import httpx
from app.services.auth_service import create_access_token

TOKEN = create_access_token("9f0bba98-03e5-40aa-90c7-930ae0ec835e")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "X-Workspace-ID": "e757043f-2325-506b-b3eb-e61f8d07147d"}
ACCOUNTS = [
    ("aws", "f4b259ca-3a0d-49bb-ade9-bf75101317c8"),
    ("gcp", "a77c3a50-d925-4a4e-9ae8-b15b9c8cdf5b"),
    ("azure", "212dc724-eb8f-4ab4-b108-0321076cbb12"),
]
out = {"connections": {}, "unified": None}
for label, account in ACCOUNTS:
    r = httpx.post(
        f"http://localhost:8000/api/v1/cloud-accounts/{account}/check-connection",
        headers=HEADERS,
        timeout=120,
    )
    data = r.json().get("data", r.json())
    out["connections"][label] = {"status": data.get("status"), "error": data.get("error")}
for _ in range(8):
    r = httpx.post(
        "http://localhost:8000/api/v1/costs/unified?start_date=2026-10-01&end_date=2026-10-26",
        headers=HEADERS,
        timeout=300,
    )
    data = r.json().get("data") or r.json()
    if data.get("total_cost") and data.get("is_stale") is False:
        out["unified"] = {"total": data["total_cost"], "stale": data["is_stale"]}
        break
    time.sleep(8)
print("SMOKE:" + json.dumps(out))
'@
    $raw = ($python | & podman exec -i cloudpilot_backend python - 2>&1)
    $line = $raw | Where-Object { $_ -like 'SMOKE:*' } | Select-Object -Last 1
    if (-not $line) {
        Add-Problem "smoke did not return a result: $($raw | Select-Object -Last 3)"
        return
    }
    $result = ($line.Substring(6) | ConvertFrom-Json)
    foreach ($provider in @('aws', 'gcp', 'azure')) {
        $entry = $result.connections.$provider
        if ($entry.status -ne 'connected') {
            Add-Problem "connection check $provider = $($entry.status) ($($entry.error))"
        } else {
            Write-Log 'INFO' "connection check $provider = connected"
        }
    }
    if ($result.unified) {
        Write-Log 'INFO' ("unified total {0} stale {1}" -f $result.unified.total, $result.unified.stale)
    } else {
        Add-Problem 'unified-costs did not return a fresh non-zero result'
    }
}

# ── main ────────────────────────────────────────────────────────────────────
Write-Log 'INFO' '=== ensure CloudPilot <-> simulator integration ==='
if (-not (Test-Podman)) { exit 2 }

# 1/2. emulators up
if (Test-ContainerExists $AzureSim) {
    if (Start-Container $AzureSim) { Write-Log 'INFO' 'azure-sim running/healthy' }
    else { Add-Problem 'azure-sim did not become healthy' }
} else {
    Write-Log 'INFO' 'azure-sim container missing; creating from compose'
    Push-Location $DeployDir
    try {
        & podman compose -f compose.yaml up -d --no-deps --no-build azure-sim *> $null
    } finally { Pop-Location }
    if (-not (Wait-Healthy $AzureSim 300)) { Add-Problem 'azure-sim was not created healthy' }
}

if (Test-ContainerExists $TlsFront) {
    # The front is NOT started here: nginx resolves its upstreams
    # (bigquery-emulator, gcp-sim, aws-sim) at STARTUP and exits with
    # "host not found in upstream" when they are absent, so starting it
    # before step 2 attaches those aliases burns the whole Wait-Healthy
    # timeout in a restart loop and reports a false "did not become
    # healthy". It is started in step 2b, right after the aliases land.
    Write-Log 'INFO' 'tls-front container present; start deferred until the upstream aliases exist'
} else {
    Write-Log 'INFO' 'tls-front container missing; creating from compose'
    Push-Location $DeployDir
    try {
        & podman compose -f compose.tls-front.yaml up -d *> $null
    } finally { Pop-Location }
    if (-not (Wait-Healthy $TlsFront 120)) { Add-Problem 'tls-front was not created healthy' }
}

foreach ($name in @($GcpSim, $AwsSim, $S3Mock, $BqEmu)) {
    if (-not (Test-ContainerExists $name)) {
        Add-Problem "$name is missing; recreate the emulator stack (see docs/INTEGRACAO-CLOUDPILOT-TLS.md)"
        continue
    }
    if (-not (Start-Container $name)) { Add-Problem "$name did not start" }
}

# 2. DNS aliases
Ensure-NetworkAliases -Container $AzureSim -Network $CpNet -Aliases $AzureHostAliases
Ensure-NetworkAliases -Container $TlsFront -Network $CpNet -Aliases $FrontAliases
Ensure-NetworkAliases -Container $GcpSim -Network $CpNet -Aliases @('gcp-sim')
Ensure-NetworkAliases -Container $AwsSim -Network $CpNet -Aliases @('aws-sim')
Ensure-NetworkAliases -Container $S3Mock -Network $CpNet -Aliases @('s3mock')
Ensure-NetworkAliases -Container $BqEmu -Network $CpNet -Aliases @('bigquery-emulator')

# 2b. Now that the upstreams answer by name, the front can start.
if (Test-ContainerExists $TlsFront) {
    if (-not (Start-Container $TlsFront)) { Add-Problem 'tls-front did not become healthy' }
}

# 3. CA trust
Repair-CaBundle | Out-Null
Test-CloudPilotTrust | Out-Null

# 3b. the front leaf covers the hostnames the front routes
Ensure-FrontCertificate | Out-Null

# 4. estate window
if (-not $SkipEstate) { Ensure-Estate -Force:$ForceRefresh }

# 5. optional end-to-end smoke
if ($Smoke) { Invoke-Smoke }

# ── summary ─────────────────────────────────────────────────────────────────
if ($script:Problems.Count -eq 0) {
    Write-Log 'INFO' 'summary: integration OK (0 problems)'
    exit 0
}
Write-Log 'FAIL' ("summary: {0} problem(s)" -f $script:Problems.Count)
foreach ($problem in $script:Problems) { Write-Host "  - $problem" }
exit 1
