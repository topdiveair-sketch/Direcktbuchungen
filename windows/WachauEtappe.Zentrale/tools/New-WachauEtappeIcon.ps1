param(
  [string]$OutputPath = "$PSScriptRoot\..\Assets\WachauEtappe.ico"
)

Add-Type -AssemblyName System.Drawing
$dir = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$size = 256
$bmp = [System.Drawing.Bitmap]::new($size,$size)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.Clear([System.Drawing.Color]::Transparent)

$green = [System.Drawing.Color]::FromArgb(23,61,50)
$gold  = [System.Drawing.Color]::FromArgb(220,176,73)
$white = [System.Drawing.Color]::White
$bgBrush = [System.Drawing.SolidBrush]::new($green)
$g.FillEllipse($bgBrush, 8, 8, 240, 240)

$pen = [System.Drawing.Pen]::new($gold,[single]14)
$pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
$pen.EndCap   = [System.Drawing.Drawing2D.LineCap]::Round
[System.Drawing.Point[]]$pts = @(
  [System.Drawing.Point]::new(45,180),
  [System.Drawing.Point]::new(92,105),
  [System.Drawing.Point]::new(128,145),
  [System.Drawing.Point]::new(180,72),
  [System.Drawing.Point]::new(214,110)
)
$g.DrawLines($pen,$pts)

$font = [System.Drawing.Font]::new('Segoe UI Semibold',[single]48,[System.Drawing.FontStyle]::Bold,[System.Drawing.GraphicsUnit]::Pixel)
$brush = [System.Drawing.SolidBrush]::new($white)
$sf = [System.Drawing.StringFormat]::new()
$sf.Alignment = [System.Drawing.StringAlignment]::Center
$sf.LineAlignment = [System.Drawing.StringAlignment]::Center
$rect = [System.Drawing.RectangleF]::new(0,155,256,70)
$g.DrawString('WE',$font,$brush,$rect,$sf)

$hIcon = $bmp.GetHicon()
$icon = [System.Drawing.Icon]::FromHandle($hIcon)
$fs = [System.IO.File]::Open($OutputPath,[System.IO.FileMode]::Create)
$icon.Save($fs)
$fs.Dispose()

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class NativeIconCleanup {
  [DllImport("user32.dll", CharSet=CharSet.Auto)]
  public static extern bool DestroyIcon(IntPtr handle);
}
'@
[NativeIconCleanup]::DestroyIcon($hIcon) | Out-Null

$g.Dispose(); $bmp.Dispose(); $font.Dispose(); $brush.Dispose(); $bgBrush.Dispose(); $pen.Dispose(); $sf.Dispose()
Write-Host "Created native Windows icon $OutputPath"
