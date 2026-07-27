$ErrorActionPreference = 'Stop'

Write-Host ''
Write-Host 'Gurevic Real Estate - Dropbox connection' -ForegroundColor Cyan
Write-Host 'Enter the App key and App secret from Dropbox App Console.'
Write-Host 'They are used only in this window and are not saved to files.' -ForegroundColor DarkGray
Write-Host ''

$env:DROPBOX_APP_KEY = Read-Host 'Dropbox App key'
$secret = Read-Host 'Dropbox App secret' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
  $env:DROPBOX_APP_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  $oauthScript = Join-Path $PSScriptRoot 'dropbox_authorize.py'
  $python = Get-Command py -ErrorAction SilentlyContinue
  if ($python) {
    & py $oauthScript
  } else {
    & python $oauthScript
  }
} finally {
  if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
  Remove-Item Env:DROPBOX_APP_KEY -ErrorAction SilentlyContinue
  Remove-Item Env:DROPBOX_APP_SECRET -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host 'Copy the refresh token into GitHub Secret DROPBOX_REFRESH_TOKEN. Do not send it in chat.' -ForegroundColor Yellow
