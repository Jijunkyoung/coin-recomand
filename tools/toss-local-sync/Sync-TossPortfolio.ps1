$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$InstallDir = Join-Path $env:LOCALAPPDATA "CoinRecomand"
$ConfigPath = Join-Path $InstallDir "toss-sync-config.json"
$LogPath = Join-Path $InstallDir "toss-sync.log"
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
. (Join-Path $PSScriptRoot "Toss-Auth.ps1")

function Write-SyncLog([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogPath -Value $line -Encoding UTF8
    Write-Host $line
}

function Unprotect-Value([string]$Value) {
    $secure = ConvertTo-SecureString $Value
    return (New-Object System.Net.NetworkCredential("", $secure)).Password
}

function Get-Number($Value) {
    if ($null -eq $Value) { return 0.0 }
    if ($Value -is [byte] -or $Value -is [int16] -or $Value -is [int32] -or $Value -is [int64] -or $Value -is [single] -or $Value -is [double] -or $Value -is [decimal]) {
        return [double]$Value
    }
    $parsed = 0.0
    $text = ([string]$Value).Replace(",", "")
    [void][double]::TryParse($text, [Globalization.NumberStyles]::Any, [Globalization.CultureInfo]::InvariantCulture, [ref]$parsed)
    return $parsed
}

function Get-CurrentPublicIp {
    try { return ([string](Invoke-RestMethod -Uri "https://checkip.amazonaws.com" -TimeoutSec 15)).Trim() }
    catch { Write-SyncLog "공인 IP 확인을 건너뜁니다: $($_.Exception.Message)"; return "" }
}

$stage = "설정 읽기 및 키 복호화"
try {
    if (-not (Test-Path $ConfigPath)) { throw "설정 파일이 없습니다. install-toss-sync.cmd를 먼저 실행해 주세요." }
    $config = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $clientId = Unprotect-Value $config.ClientId
    $clientSecret = Unprotect-Value $config.ClientSecret
    $syncKey = Unprotect-Value $config.SyncKey

    $stage = "공인 IP 확인"
    $currentIp = Get-CurrentPublicIp
    if ($currentIp -and $config.RegisteredIp -and $currentIp -ne $config.RegisteredIp) {
        throw "집 공인 IP가 $($config.RegisteredIp)에서 $currentIp(으)로 바뀌었습니다. 토스증권 WTS 허용 IP를 변경한 뒤 설치 프로그램을 다시 실행해 주세요."
    }

    Write-SyncLog "토스증권 보유종목 조회를 시작합니다."
    $stage = "1단계: 토스 인증 토큰 발급"
    Write-SyncLog "$stage 시작"
    $authMethod = "form"
    if ($config.TossAuthMethod -eq "basic") { $authMethod = "basic" }
    $tokenResponse = Request-TossToken $clientId $clientSecret $authMethod
    if (-not $tokenResponse.access_token) { throw "토스증권 토큰 응답에 access_token이 없습니다." }
    Write-SyncLog "1단계 성공: 토스 인증 완료"
    $headers = @{ Authorization = "Bearer $($tokenResponse.access_token)"; Accept = "application/json" }

    $accountSeq = [string]$config.AccountSeq
    if ([string]::IsNullOrWhiteSpace($accountSeq)) {
        $stage = "2단계: 토스 계좌 목록 조회"
        Write-SyncLog "$stage 시작"
        $accountsResponse = Invoke-RestMethod -Method Get -Uri "https://openapi.tossinvest.com/api/v1/accounts" -Headers $headers -TimeoutSec 45
        $accounts = @($accountsResponse.result)
        $selected = @($accounts | Where-Object { $_.accountType -eq "BROKERAGE" }) | Select-Object -First 1
        if ($null -eq $selected) { $selected = $accounts | Select-Object -First 1 }
        if ($null -eq $selected -or $null -eq $selected.accountSeq) { throw "토스증권 종합매매 계좌를 찾지 못했습니다." }
        $accountSeq = [string]$selected.accountSeq
        Write-SyncLog "2단계 성공: 조회할 계좌 선택 완료"
    }

    $headers["X-Tossinvest-Account"] = $accountSeq
    $stage = "3단계: 토스 보유종목 조회"
    Write-SyncLog "$stage 시작"
    $holdingsResponse = Invoke-RestMethod -Method Get -Uri "https://openapi.tossinvest.com/api/v1/holdings" -Headers $headers -TimeoutSec 60
    $positions = @()
    foreach ($item in @($holdingsResponse.result.items)) {
        $quantity = Get-Number $item.quantity
        if ($quantity -le 0 -or [string]::IsNullOrWhiteSpace([string]$item.symbol)) { continue }
        $market = if (([string]$item.marketCountry).ToUpperInvariant() -eq "US") { "us" } else { "kr" }
        $currency = if ($market -eq "us") { "USD" } else { "KRW" }
        $positions += [pscustomobject]@{
            broker = "toss"
            market = $market
            symbol = ([string]$item.symbol).Trim().ToUpperInvariant()
            name = ([string]$item.name).Trim()
            quantity = $quantity
            average_price = Get-Number $item.averagePurchasePrice
            current_price = Get-Number $item.lastPrice
            evaluation_amount = Get-Number $item.marketValue.amount
            profit_loss = Get-Number $item.profitLoss.amount
            profit_rate = (Get-Number $item.profitLoss.rate) * 100
            daily_change_rate = (Get-Number $item.dailyProfitLoss.rate) * 100
            currency = $currency
        }
    }

    Write-SyncLog "3단계 성공: $($positions.Count)개 종목 확인"
    $stage = "4단계: 대시보드 서버 업로드"
    Write-SyncLog "$stage 시작"
    $payload = @{ action = "upload_toss_positions"; positions = @($positions); export_history = $true } | ConvertTo-Json -Depth 8 -Compress
    $uploadResponse = Invoke-RestMethod -Method Post -Uri $config.FunctionUrl -Headers @{ "x-toss-local-sync-key" = $syncKey } -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -TimeoutSec 180
    if (-not $uploadResponse.ok) { throw "Supabase 업로드가 완료되지 않았습니다." }
    Write-SyncLog "성공: 토스증권 $($uploadResponse.positions_count)개 종목을 대시보드에 동기화했습니다."
    $stage = "5단계: 일별 자산 엑셀 저장"
    Write-SyncLog "$stage 시작"
    if ($uploadResponse.export_warning) { throw "동기화는 성공했지만 자산기록 실패: $($uploadResponse.export_warning)" }
    . (Join-Path $PSScriptRoot "Save-PortfolioExcel.ps1")
    $excelDir = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "CoinRecomand\portfolio-excel"
    $excelPath = Save-PortfolioExcel $uploadResponse.excel_portfolio (Join-Path $PSScriptRoot "stock-portfolio-history-template.xlsx") $excelDir
    Write-SyncLog "5단계 성공: 엑셀 저장 완료 / $excelPath"
    exit 0
} catch {
    $failure = $_
    $statusCode = "확인 불가"
    if ($null -ne $failure.Exception.Response) {
        try { $statusCode = [string]([int]$failure.Exception.Response.StatusCode) } catch {}
    }
    Write-SyncLog "실패 단계: $stage / HTTP $statusCode"
    $safeError = ""
    if ($failure.ErrorDetails -and $failure.ErrorDetails.Message) {
        try {
            $details = $failure.ErrorDetails.Message | ConvertFrom-Json
            $candidate = [string]$details.error
            if ($candidate -in @("invalid_client", "access_denied", "invalid_token", "invalid_request", "unauthorized", "UNAUTHORIZED")) {
                $safeError = $candidate
            }
        } catch {}
    }
    if ($safeError) { Write-SyncLog "서버 오류 코드: $safeError" }
    if ($stage -eq "1단계: 토스 인증 토큰 발급" -and $statusCode -eq "401") {
        Write-Host "토스 Client ID와 Client Secret의 일치 여부 및 활성 상태를 확인해야 합니다." -ForegroundColor Yellow
    }
    if ($stage -eq "4단계: 대시보드 서버 업로드") {
        Write-Host "토스 조회는 완료됐습니다. 서버 함수 인증 설정과 동기화 키 적용 상태를 확인해야 합니다." -ForegroundColor Yellow
    }
    Write-Host $failure.Exception.Message -ForegroundColor Red
    exit 1
}
