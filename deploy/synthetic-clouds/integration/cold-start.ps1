#Requires -Version 7
<#
.SYNOPSIS
    One command that brings the whole local environment back after the podman
    machine was stopped (or Windows rebooted).

.DESCRIPTION
    WHY THIS EXISTS (measured 2026-10-28 on this host):

      * `podman machine stop` kills every container, and NOTHING restarts them
        when the machine comes back -- not even the ones with
        `restart=unless-stopped`. The restart policy is honoured only while
        the service lives; it does not survive the service lifecycle.
      * The emulators must also be re-attached to the CloudPilot bridge
        (`cloudpilot-deploy_cloudpilot_net`) with their DNS aliases, or the
        TLS front crash-loops with `host not found in upstream
        "bigquery-emulator:9050"`. `ensure-cloudpilot.ps1` owns that step.
      * There are THREE controllers for the same machine on this host: the
        Podman Desktop GUI, the scheduled task `CloudPilot-Simulator-Ensure`
        and the CLI. Two of them starting the machine at the same time makes
        the loser fail with `unable to start "podman-machine-default":
        already running` (exit 125) -- which is harmless, but the GUI shows
        it as a red error dialog. This script tolerates it instead of
        racing.

    ORDER MATTERS: machine -> CloudPilot stack -> simulators -> integration.
    The simulators' compose must not start before the CloudPilot bridge
    exists, and the integration step must come last (it is what attaches the
    emulators to that bridge).

.PARAMETER SkipSimulators
    Only bring back the CloudPilot stack (no azure/gcp/aws simulators).

.PARAMETER SkipIntegration
    Skip the ensure-cloudpilot step (aliases/CA/estate).

.PARAMETER SkipMachine
    Assume the podman machine is already running.

.EXAMPLE
    .\cold-start.ps1
    .\cold-start.ps1 -SkipSimulators
#>
[CmdletBinding()]
param(
    [switch]$SkipSimulators,
    [switch]$SkipIntegration,
    [switch]$SkipMachine
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$IntegrationDir = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $IntegrationDir '..\..\..')).Path
$CloudPilotRoot = 'D:\cloudpilot-deploy'
$ComposeLocal = Join-Path $CloudPilotRoot 'scripts\compose-local.ps1'
$SimulatorsUp = Join-Path $RepoRoot 'scripts\synthetic-clouds\up.ps1'
$EnsureScript = Join-Path $IntegrationDir 'ensure-cloudpilot.ps1'

$PodmanBin = Join-Path $env:LOCALAPPDATA 'Programs\Podman\podman.exe'
if (-not (Test-Path $PodmanBin)) { $PodmanBin = 'podman' }
$env:PODMAN_COMPOSE_WARNING_LOGS = 'false'

$script:Problems = [System.Collections.Generic.List[string]]::new()

function Write-Step([string]$Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Problem([string]$Message) {
    $script:Problems.Add($Message) | Out-Null
    Write-Host "    [PROBLEMA] $Message" -ForegroundColor Red
}

function Test-PodmanResponding {
    & $PodmanBin info *> $null
    return ($LASTEXITCODE -eq 0)
}

function Remove-OrphanProxies {
    # A gvproxy left alive by an ABNORMAL end (crash, Hyper-V stop, killed
    # Podman Desktop) keeps the named pipe `\\.\pipe\podman-machine-default`
    # and an old SSH port, and then `podman machine start` fails with
    # "could not start api proxy since expected pipe is not available".
    # Only ever called when the machine is NOT running -- killing the proxy
    # of a healthy machine would break it.
    $orphans = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq 'gvproxy.exe' -or $_.CommandLine -match 'machine server9p' })
    if ($orphans.Count -eq 0) { return $false }
    Write-Host "    limpando $($orphans.Count) processo(s) proxy orfao(s) (gvproxy / machine server9p)" -ForegroundColor Yellow
    foreach ($p in $orphans) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    return $true
}

