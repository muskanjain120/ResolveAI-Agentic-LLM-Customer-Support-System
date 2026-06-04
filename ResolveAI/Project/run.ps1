$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            Set-Item -Path "env:$name" -Value $value
        }
    }
    Write-Host "Loaded .env" -ForegroundColor DarkGray
}

if (-not (Test-Path "data")) {
    New-Item -ItemType Directory -Path "data" | Out-Null
}

Write-Host "Starting FastAPI backend..." -ForegroundColor Green
Start-Process -NoNewWindow -FilePath "uvicorn" -ArgumentList "backend.server:app --host 0.0.0.0 --port 8000 --reload"

Start-Sleep -Seconds 3

Write-Host "Starting Streamlit frontend..." -ForegroundColor Green
Start-Process -NoNewWindow -FilePath "streamlit" -ArgumentList "run frontend/app.py --server.port 8501"

Write-Host ""
Write-Host "System running:" -ForegroundColor Cyan
Write-Host "   API docs  ->  http://localhost:8000/docs"
Write-Host "   Dashboard ->  http://localhost:8501"
Write-Host ""
Write-Host "Demo user: alex.morgan@example.com (user_id=1)" -ForegroundColor Yellow
Write-Host "Press Ctrl+C in each terminal to stop." -ForegroundColor DarkGray
