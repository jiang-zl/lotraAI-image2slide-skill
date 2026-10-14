param([Parameter(Mandatory=$true)][string]$Request)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$job=Get-Content -LiteralPath $Request -Raw -Encoding UTF8 | ConvertFrom-Json
if((Get-FileHash -LiteralPath $job.input -Algorithm SHA256).Hash.ToLowerInvariant() -ne $job.input_sha256){throw 'Font provider input changed'}
if(Test-Path -LiteralPath $job.output){throw 'Font provider output must be new'}
$outputDirectory=Split-Path -Parent $job.output
[IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
$staged=Join-Path $outputDirectory 'font-provider-owned-input.pptx'
if(Test-Path -LiteralPath $staged){throw 'Preserve the previous provider attempt'}
Copy-Item -LiteralPath $job.input -Destination $staged
$presentation=$null
$application=$null
try {
  try {$application=[Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application')}
  catch {$application=New-Object -ComObject PowerPoint.Application}
  $presentation=$application.Presentations.Open($staged,$true,$false,$false)
  $presentation.SaveCopyAs([string]$job.output,24,1)
  $fonts=@()
  foreach($font in $presentation.Fonts){$fonts+=@{name=[string]$font.Name;embedded=([int]$font.Embedded -ne 0)}}
  $receipt=@{status='OFFICE_FONT_SAVE_EXECUTED';input_sha256=$job.input_sha256;output=$job.output;
    output_sha256=(Get-FileHash -LiteralPath $job.output -Algorithm SHA256).Hash.ToLowerInvariant();
    office_version=[string]$application.Version;opened_input_font_metadata=$fonts;
    scope='Staged font-save provider; saved font parts are handled separately; original file untouched; no rendering or native edit claim'}
  $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $job.receipt -Encoding UTF8
} finally {
  if($null -ne $presentation){$presentation.Close();[Runtime.InteropServices.Marshal]::ReleaseComObject($presentation) | Out-Null}
  if($null -ne $application){[Runtime.InteropServices.Marshal]::ReleaseComObject($application) | Out-Null}
  # Never Quit/Kill shared Office or close any user document.
}
