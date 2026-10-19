#Requires -Version 5.1
<#
.SYNOPSIS
    Trigger a one-time Cost Management export inside the running azure-sim
    container and optionally extract its blobs via `podman cp`.

.DESCRIPTION
    Runs `podman compose exec azure-sim python -m azure_sim export ...` so a
    single export run writes into Azurite over the network. If -OutDir is given,
    the resulting blobs are copied OUT of the azure-sim container with
    `podman cp` — NEVER a D:\ bind mount (design §6.4).

    Supports -WhatIf (via SupportsShouldProcess): every podman invocation is
    gated by $PSCmdlet.ShouldProcess, so `-WhatIf` prints the planned commands
    and executes nothing. Parses and runs under
    `pwsh -NoProfile -File ... -WhatIf` without podman installed.

.PARAMETER Schedule
    Export schedule to run: one-time | daily | monthly. Default: one-time.

.PARAMETER Exports
    Comma list of export types to emit (focus,actual,amortized). Optional —
    falls through to the container's EXPORTS env when omitted.

.PARAMETER Format
    Comma list of file formats (csv,parquet). Optional — falls through to env.

.PARAMETER Service
    Compose service name to exec into. Default: azure-sim.

.PARAMETER OutDir
    If set, `podman cp` the export output from the container to this host dir
    after the run (uses podman cp, not a bind mount, §6.4).

.PARAMETER ContainerExportPath
    In-container path to copy from when -OutDir is set. Default: /tmp/azure-sim-export.

.PARAMETER ComposeFile
    Path to the compose file. Defaults to deploy/synthetic-clouds/compose.yaml
    resolved relative to this script.

.EXAMPLE
    pwsh -NoProfile -File scripts/synthetic-clouds/export_once.ps1 -WhatIf
    pwsh -NoProfile -File scripts/synthetic-clouds/export_once.ps1
    pwsh -NoProfile -File scripts/synthetic-clouds/export_once.ps1 -Exports focus -Format csv,parquet
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("one-time", "daily", "monthly")]
    [string]$Schedule = "one-time",
    [string]$Exports,
    [string]$Format,
    [string]$Service = "azure-sim",
    [string]$OutDir,
    [string]$ContainerExportPath = "/tmp/azure-sim-export",
    [string]$ComposeFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ComposeFile)) {
    $root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
    $ComposeFile = Join-Path $root "deploy\synthetic-clouds\compose.yaml"
}

Write-Host "[export_once] compose file: $ComposeFile"

if (-not (Test-Path $ComposeFile)) {
    throw "compose file not found: $ComposeFile"
}

$podman = Get-Command podman -ErrorAction SilentlyContinue
$podmanCompose = Get-Command podman-compose -ErrorAction SilentlyContinue

function Invoke-Podman {
    param(
        [string[]]$PodmanArgs,
        [switch]$UseCompose
    )

    if ($UseCompose) {
        $display = "podman compose -f `"$ComposeFile`" " + ($PodmanArgs -join " ")
    }
    else {
        $display = "podman " + ($PodmanArgs -join " ")
    }

    if ($PSCmdlet.ShouldProcess($display, "podman")) {
        if ($null -ne $podman) {
            if ($UseCompose) {
                & podman compose -f $ComposeFile @PodmanArgs
            }
            else {
                & podman @PodmanArgs
            }
            if ($LASTEXITCODE -ne 0) { throw "podman failed (exit $LASTEXITCODE): $display" }
        }
        elseif ($UseCompose -and $null -ne $podmanCompose) {
            & podman-compose -f $ComposeFile @PodmanArgs
            if ($LASTEXITCODE -ne 0) { throw "podman-compose failed (exit $LASTEXITCODE): $display" }
        }
        else {
            throw "podman is not available on PATH"
        }
    }
    else {
        Write-Host "[dry-run] $display"
    }
}

# Build the in-container export command. Only pass flags the caller set; the rest
# fall through to the container's env (config.py defaults).
$execArgs = @("exec", $Service, "python", "-m", "azure_sim", "export", "--schedule", $Schedule)
if (-not [string]::IsNullOrWhiteSpace($Exports)) { $execArgs += @("--exports", $Exports) }
if (-not [string]::IsNullOrWhiteSpace($Format)) { $execArgs += @("--format", $Format) }

Write-Host "[export_once] running export (schedule=$Schedule) in service '$Service'"
Invoke-Podman -UseCompose -PodmanArgs $execArgs

if (-not [string]::IsNullOrWhiteSpace($OutDir)) {
    Write-Host "[export_once] copying export output to $OutDir via podman cp (no bind mount, §6.4)"
    if ($PSCmdlet.ShouldProcess($OutDir, "create host output dir")) {
        New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    }
    else {
        Write-Host "[dry-run] New-Item -ItemType Directory -Force -Path $OutDir"
    }
    # podman cp <container>:<path> <hostDir>. The container id is resolved by
    # compose; use the service name as the container reference for the dry display.
    Invoke-Podman -PodmanArgs @("cp", "$($Service):$ContainerExportPath", $OutDir)
}

Write-Host "[export_once] done."
