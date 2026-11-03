$ErrorActionPreference = 'Stop'
$probeScript = Join-Path $PSScriptRoot 'setup_check.py'
function Check-Python([string]$Executable) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $null }
    if ($Executable -like '*\WindowsApps\*') { return $null }
    try {
        $result = & $Executable $probeScript python 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        $info = $result | ConvertFrom-Json
        if ($info.valid) { return $info }
    } catch { }
    return $null
}
$applicationEnvironment = Join-Path $PSScriptRoot '.venv'
$applicationPython = Join-Path $applicationEnvironment 'Scripts\python.exe'
Write-Host 'Checking existing Python installations (Anaconda is excluded)...'
$candidates = @($applicationPython)
foreach ($command in @(Get-Command python.exe,python3.exe -All -ErrorAction SilentlyContinue)) { $candidates += $command.Source }
foreach ($registryRoot in @('HKCU:\Software\Python\PythonCore','HKLM:\Software\Python\PythonCore','HKLM:\Software\WOW6432Node\Python\PythonCore')) {
    if (Test-Path $registryRoot) {
        foreach ($versionKey in Get-ChildItem $registryRoot) {
            $installKey = Join-Path $versionKey.PSPath 'InstallPath'
            if (Test-Path $installKey) {
                $properties = Get-ItemProperty $installKey
                if ($properties.ExecutablePath) { $candidates += $properties.ExecutablePath }
                if ($properties.'(default)') { $candidates += Join-Path $properties.'(default)' 'python.exe' }
            }
        }
    }
}
foreach ($version in @('314','313','312')) {
    $candidates += Join-Path $env:LOCALAPPDATA "Programs\Python\Python$version\python.exe"
    $candidates += Join-Path $env:ProgramFiles "Python$version\python.exe"
}
$pythonInfo = $null
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    $pythonInfo = Check-Python $candidate
    if ($pythonInfo) { break }
}
if (-not $pythonInfo) {
    Write-Host 'No compatible working standalone Python found. Installing Python 3.14...'
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) { throw 'WinGet is required to install missing Python. Install Windows App Installer, then rerun Setup.cmd.' }
    $pythonRoot = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314'
    $installerOptions = '/quiet InstallAllUsers=0 Include_launcher=1 InstallLauncherAllUsers=0 Include_pip=1 Include_tcltk=1 Include_test=0 PrependPath=1 TargetDir="' + $pythonRoot + '"'
    & winget install --id Python.Python.3.14 --exact --source winget --scope user --accept-package-agreements --accept-source-agreements --disable-interactivity --override $installerOptions
    $pythonInfo = Check-Python (Join-Path $pythonRoot 'python.exe')
    if (-not $pythonInfo) { throw 'A working standalone Python could not be installed. Check the installer output above.' }
} else { Write-Host "Found Python $($pythonInfo.version): $($pythonInfo.base) - no Python installation needed." }
$standalonePython = Join-Path $pythonInfo.base 'python.exe'
if (-not (Check-Python $applicationPython)) {
    Write-Host 'Creating the application environment...'
    & $standalonePython -m venv $applicationEnvironment
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the application environment.' }
} else { Write-Host 'Application environment already works - keeping it.' }
& $applicationPython -m pip --version
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing missing pip...'
    & $applicationPython -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw 'Could not install pip.' }
}
$dependencyState = (& $applicationPython $probeScript dependencies) | ConvertFrom-Json
foreach ($installed in $dependencyState.installed) { Write-Host "Already working: $installed" }
if ($dependencyState.missing.Count -gt 0) {
    Write-Host "Installing missing or incompatible dependencies: $($dependencyState.missing -join ', ')"
    & $applicationPython -m pip install --force-reinstall @($dependencyState.missing)
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
} else { Write-Host 'All required dependencies already work - skipping installation.' }
& $applicationPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency compatibility check failed.' }
& $applicationPython (Join-Path $PSScriptRoot 'verify_setup.py')
if ($LASTEXITCODE -ne 0) { throw 'Final verification failed.' }
$baseRoot = $pythonInfo.base
$userPath = [Environment]::GetEnvironmentVariable('Path','User')
$pathParts = @($userPath -split ';' | Where-Object { $_ -and $_.TrimEnd('\') -ne $baseRoot.TrimEnd('\') -and $_.TrimEnd('\') -ne (Join-Path $baseRoot 'Scripts').TrimEnd('\') })
$newUserPath = (@($baseRoot,(Join-Path $baseRoot 'Scripts')) + $pathParts) -join ';'
if ($newUserPath -ne $userPath) { [Environment]::SetEnvironmentVariable('Path',$newUserPath,'User') }
Set-Content -LiteralPath (Join-Path $PSScriptRoot 'python-path.txt') -Value $baseRoot -Encoding Default
Write-Host 'Checking available CPU and OpenCL GPUs...'
& $applicationPython -X utf8 (Join-Path $PSScriptRoot 'hardware.py')
Write-Host 'Setup complete. Run Run.cmd. Open a fresh terminal for the updated global python command.'
