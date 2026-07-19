param([switch]$Ensure)
$ErrorActionPreference = "Stop"

$SkillDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DataRoot = if ($env:XDG_DATA_HOME) { $env:XDG_DATA_HOME } else { Join-Path $env:LOCALAPPDATA "TheWriterAndReader" }
$RuntimeDir = Join-Path $DataRoot "runtime"
$PythonBin = Join-Path $RuntimeDir "Scripts\python.exe"
$TwrBin = Join-Path $RuntimeDir "Scripts\twr.exe"
$Marker = Join-Path $DataRoot "initialized-0.1.6"
$Wheel = Join-Path $SkillDir "assets\the_writer_and_reader_tools-0.1.6-py3-none-any.whl"
$ExpectedSha256 = "c92b89e0f9d5054c6393d08cd70f6c783a2f9f4efd27323e2e4d15116e394c14"

if ((Test-Path $Marker) -and (Test-Path $TwrBin)) { Write-Output $TwrBin; exit 0 }
New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
$ActualSha256 = (Get-FileHash -Algorithm SHA256 $Wheel).Hash.ToLowerInvariant()
if ($ActualSha256 -ne $ExpectedSha256) { throw "TWR wheel checksum mismatch." }

if (-not (Test-Path $PythonBin)) {
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    irm https://astral.sh/uv/install.ps1 | iex
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
  }
  uv venv --python 3.11 $RuntimeDir
}

& $PythonBin -m ensurepip --upgrade
& $PythonBin -m pip install --upgrade $Wheel
& $TwrBin setup --ensure
New-Item -ItemType File -Force -Path $Marker | Out-Null
Write-Output $TwrBin
