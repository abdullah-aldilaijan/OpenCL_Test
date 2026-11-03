@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup.ps1"
if errorlevel 1 exit /b 1
set /p "OPENCL_PYTHON_ROOT="<"%~dp0python-path.txt"
set "PATH=%OPENCL_PYTHON_ROOT%;%OPENCL_PYTHON_ROOT%\Scripts;%PATH%"
python --version
