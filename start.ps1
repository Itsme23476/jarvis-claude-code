# Launch the JARVIS memory HUD on Windows. Mirrors start.sh.
# Uses the self-contained interpreter in .python\ so no system Python is needed.
Set-Location -Path $PSScriptRoot

# Never set ANTHROPIC_API_KEY and never pass --bare: both force API-key auth and
# bypass the Claude subscription. Clear it for this process in case it leaked in.
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue

# Don't hijack the default browser; open http://localhost:8720 yourself.
if (-not $env:JARVIS_OPEN) { $env:JARVIS_OPEN = "0" }

# The startup banner uses box-drawing characters; a cp1252 stdout cannot encode
# them and server.py dies before it ever binds. Force UTF-8 for Python's I/O.
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

& "$PSScriptRoot\.python\python.exe" "$PSScriptRoot\server.py"
