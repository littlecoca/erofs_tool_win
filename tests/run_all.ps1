# SPDX-License-Identifier: 0BSD
# 一键跑完全部验收测试（端到端 / GUI 拖放 / 启动器），并打印简洁结论。
# 用法: powershell -File tests\run_all.ps1
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$log = Join-Path $Root 'test'
New-Item -ItemType Directory -Force -Path $log | Out-Null

$results = @{}
$t0 = Get-Date

Write-Host '===== 1/3 端到端测试 (tests\e2e_test.py) ====='
python tests\e2e_test.py *> (Join-Path $log 'final_e2e.log')
$results['e2e'] = $LASTEXITCODE
Get-Content (Join-Path $log 'final_e2e.log') -Encoding UTF8 | Select-Object -Last 4

Write-Host ''
Write-Host '===== 2/3 GUI + 拖放测试 (tests\gui_test.py) ====='
python tests\gui_test.py *> (Join-Path $log 'final_gui.log')
$results['gui'] = $LASTEXITCODE
Get-Content (Join-Path $log 'final_gui.log') -Encoding UTF8 | Select-Object -Last 3

Write-Host ''
Write-Host '===== 3/3 启动器测试 (tests\launcher_test.ps1) ====='
& (Join-Path $PSScriptRoot 'launcher_test.ps1') *> (Join-Path $log 'final_launcher.log')
$results['launcher'] = $LASTEXITCODE
Get-Content (Join-Path $log 'final_launcher.log') -Encoding UTF8 | Select-Object -Last 3

Write-Host ''
Write-Host '===== 文档自检 ====='
python tools\check_docs.py
$results['docs'] = $LASTEXITCODE

$fail = ($results.Values | Where-Object { $_ -ne 0 }).Count
Write-Host ''
Write-Host ("===== 总耗时 {0:N0} 秒；e2e={1} gui={2} launcher={3} docs={4} =====" -f `
    ((Get-Date) - $t0).TotalSeconds, $results['e2e'], $results['gui'], $results['launcher'], $results['docs'])
Write-Host ("===== 结果: {0} =====" -f $(if ($fail -eq 0) { 'ALL PASS' } else { "FAIL($fail)" }))
exit $fail
