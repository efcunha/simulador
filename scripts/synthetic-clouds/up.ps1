<#
.SYNOPSIS
  Bring up ALL THREE synthetic-clouds planes (Azure, GCP, AWS) with one command (AC-19).

.DESCRIPTION
  The single entry point the acceptance criterion names. Each cloud keeps its own compose
  fragment -- the hardened azure and GCP definitions are NOT re-opened or merged, because
  merging them is what the phase decisions deliberately avoided (A0.9 decision 2) -- and
  this script only sequences the three bring-ups.

    * Azure  -- podman compose -f compose.yaml up -d  (Azurite + azure-sim)
    * GCP    -- scripts/synthetic-clouds/gcp-up.ps1   (emulator + fixture provisioning)
    * AWS    -- scripts/synthetic-clouds/aws-up.ps1   (MinIO + aws-sim + artefact upload)

  Failures are reported per cloud and the script exits non-zero if any plane failed, so a
  partially-up stack is never reported as success.

.PARAMETER DryRun
  Print the plan without executing anything.

.PARAMETER Skip
  Comma-separated clouds to skip, e.g. -Skip gcp,aws. Useful when only one plane changed.
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [string]$Skip = ""
)

$ErrorActionPreference = "Continue"   # each plane is reported independently
Set-StrictMode -Version Latest

$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorktreeRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$AzureCompose = Join-Path $WorktreeRoot "deploy\synthetic-clouds\compose.yaml"
# Compose project override. The azure compose.yaml carries name: synthetic-clouds, which -p
# overrides; the gcp/aws sub-scripts inherit SYNTHCLOUDS_PROJECT from this process, so one env
# var moves all three planes to a parallel stack. Default (no env) stays "synthetic-clouds".
$ComposeProject = if ($env:SYNTHCLOUDS_PROJECT) { $env:SYNTHCLOUDS_PROJECT } else { "synthetic-clouds" }

$skipped = @($Skip.Split(",") | Where-Object { $_ -ne "" } | ForEach-Object { $_.Trim().ToLower() })

$Plan = @(
    "azure: podman compose -p $ComposeProject -f $AzureCompose up -d",
    "gcp  : $ScriptDir\gcp-up.ps1",
    "aws  : $ScriptDir\aws-up.ps1"
)

if ($DryRun) {
    Write-Host "DRY RUN -- ordered plan:`n"
    $Plan | ForEach-Object { Write-Host "  $_" }
    if ($skipped.Count) { Write-Host "`n  skipping: $($skipped -join ', ')" }
    exit 0
}

$failures = @()

function Invoke-Plane([string]$Name, [scriptblock]$Block) {
    if ($skipped -contains $Name) { Write-Host "==> $Name skipped (-Skip)"; return }
    Write-Host "`n==> bring up $Name"
    & $Block
    if ($LASTEXITCODE -ne 0) { $script:failures += "$Name (exit $LASTEXITCODE)" }
}

Invoke-Plane "azure" { podman compose -p $ComposeProject -f $AzureCompose up -d }
Invoke-Plane "gcp" { & (Join-Path $ScriptDir "gcp-up.ps1") }
Invoke-Plane "aws" { & (Join-Path $ScriptDir "aws-up.ps1") }

Write-Host ""
if ($failures.Count) {
    Write-Host "==> FAILED: $($failures -join '; ')"
    exit 1
}
Write-Host "==> all requested planes are up."
Write-Host "    azure : $(if ($env:API_PORT) { $env:API_PORT } else { '8080' })   gcp : $(if ($env:GCP_SIM_PORT) { $env:GCP_SIM_PORT } else { '8085' })   aws : $(if ($env:AWS_SIM_PORT) { $env:AWS_SIM_PORT } else { '8086' })"
