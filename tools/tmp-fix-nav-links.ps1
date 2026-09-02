$ErrorActionPreference = 'Stop'
$path = 'stations/001-TestStation/TestStationOMJSON.json'
$data = Get-Content $path -Raw | ConvertFrom-Json

# Map: inpatient_name => (slug, term1_override)
# These are the key missing combined pages for cardiovascular and other navs
$inptToCombined = [ordered]@{
  'ORZID2 GMENU ABX DIAGNOSIS OF ENDOCARDITIS' = @('diagnosis-of-endocarditis', 'Diagnosis of Endocarditis')
  'ORZID2 GMENU ABX MYOCARDITIS' = @('myocarditis', 'Myocarditis')
  'ORZID2 GMENU ABX PERICARDITIS' = @('pericarditis', 'Pericarditis')
  'ORZID2 GMENU LYME CARDIAC DISEASE' = @('lyme-cardiac-disease', 'Cardiac Lyme Disease')
  'ORZID2 GMENU EC PV EMP THERAPY' = @('prosthetic-valve-endocarditis-empirical-therapy', 'Prosthetic Valve Endocarditis - Empirical Therapy')
  'ORZID2 GMENU EC PV SEL PATH' = @('prosthetic-valve-endocarditis-selected-pathogens', 'Prosthetic Valve Endocarditis - Selected Pathogens')
  'ORZID2 GMENU ABX APPRO TO ENDOCARDITIS' = @('approach-to-endocarditis', 'Approach to Endocarditis')
}

$created = @()
$skipped = @()

# Create missing combined pages
foreach($inptName in $inptToCombined.Keys){
  $slug, $term1 = $inptToCombined[$inptName]
  
  # Check if combined page already exists
  if($data.menus | Where-Object { $_.Name -eq $slug }){
    continue
  }
  
  # Find inpatient source
  $src = $data.menus | Where-Object { $_.Name -eq $inptName } | Select-Object -First 1
  if(-not $src){
    $skipped += "$inptName (no inpatient source found)"
    continue
  }
  
  # Create combined page object
  $obj = [pscustomobject]@{
    Name = $slug
    Term1 = $term1
    Term2 = ''
    Text = $src.Text
    LinkTargets = if($src.LinkTargets){ $src.LinkTargets } else { @() }
    Inpt = $src.Name
  }
  if($src.Outpt){ $obj | Add-Member -NotePropertyName Outpt -NotePropertyValue $src.Outpt }
  if($src.ERUC){ $obj | Add-Member -NotePropertyName ERUC -NotePropertyValue $src.ERUC }
  
  $data.menus += $obj
  $created += "$slug <= $inptName"
}

# Now update navigation pages to link to new combined pages
# For cardiovascular: link "Diagnosis of Endocarditis", "Myocarditis", "Pericarditis", "Cardiac Lyme Disease" as markdown links
$cardio = $data.menus | Where-Object { $_.Name -eq 'cardiovascular' } | Select-Object -First 1
if($cardio){
  $replacements = @(
    @{ old = '^Diagnosis of Endocarditis$'; new = '[Diagnosis of Endocarditis](diagnosis-of-endocarditis)' }
    @{ old = '^Native Valve Endocarditis$'; new = '[Native Valve Endocarditis](orzid2-gmenu-ec-nv-emp-thera)' }
    @{ old = '^Prosthetic Valve Endocarditis$'; new = '[Prosthetic Valve Endocarditis](prosthetic-valve-endocarditis-empirical-therapy)' }
    @{ old = '^Cardiac Lyme Disease$'; new = '[Cardiac Lyme Disease](lyme-cardiac-disease)' }
    @{ old = '^Myocarditis$'; new = '[Myocarditis](myocarditis)' }
    @{ old = '^Pericarditis$'; new = '[Pericarditis](pericarditis)' }
  )
  
  $lines = $cardio.Text -split '\n'
  $updatedLines = @()
  foreach($line in $lines){
    $updated = $line
    foreach($repl in $replacements){
      if($line -match $repl.old){
        $updated = $line -replace $repl.old, $repl.new
        break
      }
    }
    $updatedLines += $updated
  }
  $cardio.Text = $updatedLines -join "`n"
}

# Save
$data | ConvertTo-Json -Depth 100 | Set-Content $path

"Created: $($created.Count) combined pages"
$created

"Skipped: $($skipped.Count)"
$skipped | ForEach-Object { "  $_" }
