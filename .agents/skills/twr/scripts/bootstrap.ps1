param([switch]$Ensure)
$ErrorActionPreference = "Stop"

$SkillDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DataRoot = if ($env:XDG_DATA_HOME) { $env:XDG_DATA_HOME } else { Join-Path $env:LOCALAPPDATA "TheWriterAndReader" }
$RuntimeDir = Join-Path $DataRoot "runtime"
$PythonBin = Join-Path $RuntimeDir "Scripts\python.exe"
$TwrBin = Join-Path $RuntimeDir "Scripts\twr.exe"
$Marker = Join-Path $DataRoot "initialized-0.1.5"
$Wheel = Join-Path $SkillDir "assets\the_writer_and_reader_tools-0.1.5-py3-none-any.whl"
$ExpectedSha256 = "723dda6a2e2b0e623b20e1bb6c4273401ca5934ada72498510bb8cb5532d8f69"

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
