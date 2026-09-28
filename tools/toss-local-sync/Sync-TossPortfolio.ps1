$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$InstallDir = Join-Path $env:LOCALAPPDATA "CoinRecomand"
$ConfigPath = Join-Path $InstallDir "toss-sync-config.json"
$LogPath = Join-Path $InstallDir "toss-sync.log"
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

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

try {
    if (-not (Test-Path $ConfigPath)) { throw "설정 파일이 없습니다. install-toss-sync.cmd를 먼저 실행해 주세요." }
    $config = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $clientId = Unprotect-Value $config.ClientId
    $clientSecret = Unprotect-Value $config.ClientSecret
    $syncKey = Unprotect-Value $config.SyncKey

    $currentIp = Get-CurrentPublicIp
    if ($currentIp -and $config.RegisteredIp -and $currentIp -ne $config.RegisteredIp) {
        throw "집 공인 IP가 $($config.RegisteredIp)에서 $currentIp(으)로 바뀌었습니다. 토스증권 WTS 허용 IP를 변경한 뒤 설치 프로그램을 다시 실행해 주세요."
    }

    Write-SyncLog "토스증권 보유종목 조회를 시작합니다."
    $tokenResponse = Invoke-RestMethod -Method Post -Uri "https://openapi.tossinvest.com/oauth2/token" -ContentType "application/x-www-form-urlencoded" -Body @{
        grant_type = "client_credentials"
        client_id = $clientId
        client_secret = $clientSecret
    } -TimeoutSec 45
    if (-not $tokenResponse.access_token) { throw "토스증권 토큰 응답에 access_token이 없습니다." }
    $headers = @{ Authorization = "Bearer $($tokenResponse.access_token)"; Accept = "application/json" }

    $accountSeq = [string]$config.AccountSeq
    if ([string]::IsNullOrWhiteSpace($accountSeq)) {
        $accountsResponse = Invoke-RestMethod -Method Get -Uri "https://openapi.tossinvest.com/api/v1/accounts" -Headers $headers -TimeoutSec 45
        $accounts = @($accountsResponse.result)
        $selected = @($accounts | Where-Object { $_.accountType -eq "BROKERAGE" }) | Select-Object -First 1
        if ($null -eq $selected) { $selected = $accounts | Select-Object -First 1 }
        if ($null -eq $selected -or $null -eq $selected.accountSeq) { throw "토스증권 종합매매 계좌를 찾지 못했습니다." }
        $accountSeq = [string]$selected.accountSeq
    }

    $headers["X-Tossinvest-Account"] = $accountSeq
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

    $payload = @{ action = "upload_toss_positions"; positions = @($positions) } | ConvertTo-Json -Depth 8 -Compress
    $uploadResponse = Invoke-RestMethod -Method Post -Uri $config.FunctionUrl -Headers @{ "x-toss-local-sync-key" = $syncKey } -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -TimeoutSec 60
    if (-not $uploadResponse.ok) { throw "Supabase 업로드가 완료되지 않았습니다." }
    Write-SyncLog "성공: 토스증권 $($uploadResponse.positions_count)개 종목을 대시보드에 동기화했습니다."
    exit 0
} catch {
    Write-SyncLog "실패: $($_.Exception.Message)"
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
