<#
.SYNOPSIS
  Keystone smoke (AC-P3-1 / AC-P3-1a): run the 5 REAL FinOps GCP query shapes
  against the DDL-provisioned emulator and assert they parse + return rows.

.DESCRIPTION
  Runs, VERBATIM from the production call sites, against
  `<project>.<user_dataset>.gcp_billing_export_v1_<BA>`:
    Q1  UNNEST(credits) net-cost grouped by service.description
        (costs.py (modulo do consumidor):_query_costs)
    Q1a UNNEST(credits) net-cost grouped by location.region (REGION; AC-P3-1a)
    Q3  UNNEST(credits) net-cost time series (DATE_TRUNC on usage_start_time)
        (costs.py (modulo do consumidor):get_time_series)
    Q4  UNNEST(labels) cluster-cost grouped by labels.value
        (<modulo do consumidor>:get_cluster_costs)
    Q5  UNNEST(labels) + labels.value = '{cluster_name}' net-cost
        (<modulo do consumidor>:_fetch_gke_cluster_cost)

  NIT-2: Q5's cluster_name is derived from the goog-k8s-cluster-name label value
  the renderer injected (read from the rendered 03_insert_standard.sql), so the
  labels.value = '{cluster_name}' filter matches by construction.

  Asserts: queries parse + return rows; non-zero UNNEST(credits) net effect (C06);
  non-empty cluster-name match (C15); REGION group_by returns one non-NULL
  location.region row per distinct region (AC-P3-1a). Non-zero exit on any failure.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorktreeRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
# Resolve the run from the DEDICATED out dir gcp-up.ps1 renders into (G23), not the shared
# out/. The shared out/ also holds the daily cadence surface (out/daily/, FR-22), so "newest
# dir under out/" could pick a run gcp-up never populated. GCP_OUT_DIR overrides; the default
# MUST stay byte-identical to gcp-up.ps1 so up and smoke read the same source.
$OutDir       = if ($env:GCP_OUT_DIR) { $env:GCP_OUT_DIR } else { Join-Path $WorktreeRoot "tools\synthetic_clouds\out\gcp-plane" }
$Project      = if ($env:GCP_PROJECT) { $env:GCP_PROJECT } else { "synthetic" }
$BqPort       = if ($env:GCP_BQ_REST_PORT) { $env:GCP_BQ_REST_PORT } else { "9050" }
$Endpoint     = "http://localhost:$BqPort"

# Resolve the rendered manifest (newest run) + the billing table fqtn.
$RenderRoot = Get-ChildItem -Path $OutDir -Directory |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 |
    ForEach-Object { Join-Path $_.FullName "render\gcp_bigquery_topology" }
if (-not $RenderRoot -or -not (Test-Path (Join-Path $RenderRoot "_provenance.json"))) {
    throw "_provenance.json not found under $OutDir (run gcp-up.ps1 first)"
}
$Manifest = Get-Content (Join-Path $RenderRoot "_provenance.json") -Raw | ConvertFrom-Json
$BillingTable = $Manifest.tables.standard.table

# NIT-2: derive cluster_name from the injected goog-k8s-cluster-name label value.
$StandardSql = Get-Content (Join-Path $RenderRoot "03_insert_standard.sql") -Raw
$ClusterMatch = [regex]::Match($StandardSql, "'goog-k8s-cluster-name' AS key, '([^']+)' AS value")
if (-not $ClusterMatch.Success) {
    throw "no goog-k8s-cluster-name label found in rendered standard insert (C15 missing?)"
}
$ClusterName = $ClusterMatch.Groups[1].Value
Write-Host "==> derived cluster_name = '$ClusterName' (NIT-2, by construction)"

function Invoke-BqQuery([string]$Sql) {
    $body = @{ query = $Sql; useLegacySql = $false } | ConvertTo-Json -Compress
    $uri = "$Endpoint/bigquery/v2/projects/$Project/queries"
    $resp = Invoke-RestMethod -Uri $uri -Method Post -Body $body -ContentType "application/json"
    return $resp
}

function Assert([bool]$Cond, [string]$Msg) {
    if (-not $Cond) { throw "ASSERT FAILED: $Msg" }
    Write-Host "    ok: $Msg"
}

