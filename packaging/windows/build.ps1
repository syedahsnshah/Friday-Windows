$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path "$PSScriptRoot\..\..")
function Run-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
Write-Host 'FRIDAY 56.0.0 - techobux - Windows Setup build'
$Python = (Get-Command python -ErrorAction Stop).Source
Run-Checked $Python @('-c', 'import sys,struct; assert sys.version_info[:2] == (3,11) and struct.calcsize("P") == 8, "Use 64-bit Python 3.11"')
if (-not (Test-Path '.venv-windows\Scripts\python.exe')) {
    Run-Checked $Python @('-m', 'venv', '.venv-windows')
}
$Python = (Resolve-Path '.venv-windows\Scripts\python.exe').Path
Run-Checked $Python @('-m', 'pip', 'install', '--upgrade', 'pip')
Run-Checked $Python @('-m', 'pip', 'install', '-r', 'requirements.txt', 'pyinstaller>=6.16,<7')
Run-Checked $Python @('packaging\windows\build_exe.py', '--installer')
Write-Host 'Setup created: dist\windows\FRIDAY_Setup_56.0.0_x64.exe'
