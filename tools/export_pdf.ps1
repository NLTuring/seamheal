$ErrorActionPreference = 'Continue'
$src = 'D:\挑战杯项目\3D模型智能修复与接缝优化工具\愈缝SeamHeal-项目简介文档.docx'
$out = 'D:\挑战杯项目\3D模型智能修复与接缝优化工具\preview\brief.pdf'

if (Test-Path $out) { Remove-Item $out -Force }

$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0

try {
    $d = $w.Documents.Open($src, $false, $true)
    Write-Output ('OPENED  pages=' + $d.ComputeStatistics(2))

    $done = $false

    # 方法一：SaveAs2（Word 2010+ / WPS）
    if (-not $done) {
        try {
            $d.SaveAs2($out, 17)
            if (Test-Path $out) { $done = $true; Write-Output 'METHOD=SaveAs2' }
        } catch { Write-Output ('SaveAs2 failed: ' + $_.Exception.Message) }
    }

    # 方法二：SaveAs（Word 2007 + PDF 加载项）
    if (-not $done) {
        try {
            $d.SaveAs([ref]$out, [ref]17)
            if (Test-Path $out) { $done = $true; Write-Output 'METHOD=SaveAs' }
        } catch { Write-Output ('SaveAs failed: ' + $_.Exception.Message) }
    }

    # 方法三：ExportAsFixedFormat
    if (-not $done) {
        try {
            $d.ExportAsFixedFormat($out, 17)
            if (Test-Path $out) { $done = $true; Write-Output 'METHOD=ExportAsFixedFormat' }
        } catch { Write-Output ('ExportAsFixedFormat failed: ' + $_.Exception.Message) }
    }

    # 方法四：打印到 Microsoft Print to PDF
    if (-not $done) {
        try {
            $d.PrintOut([ref]$false, [ref]$false, [ref]0, [ref]'', [ref]'Microsoft Print to PDF', [ref]$true, [ref]0, [ref]'', [ref]$out)
            Start-Sleep -Seconds 12
            if (Test-Path $out) { $done = $true; Write-Output 'METHOD=PrintOut' }
        } catch { Write-Output ('PrintOut failed: ' + $_.Exception.Message) }
    }

    Write-Output ('DONE=' + $done)
    $d.Close(0)
} catch {
    Write-Output ('FATAL: ' + $_.Exception.Message)
}

$w.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($w) | Out-Null

if (Test-Path $out) {
    Write-Output ('PDF_SIZE=' + (Get-Item $out).Length)
} else {
    Write-Output 'PDF_MISSING'
}