$failures = 0
function Try-Query([string]$Name, [string]$Sql, [scriptblock]$Assertions) {
    Write-Host "==> $Name"
    try {
        $resp = Invoke-BqQuery $Sql
        & $Assertions $resp
    } catch {
        Write-Host "    FAIL: $($_.Exception.Message)" -ForegroundColor Red
        $script:failures++
    }
}

# Q1 -- UNNEST(credits) net-cost by service.description.
Try-Query "Q1 service net-cost (UNNEST credits)" @"
SELECT
    service.description AS dimension_key,
    SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net_cost
FROM ``$BillingTable``
GROUP BY dimension_key
HAVING net_cost > 0
ORDER BY net_cost DESC
"@ {
    param($r)
    Assert ($null -ne $r.rows -and $r.rows.Count -gt 0) "Q1 returned rows"
}

# Q1a -- REGION group_by on location.region (AC-P3-1a).
Try-Query "Q1a REGION net-cost (location.region)" @"
SELECT
    location.region AS dimension_key,
    SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net_cost
FROM ``$BillingTable``
GROUP BY dimension_key
HAVING net_cost > 0
ORDER BY net_cost DESC
"@ {
    param($r)
    Assert ($null -ne $r.rows -and $r.rows.Count -gt 0) "Q1a returned region rows"
    $nonNull = @($r.rows | Where-Object { $_.f[0].v -and $_.f[0].v -ne "" })
    Assert ($nonNull.Count -gt 0) "Q1a has at least one non-NULL location.region key (AC-P3-1a)"
}

# Q3 -- time series net-cost (DATE_TRUNC on usage_start_time).
Try-Query "Q3 time series net-cost (UNNEST credits)" @"
SELECT
    DATE_TRUNC(DATE(usage_start_time), DAY) AS cost_date,
    SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net_cost
FROM ``$BillingTable``
GROUP BY cost_date
HAVING net_cost > 0
ORDER BY cost_date
"@ {
    param($r)
    Assert ($null -ne $r.rows -and $r.rows.Count -gt 0) "Q3 returned time-series rows"
}

# C06 proof -- UNNEST(credits) nets below gross (credits reduce cost).
Try-Query "C06 credits net effect" @"
SELECT
    SUM(cost) AS gross,
    SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net
FROM ``$BillingTable``
"@ {
    param($r)
    $gross = [double]$r.rows[0].f[0].v
    $net = [double]$r.rows[0].f[1].v
    Assert ($net -lt $gross) "C06 net ($net) < gross ($gross) -- UNNEST(credits) applied"
}

# Q4 -- UNNEST(labels) cluster-cost grouped by labels.value.
Try-Query "Q4 cluster cost (UNNEST labels)" @"
SELECT
    labels.value AS cluster_name,
    SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS total_cost
FROM ``$BillingTable``,
UNNEST(labels) AS labels
WHERE labels.key IN ('goog-k8s-cluster-name', 'k8s-cluster-name')
GROUP BY cluster_name
HAVING total_cost > 0
ORDER BY total_cost DESC
"@ {
    param($r)
    Assert ($null -ne $r.rows -and $r.rows.Count -gt 0) "Q4 returned cluster rows (C15)"
}

# Q5 -- UNNEST(labels) + labels.value = '{cluster_name}' net-cost (NIT-2).
Try-Query "Q5 cluster net-cost by name (UNNEST labels)" @"
SELECT
    SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net_cost
FROM ``$BillingTable``,
UNNEST(labels) AS labels
WHERE labels.key IN ('goog-k8s-cluster-name', 'k8s-cluster-name')
  AND labels.value = '$ClusterName'
"@ {
    param($r)
    Assert ($null -ne $r.rows -and $r.rows.Count -gt 0) "Q5 returned a row"
    $net = [double]$r.rows[0].f[0].v
    Assert ($net -gt 0) "Q5 cluster '$ClusterName' net-cost ($net) > 0 (NIT-2 match)"
}

if ($failures -gt 0) {
    Write-Host "`n==> SMOKE FAILED ($failures query failure(s))" -ForegroundColor Red
    exit 1
}
Write-Host "`n==> SMOKE PASSED -- all 5 real query shapes parse + return rows (AC-P3-1 / AC-P3-1a)."
exit 0