function Start-MachineIfNeeded {
    Write-Step 'podman machine'
    if (Test-PodmanResponding) {
        Write-Host '    a maquina ja responde (running) - nada a fazer' -ForegroundColor DarkGray
        return $true
    }

    $cleaned = Remove-OrphanProxies
    Write-Host '    iniciando a maquina...'
    & $PodmanBin machine start *> $null
    $rc = $LASTEXITCODE
    if ($rc -ne 0) {
        # "already running" means another controller (the Podman Desktop GUI,
        # the scheduled task, another shell) won the race. The machine being
        # up is exactly what we wanted, so this is NOT a failure.
        & $PodmanBin machine inspect --format '{{.State}}' *> $null
        $state = (& $PodmanBin machine inspect --format '{{.State}}' 2>$null)
        if ("$state".Trim() -eq 'running') {
            Write-Host '    outra instancia iniciou a maquina primeiro (already running) - aceitavel' -ForegroundColor Yellow
        } else {
            Write-Host "    `podman machine start` falhou (exit $rc) sem estado 'running'" -ForegroundColor Yellow
        }
    }

    for ($i = 0; $i -lt 60; $i++) {
        if (Test-PodmanResponding) {
            Write-Host '    maquina respondendo' -ForegroundColor Green
            return $true
        }
        Start-Sleep -Seconds 3
    }
    Write-Problem 'a maquina podman nao respondeu apos 180s'
    return $false
}

function Invoke-Step([string]$Label, [string]$ScriptPath, [string[]]$ScriptArgs) {
    Write-Step $Label
    if (-not (Test-Path $ScriptPath)) {
        Write-Problem "script ausente: $ScriptPath"
        return $false
    }
    & pwsh.exe -NoProfile -File $ScriptPath @ScriptArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Problem "$Label falhou (exit $LASTEXITCODE)"
        return $false
    }
    return $true
}

function Show-Summary {
    Write-Host ''
    Write-Host '=== estado final ===' -ForegroundColor Cyan
    $rows = @(
        @{ label = 'CloudPilot frontend'; url = 'http://localhost:5174/' },
        @{ label = 'CloudPilot API';      url = 'http://localhost:8000/health' },
        @{ label = 'CIP API';             url = 'http://localhost:8001/health' },
        @{ label = 'azure-sim';           url = 'http://localhost:8080/healthz' },
        @{ label = 'gcp-sim';             url = 'http://localhost:8085/healthz' },
        @{ label = 'aws-sim';             url = 'http://localhost:8086/healthz' }
    )
    foreach ($r in $rows) {
        try {
            $resp = Invoke-WebRequest -Uri $r.url -UseBasicParsing -TimeoutSec 8
            Write-Host ("    {0,-20} {1}" -f $r.label, $resp.StatusCode) -ForegroundColor Green
        } catch {
            Write-Host ("    {0,-20} FALHOU" -f $r.label) -ForegroundColor Red
            $script:Problems.Add("endpoint $($r.label) nao respondeu") | Out-Null
        }
    }

    Write-Host ''
    Write-Host '=== containers ===' -ForegroundColor Cyan
    & $PodmanBin ps -a --format '{{.Names}} | {{.Status}}' 2>$null | Sort-Object | ForEach-Object {
        Write-Host "    $_"
    }
}

# ── main ────────────────────────────────────────────────────────────────────
Write-Host '=== cold start: CloudPilot + simuladores ===' -ForegroundColor Cyan

if (-not $SkipMachine) {
    if (-not (Start-MachineIfNeeded)) {
        Show-Summary
        Write-Host ''
        Write-Host 'FALHOU: a maquina podman nao subiu.' -ForegroundColor Red
        exit 2
    }
} else {
    Write-Step 'podman machine (assumida no ar)'
}

Invoke-Step 'stack CloudPilot + CIP' $ComposeLocal @('-Action', 'up') | Out-Null

if (-not $SkipSimulators) {
    Invoke-Step 'planos de nuvem sintetica (azure/gcp/aws)' $SimulatorsUp @() | Out-Null
} else {
    Write-Step 'planos de nuvem sintetica (pulados)'
}

if (-not $SkipIntegration) {
    Invoke-Step 'integracao CloudPilot <-> simulador (aliases/CA/estate)' $EnsureScript @('-Quiet') | Out-Null
} else {
    Write-Step 'integracao (pulada)'
}

Show-Summary

Write-Host ''
if ($script:Problems.Count -eq 0) {
    Write-Host 'COLD START OK - ambiente completo.' -ForegroundColor Green
    exit 0
}
Write-Host ("COLD START COM {0} PROBLEMA(S):" -f $script:Problems.Count) -ForegroundColor Red
foreach ($p in $script:Problems) { Write-Host "  - $p" }
exit 1
