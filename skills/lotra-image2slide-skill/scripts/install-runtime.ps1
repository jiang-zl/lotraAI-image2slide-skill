param([Parameter(Mandatory=$true)][string]$Project,[string]$DownloadBundle,[string]$BundleRoot)
function Get-LotraResource {
 param([string]$Uri,[string]$Destination,[string]$Sha256,[long]$Bytes,[string]$ApiUri)
 $ErrorActionPreference='Stop'
 if($Sha256 -notmatch '^[a-f0-9]{64}$' -or $Bytes -le 0){throw 'Invalid pinned resource.'}
 if(Test-Path -LiteralPath $Destination){
  if((Get-Item -LiteralPath $Destination).Length -eq $Bytes -and (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant() -eq $Sha256){return}
  throw 'Preserve changed download.'
 }
 $partial=$Destination+'.part';$owner=$Destination+'.owner'
 if(Test-Path -LiteralPath $owner){if([IO.File]::ReadAllText($owner) -ne ($Sha256+':'+$Bytes)){throw 'Preserve foreign download checkpoint.'}}
 else{if(Test-Path -LiteralPath $partial){throw 'Preserve unowned partial.'};[IO.File]::WriteAllText($owner,($Sha256+':'+$Bytes))}
 for($attempt=0;$attempt -lt 3;$attempt++){
  try{
   $offset=if(Test-Path -LiteralPath $partial){(Get-Item -LiteralPath $partial).Length}else{0}
   if($offset -eq $Bytes -and (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -eq $Sha256){Move-Item -LiteralPath $partial -Destination $Destination;return}
   if($offset -ge $Bytes){[IO.File]::WriteAllBytes($partial,[byte[]]@());$offset=0}
   if($attempt -gt 0 -and $ApiUri){$Uri=$ApiUri}
   $request=[Net.HttpWebRequest]::Create($Uri);
   if($Uri.StartsWith('https://api.github.com/')){$request.Accept='application/octet-stream'};$request.Timeout=60000;$request.ReadWriteTimeout=60000
   if($attempt -gt 0 -and $lastFailure -match '10061|refused|拒绝'){$request.Proxy=$null}
   if($offset -gt 0){$request.AddRange($offset)}
   $response=$request.GetResponse()
   try{
    if([int]$response.StatusCode -eq 206){if($response.Headers['Content-Range'] -notmatch ('^bytes '+$offset+'-\d+/'+$Bytes+'$')){throw 'Range mismatch.'}}
    elseif([int]$response.StatusCode -eq 200){$offset=0}else{throw 'Unexpected HTTP status.'}
    $stream=$response.GetResponseStream();$file=[IO.File]::Open($partial,$(if($offset -gt 0){[IO.FileMode]::Append}else{[IO.FileMode]::Create}))
    try{
     $buffer=New-Object byte[] (1024*1024);$total=$offset
     while(($read=$stream.Read($buffer,0,$buffer.Length)) -gt 0){$total+=$read;if($total -gt $Bytes){throw 'Download byte limit.'};$file.Write($buffer,0,$read)}
    }finally{$file.Dispose();$stream.Dispose()}
   }finally{$response.Dispose()}
   if((Get-Item -LiteralPath $partial).Length -eq $Bytes -and (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -eq $Sha256){Move-Item -LiteralPath $partial -Destination $Destination;return}
  }catch{$lastFailure=$_.Exception.Message}
  if($attempt -lt 2){Start-Sleep -Seconds ([Math]::Min(4,[Math]::Pow(2,$attempt)))}
 }
 throw ('DOWNLOAD_LIMIT_REACHED: '+$lastFailure+'; retain partial and rerun the same command.')
}

$ErrorActionPreference='Stop'
# Host-owned PowerShell utility module; do not inherit an incompatible Core module.
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1') -ErrorAction Stop
$projectRoot=(Resolve-Path -LiteralPath $Project).Path
if($projectRoot -eq [IO.Path]::GetPathRoot($projectRoot) -or $projectRoot -eq $env:USERPROFILE){throw 'Choose a project directory.'}
# Local bundle dispatch: prepare resources before registering the main skill.
if($DownloadBundle -and $BundleRoot){throw 'Choose bundle download or local installation.'}
if($BundleRoot){
 $localRoot=(Resolve-Path -LiteralPath $BundleRoot).Path
 $localEntry=Join-Path $localRoot 'installer/install.ps1'
 if(-not(Test-Path -LiteralPath $localEntry -PathType Leaf)){throw 'The supplied bundle has no installer/install.ps1.'}
 & $localEntry -Project $projectRoot -Harness codex
 exit $LASTEXITCODE
}
$state=Join-Path $projectRoot '.lotraAI-build/install-entry'
New-Item -ItemType Directory -Path $state -Force|Out-Null
$python=$null
$descriptor=Join-Path $projectRoot '.lotraAI-build/toolchain/core-runtime-windows-amd64-cp312.json'
if(Test-Path -LiteralPath $descriptor){
 $prior=Get-Content -LiteralPath $descriptor -Raw|ConvertFrom-Json
 if($prior.engine.path -notmatch '^\.lotraAI-build[/\\]' -or $prior.engine.path -match '[.][.]'){throw 'Invalid prepared engine path.'}
 $candidate=Join-Path $projectRoot $prior.engine.path
 if((Test-Path -LiteralPath $candidate) -and (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant() -eq $prior.engine.sha256){$python=$candidate}
}
if(-not $python){
 $base=Join-Path $projectRoot '.lotraAI-build/bootstrap/e0f12f47ffb709e2401825fe9dc6a386ec52962ffc96bdb0af06bfc93b471f42'
 $archive=Join-Path $projectRoot '.lotraAI-build/install-entry/e0f12f47ffb709e2401825fe9dc6a386ec52962ffc96bdb0af06bfc93b471f42.zip'
 New-Item -ItemType Directory -Path $base -Force|Out-Null
 Get-LotraResource -Uri 'https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/download/v1.34.0/windows-amd64-cp312.zip' -Destination $archive -Sha256 'e0f12f47ffb709e2401825fe9dc6a386ec52962ffc96bdb0af06bfc93b471f42' -Bytes 23135647 -ApiUri 'https://api.github.com/repos/jiang-zl/lotraAI-image2slide-skill-runtime/releases/assets/647391937'
 $python=Join-Path $base 'python/python.exe'
 if(-not(Test-Path -LiteralPath $python)){
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $zip=[IO.Compression.ZipFile]::OpenRead($archive)
  try{
   foreach($entry in $zip.Entries){
    if($entry.FullName -notmatch '^python/' -or $entry.FullName -match '(^|/)[.][.](/|$)|\\|:' -or (($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000){throw 'Unsafe Python archive member.'}
    $destination=[IO.Path]::GetFullPath((Join-Path $base $entry.FullName))
    if(-not $destination.StartsWith($base+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Python path escaped root.'}
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))|Out-Null
    if($entry.FullName.EndsWith('/')){continue}
    if(Test-Path -LiteralPath $destination){continue}
    $inp=$entry.Open();$out=[IO.File]::Open($destination,[IO.FileMode]::CreateNew)
    try{$inp.CopyTo($out)}finally{$out.Dispose();$inp.Dispose()}
   }
  }finally{$zip.Dispose()}
 }
 if((Get-FileHash -LiteralPath $python -Algorithm SHA256).Hash.ToLowerInvariant() -ne '86c4690be87a6bb6be1affe24b3c1b67ceedc86b477d6cde9f812fafd0f6d3b9'){throw 'Python executable differs.'}
}
$entryRoot=Join-Path $projectRoot '.lotraAI-build/bootstrap/ae1a062cab42fe36e5c851fc1e3d70c64f5817bd8837378350a7b9ca56022694'
New-Item -ItemType Directory -Path $entryRoot -Force|Out-Null
$entry=Join-Path $entryRoot 'install_lotra.py'
Get-LotraResource -Uri 'https://raw.githubusercontent.com/jiang-zl/lotraAI-image2slide-skill-runtime/1.37.4/tools/install_lotra.py' -Destination $entry -Sha256 'ae1a062cab42fe36e5c851fc1e3d70c64f5817bd8837378350a7b9ca56022694' -Bytes 10280
$entryArgs=@('--project',$projectRoot)
if($DownloadBundle -and $BundleRoot){throw 'Choose bundle download or local installation.'}
if($DownloadBundle){$entryArgs+=@('--download-bundle',$DownloadBundle)}
if($BundleRoot){$entryArgs+=@('--bundle-root',$BundleRoot)}
& $python -I -X utf8 -B $entry @entryArgs
exit $LASTEXITCODE
