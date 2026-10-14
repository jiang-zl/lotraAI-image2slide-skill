param(
 [Parameter(Mandatory=$true)][ValidateSet('render','native','components')][string]$Kind,
 [Parameter(Mandatory=$true)][string]$InputPptx,
 [Parameter(Mandatory=$true)][string]$OutDir,
 [string]$PlanPath,
 [int]$PreviewWidth=1600,
 [switch]$SkipTextMetrics,
 [switch]$ExportSvg,
 [switch]$SaveNativeCopy,
 [string]$CompositionRequest,
 [ValidateRange(30,1800)][int]$TimeoutSeconds=300
)
$ErrorActionPreference='Stop'
# WSL can inherit a PowerShell 7 module search path while launching Windows
# PowerShell 5.1. Prefer this executable's built-in modules in this process only.
$env:PSModulePath=(Join-Path $PSHOME 'Modules')+[IO.Path]::PathSeparator+$env:PSModulePath
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -Force
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Management\Microsoft.PowerShell.Management.psd1') -Force
if(Test-Path -LiteralPath $OutDir){throw 'Office job output already exists'}
if($Kind -eq 'native' -and -not $PlanPath){throw 'Native job requires its bound plan'}
$inputHash=(Get-FileHash -LiteralPath $InputPptx -Algorithm SHA256).Hash.ToLower()
$jobRoot=Join-Path ([IO.Path]::GetTempPath()) ('sci-rebuild-office\'+[Guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $jobRoot -Force
$localInput=Join-Path $jobRoot 'Input.pptx';Copy-Item -LiteralPath $InputPptx -Destination $localInput
if((Get-FileHash -LiteralPath $localInput -Algorithm SHA256).Hash.ToLower() -ne $inputHash){throw 'Office staging changed input'}
$scriptName=switch($Kind){'render'{'render_office.ps1'}'native'{'native_task_probe.ps1'}'components'{'probe_saved_components.ps1'}}
$localScript=Join-Path $jobRoot $scriptName;Copy-Item -LiteralPath (Join-Path $PSScriptRoot $scriptName) -Destination $localScript
$localOutput=Join-Path $jobRoot 'result'
$arguments=@{InputPptx=$localInput;OutDir=$localOutput}
if($Kind -eq 'native'){
 $localPlan=Join-Path $jobRoot 'plan.json';Copy-Item -LiteralPath $PlanPath -Destination $localPlan
 $arguments.PlanPath=$localPlan
}elseif($Kind -eq 'components'){$arguments.ExpectedHash=$inputHash}
else{
 if($SaveNativeCopy){$arguments.SaveNativeCopy=$true}
 $arguments.PreviewWidth=$PreviewWidth;if($SkipTextMetrics){$arguments.SkipTextMetrics=$true};if($ExportSvg){$arguments.ExportSvg=$true}
 if(-not $CompositionRequest){$possible=Join-Path (Split-Path -Parent $InputPptx) 'semantic-composition-capture.json';if(Test-Path -LiteralPath $possible){$CompositionRequest=$possible}}
 if($CompositionRequest){$localRequest=Join-Path $jobRoot 'semantic-composition-capture.json';Copy-Item -LiteralPath $CompositionRequest -Destination $localRequest;$arguments.CompositionRequest=$localRequest}
}
@{script=$localScript;arguments=$arguments} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $jobRoot 'job.json') -Encoding UTF8
$child=Join-Path $jobRoot 'execute.ps1'
@'
$ErrorActionPreference='Stop'
$env:PSModulePath=(Join-Path $PSHOME 'Modules')+[IO.Path]::PathSeparator+$env:PSModulePath
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -Force
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Management\Microsoft.PowerShell.Management.psd1') -Force
$job=Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $PSScriptRoot 'job.json') | ConvertFrom-Json
$parameters=@{};foreach($property in $job.arguments.PSObject.Properties){$parameters[$property.Name]=$property.Value}
try{
 & $job.script @parameters
 @{status='COMPLETED';exit_code=0} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'execute-status.json') -Encoding UTF8
 exit 0
}catch{
 @{status='FAILED';exit_code=1;reason=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'execute-status.json') -Encoding UTF8
 Write-Error $_
 exit 1
}
'@ | Set-Content -LiteralPath $child -Encoding UTF8
$watch=[Diagnostics.Stopwatch]::StartNew()
$windowsPowerShell=Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
# Case-duplicate inherited environment names (PATH/Path) can make Windows
# PowerShell's Start-Process fail before the helper starts. Normalize only this
# child environment; never modify machine/user environment or shared Office.
$startInfo=New-Object Diagnostics.ProcessStartInfo
$startInfo.FileName=$windowsPowerShell
$startInfo.Arguments='-NoProfile -ExecutionPolicy Bypass -File "'+$child+'"'
$startInfo.UseShellExecute=$false
$startInfo.CreateNoWindow=$true
$startInfo.WindowStyle=[Diagnostics.ProcessWindowStyle]::Hidden
$startInfo.RedirectStandardOutput=$true
$startInfo.RedirectStandardError=$true
$startInfo.EnvironmentVariables.Clear()
foreach($entry in [Environment]::GetEnvironmentVariables().GetEnumerator()){
 $startInfo.EnvironmentVariables[$entry.Key.ToUpperInvariant()]=$entry.Value
}
$process=New-Object Diagnostics.Process
$process.StartInfo=$startInfo
$null=$process.Start()
$stdoutRead=$process.StandardOutput.ReadToEndAsync()
$stderrRead=$process.StandardError.ReadToEndAsync()
$processHandle=$process.Handle
$finished=$process.WaitForExit($TimeoutSeconds*1000)
$watch.Stop()
$receipt=[ordered]@{kind=$Kind;input_pptx_hash=$inputHash;staging_directory=$jobRoot;timeout_seconds=$TimeoutSeconds;elapsed_seconds=$watch.Elapsed.TotalSeconds;
 status='PENDING';wrapper_hash=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLower();scope='Isolated local staging; original PPT and unrelated PowerPoint documents are untouched'}
