@echo off
rem Wrapper so Task Scheduler can launch the ensure script without quoting hell.
rem Used by register-ensure-task.ps1 (schtasks /TR takes one command line).
set "PWSH=%ProgramFiles%\PowerShell\7\pwsh.exe"
if not exist "%PWSH%" set "PWSH=pwsh.exe"
rem Task Scheduler starts with the user's PATH; add the per-user Podman dir as a
rem fallback so `podman` resolves even if PATH was customized.
set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Podman"
"%PWSH%" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "D:\Simulador\deploy\synthetic-clouds\integration\ensure-cloudpilot.ps1" -Quiet
exit /b %ERRORLEVEL%
