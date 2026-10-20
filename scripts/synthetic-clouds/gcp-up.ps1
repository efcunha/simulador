<#
.SYNOPSIS
  Bring up the GCP synthetic-clouds plane (Phase 3): generate -> compose up ->
  podman cp rendered scripts/fixtures -> provision -> gcp-sim.

.DESCRIPTION
  Podman-safe sequence (design sec. 6, sec. 9):
    1. Run the Phase-1 generator on the HOST, emitting gcp_bigquery_topology/ +
       gcp_rest_fixtures/ under tools/synthetic_clouds/out/.
    2. podman compose up -d the bigquery-emulator (and build the gcp-sim image).
    3. Wait for emulator health (datasets.list 200).
    4. podman cp the rendered scripts into the provision volume and the fixtures
       into the gcp-sim volume -- NEVER a drive bind-mount (the spike's statfs
       input/output error).
    5. Start the provision one-shot, then gcp-sim.

  Includes an explicit emulator-ready -> provision -> gcp-sim fallback if the
  installed `podman compose` shim ignores depends_on.condition: service_healthy.

.PARAMETER DryRun
  Print the ordered plan without executing anything.
#>
[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Resolve worktree-relative paths from this script's location:
#   scripts/synthetic-clouds/gcp-up.ps1 -> <worktree root>
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorktreeRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$ComposeFile = Join-Path $WorktreeRoot "deploy\synthetic-clouds\compose.gcp.yaml"
# A DEDICATED output dir (G23). This script used to look for the newest directory under the
# shared out/, which is ambiguous: out/ also holds the daily cadence surface (out/daily/,
# FR-22), so the newest directory is not necessarily this run's. It broke aws-up.ps1 exactly
# that way, and therefore broke scripts/synthetic-clouds/up.ps1 on the GCP plane. Same fix.
# GCP_OUT_DIR overrides; its default MUST stay byte-identical to gcp-smoke.ps1 so up and smoke
# render and read the same source.
$OutDir      = if ($env:GCP_OUT_DIR) { $env:GCP_OUT_DIR } else { Join-Path $WorktreeRoot "tools\synthetic_clouds\out\gcp-plane" }
$Seed        = if ($env:GCP_SEED) { $env:GCP_SEED } else { "123" }
$GcpProfile  = if ($env:GCP_PROFILE) { $env:GCP_PROFILE } else { "small" }
# Length of the simulated window in days. Empty keeps the profile's own window (the historical
# behaviour); set it to reach "today" (e.g. 282 covers the canonical epoch through 2026-10-09).
# Mirrors aws-up.ps1's AWS_SIM_WINDOW_DAYS -- without it a demo run of this script silently
# regenerated the topology at the profile's 45-day window and overwrote a wide render.
$WindowDays  = if ($env:GCP_WINDOW_DAYS) { $env:GCP_WINDOW_DAYS } else { "" }
# Compose project name (podman -p) + named-volume prefix, from one source. SYNTHCLOUDS_PROJECT
# lets a parallel stack come up without colliding with the fixed-name volumes a running stack
# owns. The volume names are also hardcoded in the podman cp helper below, so -p alone would
# not be enough -- both the -p flag and the $ProvVol/$FixVol prefix derive from this variable.
# Default (no env) stays "synthetic-clouds" -> byte-identical to today's fixed names.
$ComposeProject = if ($env:SYNTHCLOUDS_PROJECT) { $env:SYNTHCLOUDS_PROJECT } else { "synthetic-clouds" }

$Plan = @(
    "1. python -m tools.synthetic_clouds --seed $Seed --profile $GcpProfile --emit gcp_bigquery_topology,gcp_rest_fixtures --out $OutDir (cwd=$WorktreeRoot)",
    "2. podman compose -f $ComposeFile up -d --build bigquery-emulator gcp-sim",
    "3. wait for bigquery-emulator health (datasets.list 200)",
    "4. podman cp <out>/render/gcp_bigquery_topology -> provision volume ; gcp_rest_fixtures -> fixtures volume",
    "5. podman compose -f $ComposeFile up gcp-bq-provision (one-shot) ; ensure gcp-sim healthy"
)

if ($DryRun) {
    Write-Host "DRY RUN -- ordered plan:`n"
    $Plan | ForEach-Object { Write-Host "  $_" }
    exit 0
}

function Invoke-Checked([string]$Desc, [scriptblock]$Block) {
    Write-Host "==> $Desc"
    & $Block
    if ($LASTEXITCODE -ne 0) { throw "$Desc failed (exit $LASTEXITCODE)" }
}

# 1. Generate on the host (writes under tools/synthetic_clouds/out/, NFR-5 guard).
Push-Location $WorktreeRoot
try {
    Invoke-Checked "generate topology + fixtures" {
        $GenArgs = @("-m", "tools.synthetic_clouds", "--seed", $Seed, "--profile", $GcpProfile, "--emit", "gcp_bigquery_topology,gcp_rest_fixtures", "--out", $OutDir)
        if ($WindowDays) { $GenArgs += @("--window-days", $WindowDays) }
        python @GenArgs
    }
} finally {
    Pop-Location
}

# Locate the newest render dir (store.write creates a timestamped run dir).
$RenderRoot = Get-ChildItem -Path $OutDir -Directory |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 |
    ForEach-Object { Join-Path $_.FullName "render" }
if (-not $RenderRoot -or -not (Test-Path $RenderRoot)) {
    throw "render dir not found under $OutDir"
}
$TopologyDir = Join-Path $RenderRoot "gcp_bigquery_topology"
$FixturesDir = Join-Path $RenderRoot "gcp_rest_fixtures"

Invoke-Checked "compose up emulator + gcp-sim (build)" {
    podman compose -p $ComposeProject -f $ComposeFile up -d --build --force-recreate bigquery-emulator gcp-sim
}

# 3. Wait for emulator health.
$Project = if ($env:GCP_PROJECT) { $env:GCP_PROJECT } else { "synthetic" }
$BqPort  = if ($env:GCP_BQ_REST_PORT) { $env:GCP_BQ_REST_PORT } else { "9050" }
$HealthUrl = "http://localhost:$BqPort/bigquery/v2/projects/$Project/datasets?maxResults=1"
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw "bigquery-emulator not healthy at $HealthUrl" }
Write-Host "==> emulator healthy"

