<#
.SYNOPSIS
  Smoke-test the AWS synthetic-clouds plane: aws-sim answers the Query protocol and the S3
  store holds the delivered FOCUS tree.

.DESCRIPTION
  Four assertions, each one a thing that can silently be absent:
    1. aws-sim responds to GET /healthz.
    2. aws-sim answers a REAL Query-protocol request (ListStacks, form-encoded, XML back)
       and the response parses as the client would see it. This exercises the protocol, not
       just the port.
    3. The bucket holds objects under the BCM layout the S3 reader looks for:
       ``<export>/data/billing_period=YYYY-MM/<execution>/``. A tree present on disk but
       never uploaded looks identical from the sim's side, so this is asserted separately.
    4. The S3 store's own ListBuckets answers on the host (the path an operator uses).

  Exits non-zero on the first failure. Run scripts/synthetic-clouds/aws-up.ps1 first.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorktreeRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$ComposeFile = Join-Path $WorktreeRoot "deploy\synthetic-clouds\compose.aws.yaml"

$SimPort = if ($env:AWS_SIM_PORT) { $env:AWS_SIM_PORT } else { "8086" }
$S3Port  = if ($env:S3_PORT) { $env:S3_PORT } else { "9090" }
$Bucket  = if ($env:AWS_SIM_BUCKET) { $env:AWS_SIM_BUCKET } else { "synthetic-focus12-daily-full" }

# 1. /healthz
$health = Invoke-WebRequest -Uri "http://localhost:$SimPort/healthz" -UseBasicParsing -TimeoutSec 5
if ($health.StatusCode -ne 200) { throw "aws-sim /healthz returned $($health.StatusCode)" }
Write-Host "[ok] aws-sim /healthz 200"

# 2. A real Query-protocol request. The version is the one botocore's service model uses;
#    hardcoding a different one here would let the emulator and the client disagree silently.
$body = @{ Action = "ListStacks"; Version = "2010-05-15" }
$resp = Invoke-WebRequest -Uri "http://localhost:$SimPort/" -Method Post -Body $body `
    -ContentType "application/x-www-form-urlencoded" -UseBasicParsing -TimeoutSec 10
if ($resp.StatusCode -ne 200) { throw "ListStacks returned $($resp.StatusCode)" }
$xml = [xml]$resp.Content
$summaries = $xml.ListStacksResponse.ListStacksResult.StackSummaries.member
if (-not $summaries -or $summaries.Count -lt 1) { throw "ListStacks returned no stacks; the control plane is not answering" }
$stackName = $summaries[0].StackName
if (-not $stackName.StartsWith("synth-")) { throw "unexpected stack name '$stackName'" }
Write-Host "[ok] ListStacks parsed: $($summaries.Count) stack(s), first '$stackName'"

# 3. The delivered tree, read over the S3 API the same way the reader would. ListObjectsV2 on
#    the bucket; the keys must carry the BCM layout, which is what proves the uploader
#    preserved it rather than flattening it.
$listUrl = "http://localhost:$S3Port/$Bucket`?list-type=2"
$list = Invoke-WebRequest -Uri $listUrl -UseBasicParsing -TimeoutSec 10
if ($list.StatusCode -ne 200) { throw "ListObjectsV2 returned $($list.StatusCode) for bucket '$Bucket'" }
$keys = ([regex]'<Key>([^<]+)</Key>').Matches($list.Content) | ForEach-Object { $_.Groups[1].Value }
if (-not $keys) { throw "no objects in bucket '$Bucket'; was the uploader run?" }
$dataKeys = $keys | Where-Object { $_ -match 'billing_period=\d{4}-\d{2}/' }
if (-not $dataKeys) { throw "objects present but none under billing_period=; the BCM layout is wrong" }
$executionKeys = $dataKeys | Where-Object { $_ -match '\d{8}T\d{6}Z-' }
if (-not $executionKeys) { throw "no execution directory in the keys; the emitter layout is wrong" }
Write-Host "[ok] bucket '$Bucket' holds $($keys.Count) object(s), $($executionKeys.Count) under the BCM execution layout"

# 4. The store answers on the host, which is the path an operator uses.
$store = Invoke-WebRequest -Uri "http://localhost:$S3Port/" -UseBasicParsing -TimeoutSec 5
if ($store.StatusCode -ne 200) { throw "S3 ListBuckets returned $($store.StatusCode)" }
Write-Host "[ok] S3 ListBuckets 200 on http://localhost:$S3Port"

Write-Host "`n==> AWS smoke passed."
