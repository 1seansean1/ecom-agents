$env:PYTHONUTF8 = "1"
Set-Location "c:\Users\seanp\Workspace\ecom-agents"
& ".\.venv\Scripts\python.exe" -m uvicorn src.serve:app --host 0.0.0.0 --port 8050
