param([Parameter(Mandatory=$true)][string]$InputPptx,[Parameter(Mandatory=$true)][string]$OutDir)
$ErrorActionPreference='Stop'
if (Test-Path -LiteralPath $OutDir) {throw 'Output exists'}
$null=New-Item -ItemType Directory -Path $OutDir
$p=$null
try {
    $app=New-Object -ComObject PowerPoint.Application
    $inputHash=(Get-FileHash -LiteralPath $InputPptx -Algorithm SHA256).Hash.ToLower()
    $p=$app.Presentations.Open($InputPptx,-1,0,0)
    $entries=@()
    for ($i=1;$i -le $p.Slides.Count;$i++) {
        $s=$p.Slides.Item($i)
        if ($s.Shapes.Count -ne 1 -or $s.Shapes.Item(1).Type -ne 6) {throw 'One native group per component page required'}
        $shape=$s.Shapes.Item(1)
        if ($shape.Name -notmatch '^[A-Za-z][A-Za-z0-9_.-]*$') {throw 'Unsafe component filename'}
        $assets=@()
        foreach ($format in @(@('png',2),@('svg',6))) {
            $path=Join-Path $OutDir ($shape.Name+'.'+$format[0])
            try {
                $shape.Export($path,[int]$format[1],[int]($p.PageSetup.SlideWidth*2),[int]($p.PageSetup.SlideHeight*2),1)
                $assets+=@{format=$format[0];status='EXPORTED';path=($shape.Name+'.'+$format[0]);sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()}
            } catch {$assets+=@{format=$format[0];status='UNVERIFIED';reason=$_.Exception.Message}}
        }
        $entries+=@{semantic_id=$shape.Name;slide=$i;assets=$assets}
    }
    @{status='EXECUTED_REQUIRES_VERIFICATION';backend='PowerPoint';backend_version=$app.Version;office_build=$app.Build;source_pptx_hash=$inputHash;components=$entries} |
        ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $OutDir 'assets.json') -Encoding UTF8
} finally {if ($null -ne $p) {$p.Close()}}
