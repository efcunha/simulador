<#
.SYNOPSIS
  Tear down the GCP synthetic-clouds plane (Phase 3): compose down -v.

.DESCRIPTION
  Stops and removes the bigquery-emulator, gcp-bq-provision, and gcp-sim
  containers and deletes the named volumes (gcp_bq_data, gcp_provision,
  gcp_sim_fixtures). Idempotent.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorktreeRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$ComposeFile  = Join-Path $WorktreeRoot "deploy\synthetic-clouds\compose.gcp.yaml"
# Mirror gcp-up.ps1's project override so the teardown hits the SAME stack the up brought up.
# Default (no env) stays "synthetic-clouds" -> byte-identical to today's behaviour.
$ComposeProject = if ($env:SYNTHCLOUDS_PROJECT) { $env:SYNTHCLOUDS_PROJECT } else { "synthetic-clouds" }

Write-Host "==> podman compose down -v ($ComposeFile)"
podman compose -p $ComposeProject -f $ComposeFile down -v
Write-Host "==> GCP synthetic-clouds plane torn down."
