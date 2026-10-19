<#
.SYNOPSIS
  Tear down the AWS synthetic-clouds plane.

.DESCRIPTION
  `compose down -v` for the AWS fragment only: it removes the aws-sim and MinIO containers
  AND their named volumes (the rendered tree and the MinIO data). The azure and GCP planes
  are untouched, because each fragment is its own compose invocation.

  This is destructive by design -- the volumes hold only synthetic artefacts that
  scripts/synthetic-clouds/aws-up.ps1 regenerates -- but it is still scoped to this
  fragment, and -WhatIf prints the command instead of running it.

.PARAMETER WhatIf
  Print the command without executing it.
#>
[CmdletBinding()]
param(
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorktreeRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$ComposeFile  = Join-Path $WorktreeRoot "deploy\synthetic-clouds\compose.aws.yaml"

if ($WhatIf) {
    Write-Host "would run: podman compose -f $ComposeFile down -v"
    exit 0
}

Write-Host "==> compose down -v ($ComposeFile)"
podman compose -f $ComposeFile down -v
if ($LASTEXITCODE -ne 0) { throw "compose down failed (exit $LASTEXITCODE)" }
Write-Host "==> AWS synthetic-clouds plane removed (containers + named volumes)."
