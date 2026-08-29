# free-llm-radar 本地定时运行脚本
# 流程：同步远端 -> 探测 Clash(7897) -> 带代理跑 radar -> 有变化则 commit + push
# 由 Windows 任务计划程序 "free-llm-radar" 每日调用，也可手动执行

$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot\..

# 先同步远端（GitHub Actions 每 6 小时也会提交更新，避免 push 冲突）
git pull --rebase origin main

# 仅当 Clash 端口在线时才设置代理环境变量；
# 不在线则直连（GitHub 清单/OpenRouter 可达，linux.do 会被 Cloudflare 拦截并自动跳过）
$client = New-Object System.Net.Sockets.TcpClient
$clashUp = $client.ConnectAsync("127.0.0.1", 7897).Wait(800) -and $client.Connected
$client.Close()
if ($clashUp) {
    $env:HTTPS_PROXY = "http://127.0.0.1:7897"
    $env:HTTP_PROXY = "http://127.0.0.1:7897"
    Write-Output "clash 7897 online, proxy env set"
} else {
    Write-Output "clash 7897 offline, running direct"
}

python -m radar --data-dir data
if ($LASTEXITCODE -ne 0) {
    Write-Output "radar run failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

git add README.md data/
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "radar: local refresh $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    git pull --rebase origin main
    if ($LASTEXITCODE -eq 0) {
        git push
        if ($LASTEXITCODE -eq 0) { Write-Output "changes pushed" } else { Write-Output "push failed" }
    } else {
        Write-Output "pull --rebase failed, resolve manually"
    }
} else {
    Write-Output "no changes"
}
