param([Parameter(Mandatory=$true)][string]$Project,[ValidateSet('auto','codex','claude','generic')][string]$Harness='auto',[switch]$Update)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1') -ErrorAction Stop
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$projectPath=(Resolve-Path -LiteralPath $Project).Path
if($projectPath -eq [IO.Path]::GetPathRoot($projectPath) -or $projectPath -eq [Environment]::GetFolderPath('UserProfile')){throw 'Select an existing project directory.'}
$manifest=Get-Content -LiteralPath (Join-Path $root 'Bundle-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if($manifest.schema -ne 'lotra-offline-product-bundle-1' -or $manifest.version -ne '1.36.0'){throw 'Unsupported pinned release.'}
if([Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString() -ne 'X64'){throw 'Complete Windows AMD64 runtime required.'}
$key='windows-amd64-cp312';$record=$manifest.engines.$key;$python=$null
$descriptor=Join-Path $projectPath '.lotraAI-build/toolchain/core-runtime-windows-amd64-cp312.json'
if(Test-Path -LiteralPath $descriptor){
 $old=Get-Content -LiteralPath $descriptor -Raw -Encoding UTF8 | ConvertFrom-Json
 $candidate=[IO.Path]::GetFullPath((Join-Path $projectPath $old.engine.path))
 if(-not $candidate.StartsWith($projectPath+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Prepared interpreter escaped project.'}
 if((Test-Path -LiteralPath $candidate) -and (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant() -eq $old.engine.sha256){$python=$candidate}
}
if(-not $python){
 $archive=Join-Path $root $record.path
 if(-not(Test-Path -LiteralPath $archive)){
  $release=Get-Content -LiteralPath (Join-Path $root 'Update-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
  . (Join-Path $PSScriptRoot 'download.ps1')
  $cache=Join-Path $projectPath '.lotraAI-build/downloads/bootstrap';New-Item -ItemType Directory -Path $cache -Force | Out-Null
  $archive=Join-Path $cache ($record.sha256+'.zip')
  Get-LotraResource -Uri $release.resources.($record.path).url -Destination $archive -Sha256 $record.sha256 -Bytes $record.bytes
 }
 if((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.sha256){throw 'Bootstrap archive checksum mismatch.'}
 $bootstrap=Join-Path $projectPath ('.lotraAI-build/bootstrap/'+$record.sha256)
 $cursor=[IO.Path]::GetFullPath($bootstrap)
 while($cursor -and $cursor.StartsWith($projectPath,[StringComparison]::OrdinalIgnoreCase)){
  if((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Preserve redirected bootstrap path.'}
  if($cursor -eq $projectPath){break};$cursor=[IO.Path]::GetDirectoryName($cursor)
 }
 New-Item -ItemType Directory -Path $bootstrap -Force | Out-Null
 $ownerFile=Join-Path $bootstrap 'lotra-bootstrap-owner.txt'
 if(Test-Path -LiteralPath $ownerFile){if([IO.File]::ReadAllText($ownerFile) -ne $record.sha256){throw 'Preserve another bootstrap.'}}
 else{if((Get-ChildItem -LiteralPath $bootstrap -Force|Measure-Object).Count -gt 0){throw 'Preserve unowned bootstrap files.'};[IO.File]::WriteAllText($ownerFile,$record.sha256)}
 Add-Type -AssemblyName System.IO.Compression.FileSystem
 $zip=[IO.Compression.ZipFile]::OpenRead($archive)
 try{
  $expanded=[long]0
  foreach($entry in $zip.Entries){
   if($entry.FullName -notmatch '^python/' -or $entry.FullName -match '(^|/)[.][.](/|$)|\\|:' -or (($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000){throw 'Unsafe bootstrap member.'}
   $destination=[IO.Path]::GetFullPath((Join-Path $bootstrap $entry.FullName))
   if(-not $destination.StartsWith($bootstrap+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Bootstrap member escaped root.'}
   $expanded+=$entry.Length;if($expanded -gt $record.uncompressed_bytes){throw 'Bootstrap expansion limit.'}
   if($entry.FullName.EndsWith('/')){[IO.Directory]::CreateDirectory($destination)|Out-Null;continue}
   [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))|Out-Null
   if(Test-Path -LiteralPath $destination){
    $inputStream=$entry.Open();$hasher=[Security.Cryptography.SHA256]::Create()
    try{$memberHash=([BitConverter]::ToString($hasher.ComputeHash($inputStream))).Replace('-','').ToLowerInvariant()}finally{$hasher.Dispose();$inputStream.Dispose()}
    if((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $memberHash){throw 'Preserve changed bootstrap member.'};continue
   }
   $inputStream=$entry.Open();$outputStream=[IO.File]::Open($destination,[IO.FileMode]::CreateNew)
   try{$inputStream.CopyTo($outputStream)}finally{$outputStream.Dispose();$inputStream.Dispose()}
  }
 }finally{$zip.Dispose()}
 $python=Join-Path $bootstrap $record.executable
 if((Get-FileHash -LiteralPath $python -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.executable_sha256){throw 'Bootstrap interpreter mismatch.'}
}
if(Test-Path -LiteralPath (Join-Path $root 'Differential-manifest.json')){
 & $python -I -X utf8 -B (Join-Path $PSScriptRoot 'differential.py') --project $projectPath --harness $Harness --catalog (Join-Path $root 'Differential-manifest.json')
 exit $LASTEXITCODE
}
$entry=if(Test-Path -LiteralPath (Join-Path $root 'Update-manifest.json')){'online.py'}else{'install.py'}
& $python -I -X utf8 -B (Join-Path $PSScriptRoot $entry) --project $projectPath --harness $Harness --bundle-root $root
exit $LASTEXITCODE
