param([Parameter(Mandatory=$true)][string]$InputPptx,
      [Parameter(Mandatory=$true)][string]$OutputDirectory,
      [Parameter(Mandatory=$true)][string]$InputSha256,
      [Parameter(Mandatory=$true)][string]$WordManifest)
$ErrorActionPreference='Stop'
if ((Get-FileHash -LiteralPath $InputPptx -Algorithm SHA256).Hash.ToLowerInvariant() -ne $InputSha256) {throw 'Bind the exact saved native slide'}
if (Test-Path -LiteralPath $OutputDirectory) {throw 'Preserve previous actual exports'}
[System.IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
$ownedFile=Join-Path $OutputDirectory 'Owned-native-words.pptx'
Copy-Item -LiteralPath $InputPptx -Destination $ownedFile
$manifest=Get-Content -LiteralPath $WordManifest -Raw -Encoding UTF8 | ConvertFrom-Json
$presentation=$null; $application=$null
$receipt=[ordered]@{source_pptx_hash=$InputSha256; stage='staged'; words=@(); scope='Owned read-only slide; actual Office native word EMF/PNG and character advances; original PPT/global Office unchanged'}
function Save-Receipt { $receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'Native-word-export-receipt.json') -Encoding UTF8 }
Save-Receipt
try {
    $receipt.stage='connect-office'; Save-Receipt
    $application=New-Object -ComObject PowerPoint.Application
    $receipt.office_version=$application.Version
    $receipt.stage='open-owned-slide'; Save-Receipt
    $presentation=$application.Presentations.Open($ownedFile,-1,0,0)
    $receipt.slide_points=@($presentation.PageSetup.SlideWidth,$presentation.PageSetup.SlideHeight)
    foreach($entry in $manifest.word_export_inputs.PSObject.Properties) {
        $ident=$entry.Name; $spec=$entry.Value
        $receipt.stage='locate-'+$ident; Save-Receipt
        $collection=$presentation.Slides.Item(1).Shapes
        foreach($parentName in $spec.native_parent_chain) { $collection=$collection.Item($parentName).GroupItems }
        $shape=$collection.Item($spec.native_shape_name)
        $range=$shape.TextFrame.TextRange
        if ($range.Text -cne $spec.literal) {throw 'Actual native word content differs from its bound manifest'}
        $chars=@()
        for($index=1;$index -le $range.Length;$index++) {
            $char=$range.Characters($index,1)
            $chars+=@{literal=$char.Text; font=$char.Font.Name; bold=$char.Font.Bold; size_points=$char.Font.Size; advance_bounds_points=@($char.BoundLeft,$char.BoundTop,$char.BoundWidth,$char.BoundHeight)}
        }
        $receipt.stage='EMF-'+$ident; Save-Receipt
        $emf=Join-Path $OutputDirectory ($ident+'.emf')
        $shape.Export($emf,5)
        $receipt.stage='PNG-'+$ident; Save-Receipt
        $png=Join-Path $OutputDirectory ($ident+'.png')
        $shape.Export($png,2,[int][Math]::Ceiling($presentation.PageSetup.SlideWidth*4),[int][Math]::Ceiling($presentation.PageSetup.SlideHeight*4))
        $receipt.words+=@{id=$ident; native_shape_name=$shape.Name; native_bbox_points=@($shape.Left,$shape.Top,$shape.Width,$shape.Height); word_advance_bounds_points=@($range.BoundLeft,$range.BoundTop,$range.BoundWidth,$range.BoundHeight); characters=$chars; emf_sha256=(Get-FileHash -LiteralPath $emf -Algorithm SHA256).Hash.ToLowerInvariant(); png_sha256=(Get-FileHash -LiteralPath $png -Algorithm SHA256).Hash.ToLowerInvariant()}
        Save-Receipt
    }
    $receipt.stage='EXPORTED'; Save-Receipt
} catch {
    $receipt.error=@{stage=$receipt.stage; message=$_.Exception.Message; hresult=$_.Exception.HResult}; $receipt.stage='EXPORT_ERROR'; Save-Receipt
    throw
} finally {
    if ($null -ne $presentation) {try {$presentation.Close()} catch {$receipt.close_error=$_.Exception.Message; Save-Receipt}}
    if ($null -ne $application) {[System.Runtime.InteropServices.Marshal]::ReleaseComObject($application) | Out-Null}
}
