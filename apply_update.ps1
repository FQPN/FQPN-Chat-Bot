# Copies the newest fqpn_update*.zip from your Downloads folder into this project folder.
# Nothing of yours is touched: commands, timers, counters and your Twitch login live in the
# "data" and "authentication" folders, which are never inside the zip.
$ErrorActionPreference = "Stop"
$dl = Join-Path $env:USERPROFILE "Downloads\fqpn_update*.zip"
$zip = Get-ChildItem $dl -ErrorAction SilentlyContinue |
       Sort-Object { if ($_.CreationTime -gt $_.LastWriteTime) { $_.CreationTime } else { $_.LastWriteTime } } -Descending |
       Select-Object -First 1
if (-not $zip) {
  Write-Host ""
  Write-Host "No fqpn_update.zip found in your Downloads folder." -ForegroundColor Red
  Write-Host "Download it first, then run this again." -ForegroundColor Red
  exit 1
}
Write-Host ""
Write-Host ("Using: " + $zip.Name + "   (" + $zip.CreationTime + ")") -ForegroundColor Cyan
Write-Host ""
$tmp = Join-Path $env:TEMP "fqpn_update"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive $zip.FullName $tmp -Force
$n = 0
Get-ChildItem $tmp -Recurse -File | ForEach-Object {
  $rel = $_.FullName.Substring($tmp.Length + 1)
  $dst = Join-Path $PSScriptRoot $rel
  New-Item (Split-Path $dst) -ItemType Directory -Force | Out-Null
  Copy-Item $_.FullName $dst -Force
  Write-Host ("Updated: " + $rel) -ForegroundColor Green
  $n++
}
Remove-Item $tmp -Recurse -Force
Write-Host ""
Write-Host ("Done. " + $n + " files updated. Start the bot with run.bat") -ForegroundColor Cyan
