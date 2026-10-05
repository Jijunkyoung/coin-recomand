$ErrorActionPreference = "Stop"
try {
    # Only the fixed, existing task can be launched; URL parameters are never executed.
    Start-ScheduledTask -TaskName "CoinRecomand-TossSync"
} catch {
    Add-Content -Path (Join-Path $env:LOCALAPPDATA "CoinRecomand/toss-sync.log") -Value ("수동 실행 실패: " + $_.Exception.Message) -Encoding UTF8
}
