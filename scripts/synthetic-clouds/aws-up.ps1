<#
.SYNOPSIS
  Bring up the AWS synthetic-clouds plane (Phase 6, Item 6): generate -> compose up ->
  podman cp the rendered tree into the sim volume -> upload it to the S3 store.

.DESCRIPTION
  Podman-safe sequence, mirroring scripts/synthetic-clouds/gcp-up.ps1:
    1. Run the Phase-1 generator on the HOST, emitting focus_aws into a DEDICATED out dir.
    2. podman compose up -d --build s3mock + aws-sim (build context = worktree root).
    3. Wait for the S3 store to answer on the host before anything is uploaded.
    4. podman cp the rendered tree into the aws_sim_render NAMED VOLUME via a throwaway
       helper container -- NEVER a drive bind-mount (the spike's statfs i/o error).
    5. Run the uploader INSIDE aws-sim: `python -m aws_sim.upload`. Upload order is
       sorted-key order, which is what makes the newest execution per billing period carry
       the newest LastModified -- see aws_sim/upload.py.
    6. Wait for aws-sim /healthz.

  The bucket needs no separate init step: `upload.ensure_bucket()` creates it when absent,
  which is why the MinIO-era `mc` one-shot is gone (and why the plan no longer depends on a
  second image).

.PARAMETER DryRun
  Print the ordered plan without executing anything.
#>
[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# scripts/synthetic-clouds/aws-up.ps1 -> <worktree root>
$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorktreeRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$ComposeFile  = Join-Path $WorktreeRoot "deploy\synthetic-clouds\compose.aws.yaml"
# A DEDICATED output dir, and the generator is told to use it. Discovering the run dir by
# "newest under out/" is what gcp-up.ps1 does and it is fragile: out/ also holds the daily
# cadence surface (out/daily/, FR-22), so the newest directory is not necessarily this run's.
$OutDir       = Join-Path $WorktreeRoot "tools\synthetic_clouds\out\aws-plane"

$Seed       = if ($env:AWS_SIM_SEED) { $env:AWS_SIM_SEED } else { "123" }
$AwsProfile = if ($env:AWS_SIM_PROFILE) { $env:AWS_SIM_PROFILE } else { "small" }
$S3Port     = if ($env:S3_PORT) { $env:S3_PORT } else { "9090" }
$SimPort    = if ($env:AWS_SIM_PORT) { $env:AWS_SIM_PORT } else { "8086" }
$Bucket     = if ($env:AWS_SIM_BUCKET) { $env:AWS_SIM_BUCKET } else { "synthetic-focus12-daily-full" }
$RenderVol  = "synthetic-clouds_aws_sim_render"
# Length of the simulated window in days. Empty keeps the profile's own window (the historical
# behaviour); set it to reach "today" (e.g. 282 covers the canonical epoch through 2026-10-09).
$WindowDays = if ($env:AWS_SIM_WINDOW_DAYS) { $env:AWS_SIM_WINDOW_DAYS } else { "" }

$Plan = @(
    "1. python -m tools.synthetic_clouds --seed $Seed --profile $AwsProfile --emit focus_aws --out $OutDir (cwd=$WorktreeRoot)",
    "2. podman compose -f $ComposeFile up -d --build s3mock aws-sim",
    "3. wait for the S3 store at http://localhost:$S3Port/",
    "4. podman cp <out>/*/render/aws_focus -> $RenderVol (throwaway helper container)",
    "5. podman exec <aws-sim> python -m aws_sim.upload --dir /render/aws_focus --bucket $Bucket",
    "6. wait for aws-sim health at http://localhost:$SimPort/healthz"
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

# 1. Generate on the host. Writes under tools/synthetic_clouds/ (NFR-5 guard).
Push-Location $WorktreeRoot
try {
    Invoke-Checked "generate the AWS FOCUS 1.2 export tree" {
        $GenArgs = @("-m", "tools.synthetic_clouds", "--seed", $Seed, "--profile", $AwsProfile, "--emit", "focus_aws", "--out", $OutDir)
        if ($WindowDays) { $GenArgs += @("--window-days", $WindowDays) }
        python @GenArgs
    }
} finally { Pop-Location }

Invoke-Checked "compose up s3mock + aws-sim (build)" {
    podman compose -f $ComposeFile up -d --build s3mock aws-sim
}

# 3. Wait for the S3 store. `GET /` is the S3 ListBuckets call, so a 200 proves the API is
#    answering -- not merely that a port is open.
if (-not (Test-Path $OutDir)) { throw "generator wrote nothing under $OutDir" }
$RenderRoot = Get-ChildItem -Path $OutDir -Directory |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 |
    ForEach-Object { Join-Path $_.FullName "render" }
if (-not $RenderRoot -or -not (Test-Path $RenderRoot)) { throw "render dir not found under $OutDir" }
$AwsFocusDir = Join-Path $RenderRoot "aws_focus"
if (-not (Test-Path $AwsFocusDir)) { throw "aws_focus not rendered at $AwsFocusDir" }

$S3Health = "http://localhost:$S3Port/"
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri $S3Health -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw "S3 store not answering at $S3Health" }
Write-Host "==> S3 store answering"

# 4. podman cp the rendered tree into the named volume. Throwaway helper container bound to
#    the volume, cp into it, remove it -- NEVER a drive bind-mount.
$helper = "synthclouds-helper-$([guid]::NewGuid().ToString('N').Substring(0,8))"
Invoke-Checked "create helper for $RenderVol" {
    podman create --name $helper -v "${RenderVol}:/vol" docker.io/library/busybox:latest sh -c "true"
}
try {
    Invoke-Checked "podman cp the rendered tree into $RenderVol" {
        podman cp "$AwsFocusDir" "${helper}:/vol/"
    }
} finally {
    podman rm -f $helper | Out-Null
}

# 5. Upload from INSIDE the sim, so settings stay in the container environment and never
#    appear on a command line. `compose ps -q` is the reliable way to name the container: a
#    compose-built image is tagged with the project prefix, not `aws-sim`.
$ContainerId = (podman compose -f $ComposeFile ps -q aws-sim | Select-Object -First 1)
if (-not $ContainerId) { throw "aws-sim container not found (compose ps -q aws-sim was empty)" }
Invoke-Checked "upload the rendered tree to the S3 store" {
    podman exec $ContainerId python -m aws_sim.upload --dir "/render/aws_focus" --bucket $Bucket
}

# 6. Wait for the sim to be healthy.
$SimHealth = "http://localhost:$SimPort/healthz"
$simReady = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri $SimHealth -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) { $simReady = $true; break }
    } catch { Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 1
}
if (-not $simReady) { throw "aws-sim not healthy at $SimHealth" }

Write-Host "`n==> AWS synthetic-clouds plane is up."
Write-Host "    aws-sim       : http://localhost:$SimPort/healthz"
Write-Host "    S3 store      : http://localhost:$S3Port (ListBuckets)"
Write-Host "    bucket        : $Bucket"
Write-Host "    render dir    : $RenderRoot"
