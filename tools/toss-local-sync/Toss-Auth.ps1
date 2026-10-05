function Request-TossToken([string]$clientId, [string]$clientSecret, [string]$method) {
    $arguments = @{
        Method = "Post"
        Uri = "https://openapi.tossinvest.com/oauth2/token"
        ContentType = "application/x-www-form-urlencoded"
        TimeoutSec = 45
    }
    if ($method -eq "basic") {
        $credentials = [Uri]::EscapeDataString($clientId) + ":" + [Uri]::EscapeDataString($clientSecret)
        $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($credentials))
        $arguments.Headers = @{ Authorization = "Basic $encoded" }
        $arguments.Body = @{ grant_type = "client_credentials" }
    } elseif ($method -eq "form") {
        $arguments.Body = @{ grant_type = "client_credentials"; client_id = $clientId; client_secret = $clientSecret }
    } else { throw "지원하지 않는 토스 인증 방식입니다." }
    return Invoke-RestMethod @arguments
}
function Get-TossHttpStatus($failure) {
    if ($null -ne $failure.Exception.Response) {
        try { return [string]([int]$failure.Exception.Response.StatusCode) } catch {}
    }
    return "확인 불가"
}