if(-not $finished){
 # Stop only the helper we created. Never kill the shared PowerPoint process.
 Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
 $receipt.status='PAUSED_RESOURCE_LIMIT';$receipt.note='Task-specific PowerPoint copy may remain open; inspect this staging path before resuming.'
 $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $jobRoot 'job-receipt.json') -Encoding UTF8
 throw ('Office helper exceeded resource limit. Preserved work: '+$jobRoot)
}
$process.Refresh()
[IO.File]::WriteAllText((Join-Path $jobRoot 'stdout.txt'),$stdoutRead.Result,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $jobRoot 'stderr.txt'),$stderrRead.Result,[Text.UTF8Encoding]::new($false))
$executionPath=Join-Path $jobRoot 'execute-status.json'
$execution=if(Test-Path -LiteralPath $executionPath){Get-Content -Raw -Encoding UTF8 -LiteralPath $executionPath | ConvertFrom-Json}else{$null}
if(($null -ne $process.ExitCode -and $process.ExitCode -ne 0) -or $null -eq $execution -or $execution.status -ne 'COMPLETED'){
 $receipt.status='FAILED';$receipt.exit_code=$process.ExitCode
 $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $jobRoot 'job-receipt.json') -Encoding UTF8
 Write-Output ('LOTRAAI_OFFICE_FAILURE:'+($receipt | ConvertTo-Json -Compress -Depth 8))
 Get-Content -LiteralPath (Join-Path $jobRoot 'stderr.txt')
 throw ('Office helper failed. Preserved work: '+$jobRoot)
}
if((Get-FileHash -LiteralPath $InputPptx -Algorithm SHA256).Hash.ToLower() -ne $inputHash){throw 'Original input changed during Office job'}
$receipt.status='COMPLETED_REQUIRES_RESULT_REVIEW'
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $localOutput 'job-receipt.json') -Encoding UTF8
Copy-Item -LiteralPath $localOutput -Destination $OutDir -Recurse
$receipt | ConvertTo-Json -Depth 8
