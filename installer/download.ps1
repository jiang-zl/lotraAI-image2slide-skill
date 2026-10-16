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
