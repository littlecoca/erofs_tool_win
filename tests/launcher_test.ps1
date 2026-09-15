# Verify the two launchers actually work:
#   1-<gui>.bat   -- starts the GUI (auto-closed afterwards)
#   2-<drop>.cmd  -- extracts an image dropped onto it into a same-name folder
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$fail = 0
$GuiBat  = (Get-ChildItem $Root -Filter '1-*.bat' | Select-Object -First 1).Name
$DropCmd = (Get-ChildItem $Root -Filter '2-*.cmd' | Select-Object -First 1).Name
Write-Host "GUI launcher : $GuiBat"
Write-Host "Drop launcher: $DropCmd"

Write-Host "`n===== 1) $GuiBat ====="
$before = @(Get-Process pythonw -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
# 用 Start-Process 起 cmd，别用管道：GUI 会继承 stdout，管道会一直挂着不返回
$proc = Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', $GuiBat -PassThru -WindowStyle Hidden
$proc.WaitForExit(20000) | Out-Null
Start-Sleep -Seconds 5
$new = @(Get-Process pythonw -ErrorAction SilentlyContinue |
         Where-Object { $before -notcontains $_.Id })
if ($new.Count -gt 0) {
    $titles = ($new | ForEach-Object { $_.MainWindowTitle }) -join ' / '
    Write-Host "  [PASS] GUI 进程已启动 pid=$(($new | ForEach-Object {$_.Id}) -join ',')  窗口标题: $titles"
    foreach ($p in $new) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    Write-Host "  （已自动关掉测试用的 GUI）"
} else {
    Write-Host "  [FAIL] 没有看到新的 pythonw 进程"
    $fail++
}

Write-Host "`n===== 2) $DropCmd （模拟把 IMG 拖到它上面）====="
$work = Join-Path $Root 'test\launcher'
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory -Force -Path $work | Out-Null
$src = Join-Path $Root 'test\e2e\fixtures\fixture_lz4.img'
if (-not (Test-Path $src)) {
    Write-Host "  [SKIP] 缺少测试镜像 $src （先跑 tests\e2e_test.py）"
    exit 1
}
$img = Join-Path $work 'system.img'
Copy-Item $src $img

$out = ('' | cmd /c "`"$DropCmd`" `"$img`"" 2>&1 | Out-String)
($out.Trim() -split "`r?`n" | Select-Object -First 16) | ForEach-Object { "  | $_" }

$dest = Join-Path $work 'system'
if (Test-Path $dest) {
    $n = (Get-ChildItem $dest -Recurse -File -Force |
          Where-Object { -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } |
          Measure-Object).Count
    Write-Host "  [PASS] 生成同名目录 system\，$n 个文件"
    if (-not (Test-Path (Join-Path $dest 'system\bin\mksh'))) {
        Write-Host "  [FAIL] 没找到 system/bin/mksh"; $fail++
    }
    if (-not (Test-Path (Join-Path $dest '中文目录\中文文件.txt'))) {
        Write-Host "  [FAIL] 没找到中文目录/中文文件.txt"; $fail++
    }
} else {
    Write-Host "  [FAIL] 没有生成 $dest"
    $fail++
}

Write-Host "`n===== 结果：$(if ($fail -eq 0) {'PASS'} else {"FAIL($fail)"}) ====="
exit $fail
