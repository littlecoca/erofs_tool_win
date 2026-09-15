# Smoke test: mkfs.erofs round-trip -> fsck.erofs extract -> compare
# 用法: pwsh -File tools\smoke_engine.ps1
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Engine = Join-Path $Root 'engine'
$Work   = Join-Path $Root 'test\smoke'
Remove-Item $Work -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Join-Path $Work 'src\sub') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Work 'out')      | Out-Null

# --- build a source tree (F: forward-slash windows paths for cygwin) ---
$F = ($Root -replace '\\', '/')
Set-Content -Path (Join-Path $Work 'src\hello.txt') -Value "hello erofs`n" -NoNewline -Encoding utf8
Set-Content -Path (Join-Path $Work 'src\sub\nested.txt') -Value ('ABC' * 50000) -NoNewline
Set-Content -Path (Join-Path $Work 'src\empty.txt') -Value '' -NoNewline
# 1MB pseudo-random blob
$bytes = New-Object byte[] (1024*1024)
(New-Object Random 12345).NextBytes($bytes)
[IO.File]::WriteAllBytes((Join-Path $Work 'src\blob.bin'), $bytes)
"source tree:"; Get-ChildItem -Recurse -File (Join-Path $Work 'src') | ForEach-Object { "   {0,-28} {1}" -f $_.FullName.Substring($Work.Length+1), $_.Length }

Write-Host "`n===== mkfs.erofs (-zlz4) ====="
& "$Engine\mkfs.erofs.exe" -zlz4 -T 1700000000 "$F/test/smoke/smoke.img" "$F/test/smoke/src" 2>&1
Write-Host "mkfs exit=$LASTEXITCODE"
if (Test-Path "$Work\smoke.img") { Write-Host ("image size = {0}" -f (Get-Item "$Work\smoke.img").Length) }

Write-Host "`n===== dump.erofs -s ====="
& "$Engine\dump.erofs.exe" -s "$F/test/smoke/smoke.img" 2>&1 | Select-Object -First 15
Write-Host "dump exit=$LASTEXITCODE"

Write-Host "`n===== fsck.erofs --extract ====="
& "$Engine\fsck.erofs.exe" "--extract=$F/test/smoke/out" "$F/test/smoke/smoke.img" 2>&1 | Select-Object -First 25
Write-Host "fsck exit=$LASTEXITCODE"

Write-Host "`n===== extracted tree ====="
Get-ChildItem -Recurse -Force (Join-Path $Work 'out') | ForEach-Object { "   {0,-40} {1}" -f $_.FullName.Substring($Work.Length+1), $_.Length }

Write-Host "`n===== hash compare ====="
$ok = $true
foreach ($f in Get-ChildItem -Recurse -File (Join-Path $Work 'src')) {
    $rel = $f.FullName.Substring((Join-Path $Work 'src').Length + 1)
    $dst = Join-Path (Join-Path $Work 'out') $rel
    if (-not (Test-Path $dst)) { Write-Host "MISSING  $rel"; $ok = $false; continue }
    $a = (Get-FileHash $f.FullName -Algorithm SHA256).Hash
    $b = (Get-FileHash $dst -Algorithm SHA256).Hash
    if ($a -eq $b) { Write-Host "OK       $rel  ($($f.Length) bytes)" } else { Write-Host "MISMATCH $rel"; $ok = $false }
}
Write-Host "`nRESULT: $(if ($ok) {'PASS'} else {'FAIL'})"
