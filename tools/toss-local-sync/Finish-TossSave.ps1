$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$installDir = Join-Path $env:LOCALAPPDATA "CoinRecomand"
$configPath = Join-Path $installDir "toss-sync-config.json"
$syncScript = Join-Path $installDir "Sync-TossPortfolio.ps1"
. (Join-Path $PSScriptRoot "Toss-Auth.ps1")
. (Join-Path $PSScriptRoot "Toss-Config.ps1")
function Unprotect-Text([string]$value) {
    $secure = ConvertTo-SecureString $value
    return (New-Object System.Net.NetworkCredential("", $secure)).Password
}
try {
    if (-not (Test-Path $configPath)) { throw "기존 설정 파일이 없습니다. 설치했던 Windows 계정에서 실행해 주세요." }
    $originalJson = Get-Content $configPath -Raw -Encoding UTF8
    $config = $originalJson | ConvertFrom-Json
    if (-not $config.SyncKey -or -not $config.FunctionUrl) { throw "기존 동기화 설정을 확인할 수 없습니다." }
    $pending = @(Get-ChildItem -LiteralPath $installDir -Filter "toss-sync-config.json.new.*" -File | Sort-Object LastWriteTimeUtc -Descending)
    if ($pending.Count -eq 0) { throw "저장 대기 중인 키가 없습니다. repair-toss-auth.cmd를 실행해 현재 유효한 API 키를 다시 입력해 주세요. 키 재발급은 필요 없습니다." }
    $candidatePath = $pending[0].FullName
    $candidate = Get-Content -LiteralPath $candidatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$candidate.SyncKey -cne [string]$config.SyncKey -or [string]$candidate.FunctionUrl -cne [string]$config.FunctionUrl) {
        throw "임시파일과 현재 동기화 설정이 다릅니다. 기존 설정은 변경하지 않았습니다. repair-toss-auth.cmd를 실행해 주세요."
    }
    if (-not $candidate.ClientId -or -not $candidate.ClientSecret) { throw "임시파일에 API 키가 없습니다. 기존 설정은 변경하지 않았습니다." }
    Write-Host "이전에 인증에 성공했던 키를 암호화 임시파일에서 찾았습니다. 키를 다시 입력하지 않아도 됩니다." -ForegroundColor Cyan
    $clientId = Unprotect-Text $candidate.ClientId
    $clientSecret = Unprotect-Text $candidate.ClientSecret
    $authMethod = "form"
    if ($candidate.TossAuthMethod -eq "basic") { $authMethod = "basic" }
    Write-Host "토스 서버에서 키를 다시 검증합니다."
    try { $token = Request-TossToken $clientId $clientSecret $authMethod }
    catch { $status = Get-TossHttpStatus $_; throw "토스 인증 재확인 실패 / HTTP $status. 기존 설정은 변경하지 않았습니다." }
    if (-not $token.access_token) { throw "토스 인증 응답에 토큰이 없습니다. 기존 설정은 변경하지 않았습니다." }
    Write-Host "토스 인증 성공" -ForegroundColor Green
    if ((Get-Content $configPath -Raw -Encoding UTF8) -cne $originalJson) { throw "실행 중 설정이 변경됐습니다. 다시 실행해 주세요." }
    # Merge only validated API credentials into the current configuration.
    $config.ClientId = $candidate.ClientId
    $config.ClientSecret = $candidate.ClientSecret
    $config | Add-Member -NotePropertyName TossAuthMethod -NotePropertyValue $authMethod -Force
    Copy-Item (Join-Path $PSScriptRoot "Toss-Auth.ps1") (Join-Path $installDir "Toss-Auth.ps1") -Force
    Copy-Item (Join-Path $PSScriptRoot "Sync-TossPortfolio.ps1") $syncScript -Force
    Save-TossConfig $configPath $config
    Remove-Item -LiteralPath $candidatePath -Force -ErrorAction SilentlyContinue
    Write-Host "API 키 저장 완료. GitHub 동기화 키와 계좌 설정은 유지했습니다." -ForegroundColor Green
    Write-Host "보유종목 동기화를 실행합니다."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $syncScript
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
