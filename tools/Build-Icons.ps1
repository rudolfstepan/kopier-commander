# Rebuild the icon assets using only Windows/.NET drawing tools.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$assets = Join-Path $projectRoot 'src\kopier_commander\assets'
New-Item -ItemType Directory -Force -Path $assets | Out-Null
Add-Type -AssemblyName System.Drawing

function New-CommanderBitmap([int] $size) {
    # Draw at four times the final resolution for clean small-size edges.
    $bitmap = New-Object System.Drawing.Bitmap ($size * 4), ($size * 4)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.ScaleTransform(($size * 4 / 256.0), ($size * 4 / 256.0))
    $graphics.Clear([System.Drawing.Color]::Transparent)
    $background = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#101b62'))
    $panel = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#17419c'))
    $cyan = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#55ffff'))
    $yellow = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#ffff55'))
    $border = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml('#55ffff')), 7
    $shape = New-Object System.Drawing.Drawing2D.GraphicsPath
    foreach ($arc in @(@(8, 8, 180), @(200, 8, 270), @(200, 200, 0), @(8, 200, 90))) {
        $shape.AddArc($arc[0], $arc[1], 48, 48, $arc[2], 90)
    }
    $shape.CloseFigure()
    $graphics.FillPath($background, $shape)
    foreach ($x in @(31, 143)) {
        $graphics.FillRectangle($panel, $x, 40, 82, 176)
        $graphics.DrawRectangle($border, $x, 40, 82, 176)
        $graphics.FillRectangle($cyan, $x, 40, 82, 23)
        foreach ($y in @(83, 105, 177)) {
            $graphics.FillRectangle($cyan, ($x + 13), $y, 9, 8)
            $graphics.FillRectangle($cyan, ($x + 31), $y, 37, 8)
        }
    }
    # A dark outline separates the copy arrow from the two panel borders.
    $arrow = [System.Drawing.PointF[]] @(
        (New-Object System.Drawing.PointF 76, 126),
        (New-Object System.Drawing.PointF 145, 126),
        (New-Object System.Drawing.PointF 145, 109),
        (New-Object System.Drawing.PointF 190, 144),
        (New-Object System.Drawing.PointF 145, 179),
        (New-Object System.Drawing.PointF 145, 162),
        (New-Object System.Drawing.PointF 76, 162)
    )
    $outline = New-Object System.Drawing.Pen ($background.Color), 12
    $outline.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
    $graphics.DrawPolygon($outline, $arrow)
    $graphics.FillPolygon($yellow, $arrow)
    $result = New-Object System.Drawing.Bitmap $size, $size
    $resize = [System.Drawing.Graphics]::FromImage($result)
    $resize.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $resize.DrawImage($bitmap, 0, 0, $size, $size)
    $resize.Dispose()
    $graphics.Dispose()
    $bitmap.Dispose()
    foreach ($resource in @($background, $panel, $cyan, $yellow, $border, $shape, $outline)) { $resource.Dispose() }
    return $result
}

$sizes = @(16, 20, 24, 32, 48, 64, 128, 256)
$frames = @()
foreach ($size in $sizes) {
    $bitmap = New-CommanderBitmap $size
    $stream = New-Object System.IO.MemoryStream
    try {
        $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
        $frames += ,$stream.ToArray()
        if ($size -in @(16, 32, 48, 256)) {
            [System.IO.File]::WriteAllBytes((Join-Path $assets "kopier-commander-$size.png"), $stream.ToArray())
        }
    } finally { $stream.Dispose(); $bitmap.Dispose() }
}

$iconPath = Join-Path $assets 'kopier-commander.ico'
$writer = New-Object System.IO.BinaryWriter ([System.IO.File]::Create($iconPath))
try {
    $writer.Write([uint16] 0)
    $writer.Write([uint16] 1)
    $writer.Write([uint16] $sizes.Count)
    $offset = 6 + 16 * $sizes.Count
    for ($i = 0; $i -lt $sizes.Count; $i++) {
        $dimension = $sizes[$i] % 256
        $writer.Write([byte] $dimension)
        $writer.Write([byte] $dimension)
        $writer.Write([uint16] 0)
        $writer.Write([uint16] 1)
        $writer.Write([uint16] 32)
        $writer.Write([uint32] $frames[$i].Length)
        $writer.Write([uint32] $offset)
        $offset += $frames[$i].Length
    }
    foreach ($frame in $frames) { $writer.Write([byte[]] $frame) }
} finally { $writer.Dispose() }

Write-Host 'Icon assets rebuilt.'
