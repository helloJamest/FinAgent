$ErrorActionPreference = 'Stop'

Write-Host 'Building React UI (static assets)...'
Push-Location 'apps\finagent-web'
if (!(Test-Path 'node_modules')) {
  npm install
}
npm run build
Pop-Location

Write-Host 'Starting Electron desktop (dev mode)...'
Push-Location 'apps\finagent-desktop'
if (!(Test-Path 'node_modules')) {
  npm install
}
npm run dev
Pop-Location
