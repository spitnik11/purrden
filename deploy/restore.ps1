param([Parameter(Mandatory)][string]$Backup)
$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Backup)) { throw "Backup not found: $Backup" }
Get-Content -LiteralPath $Backup -AsByteStream -Raw | docker compose -f "$PSScriptRoot\compose\docker-compose.yml" exec -T postgres pg_restore -U purrden -d purrden --clean --if-exists
