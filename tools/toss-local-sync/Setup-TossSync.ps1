$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$InstallDir = Join-Path $env:LOCALAPPDATA "CoinRecomand"
$ConfigPath = Join-Path $InstallDir "toss-sync-config.json"
$SyncSource = Join-Path $PSScriptRoot "Sync-TossPortfolio.ps1"
$SyncTarget = Join-Path $InstallDir "Sync-TossPortfolio.ps1"
$TaskName = "CoinRecomand-TossSync"

function Protect-Text([string]$Value) {
    return ConvertFrom-SecureString (ConvertTo-SecureString $Value -AsPlainText -Force)
}

function New-SyncKey {
    $bytes = New-Object byte[] 32
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($bytes) } finally { $random.Dispose() }
    return [Convert]::ToBase64String($bytes)
}

function Read-Required([string]$Prompt) {
    do { $value = (Read-Host $Prompt).Trim() } while ([string]::IsNullOrWhiteSpace($value))
    return $value
}

function Read-Secret([string]$Prompt) {
    $secure = Read-Host $Prompt -AsSecureString
    $plain = (New-Object System.Net.NetworkCredential("", $secure)).Password
    if ([string]::IsNullOrWhiteSpace($plain)) { throw "$Prompt 값이 비어 있습니다." }
    return $plain
}

try {
    Write-Host ""
    Write-Host "코인 리포트 - 토스증권 집 PC 동기화 설치" -ForegroundColor Cyan
    Write-Host "토스 API 키는 이 Windows 계정으로만 복호화할 수 있게 저장됩니다."
    Write-Host ""

    $publicIp = ([string](Invoke-RestMethod -Uri "https://checkip.amazonaws.com" -TimeoutSec 15)).Trim()
    Write-Host "현재 집 공인 IPv4: $publicIp" -ForegroundColor Yellow
    Set-Clipboard $publicIp
    Write-Host "IP를 클립보드에 복사했습니다."
    Write-Host "토스증권 WTS > 설정 > Open API > 허용 IP 관리에서 이 IP를 등록해 주세요."
    Start-Process "https://wts.tossinvest.com"
    Read-Host "허용 IP 등록을 마쳤으면 Enter"

    $clientId = Read-Required "토스증권 Client ID"
    $clientSecret = Read-Secret "토스증권 Client Secret"
    $accountSeq = (Read-Host "accountSeq (계좌가 하나면 비워두고 Enter)").Trim()
    $syncKey = New-SyncKey

    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Copy-Item $SyncSource $SyncTarget -Force
    Copy-Item (Join-Path $PSScriptRoot "Toss-Auth.ps1") (Join-Path $InstallDir "Toss-Auth.ps1") -Force
    @{
        FunctionUrl = "https://pgtxtnggjqaysjhtdepz.supabase.co/functions/v1/kis-portfolio"
        ClientId = Protect-Text $clientId
        ClientSecret = Protect-Text $clientSecret
        AccountSeq = $accountSeq
        SyncKey = Protect-Text $syncKey
        RegisteredIp = $publicIp
        InstalledAt = (Get-Date).ToString("o")
    } | ConvertTo-Json | Set-Content -Path $ConfigPath -Encoding UTF8

    Set-Clipboard $syncKey
    Write-Host ""
    Write-Host "GitHub Secret용 동기화 키를 클립보드에 복사했습니다." -ForegroundColor Yellow
    Write-Host "지금 열리는 화면에서 Name은 TOSS_LOCAL_SYNC_KEY, Secret에는 붙여넣기(Ctrl+V) 하세요."
    Start-Process "https://github.com/Jijunkyoung/coin-recomand/settings/secrets/actions/new"
    Read-Host "GitHub Secret 저장을 마쳤으면 Enter"
    Start-Process "https://github.com/Jijunkyoung/coin-recomand/actions/workflows/deploy-supabase.yml"
    Write-Host "Actions에서 Run workflow를 실행하고 초록색 성공 표시가 될 때까지 기다려 주세요."
    Read-Host "Deploy Supabase backend 성공을 확인했으면 Enter"

    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$SyncTarget`""
    $trigger = New-ScheduledTaskTrigger -Daily -At "07:10"
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "토스증권 보유종목을 coin-recomand 대시보드에 동기화" -Force | Out-Null

    Write-Host ""
    & (Join-Path $PSScriptRoot "Enable-BrowserSync.ps1")
    Write-Host "첫 동기화를 실행합니다." -ForegroundColor Cyan
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SyncTarget
    if ($LASTEXITCODE -ne 0) { throw "첫 동기화가 실패했습니다. 위 오류를 확인한 뒤 sync-toss-now.cmd를 다시 실행해 주세요." }

    Write-Host ""
    Write-Host "설치 완료: 매일 오전 7시 10분에 자동 동기화됩니다." -ForegroundColor Green
    Write-Host "PC가 꺼져 있었다면 다음 로그인 후 가능한 시점에 실행됩니다."
    Read-Host "창을 닫으려면 Enter"
} catch {
    Write-Host ""
    Write-Host "설치 실패: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host "창을 닫으려면 Enter"
    exit 1
}
