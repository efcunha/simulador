#Requires -Version 5.1
<#
.SYNOPSIS
    Build and start the synthetic-clouds azure-sim stack via Podman compose.

.DESCRIPTION
    Wraps `podman compose` for deploy/synthetic-clouds/compose.yaml:
      - builds the azure-sim image (build context = worktree root),
      - starts azurite + azure-sim with named volumes (NO C:\Projetos\ bind mounts, §6.4),
      - optionally tears the stack down first.

    Supports -WhatIf (via SupportsShouldProcess): every podman invocation is
    gated by $PSCmdlet.ShouldProcess, so `-WhatIf` prints the planned commands
    and executes nothing. The script also parses and runs end-to-end under
    `pwsh -NoProfile -File ... -WhatIf` without podman installed.

.PARAMETER Detached
    Start detached (-d). Default: on. Use -Detached:$false to stream logs.

.PARAMETER Build
    Force an image (re)build before up. Default: on.

.PARAMETER Down
    Stop and remove the stack instead of starting it.

.PARAMETER ComposeFile
    Path to the compose file. Defaults to deploy/synthetic-clouds/compose.yaml
    resolved relative to this script.

.EXAMPLE
    pwsh -NoProfile -File scripts/synthetic-clouds/run_azure_sim.ps1 -WhatIf
    pwsh -NoProfile -File scripts/synthetic-clouds/run_azure_sim.ps1
    pwsh -NoProfile -File scripts/synthetic-clouds/run_azure_sim.ps1 -Down
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$Detached = $true,
    [switch]$Build = $true,
    [switch]$Down,
    [string]$ComposeFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Resolve the compose file relative to this script (scripts/synthetic-clouds/ ->
# ../../deploy/synthetic-clouds/compose.yaml) when not supplied.
if ([string]::IsNullOrWhiteSpace($ComposeFile)) {
    $root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
    $ComposeFile = Join-Path $root "deploy\synthetic-clouds\compose.yaml"
}

Write-Host "[run_azure_sim] compose file: $ComposeFile"

if (-not (Test-Path $ComposeFile)) {
    throw "compose file not found: $ComposeFile"
}

# Prefer `podman compose`; fall back to `podman-compose`. Detection is best-effort
# and never fatal under -WhatIf (dry mode does not execute podman).
$podman = Get-Command podman -ErrorAction SilentlyContinue
$podmanCompose = Get-Command podman-compose -ErrorAction SilentlyContinue

function Invoke-Compose {
    param([string[]]$ComposeArgs)

    $display = "podman compose -f `"$ComposeFile`" " + ($ComposeArgs -join " ")
    if ($PSCmdlet.ShouldProcess($display, "podman compose")) {
        if ($null -ne $podman) {
            & podman compose -f $ComposeFile @ComposeArgs
            if ($LASTEXITCODE -ne 0) { throw "podman compose failed (exit $LASTEXITCODE): $display" }
        }
        elseif ($null -ne $podmanCompose) {
            & podman-compose -f $ComposeFile @ComposeArgs
            if ($LASTEXITCODE -ne 0) { throw "podman-compose failed (exit $LASTEXITCODE): $display" }
        }
        else {
            throw "neither 'podman compose' nor 'podman-compose' is available on PATH"
        }
    }
    else {
        Write-Host "[dry-run] $display"
    }
}

if ($Down) {
    Write-Host "[run_azure_sim] tearing down the stack"
    Invoke-Compose -ComposeArgs @("down")
    return
}

if ($Build) {
    Write-Host "[run_azure_sim] building image(s)"
    Invoke-Compose -ComposeArgs @("build")
}

$upArgs = @("up")
if ($Detached) { $upArgs += "-d" }
Write-Host "[run_azure_sim] starting the stack"
Invoke-Compose -ComposeArgs $upArgs

Write-Host "[run_azure_sim] done. API: http://localhost:8080/healthz  Blob: http://localhost:10000/devstoreaccount1"
