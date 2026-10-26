$ErrorActionPreference = 'Stop'
$appName = 'Growth Cockpit'
$installDir = Join-Path $env:LOCALAPPDATA 'GrowthCockpit'
$desktop = [Environment]::GetFolderPath('Desktop')
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$url = 'https://zab-windis-growth-runtime.topdiveair.workers.dev/cockpit'

New-Item -ItemType Directory -Force -Path $installDir | Out-Null

$launcher = @"
`$url = '$url'
`$edge = Join-Path `${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
`$chrome = Join-Path `$env:ProgramFiles 'Google\Chrome\Application\chrome.exe'
if (Test-Path `$edge) { Start-Process `$edge -ArgumentList '--app='+`$url; exit }
if (Test-Path `$chrome) { Start-Process `$chrome -ArgumentList '--app='+`$url; exit }
Start-Process `$url
"@
$launcherPath = Join-Path $installDir 'GrowthCockpit.ps1'
Set-Content -Path $launcherPath -Value $launcher -Encoding UTF8

$cmd = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcherPath`"`r`n"
$cmdPath = Join-Path $installDir 'Growth Cockpit.cmd'
Set-Content -Path $cmdPath -Value $cmd -Encoding ASCII

$ws = New-Object -ComObject WScript.Shell
foreach ($shortcutPath in @((Join-Path $desktop 'Growth Cockpit.lnk'), (Join-Path $startMenu 'Growth Cockpit.lnk'))) {
  $shortcut = $ws.CreateShortcut($shortcutPath)
  $shortcut.TargetPath = $cmdPath
  $shortcut.WorkingDirectory = $installDir
  $shortcut.Description = 'Growth Cockpit - wirtschaftliche Steuerung fuer Zuhause am Bach und Windis'
  $shortcut.Save()
}

$uninstall = @"
`$ErrorActionPreference='SilentlyContinue'
Remove-Item -Force (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Growth Cockpit.lnk')
Remove-Item -Force (Join-Path `$env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Growth Cockpit.lnk')
Remove-Item -Recurse -Force '$installDir'
"@
Set-Content -Path (Join-Path $installDir 'Uninstall.ps1') -Value $uninstall -Encoding UTF8

Write-Host 'Growth Cockpit wurde installiert.' -ForegroundColor Green
Write-Host 'Desktop- und Startmenue-Verknuepfung wurden angelegt.'
Write-Host 'Der ADMIN_TOKEN ist absichtlich nicht im Installer gespeichert.'
Start-Process $cmdPath
