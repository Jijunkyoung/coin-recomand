# Native XLSX writer. Uses the same server report model as the browser, without Excel installation.
function Save-PortfolioExcel($Report, [string]$Template, [string]$OutputDir) {
    if (-not $Report -or -not $Report.date -or -not (Test-Path -LiteralPath $Template)) { throw "엑셀 보고서 또는 양식이 없습니다. 업데이트 파일을 다시 실행해 주세요." }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    $chartNs = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    $culture = [Globalization.CultureInfo]::InvariantCulture
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    $target = Join-Path $OutputDir ("portfolio-history-{0}.xlsx" -f $Report.date)
    $temp = Join-Path $OutputDir ("portfolio-history-{0}.{1}.tmp" -f $Report.date, [Guid]::NewGuid().ToString("N"))
    Copy-Item -LiteralPath $Template -Destination $temp
    $zip = [IO.Compression.ZipFile]::Open($temp, [IO.Compression.ZipArchiveMode]::Update)
    function Read-Xml([string]$Path) {
        $entry = $zip.GetEntry($Path)
        if ($null -eq $entry) { throw "엑셀 양식 항목 누락: $Path" }
        $reader = New-Object IO.StreamReader($entry.Open())
        try { [xml]$doc = $reader.ReadToEnd(); return ,$doc } finally { $reader.Dispose() }
    }
    function Write-Xml([string]$Path, [xml]$Doc) {
        $zip.GetEntry($Path).Delete()
        $writer = New-Object IO.StreamWriter($zip.CreateEntry($Path).Open(), (New-Object Text.UTF8Encoding($false)))
        try { $writer.Write($Doc.OuterXml) } finally { $writer.Dispose() }
    }
    function Write-Cell([xml]$Doc, $Cell, $Value) {
        while ($Cell.HasChildNodes) { [void]$Cell.RemoveChild($Cell.FirstChild) }
        $Cell.RemoveAttribute("t")
        if ($null -ne $Value -and $null -ne $Value.formula) {
            $f = $Doc.CreateElement("x", "f", $ns); $f.InnerText = [string]$Value.formula; [void]$Cell.AppendChild($f)
            $Value = $Value.value
        }
        if ($null -eq $Value -or [string]$Value -eq "") { return }
        $isNumber = $Value -is [ValueType] -and $Value -isnot [bool]
        $Cell.SetAttribute("t", $(if ($isNumber) { "n" } else { "str" }))
        $v = $Doc.CreateElement("x", "v", $ns)
        $v.InnerText = if ($isNumber) { [Convert]::ToString($Value, $culture) } else { [string]$Value }
        [void]$Cell.AppendChild($v)
    }
    try {
        $summary = Read-Xml "xl/worksheets/sheet1.xml"
        foreach ($item in $Report.summary) {
            $cell = @($summary.GetElementsByTagName("c", $ns) | Where-Object { $_.GetAttribute("r") -eq $item.ref })[0]
            if ($null -eq $cell) { throw "엑셀 요약 셀 누락" }
            Write-Cell $summary $cell $item
        }
        Write-Xml "xl/worksheets/sheet1.xml" $summary
        foreach ($sheet in $Report.sheets) {
            $doc = Read-Xml $sheet.path
            $body = $doc.GetElementsByTagName("sheetData", $ns)[0]
            $sample = @($body.ChildNodes | Where-Object { $_.GetAttribute("r") -eq "2" })[0]
            $styles = @{}; foreach ($c in $sample.ChildNodes) { $styles[$c.GetAttribute("r") -replace "\d+$", ""] = $c.GetAttribute("s") }
            foreach ($r in @($body.ChildNodes)) { if ([int]$r.GetAttribute("r") -ge 2) { [void]$body.RemoveChild($r) } }
            $index = 2
            foreach ($values in $sheet.rows) {
                $r = $doc.CreateElement("x", "row", $ns); $r.SetAttribute("r", [string]$index)
                $r.SetAttribute("ht", "24"); $r.SetAttribute("customHeight", "1")
                for ($j = 0; $j -lt $sheet.columns; $j++) {
                    $col = [string][char](65 + $j); $c = $doc.CreateElement("x", "c", $ns); $c.SetAttribute("r", "$col$index")
                    if ($styles[$col]) { $c.SetAttribute("s", $styles[$col]) }
                    Write-Cell $doc $c $values[$j]; [void]$r.AppendChild($c)
                }
                [void]$body.AppendChild($r); $index++
            }
            $dimension = $doc.GetElementsByTagName("dimension", $ns)[0]
            if ($dimension) { $dimension.SetAttribute("ref", "A1:$([char](64 + $sheet.columns))$([Math]::Max(2, $index - 1))") }
            Write-Xml $sheet.path $doc
        }
        foreach ($path in @($zip.Entries | Where-Object { $_.FullName -match "^xl/tables/.*\.xml$" } | ForEach-Object { $_.FullName })) {
            $doc = Read-Xml $path
            $sheet = @($Report.sheets | Where-Object { $_.table -eq $doc.DocumentElement.GetAttribute("name") })[0]
            if ($null -eq $sheet) { continue }
            $ref = "A1:$([char](64 + $sheet.columns))$([Math]::Max(2, $sheet.rows.Count + 1))"
            $doc.DocumentElement.SetAttribute("ref", $ref)
            foreach ($filter in $doc.GetElementsByTagName("autoFilter", $ns)) { $filter.SetAttribute("ref", $ref) }
            Write-Xml $path $doc
        }
        foreach ($chart in $Report.charts) {
            $doc = Read-Xml $chart.path
            foreach ($role in @("cat", "val")) {
                $parent = $doc.GetElementsByTagName($role, $chartNs)[0]
                while ($parent.HasChildNodes) { [void]$parent.RemoveChild($parent.FirstChild) }
                $kind = if ($role -eq "cat") { "str" } else { "num" }
                $data = if ($role -eq "cat") { @($chart.labels) } else { @($chart.points) }
                $reference = if ($role -eq "cat") { $chart.category } else { $chart.values }
                $r = $doc.CreateElement("c", "$($kind)Ref", $chartNs); $f = $doc.CreateElement("c", "f", $chartNs); $f.InnerText = $reference
                $cache = $doc.CreateElement("c", "$($kind)Cache", $chartNs); $count = $doc.CreateElement("c", "ptCount", $chartNs); $count.SetAttribute("val", [string]$data.Count); [void]$cache.AppendChild($count)
                for ($i = 0; $i -lt $data.Count; $i++) {
                    if ($null -eq $data[$i]) { continue }
                    $pt = $doc.CreateElement("c", "pt", $chartNs); $pt.SetAttribute("idx", [string]$i); $v = $doc.CreateElement("c", "v", $chartNs)
                    $v.InnerText = if ($role -eq "cat") { [string]$data[$i] } else { [Convert]::ToString($data[$i], $culture) }
                    [void]$pt.AppendChild($v); [void]$cache.AppendChild($pt)
                }
                [void]$r.AppendChild($f); [void]$r.AppendChild($cache); [void]$parent.AppendChild($r)
            }
            if ($doc.GetElementsByTagName("lineChart", $chartNs).Count -gt 0) {
                $series = $doc.GetElementsByTagName("ser", $chartNs)[0]
                $marker = $series.GetElementsByTagName("marker", $chartNs)[0]
                if ($null -eq $marker) { $marker = $doc.CreateElement("c", "marker", $chartNs); [void]$series.InsertBefore($marker, $series.GetElementsByTagName("cat", $chartNs)[0]) }
                while ($marker.HasChildNodes) { [void]$marker.RemoveChild($marker.FirstChild) }
                $symbol = $doc.CreateElement("c", "symbol", $chartNs); $symbol.SetAttribute("val", "circle"); [void]$marker.AppendChild($symbol)
                $size = $doc.CreateElement("c", "size", $chartNs); $size.SetAttribute("val", "4"); [void]$marker.AppendChild($size)
                $axis = $doc.GetElementsByTagName("catAx", $chartNs)[0]; $skip = $axis.GetElementsByTagName("tickLblSkip", $chartNs)[0]
                if ($null -eq $skip) { $skip = $doc.CreateElement("c", "tickLblSkip", $chartNs); [void]$axis.AppendChild($skip) }
                $skip.SetAttribute("val", [string][Math]::Max(1, [Math]::Ceiling($chart.labels.Count / 8)))
            }
            Write-Xml $chart.path $doc
        }
        $wb = Read-Xml "xl/workbook.xml"
        $calc = $wb.GetElementsByTagName("calcPr", $ns)[0]
        if ($null -eq $calc) { $calc = $wb.CreateElement("x", "calcPr", $ns); [void]$wb.DocumentElement.AppendChild($calc) }
        $calc.SetAttribute("calcMode", "auto"); $calc.SetAttribute("fullCalcOnLoad", "1"); $calc.SetAttribute("forceFullCalc", "1")
        Write-Xml "xl/workbook.xml" $wb
    } finally { $zip.Dispose() }
    # Only replace an existing daily report after its replacement has been fully generated.
    try { Move-Item -LiteralPath $temp -Destination $target -Force } catch { Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue; throw "엑셀 파일이 열려 있으면 닫은 뒤 다시 동기화해 주세요. 이전 파일은 유지했습니다." }
    return $target
}
