# Simple file watcher for Python development
param(
    [string]$Path = "src\backend",
    [string]$Filter = "*.py",
    [string]$Command = "python app.py"
)

$job = $null

function Start-App {
    if ($job) {
        Stop-Job $job -PassThru | Remove-Job
    }
    
    Write-Host "Starting application..." -ForegroundColor Green
    $job = Start-Job -ScriptBlock {
        param($cmd)
        Invoke-Expression $cmd
    } -ArgumentList $Command
}

# Start the app initially
Start-App

# Set up file watcher
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = (Resolve-Path $Path).Path
$watcher.Filter = $Filter
$watcher.IncludeSubdirectories = $true
$watcher.EnableRaisingEvents = $true

# Define the action
$action = {
    $path = $Event.SourceEventArgs.FullPath
    $name = $Event.SourceEventArgs.Name
    $changeType = $Event.SourceEventArgs.ChangeType
    
    Write-Host "File $name $changeType at $path" -ForegroundColor Yellow
    Start-Sleep -Seconds 1  # Debounce
    Start-App
}

# Register the event
Register-ObjectEvent -InputObject $watcher -EventName "Changed" -Action $action

Write-Host "Watching $Path for changes. Press Ctrl+C to stop." -ForegroundColor Cyan

try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
} finally {
    $watcher.EnableRaisingEvents = $false
    $watcher.Dispose()
    if ($job) {
        Stop-Job $job -PassThru | Remove-Job
    }
}
