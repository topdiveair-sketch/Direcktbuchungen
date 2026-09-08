param(
  [string]$OutputPath = "$PSScriptRoot\..\Assets\WachauEtappe.ico"
)

Add-Type -AssemblyName System.Drawing
$dir = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $dir | Out-Null

function New-IconPng([int]$Size) {
  $bmp = [System.Drawing.Bitmap]::new($Size,$Size)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $g.Clear([System.Drawing.Color]::Transparent)

  $green = [System.Drawing.Color]::FromArgb(23,61,50)
  $gold  = [System.Drawing.Color]::FromArgb(220,176,73)
  $white = [System.Drawing.Color]::White
  $bgBrush = [System.Drawing.SolidBrush]::new($green)
  $g.FillEllipse($bgBrush, 2, 2, $Size-4, $Size-4)

  $pen = [System.Drawing.Pen]::new($gold,[single]([Math]::Max(2,$Size/18)))
  $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
  $pen.EndCap   = [System.Drawing.Drawing2D.LineCap]::Round
  [System.Drawing.Point[]]$pts = @(
    [System.Drawing.Point]::new([int]($Size*0.18),[int]($Size*0.70)),
    [System.Drawing.Point]::new([int]($Size*0.36),[int]($Size*0.42)),
    [System.Drawing.Point]::new([int]($Size*0.50),[int]($Size*0.58)),
    [System.Drawing.Point]::new([int]($Size*0.70),[int]($Size*0.28)),
    [System.Drawing.Point]::new([int]($Size*0.83),[int]($Size*0.43))
  )
  $g.DrawLines($pen,$pts)

  $fontSize = [Math]::Max(7,[int]($Size*0.20))
  $font = [System.Drawing.Font]::new('Segoe UI Semibold',[single]$fontSize,[System.Drawing.FontStyle]::Bold,[System.Drawing.GraphicsUnit]::Pixel)
  $brush = [System.Drawing.SolidBrush]::new($white)
  $sf = [System.Drawing.StringFormat]::new()
  $sf.Alignment = [System.Drawing.StringAlignment]::Center
  $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
  $rect = [System.Drawing.RectangleF]::new(0,[single]($Size*0.60),[single]$Size,[single]($Size*0.28))
  $g.DrawString('WE',$font,$brush,$rect,$sf)

  $ms = [System.IO.MemoryStream]::new()
  $bmp.Save($ms,[System.Drawing.Imaging.ImageFormat]::Png)
  $bytes = $ms.ToArray()
  $g.Dispose(); $bmp.Dispose(); $font.Dispose(); $brush.Dispose(); $bgBrush.Dispose(); $pen.Dispose(); $sf.Dispose(); $ms.Dispose()
  return $bytes
}

$sizes = @(16,24,32,48,64,128,256)
$images = @()
foreach($s in $sizes){ $images += ,(New-IconPng $s) }

$fs = [System.IO.File]::Open($OutputPath,[System.IO.FileMode]::Create)
$bw = [System.IO.BinaryWriter]::new($fs)
$bw.Write([UInt16]0); $bw.Write([UInt16]1); $bw.Write([UInt16]$sizes.Count)
$offset = 6 + (16 * $sizes.Count)
for($i=0;$i -lt $sizes.Count;$i++){
  $s=$sizes[$i]; $data=$images[$i]
  $bw.Write([Byte]($(if($s -eq 256){0}else{$s})))
  $bw.Write([Byte]($(if($s -eq 256){0}else{$s})))
  $bw.Write([Byte]0); $bw.Write([Byte]0)
  $bw.Write([UInt16]1); $bw.Write([UInt16]32)
  $bw.Write([UInt32]$data.Length); $bw.Write([UInt32]$offset)
  $offset += $data.Length
}
foreach($data in $images){ $bw.Write($data) }
$bw.Flush(); $bw.Dispose(); $fs.Dispose()
Write-Host "Created $OutputPath"
