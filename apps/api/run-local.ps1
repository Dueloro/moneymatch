# Run feat/beta-tournaments locally as ONE process: the API, with the worker
# loop (settlement + background PUBG/chess match fetching) running inside it,
# exactly as it runs on the free-tier deploy.
#
#   powershell -NoExit -File run-local.ps1
#
# (`run-local.ps1 worker` still starts a standalone worker, but you don't need
# one: if both run, a Postgres lock lets only one loop do the work.)
#
# Loads ../../.env into this process (so PUBG_API_KEY etc. are always picked
# up), then points DATABASE_URL at `moneymatch_future` — this branch's database
# (migrated to 0034). Your main `moneymatch` database (feat/bucket_system) is
# never touched. No --reload: it wedges on this machine.
#
# Test timings: joins close after 2 min and the tournament runs 40 min. A PUBG
# game counts if it starts after you join and you die (or win) before the end;
# your first 3 such games count. Then a 2 min grace before the final fetch.
# Delete these three lines for the real 1 h join window / 3 h tournament /
# per-game grace.
param([ValidateSet('api', 'worker')][string]$What = 'api')

Set-Location $PSScriptRoot
Get-Content ..\..\.env | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        Set-Item -Path "env:$($matches[1])" -Value $matches[2].Trim().Trim('"').Trim("'")
    }
}
$env:DATABASE_URL = 'postgresql+asyncpg://moneymatch:moneymatch@localhost:5432/moneymatch_future'
$env:TOURNAMENT_JOIN_WINDOW_SECONDS = '120'
$env:TOURNAMENT_WINDOW_SECONDS = '2400'
$env:TOURNAMENT_GRACE_SECONDS = '120'
# The worker loop runs inside the API process (also the default in config).
$env:RUN_WORKER_IN_PROCESS = if ($What -eq 'api') { 'true' } else { 'false' }

$keyState = if ($env:PUBG_API_KEY) { 'set' } else { 'MISSING' }
Write-Host "[$What] database: moneymatch_future | PUBG key: $keyState" -ForegroundColor Cyan

if ($What -eq 'api') {
    $host.UI.RawUI.WindowTitle = 'moneymatch API + worker :8000 (moneymatch_future)'
    .\.venv\Scripts\python.exe -m uvicorn moneymatch_api.main:app --port 8000
} else {
    $host.UI.RawUI.WindowTitle = 'moneymatch worker (moneymatch_future)'
    .\.venv\Scripts\python.exe -m moneymatch_api.workers.settlement_worker
}
