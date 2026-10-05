function Save-TossConfig([string]$path, $config) {
    $fullPath = [IO.Path]::GetFullPath($path)
    if (-not [IO.File]::Exists($fullPath)) { throw "기존 설정 파일이 없습니다." }
    $unique = [Guid]::NewGuid().ToString("N")
    $temporaryPath = $fullPath + ".new." + $unique
    $backupPath = $fullPath + ".backup." + $unique
    $json = $config | ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText($temporaryPath, $json, (New-Object Text.UTF8Encoding($true)))
    # An explicit backup path avoids Windows PowerShell binding null as an empty path.
    [IO.File]::Replace($temporaryPath, $fullPath, $backupPath)
}
