param([Parameter(Mandatory=$true)][string]$InputPptx,[Parameter(Mandatory=$true)][string]$OutDir,[int]$PreviewWidth=1440,[switch]$SkipTextMetrics,[switch]$ExportSvg,[string]$CompositionRequest,[switch]$SaveNativeCopy)
$ErrorActionPreference='Stop'
if (Test-Path -LiteralPath $OutDir) { throw 'Output exists' }
$null=New-Item -ItemType Directory -Path $OutDir
$p=$null
$stage='application'
function RememberVisibility($collection,$records) {
    for($j=1;$j -le $collection.Count;$j++) {
        $shape=$collection.Item($j)
        $records[[string]$shape.Id]=@{name=$shape.Name;visible=$shape.Visible}
        if($shape.Type -eq 6){RememberVisibility $shape.GroupItems $records}
    }
}
function IsolateOwners($collection,$owners,$original,[bool]$selectedParent=$false) {
    for($j=1;$j -le $collection.Count;$j++) {
        $shape=$collection.Item($j)
        $key=[string]$shape.Id
        $selected=$selectedParent -or $owners.ContainsKey($key)
        if($shape.Type -eq 6) {
            # Parent frames remain unchanged; only unowned leaves are hidden.
            IsolateOwners $shape.GroupItems $owners $original $selected
        } else {
            $desired=$(if($selected){$original[$key].visible}else{0})
            if($script:compositionVisibility[$key] -ne $desired){$shape.Visible=$desired;$script:compositionVisibility[$key]=$desired}
        }
    }
}
function RestoreVisibility($collection,$original) {
    for($j=1;$j -le $collection.Count;$j++) {
        $shape=$collection.Item($j)
        $key=[string]$shape.Id
        if($script:compositionVisibility[$key] -ne $original[$key].visible){$shape.Visible=$original[$key].visible;$script:compositionVisibility[$key]=$original[$key].visible}
        if($shape.Type -eq 6){RestoreVisibility $shape.GroupItems $original}
    }
}
function ProjectContainerInterior($collection,$owners) {
    for($j=1;$j -le $collection.Count;$j++) {
        $shape=$collection.Item($j)
        if($shape.Type -eq 6){ProjectContainerInterior $shape.GroupItems $owners;continue}
        if($owners.ContainsKey([string]$shape.Id)) {
            # Only a separate private presentation is projected. Native path,
            # adjustments and parent coordinates remain the saved geometry.
            $shape.Fill.Solid();$shape.Fill.Visible=-1
            $shape.Fill.ForeColor.RGB=0;$shape.Fill.Transparency=0
            $shape.Line.Visible=0
            if($shape.HasTextFrame -eq -1){$shape.TextFrame2.TextRange.Text=''}
        }
    }
}
function HideNonText($collection) {
    for ($j=1;$j -le $collection.Count;$j++) {
        $shape=$collection.Item($j)
        if ($shape.Type -eq 6) {HideNonText $shape.GroupItems;continue}
        if ($shape.HasTable -eq -1) {
            for ($r=1;$r -le $shape.Table.Rows.Count;$r++) {
                for ($c=1;$c -le $shape.Table.Columns.Count;$c++) {
                    $shape.Table.Cell($r,$c).Shape.Fill.Visible=0
                    foreach ($side in @(1,2,3,4,5,6)) {try {$shape.Table.Cell($r,$c).Borders.Item($side).Visible=0}catch{}}
                }
            }
            continue
        }
        $hasWords=($shape.HasTextFrame -eq -1 -and $shape.TextFrame2.TextRange.Length -gt 0)
        if (-not $hasWords) {$shape.Visible=0}
        else {$shape.Fill.Visible=0;$shape.Line.Visible=0}
    }
}
function MeasureText($collection,$records) {
    for ($j=1;$j -le $collection.Count;$j++) {
        $shape=$collection.Item($j)
        if ($shape.Type -eq 6) {MeasureText $shape.GroupItems $records}
        if ($shape.HasTable -eq -1) {
            for ($row=1;$row -le $shape.Table.Rows.Count;$row++) {
                for ($col=1;$col -le $shape.Table.Columns.Count;$col++) {
                    $cellShape=$shape.Table.Cell($row,$col).Shape
                    try {
                        $range=$cellShape.TextFrame2.TextRange
                        $records.Add(@{id=($shape.Name+'@cell:'+($row-1)+':'+($col-1));frame=@($cellShape.Left,$cellShape.Top,$cellShape.Width,$cellShape.Height);ink=@($range.BoundLeft,$range.BoundTop,$range.BoundWidth,$range.BoundHeight);text=$range.Text;unit='pt';status='MEASURED'})
                    } catch {$records.Add(@{id=($shape.Name+'@cell:'+($row-1)+':'+($col-1));status='UNVERIFIED';reason=$_.Exception.Message})}
                }
            }
        }
        if ($shape.HasTextFrame -eq -1) {
            try {
                $range=$shape.TextFrame2.TextRange
                $records.Add(@{id=$shape.Name;frame=@($shape.Left,$shape.Top,$shape.Width,$shape.Height);ink=@($range.BoundLeft,$range.BoundTop,$range.BoundWidth,$range.BoundHeight);text=$range.Text;unit='pt';status='MEASURED'})
            } catch {$records.Add(@{id=$shape.Name;status='UNVERIFIED';reason=$_.Exception.Message})}
        }
    }
}
try {
    $app=New-Object -ComObject PowerPoint.Application
    $inputHash=(Get-FileHash -LiteralPath $InputPptx -Algorithm SHA256).Hash.ToLower()
    $stage='open'
    $p=$app.Presentations.Open($InputPptx,-1,0,0)
    if($SaveNativeCopy){$p.SaveCopyAs((Join-Path $OutDir 'Native_roundtrip.pptx'),24,0)}
    $stage='pdf'
    $pdfRecord=@{status='EXPORTED';path='Final.pdf'}
    try { $p.SaveCopyAs((Join-Path $OutDir 'Final.pdf'),32,0) }
    catch {
        $pdfRecord=@{status='EXPORT_ERROR';path='Final.pdf';reason=$_.Exception.Message;
          next='Keep actual PNG observation separate; use the bound Office layout carrier and vector masters for paper export.'}
        $pdfRecord | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutDir 'pdf-failure.json') -Encoding UTF8
    }
    @{backend='PowerPoint';backend_version=$app.Version;office_build=$app.Build;platform='Windows';pptx_hash=$inputHash;pdf=$pdfRecord} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $OutDir 'office-session.json') -Encoding UTF8
    $stage='png'
    $width=$PreviewWidth
    $height=[int][Math]::Round($width*$p.PageSetup.SlideHeight/$p.PageSetup.SlideWidth)
    $pages=@()
    for ($i=1;$i -le $p.Slides.Count;$i++) {
        $name=if ($i -eq 1) {'Final_preview.png'} else {'Page_'+$i+'.png'}
        $file=Join-Path $OutDir $name
        $p.Slides.Item($i).Export($file,'PNG',$width,$height)
        $pages+=@{slide=$i;path=$name;sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower()}
    }
    $svgRecords=@()
    if ($ExportSvg) {
        for ($i=1;$i -le $p.Slides.Count;$i++) {
            $svgName=if ($i -eq 1) {'Final.svg'} else {'Page_'+$i+'.svg'}
            $svgFile=Join-Path $OutDir $svgName
            try {
                $p.Slides.Item($i).Export($svgFile,'SVG',$width,$height)
                $svgRecords+=@{slide=$i;path=$svgName;status='EXPORTED';sha256=(Get-FileHash -LiteralPath $svgFile -Algorithm SHA256).Hash.ToLower()}
            } catch { $svgRecords+=@{slide=$i;status='EXPORT_ERROR';reason=$_.Exception.Message} }
        }
    }
    $fontRoots=@((Join-Path $env:WINDIR 'Fonts'),(Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\Fonts')) | Where-Object {Test-Path -LiteralPath $_}
    $fontFiles=@(foreach($fontRoot in $fontRoots){Get-ChildItem -LiteralPath $fontRoot -File})
    $fonts=@($fontFiles | Select-Object -ExpandProperty Name | Sort-Object -Unique)
    $fontRecords=@($fontFiles | Sort-Object FullName | ForEach-Object {
        [ordered]@{name=$_.Name;path=$_.FullName;bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()}
    })
    $fontJson=$fontRecords | ConvertTo-Json -Compress -Depth 4
    $sha=[Security.Cryptography.SHA256]::Create()
    $fontHash=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($fontJson)))).Replace('-','').ToLower()
    $sha.Dispose()
    $textBounds=[System.Collections.Generic.List[object]]::new()
    if (-not $SkipTextMetrics) { MeasureText $p.Slides.Item(1).Shapes $textBounds }
    @{pptx_hash=$inputHash;backend='PowerPoint';backend_version=$app.Version;objects=$textBounds} | ConvertTo-Json -Depth 10 |
      Set-Content -LiteralPath (Join-Path $OutDir 'text-bounds.json') -Encoding UTF8
    @{status='PASS';scope='target_render_only';backend='PowerPoint';backend_version=$app.Version;office_build=$app.Build;
      platform='Windows';pptx_hash=$inputHash;pages=$pages;svg=$svgRecords;fonts=$fonts;font_inventory_hash=$fontHash;
      font_identity_method='sha256 of per-file content identities';renderer_script_hash=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLower();
      text_metrics_status=$(if ($SkipTextMetrics) {'NOT_REQUESTED'} else {'MEASURED'});
      pdf=$pdfRecord;
      pdf_hash=$(if($pdfRecord.status -eq 'EXPORTED'){(Get-FileHash -LiteralPath (Join-Path $OutDir 'Final.pdf') -Algorithm SHA256).Hash.ToLower()}else{$null});
      preview_hash=(Get-FileHash -LiteralPath (Join-Path $OutDir 'Final_preview.png') -Algorithm SHA256).Hash.ToLower()} |
        ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $OutDir 'render.json') -Encoding UTF8
    if($CompositionRequest) {
        $stage='semantic-composition'
        $request=Get-Content -LiteralPath $CompositionRequest -Raw -Encoding UTF8 | ConvertFrom-Json
        if($request.schema -ne 'office-composition-capture-1' -or $request.pptx_hash -ne $inputHash){throw 'Composition request is not bound to this native drawing'}
        if(@($request.captures).Count -gt 16){throw 'Use bounded owner-matte batches'}
        $original=@{};RememberVisibility $p.Slides.Item(1).Shapes $original
        $script:compositionVisibility=@{};foreach($key in $original.Keys){$script:compositionVisibility[$key]=$original[$key].visible}
        @{native_ids=$original;count=$original.Count} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $OutDir 'composition-native-owners.json') -Encoding UTF8
        $p.Slides.Item(1).DisplayMasterShapes=0
        $sampleScale=if($request.sampling_scale){[int]$request.sampling_scale}else{3}
        if($sampleScale -lt 3 -or $sampleScale -gt 8){throw 'Bounded composition sampling scale required'}
        $captureRows=@();$cw=[int]$request.canvas[0]*$sampleScale;$ch=[int]$request.canvas[1]*$sampleScale
        if([long]$cw*$ch -gt 64000000){throw 'Composition capture exceeds bounded pixel resources'}
        foreach($capture in $request.captures) {
            $owners=@{};$bindings=@()
            for($ci=0;$ci -lt @($capture.native_ids).Count;$ci++) {
                $key=[string]$capture.native_ids[$ci]
                if(-not $original.ContainsKey($key)){throw ('Missing native owner ID: '+$key)}
                if($original[$key].name -ne $capture.leaf_objects[$ci]){throw ('Native ID/name disagreement: '+$key+' / '+$original[$key].name)}
                $owners[$key]=$true;$bindings+=@{id=$key;name=$original[$key].name}
            }
            IsolateOwners $p.Slides.Item(1).Shapes $owners $original
            $pair=@{}
            $projected=$null;$capturePresentation=$p
            try {
                if($capture.measurement -eq 'container_interior') {
                    $nativeCopy=Join-Path $OutDir ('Interior-'+$capture.id+'.pptx')
                    $p.SaveCopyAs($nativeCopy,24,0)
                    $projected=$app.Presentations.Open($nativeCopy,-1,0,0)
                    ProjectContainerInterior $projected.Slides.Item(1).Shapes $owners
                    $capturePresentation=$projected
                }
                foreach($background in @('black','white')) {
                    $capturePresentation.Slides.Item(1).FollowMasterBackground=0
                    $capturePresentation.Slides.Item(1).Background.Fill.Solid()
                    $capturePresentation.Slides.Item(1).Background.Fill.ForeColor.RGB=$(if($background -eq 'black'){0}else{16777215})
                    $name='Owner-'+$capture.id+'-'+$background+'.png';$file=Join-Path $OutDir $name
                    $capturePresentation.Slides.Item(1).Export($file,'PNG',$cw,$ch)
                    $pair[$background]=@{path=$name;sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower()}
                }
            } finally {if($null -ne $projected){$projected.Close()}}
            $captureRows+=@{id=$capture.id;objects=@($capture.objects);owner_hash=$capture.owner_hash;native_bindings=$bindings;black=$pair.black;white=$pair.white;
                backend='PowerPoint';backend_version=$app.Version;office_build=$app.Build;
                measurement=$capture.measurement;font_inventory_hash=$fontHash;
                renderer_script_hash=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLower()}
        }
        RestoreVisibility $p.Slides.Item(1).Shapes $original
        @{schema='office-composition-observation-1';pptx_hash=$inputHash;canvas=@($request.canvas);
          request_hash=(Get-FileHash -LiteralPath $CompositionRequest -Algorithm SHA256).Hash.ToLower();captures=$captureRows;
          scope='Original transforms, compound paths, opacity and groups preserved; private native copy, two controlled backdrops; saved input unchanged'} |
          ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $OutDir 'composition-capture.json') -Encoding UTF8
    }
    # Observe the unchanged native glyphs without nearby non-text paint. This
    # is a private in-memory copy; never save over or close user presentations.
    if (-not $SkipTextMetrics) {
        HideNonText $p.Slides.Item(1).Shapes
        $p.Slides.Item(1).Background.Fill.Solid()
        $p.Slides.Item(1).Background.Fill.ForeColor.RGB=16777215
        $isolated=Join-Path $OutDir 'Text-owners-only.pptx'
        $p.SaveCopyAs($isolated,24,0)
        $glyphFile=Join-Path $OutDir 'Text-owners-only.png'
        $p.Slides.Item(1).Export($glyphFile,'PNG',$width,$height)
        @{schema='office-native-text-ownership-1';pptx_hash=$inputHash;
          isolated_pptx_hash=(Get-FileHash -LiteralPath $isolated -Algorithm SHA256).Hash.ToLower();
          preview_path='Text-owners-only.png';preview_hash=(Get-FileHash -LiteralPath $glyphFile -Algorithm SHA256).Hash.ToLower();
          backend='PowerPoint';renderer_script_hash=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLower();
          limits='Native glyph/paragraph properties and group coordinates unchanged; only non-text paint hidden on the owned copy.'} |
          ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $OutDir 'text-ownership.json') -Encoding UTF8
    }
} catch {
    @{status='BLOCKED';stage=$stage;reason=$_.Exception.Message;line=$_.InvocationInfo.ScriptLineNumber} | ConvertTo-Json |
      Set-Content -LiteralPath (Join-Path $OutDir 'failure.json') -Encoding UTF8
    throw
} finally { if ($null -ne $p) {$p.Close()} }
