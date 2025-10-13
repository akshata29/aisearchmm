#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Start the complete Teams-integrated RAG application
.DESCRIPTION
    This script starts:
    1. The Python backend server (port 50505)
    2. The React frontend with Teams integration (port 5173)
    3. The Teams bot with DevTools (port 3979)
#>

Write-Host "🚀 Starting Teams-Integrated RAG Application..." -ForegroundColor Green

# Function to check if port is available
function Test-Port {
    param([int]$Port)
    $null = netstat -an | Select-String ":$Port "
    return $LASTEXITCODE -ne 0
}

# Check if required ports are available
$ports = @(50505, 5173, 3979)
foreach ($port in $ports) {
    if (!(Test-Port $port)) {
        Write-Host "⚠️  Port $port is already in use. Please close the application using it." -ForegroundColor Yellow
    }
}

Write-Host ""

# Start backend server
Write-Host "📊 Starting Python backend server (port 50505)..." -ForegroundColor Cyan
Start-Process pwsh -ArgumentList "-Command", "cd 'd:\repos\aisearchmm\src\backend'; python app.py" -WindowStyle Normal

Start-Sleep -Seconds 3

# Start frontend with Teams integration
Write-Host "🎨 Starting React frontend with Teams integration (port 5173)..." -ForegroundColor Cyan
Start-Process pwsh -ArgumentList "-Command", "cd 'd:\repos\aisearchmm\src\frontend'; npm run dev" -WindowStyle Normal

Start-Sleep -Seconds 3

# Start Teams bot with DevTools
Write-Host "🤖 Starting Teams bot with DevTools (port 3979)..." -ForegroundColor Cyan
Start-Process pwsh -ArgumentList "-Command", "cd 'd:\repos\aisearchmm\src\teams-app'; npm start" -WindowStyle Normal

Start-Sleep -Seconds 5

Write-Host ""
Write-Host "✅ All services started!" -ForegroundColor Green
Write-Host ""
Write-Host "📱 Access your application:" -ForegroundColor Yellow
Write-Host "   • Teams DevTools:     http://localhost:3979/devtools" -ForegroundColor White
Write-Host "   • Frontend (standalone): http://localhost:5173" -ForegroundColor White
Write-Host "   • Backend API:        http://localhost:50505" -ForegroundColor White
Write-Host ""
Write-Host "🎯 To test in Microsoft Teams:" -ForegroundColor Yellow
Write-Host "   1. Open Teams DevTools: http://localhost:3979/devtools" -ForegroundColor White
Write-Host "   2. Click 'Preview in Teams' to upload the app" -ForegroundColor White
Write-Host "   3. Test the bot, message extensions, and tab integration" -ForegroundColor White
Write-Host ""
Write-Host "💡 Features available:" -ForegroundColor Yellow
Write-Host "   • Bot commands: /help, /popular, /reset" -ForegroundColor White
Write-Host "   • Message extensions: askRag, searchRag" -ForegroundColor White
Write-Host "   • Native tab with SSO and Teams context" -ForegroundColor White

Write-Host ""
Write-Host "Press any key to continue..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")