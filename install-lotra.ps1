param([Parameter(Mandatory=$true)][string]$Project)
function Get-LotraResource {
 param([string]$Uri,[string]$Destination,[string]$Sha256,[long]$Bytes)
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
   $request=[Net.HttpWebRequest]::Create($Uri);$request.Timeout=60000;$request.ReadWriteTimeout=60000
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
$projectRoot=(Resolve-Path -LiteralPath $Project).Path
$releaseRoot=Join-Path $projectRoot '.lotraAI-build/releases/1.33.0'
New-Item -ItemType Directory -Path $releaseRoot -Force|Out-Null
$archive=Join-Path $releaseRoot 'update.zip'
Get-LotraResource -Uri 'https://github.com/jiang-zl/lotraAI-image2slide-skill/releases/download/v1.33.0/lotraAI-image2slide-v1.33.0-update.zip' -Destination $archive -Sha256 '3718fb5b5b99205577a113a318fddda71b128ef2b8cbd5130b9840ff5035e080' -Bytes 4305380
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip=[IO.Compression.ZipFile]::OpenRead($archive)
try{
 foreach($entry in $zip.Entries){
  if($entry.FullName -match '(^|/)[.][.](/|$)|\\|:' -or $entry.FullName.StartsWith('/') -or (($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000){throw 'Unsafe release member.'}
  $destination=[IO.Path]::GetFullPath((Join-Path $releaseRoot $entry.FullName))
  if(-not $destination.StartsWith($releaseRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Release path escaped root.'}
  [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))|Out-Null
  $inputStream=$entry.Open();$outputStream=[IO.File]::Open($destination,[IO.FileMode]::Create)
  try{$inputStream.CopyTo($outputStream)}finally{$outputStream.Dispose();$inputStream.Dispose()}
 }
}finally{$zip.Dispose()}
& (Join-Path $releaseRoot 'installer/install.ps1') -Project $projectRoot
exit $LASTEXITCODE
