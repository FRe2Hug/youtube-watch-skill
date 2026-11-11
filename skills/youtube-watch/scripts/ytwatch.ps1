# Runs ytwatch on Windows PowerShell. On first use, downloads ytwatch.exe
# into ~/.claude/bin (nothing else is installed, PATH is not touched).
$ErrorActionPreference = "Stop"
$bin = Join-Path $HOME ".claude\bin\ytwatch.exe"
if (-not (Test-Path $bin)) {
    New-Item -ItemType Directory -Force (Split-Path $bin) | Out-Null
    Write-Host "ytwatch: first run, downloading ytwatch-windows-x64.exe (~100 MB) ..."
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest "https://github.com/FRe2Hug/youtube-watch-skill/releases/latest/download/ytwatch-windows-x64.exe" -OutFile "$bin.part"
    Move-Item "$bin.part" $bin
}
& $bin @args
exit $LASTEXITCODE
