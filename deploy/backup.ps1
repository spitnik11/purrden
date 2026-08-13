param([string]$Output = ".\backups")
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $Output | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
docker compose -f "$PSScriptRoot\compose\docker-compose.yml" exec -T postgres pg_dump -U purrden -Fc purrden > "$Output\purrden-$stamp.dump"
Write-Host "Backup written to $Output\purrden-$stamp.dump"
