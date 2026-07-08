param(
  [ValidateSet('Export','Import')]
  [string]$Mode = 'Export'
)

$ErrorActionPreference = 'Stop'

$abxSource = 'AbxLinks.json'
$omSource = 'stations/001-TestStation/TestStationOMJSON.json'

$abxWrapper = 'cms-data/abx-links.cms.json'
$omWrapper = 'cms-data/teststation-om.cms.json'

function Write-JsonFile {
  param(
    [Parameter(Mandatory = $true)] $Data,
    [Parameter(Mandatory = $true)] [string]$Path
  )

  $json = $Data | ConvertTo-Json -Depth 100
  Set-Content -Path $Path -Value $json -Encoding utf8
}

if ($Mode -eq 'Export') {
  New-Item -ItemType Directory -Path 'cms-data' -Force | Out-Null

  $abx = Get-Content -Path $abxSource -Raw | ConvertFrom-Json
  $om = Get-Content -Path $omSource -Raw | ConvertFrom-Json

  Write-JsonFile -Data ([ordered]@{ entries = @($abx) }) -Path $abxWrapper
  Write-JsonFile -Data ([ordered]@{ menus = @($om) }) -Path $omWrapper

  Write-Output 'Export complete: wrapper files refreshed from source JSON.'
  exit 0
}

$abxCms = Get-Content -Path $abxWrapper -Raw | ConvertFrom-Json
$omCms = Get-Content -Path $omWrapper -Raw | ConvertFrom-Json

if ($null -eq $abxCms.entries) {
  throw "Missing 'entries' in $abxWrapper"
}
if ($null -eq $omCms.menus) {
  throw "Missing 'menus' in $omWrapper"
}

Write-JsonFile -Data @($abxCms.entries) -Path $abxSource
Write-JsonFile -Data @($omCms.menus) -Path $omSource

Write-Output 'Import complete: source JSON updated from CMS wrapper files.'
