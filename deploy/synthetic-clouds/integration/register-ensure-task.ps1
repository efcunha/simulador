#Requires -Version 7
<#
.SYNOPSIS
    Register (or refresh) the scheduled task that keeps the CloudPilot <-> simulator
    integration re-applied after logon and every N minutes.

.DESCRIPTION
    Registers a PER-USER task (logon trigger + repetition), the same shape as the
    existing ``simulador-nuvem-daily`` task. Scoping the logon trigger to the
    logged-on user is what makes ``schtasks /Create`` an ordinary per-user
    registration; a machine-wide logon trigger is the operation that answers
    "Acesso negado" without elevation.

    The task runs ensure-cloudpilot.ps1 at logon and then every -EveryMinutes. The
    script is idempotent: it only reconnects a network endpoint when an alias is
    missing and only rebuilds the azure-sim estate when the window is stale.

.PARAMETER EveryMinutes
    Repetition interval (default 30). Must be >= 5.

.PARAMETER RunNow
    Start the task immediately after registering it.

.EXAMPLE
    .\register-ensure-task.ps1 -RunNow
    Get-ScheduledTaskInfo -TaskName CloudPilot-Simulator-Ensure
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'CloudPilot-Simulator-Ensure',
    [ValidateRange(5, 1440)][int]$EveryMinutes = 30,
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'

$Wrapper = Join-Path $PSScriptRoot 'run-ensure.cmd'
if (-not (Test-Path $Wrapper)) { throw "wrapper not found: $Wrapper" }

$UserId = '{0}\{1}' -f $env:USERDOMAIN, $env:USERNAME
$Interval = 'PT{0}M' -f $EveryMinutes
$SchTasks = Join-Path $env:SystemRoot 'System32\schtasks.exe'

# UTF-16 (with BOM) is what schtasks /XML expects to read.
$Xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Idempotent ensure for the CloudPilot &lt;-&gt; synthetic-clouds integration (DNS aliases, CA trust, estate window).</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>$UserId</UserId>
      <Repetition>
        <Interval>$Interval</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$UserId</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT45M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>/c "$Wrapper"</Arguments>
    </Exec>
  </Actions>
</Task>
"@

$XmlPath = Join-Path $env:TEMP ("{0}-{1}.xml" -f $TaskName, ([guid]::NewGuid().ToString('N')))
Set-Content -Path $XmlPath -Value $Xml -Encoding Unicode -NoNewline

try {
    & $SchTasks /Create /TN $TaskName /XML $XmlPath /F 2>&1 | Out-String | Write-Host
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks /Create failed with exit $LASTEXITCODE. Run this script from an elevated shell, or use the Startup-folder fallback (see README)."
    }
} finally {
    Remove-Item -Force $XmlPath -ErrorAction SilentlyContinue
}

Write-Host "Registered task '$TaskName' (logon + every $EveryMinutes min) as $UserId."
Write-Host "  wrapper: $Wrapper"

if ($RunNow) {
    & $SchTasks /Run /TN $TaskName | Out-Host
    Start-Sleep -Seconds 5
}

Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State | Format-Table -AutoSize
Get-ScheduledTaskInfo -TaskName $TaskName | Select-Object LastRunTime, LastTaskResult, NextRunTime | Format-Table -AutoSize
