$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$installDir = Join-Path $env:LOCALAPPDATA "CoinRecomand"
$configPath = Join-Path $installDir "toss-sync-config.json"
$syncScript = Join-Path $installDir "Sync-TossPortfolio.ps1"
. (Join-Path $PSScriptRoot "Toss-Auth.ps1")
. (Join-Path $PSScriptRoot "Toss-Config.ps1")
function Read-PrivateText([string]$label) {
    $secure = Read-Host $label -AsSecureString
    $value = (New-Object System.Net.NetworkCredential("", $secure)).Password.Trim()
    if ([string]::IsNullOrWhiteSpace($value)) { throw "$label 값이 비어 있습니다." }
    return $value
}
function Protect-Text([string]$value) {
    return ConvertFrom-SecureString (ConvertTo-SecureString $value -AsPlainText -Force)
}
try {
    if (-not (Test-Path $configPath)) { throw "기존 설정 파일이 없습니다. 설치했던 Windows 계정에서 실행해 주세요." }
    if (-not (Test-Path $syncScript)) { throw "기존 동기화 프로그램이 없습니다. 진단 업데이트 파일을 먼저 실행해 주세요." }
    $config = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $config.SyncKey -or -not $config.FunctionUrl) { throw "기존 설정 파일을 확인할 수 없습니다." }
    $previousSyncKey = [string]$config.SyncKey
    Write-Host "토스 API 키만 다시 입력합니다. GitHub 동기화 키와 계좌 설정은 유지합니다." -ForegroundColor Cyan
    Write-Host "토스증권 PC 웹의 설정 > Open API에서 같은 클라이언트의 두 값을 복사해 주세요."
    Write-Host "두 입력값은 화면에 별표로 표시됩니다. 붙여넣고 Enter를 누르세요."
    $clientId = Read-PrivateText "토스증권 Client ID"
    $clientSecret = Read-PrivateText "토스증권 Client Secret"
    $authMethod = "form"
    Write-Host "A: 본문 인증 방식으로 검증합니다."
    try {
        $token = Request-TossToken $clientId $clientSecret "form"
        Write-Host "A: 본문 인증 성공" -ForegroundColor Green
    } catch {
        $formStatus = Get-TossHttpStatus $_
        Write-Host "A: 본문 인증 실패 / HTTP $formStatus"
        if ($formStatus -ne "401") { throw "본문 인증 실패 (HTTP $formStatus). 기존 저장값은 변경하지 않았습니다." }
        Write-Host "B: 같은 키로 Basic 헤더 인증을 한 번 확인합니다."
        try {
            $token = Request-TossToken $clientId $clientSecret "basic"
            $authMethod = "basic"
            Write-Host "B: Basic 헤더 인증 성공" -ForegroundColor Green
        } catch {
            $basicStatus = Get-TossHttpStatus $_
            Write-Host "B: Basic 헤더 인증 실패 / HTTP $basicStatus"
            if ($basicStatus -eq "401") { throw "두 인증 방식 모두 401입니다. 토스 키 관리 화면의 실제 복사값과 클라이언트 활성 상태를 확인해야 합니다. 기존 저장값은 변경하지 않았습니다." }
            if ($basicStatus -eq "403") { throw "Basic 인증에서 HTTP 403입니다. 이 PC의 공인 IP 허용 상태를 확인해야 합니다. 기존 저장값은 변경하지 않았습니다." }
            throw "Basic 인증 실패 (HTTP $basicStatus). 기존 저장값은 변경하지 않았습니다."
        }
    }
    if (-not $token.access_token) { throw "토스 인증 응답에 토큰이 없습니다. 기존 저장값은 변경하지 않았습니다." }
    Copy-Item (Join-Path $PSScriptRoot "Toss-Auth.ps1") (Join-Path $installDir "Toss-Auth.ps1") -Force
    Copy-Item (Join-Path $PSScriptRoot "Sync-TossPortfolio.ps1") $syncScript -Force
    $config | Add-Member -NotePropertyName TossAuthMethod -NotePropertyValue $authMethod -Force
    $config.ClientId = Protect-Text $clientId
    $config.ClientSecret = Protect-Text $clientSecret
    if ([string]$config.SyncKey -cne $previousSyncKey) { throw "동기화 키 보존 확인에 실패했습니다." }
    Save-TossConfig $configPath $config
    Write-Host "토스 인증 성공: API 키 두 개를 암호화해 저장했습니다. GitHub 재배포는 필요 없습니다." -ForegroundColor Green
    Write-Host "보유종목 동기화를 실행합니다."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $syncScript
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
