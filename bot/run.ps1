# run.ps1 — Windows launcher/supervisor for the BTC 5m paper bot.
# Windows equivalent of run.sh. Auto-restarts the bot if it ever exits, so a
# plain "start at boot" task keeps it alive. No caffeinate (a server stays awake;
# set the power plan to never sleep: powercfg /change standby-timeout-ac 0).
#
# Start it via Task Scheduler ("run whether user is logged on or not", trigger
# At startup) or wrap it with NSSM as a service — see MIGRATION-WINDOWS.md.

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
Set-Location $here

# Load signal.env (KEY=VALUE lines, optional leading 'export ') into this process.
$envfile = Join-Path $here 'signal.env'
if (Test-Path $envfile) {
  foreach ($raw in Get-Content $envfile) {
    $line = ($raw -replace '^\s*export\s+', '').Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
      $i = $line.IndexOf('=')
      $k = $line.Substring(0, $i).Trim()
      $v = $line.Substring($i + 1).Trim()
      [Environment]::SetEnvironmentVariable($k, $v, 'Process')
    }
  }
}
$sigEngines = if ($env:SIGNAL_ENGINES) { $env:SIGNAL_ENGINES } else { '' }
$py = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }

while ($true) {
  "$(Get-Date -Format o)  launching bot ($py)" | Add-Content "$here\bot.log"
  & $py "$here\btc5m_bot.py" `
    --asset BTC --loose 7 --stake 50 --bank 1000 --slip 1 --profile conservative `
    --state "$here\state.json" --publish --branch data --repo-dir "$repo" `
    --publish-every 300 --signal-engines "$sigEngines" --signal-file "$here\signal.json" `
    *>> "$here\bot.log"
  "$(Get-Date -Format o)  bot exited ($LASTEXITCODE) — restarting in 5s" | Add-Content "$here\bot.log"
  Start-Sleep -Seconds 5
}
