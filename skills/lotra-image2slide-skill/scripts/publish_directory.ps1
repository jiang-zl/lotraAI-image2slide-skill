param([Parameter(Mandatory=$true)][string]$SourceDirectory,[Parameter(Mandatory=$true)][string]$TargetDirectory)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$source=[IO.Path]::GetFullPath($SourceDirectory)
$target=[IO.Path]::GetFullPath($TargetDirectory)
if(![string]::Equals([IO.Path]::GetDirectoryName($source),[IO.Path]::GetDirectoryName($target),[StringComparison]::OrdinalIgnoreCase)){throw 'Delivery stage and final must be siblings on the chosen volume'}
if(!(Test-Path -LiteralPath $source -PathType Container)){throw 'Owned source directory is missing'}
if((Get-Item -LiteralPath $source -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Refuse linked delivery stage'}
# Directory.Move uses the Windows no-replace operation, including on NTFS when
# invoked from WSL/DrvFs. It does not replace an existing empty target directory.
[IO.Directory]::Move($source,$target)
