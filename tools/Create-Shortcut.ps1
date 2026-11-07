# Windows shortcuts store absolute paths; rerun after moving the checkout.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $projectRoot 'Start-KopierCommander.lnk'))
$shortcut.TargetPath = Join-Path $projectRoot 'Start-KopierCommander.cmd'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = (Join-Path $projectRoot 'src\kopier_commander\assets\kopier-commander.ico') + ',0'
$shortcut.Description = 'Kopier Commander starten'
$shortcut.WindowStyle = 7
$shortcut.Save()
Write-Host 'Start-KopierCommander.lnk created.'
