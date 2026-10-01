@echo off
setlocal

if "%~1"=="" (
  echo Usage: %~nx0 create ^| delete [additional PowerShell arguments]
  exit /b 1
)

set "ACTION=%~1"
shift

if /I "%ACTION%"=="create" (
  set "ACTION_ARG=-Action create"
) else if /I "%ACTION%"=="delete" (
  set "ACTION_ARG=-Action delete"
) else (
  echo Invalid action: %ACTION%
  echo Usage: %~nx0 create ^| delete [additional PowerShell arguments]
  exit /b 1
)

set "ARGS="
:parse
if "%~1"=="" goto run
set "ARGS=%ARGS% %~1"
shift
goto parse

:run
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gcp-trackb.ps1" %ACTION_ARG% %ARGS%
exit /b %ERRORLEVEL%
