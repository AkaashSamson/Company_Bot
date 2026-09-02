[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$StreamlitPort = 8501
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "The project virtual environment was not found at .venv\Scripts\python.exe"
}
$ApiCommand = "Set-Location '$ProjectRoot'; `$env:PYTHONPATH='$ProjectRoot'; & '$VenvPython' -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort"
$UiCommand = "Set-Location '$ProjectRoot'; & '$VenvPython' -m streamlit run streamlit_app/app.py --server.port $StreamlitPort"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $ApiCommand
Start-Process powershell -ArgumentList "-NoExit", "-Command", $UiCommand

Write-Host "FastAPI:   http://127.0.0.1:$ApiPort"
Write-Host "Streamlit: http://127.0.0.1:$StreamlitPort"
