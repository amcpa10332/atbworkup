<#
Build a distributable Windows package for ATBWorkup.

Usage (from the project root, or anywhere - it cd's itself):
    powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1

Produces:
    dist\ATBWorkup\                       the built app (onedir)
    dist\ATBWorkup-v<version>-win.zip     zipped app, ready to upload
    dist\How to Install.md                copy of the student instructions

Upload the .zip and "How to Install.md" together - same folder, same Teams
Files tab / Drive folder - so students never have one without the other.
#>

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Pull the version straight from constants.py so the zip's filename can
# never drift out of sync with what's actually running inside it.
$match = Select-String -Path "atbworkup\constants.py" -Pattern '^APP_VERSION\s*=\s*"([^"]+)"'
if (-not $match) { throw "Could not find APP_VERSION in atbworkup\constants.py" }
$version = $match.Matches[0].Groups[1].Value
Write-Host "Building ATBWorkup v$version for Windows..."

if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist" }

python -m PyInstaller atbworkup.spec --noconfirm
if (-not $?) { throw "PyInstaller build failed - see output above." }

$zipName = "dist\ATBWorkup-v$version-win.zip"
Compress-Archive -Path "dist\ATBWorkup\*" -DestinationPath $zipName -Force
Copy-Item "How to Install.md" -Destination "dist\How to Install.md" -Force

Write-Host ""
Write-Host "Build complete. Upload these two files to Teams / Drive:"
Write-Host "  $zipName"
Write-Host "  dist\How to Install.md"
