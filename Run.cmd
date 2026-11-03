@echo off
setlocal
set "PROTO_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PROTO_PY%" (
  echo Run Setup.cmd once to install standalone Python and dependencies.
  pause
  exit /b 1
)
if /i "%~1"=="devices" (
  "%PROTO_PY%" "%~dp0hardware.py"
  exit /b
)
if "%~1"=="" (
  "%PROTO_PY%" "%~dp0desktop_launcher.py"
) else (
  "%PROTO_PY%" "%~dp0opencl_lz.py" %*
)
if errorlevel 1 pause
