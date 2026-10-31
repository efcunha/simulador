<#
.SYNOPSIS
  Bring up the AWS synthetic-clouds plane (Phase 6, Item 6): generate -> compose up ->
  podman cp the rendered tree into the sim volume -> upload it to the S3 store.

.DESCRIPTION
  Podman-safe sequence, mirroring scripts/synthetic-clouds/gcp-up.ps1:
    1. Run the Phase-1 generator on the HOST, emitting focus_aws into a DEDICATED out dir.
    2. Bring the s3mock + aws-sim services up (the running containers are reused unless
       -Build is given; see PARAMETER below).
    3. Wait for the S3 store to answer on the host before anything is uploaded.
    4. Replace the rendered tree inside the aws_sim_render NAMED VOLUME via the running
       aws-sim container -- NEVER a drive bind-mount (the spike's statfs i/o error).
    5. Run the uploader INSIDE aws-sim: `python -m aws_sim.upload`. Upload order is
       sorted-key order, which is what makes the newest execution per billing period carry
       the newest LastModified -- see aws_sim/upload.py.
    6. Wait for aws-sim /healthz.

  The bucket needs no separate init step: `upload.ensure_bucket()` creates it when absent,
  which is why the MinIO-era `mc` one-shot is gone (and why the plan no longer depends on a
  second image).

  CONFIGURATION (S4b3-A) -- the installation's own .env is the source of truth.
  `podman compose` already reads deploy/synthetic-clouds/.env for interpolation, but the
  generator runs on the HOST, where that interpolation does not reach: the script used to
  read the AWS_SIM_* namespace from the PROCESS environment only, so a plain
  `aws-up.ps1` fell back to the profile default (`small`) whenever the shell did not
  export AWS_SIM_PROFILE -- the tree was rendered small while the plane served medium,
  and the two estates drifted apart. The script now resolves every setting from the
  process environment FIRST and from deploy/synthetic-clouds/.env SECOND, so the file
  that already pins the installation wins by default and an explicit export still
  overrides it.

  The generator needs the repository virtualenv: on this machine the PATH `python` is
  C:\Python314\python.exe, which does not carry the generator's dependencies. The venv
  interpreter is used when it exists; the PATH one is the fallback.

.PARAMETER DryRun
  Print the ordered plan without executing anything.

.PARAMETER Build
  Rebuild the emulator images and recreate the containers. OFF by default: the running
  containers are reused when they are already up, so a re-publish of the tree does not
  rebuild an image (and does not restart a plane that was not touched). A warning is
  printed when the running image predates the emulator sources, because then the reused
  image is stale and -Build is the way to pick the change up.
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Build
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# scripts/synthetic-clouds/aws-up.ps1 -> <worktree root>
$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorktreeRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$ComposeFile  = Join-Path $WorktreeRoot "deploy\synthetic-clouds\compose.aws.yaml"
$InstallEnv   = Join-Path $WorktreeRoot "deploy\synthetic-clouds\.env"
# A DEDICATED output dir, and the generator is told to use it. Discovering the run dir by
# "newest under out/" is what gcp-up.ps1 does and it is fragile: out/ also holds the daily
# cadence surface (out/daily/, FR-22), so the newest directory is not necessarily this run's.
$OutDir       = Join-Path $WorktreeRoot "tools\synthetic_clouds\out\aws-plane"

function Get-InstallEnvValue([string]$Name) {
    # One key of the installation's local .env (deploy/synthetic-clouds/.env), or $null.
    # The file is KEY=VALUE with # comments; a quoted value keeps its inner spaces.
    if (-not (Test-Path -LiteralPath $InstallEnv)) { return $null }
    foreach ($line in [System.IO.File]::ReadAllLines($InstallEnv)) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) { continue }
        $parts = $trimmed.Split("=", 2)
        if ($parts.Length -ne 2) { continue }
        if ($parts[0].Trim() -eq $Name) {
            return $parts[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}

function Resolve-Setting([string]$Name, [string]$Default) {
    # Process environment wins, then the installation's .env, then the built-in default.
    $fromProcess = [Environment]::GetEnvironmentVariable($Name)
    if ($fromProcess) { return $fromProcess }
    $fromFile = Get-InstallEnvValue $Name
    if ($fromFile) { return $fromFile }
    return $Default
}

$Seed       = Resolve-Setting "AWS_SIM_SEED" "123"
$AwsProfile = Resolve-Setting "AWS_SIM_PROFILE" "small"
$S3Port     = Resolve-Setting "S3_PORT" "9090"
$SimPort    = Resolve-Setting "AWS_SIM_PORT" "8086"
$Bucket     = Resolve-Setting "AWS_SIM_BUCKET" "synthetic-focus12-daily-full"
# Compose project name (podman -p) + named-volume prefix, from one source. SYNTHCLOUDS_PROJECT
# lets a parallel stack come up without colliding with the fixed-name volume a running stack
# owns. The volume name is also hardcoded in the podman cp helper below, so -p alone would not
# be enough -- both the -p flag and the $RenderVol prefix derive from this variable. Default
# (no env) stays "synthetic-clouds" -> byte-identical to today's fixed name.
$ComposeProject = if ($env:SYNTHCLOUDS_PROJECT) { $env:SYNTHCLOUDS_PROJECT } else { "synthetic-clouds" }
$RenderVol  = "${ComposeProject}_aws_sim_render"
# Length of the simulated window in days. Empty keeps the profile's own window (the historical
# behaviour); set it to reach "today" (e.g. 282 covers the canonical epoch through 2026-10-09).
$WindowDays = Resolve-Setting "AWS_SIM_WINDOW_DAYS" ""

# The generator needs the repository virtualenv: the PATH `python` on this machine is
# C:\Python314\python.exe, which has none of the generator's dependencies.
$VenvPython = Join-Path $WorktreeRoot ".venv\Scripts\python.exe"
$PythonCmd  = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }

$Plan = @(
    "1. $PythonCmd -m tools.synthetic_clouds --seed $Seed --profile $AwsProfile --emit focus_aws --out $OutDir (cwd=$WorktreeRoot)",
    "2. podman compose -f $ComposeFile up -d s3mock aws-sim (reuse the running containers; -Build rebuilds)",
    "3. wait for the S3 store at http://localhost:$S3Port/",
    "4. replace /render/aws_focus in $RenderVol with the rendered tree",
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

function Get-ServiceContainerId([string]$Service) {
    $id = (podman compose -p $ComposeProject -f $ComposeFile ps -q $Service | Select-Object -First 1)
    if ($id) { return $id.Trim() }
    return $null
}

# 1. Generate on the host. Writes under tools/synthetic_clouds/ (NFR-5 guard).
Push-Location $WorktreeRoot
try {
    Invoke-Checked "generate the AWS FOCUS 1.2 export tree" {
        $GenArgs = @("-m", "tools.synthetic_clouds", "--seed", $Seed, "--profile", $AwsProfile, "--emit", "focus_aws", "--out", $OutDir)
        if ($WindowDays) { $GenArgs += @("--window-days", $WindowDays) }
        & $PythonCmd @GenArgs
    }
} finally { Pop-Location }

# 2. Bring the plane up. The running containers are reused by default: rebuilding an
#    emulator image and recreating its containers is not part of publishing a tree, and
#    the phase that owns the images should be the one that rebuilds them.
$missing = @()
foreach ($svc in @("s3mock", "aws-sim")) {
    if (-not (Get-ServiceContainerId $svc)) { $missing += $svc }
}
if ($Build -or $missing.Count -gt 0) {
    $UpArgs = @("compose", "-p", $ComposeProject, "-f", $ComposeFile, "up", "-d")
    if ($Build) { $UpArgs += "--build" }
    # Always name the two services: `up -d` without them would touch every container of
    # the compose project, including the planes this script does not own.
    $UpArgs += @("s3mock", "aws-sim")
    Invoke-Checked "compose up s3mock + aws-sim$(if ($Build) { ' (build)' })" {
        podman @UpArgs
    }
} else {
    Write-Host "==> reusing the running s3mock + aws-sim (no image rebuild, no container recreate)"
    # The reused image must still match the sources it was built from, or the plane would
    # serve a stale estate. Say so instead of failing: publishing a tree is not the moment
    # to rebuild an image.
    try {
        # podman renders the image timestamp as "2026-10-28 14:49:03.397495799 +0000 UTC";
        # the trailing "+0000 UTC" is not a parseable offset, so it is rewritten to "+00:00".
        $rawCreated = (podman inspect --format "{{.Created}}" "docker.io/library/synthetic-clouds-aws-sim:latest" 2>$null)
        $imageCreated = [datetimeoffset]::Parse(($rawCreated -replace '\s*\+?\d{4}\s+UTC$', ' +00:00'))
        $newestSource = (Get-ChildItem -Path (Join-Path $WorktreeRoot "emulators\aws-sim") -Recurse -File |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime
        if ($newestSource -and $newestSource.ToUniversalTime() -gt $imageCreated.UtcDateTime) {
            Write-Warning "the running aws-sim image ($($imageCreated.UtcDateTime.ToString('u'))) predates the emulator sources ($($newestSource.ToUniversalTime().ToString('u'))); re-run with -Build to pick the change up."
        } else {
            Write-Host "==> the running aws-sim image ($($imageCreated.UtcDateTime.ToString('u'))) is not older than the emulator sources"
        }
    } catch {
        Write-Host "==> (image staleness not checked: $($_.Exception.Message))"
    }
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

# 4. Replace the rendered tree inside the named volume. The volume is mounted at /render
#    inside the running aws-sim, so the container itself is the writer: `podman cp` lands in
#    the volume (the cp helper runs as root), and the removal runs as root too because the
#    container's own user cannot unlink an entry of the root-owned /render.
#    REPLACING, not merging: the reader pins the newest execution PER BILLING PERIOD, so a
#    leftover period of the previous profile would be ingested next to the new one -- two
#    estates in one tree.
$ContainerId = Get-ServiceContainerId "aws-sim"
if (-not $ContainerId) { throw "aws-sim container not found (compose ps -q aws-sim was empty)" }
Invoke-Checked "remove the previous rendered tree from $RenderVol" {
    podman exec --user root $ContainerId rm -rf /render/aws_focus
}
Invoke-Checked "podman cp the rendered tree into $RenderVol" {
    podman cp "$AwsFocusDir" "${ContainerId}:/render/"
}

# 4b. Prove the volume really holds the new tree: the store root is what the aws-sim
#     serves on its own S3 surface, so listing that bucket reads the volume, not the
#     container's writable layer.
$StoreListing = "http://localhost:$SimPort/$Bucket" + "?list-type=2&max-keys=1000"
try {
    $listing = (Invoke-WebRequest -Uri $StoreListing -UseBasicParsing -TimeoutSec 15).Content
    $keyCount = ([regex]::Matches($listing, "<Key>")).Count
    Write-Host "==> store listing: $keyCount key(s) under $Bucket on the aws-sim S3 surface"
    if ($keyCount -eq 0) { throw "the rendered tree is not visible in the volume ($StoreListing returned no key)" }
} catch {
    if ($_.Exception.Message -like "the rendered tree is not visible*") { throw }
    Write-Warning "could not read the store listing ($($_.Exception.Message))"
}

# 5. Upload from INSIDE the sim, so settings stay in the container environment and never
#    appear on a command line. `compose ps -q` is the reliable way to name the container: a
#    compose-built image is tagged with the project prefix, not `aws-sim`.
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
Write-Host "    seed/profile  : $Seed / $AwsProfile"
Write-Host "    render dir    : $RenderRoot"