# 4. podman cp rendered artifacts into the provision + fixtures volumes. We create
#    throwaway helper containers bound to the named volumes, cp into them, then rm.
#    (NEVER a drive bind-mount -- the spike's statfs input/output error.)
function Copy-IntoVolume([string]$Volume, [string]$SrcDir) {
    $helper = "synthclouds-helper-$([guid]::NewGuid().ToString('N').Substring(0,8))"
    Invoke-Checked "create helper for $Volume" {
        podman create --name $helper -v "${Volume}:/vol" docker.io/library/busybox:latest sh -c "true"
    }
    try {
        Invoke-Checked "podman cp into $Volume" {
            podman cp "$SrcDir" "${helper}:/vol/"
        }
    } finally {
        podman rm -f $helper | Out-Null
    }
}

$ProvVol = "${ComposeProject}_gcp_provision"
$FixVol  = "${ComposeProject}_gcp_sim_fixtures"
Copy-IntoVolume $ProvVol $TopologyDir
Copy-IntoVolume $FixVol  $FixturesDir

# gcp-sim loads fixtures at boot; restart so it picks up the just-copied fixtures.
Invoke-Checked "restart gcp-sim to load fixtures" {
    podman compose -p $ComposeProject -f $ComposeFile restart gcp-sim
}

# 5. Run the provision one-shot (DDL + INSERT over the emulator REST endpoint).
#    --build so the provision image picks up the current gcp_sim.provision code.
Invoke-Checked "run provisioner (one-shot)" {
    podman compose -p $ComposeProject -f $ComposeFile up --build --no-deps gcp-bq-provision
}

$SimPort = if ($env:GCP_SIM_PORT) { $env:GCP_SIM_PORT } else { "8085" }
Write-Host "`n==> GCP synthetic-clouds plane is up."
Write-Host "    emulator REST : http://localhost:$BqPort"
Write-Host "    gcp-sim       : http://localhost:$SimPort/healthz"
Write-Host "    render dir    : $RenderRoot"
