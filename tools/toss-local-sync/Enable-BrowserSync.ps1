$ErrorActionPreference = "Stop"
$installDir = Join-Path $env:LOCALAPPDATA "CoinRecomand"
try {
    if (-not (Test-Path (Join-Path $installDir "toss-sync-config.json"))) { throw "기존 설치 설정이 없습니다. 설치한 Windows 계정에서 실행해 주세요." }
    $task = Get-ScheduledTask -TaskName "CoinRecomand-TossSync" -ErrorAction Stop
    foreach ($name in @("Sync-TossPortfolio.ps1", "Toss-Auth.ps1", "Launch-TossSync.ps1", "Save-PortfolioExcel.ps1", "stock-portfolio-history-template.xlsx")) {
        Copy-Item (Join-Path $PSScriptRoot $name) (Join-Path $installDir $name) -Force
    }
    $protocolPath = "HKCU:\Software\Classes\coin-toss-sync"
    New-Item -Path $protocolPath -Force | Out-Null
    Set-Item -Path $protocolPath -Value "URL:Coin Toss Sync"
    New-ItemProperty -Path $protocolPath -Name "URL Protocol" -Value "" -PropertyType String -Force | Out-Null
    $commandPath = $protocolPath + "\shell\open\command"
    New-Item -Path $commandPath -Force | Out-Null
    $launch = Join-Path $installDir "Launch-TossSync.ps1"
    $powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    Set-Item -Path $commandPath -Value ('"' + $powershell + '" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launch + '"')
    Write-Host "브라우저 갱신 버튼 연결 완료." -ForegroundColor Green
    Write-Host "기존 API 키, 동기화 키, 매일 오전 7시 10분 예약은 유지했습니다."
    Write-Host "대시보드에서 수량·가격 갱신을 누르고 프로그램 실행을 허용하세요."
    Write-Host "이 버튼은 연결한 집 PC에서 사용할 수 있습니다."
    Write-Host "매일 07:10 동기화 후 문서\CoinRecomand\portfolio-excel에 날짜별 엑셀이 자동 저장됩니다."
    Write-Host "엑셀에는 총 보유자산 추이, 종목별 금액 표와 상위 10개 종목 그래프가 포함됩니다."
} catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }
