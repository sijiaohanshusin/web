$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$distDir = Join-Path $repoRoot 'docs\manuals\dist'
$documents = Get-ChildItem -LiteralPath $distDir -Filter '*.docx' | Sort-Object Name

if (-not $documents) {
    throw "No DOCX manuals found in $distDir"
}

$formatPdf = 17
foreach ($file in $documents) {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $null
    try {
        $document = $word.Documents.Open($file.FullName, $false, $true)
        $pdfPath = [System.IO.Path]::ChangeExtension($file.FullName, '.pdf')
        $document.ExportAsFixedFormat($pdfPath, $formatPdf)
        Write-Output "Exported $pdfPath"
    }
    finally {
        try {
            if ($null -ne $document) {
                $document.Close($false)
                [System.Runtime.InteropServices.Marshal]::ReleaseComObject($document) | Out-Null
            }
        }
        catch [System.Runtime.InteropServices.COMException] {
        }
        try {
            $word.Quit()
        }
        catch [System.Runtime.InteropServices.COMException] {
        }
        try {
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
        }
        catch [System.Runtime.InteropServices.COMException] {
        }
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
    }
}
