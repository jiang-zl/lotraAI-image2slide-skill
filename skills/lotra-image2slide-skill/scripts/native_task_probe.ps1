param([Parameter(Mandatory=$true)][string]$InputPptx,[Parameter(Mandatory=$true)][string]$OutDir,[string]$PlanPath,[switch]$DecodeNativeEmf,[int]$PreviewWidth=0,[int]$PreviewHeight=0)
$ErrorActionPreference='Stop'
if (Test-Path -LiteralPath $OutDir) {throw 'Output already exists'}
function WriteNativeEmfPixels([string]$file,[string]$png,[int]$width,[int]$height){
 if($width -lt 32 -or $width -gt 12000 -or $height -lt 1 -or $height -gt 12000){throw 'Invalid fixed EMF preview canvas'}
 Add-Type -AssemblyName System.Drawing
 $image=[System.Drawing.Imaging.Metafile]::new($file);$bitmap=[System.Drawing.Bitmap]::new($width,$height);$graphics=[System.Drawing.Graphics]::FromImage($bitmap)
 try{$graphics.Clear([System.Drawing.Color]::White);$graphics.DrawImage($image,[System.Drawing.Rectangle]::new(0,0,$width,$height));$bitmap.Save($png,[System.Drawing.Imaging.ImageFormat]::Png)}
 finally{$graphics.Dispose();$bitmap.Dispose();$image.Dispose()}
}
if($DecodeNativeEmf){
 $null=New-Item -ItemType Directory -Path $OutDir
 WriteNativeEmfPixels $InputPptx (Join-Path $OutDir 'Final_preview.png') $PreviewWidth $PreviewHeight
 exit 0
}
if(-not $PlanPath){throw 'Native editing mode requires its bound plan'}
$plan=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
$inputHash=(Get-FileHash -LiteralPath $InputPptx -Algorithm SHA256).Hash.ToLower()
if ($inputHash -ne $plan.pptx_hash) {throw 'Plan does not bind input PPTX'}
$scriptHash=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLower()
if ($scriptHash -ne $plan.probe_script_hash) {throw 'Native probe script changed since plan creation'}
$null=New-Item -ItemType Directory -Path $OutDir
$copy=Join-Path $OutDir 'Native_test_copy.pptx'
Copy-Item -LiteralPath $InputPptx -Destination $copy
$p=$null;$records=[System.Collections.Generic.List[object]]::new();$ancestorUngroups=[System.Collections.Generic.List[object]]::new()
if(-not ('SciRebuildTaskWindow' -as [type])){
 Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class SciRebuildTaskWindow { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int n); }'
}
function ActivateTaskSlide($application,$presentation){
 $window=$presentation.Windows.Item(1);$window.Activate();$window.ViewType=9;$window.View.GotoSlide(1)
 if($window.Active -ne -1){throw 'Task window did not become active'}
 $null=[SciRebuildTaskWindow]::ShowWindow([IntPtr]$application.HWND,9)
 $null=[SciRebuildTaskWindow]::SetForegroundWindow([IntPtr]$application.HWND)
 for($j=1;$j -le $window.Panes.Count;$j++){if($window.Panes.Item($j).ViewType -eq 1){$window.Panes.Item($j).Activate()}}
 if($null -eq $application.ActiveWindow -or $application.ActiveWindow.Presentation.FullName -ne $presentation.FullName){throw 'Refusing to select outside the task presentation'}
}
function FindShape($collection,[string]$name) {
    for ($i=1;$i -le $collection.Count;$i++) {
        $shape=$collection.Item($i)
        if ($shape.Name -eq $name) {return $shape}
        if ($shape.Type -eq 6) {$found=FindShape $shape.GroupItems $name;if ($null -ne $found) {return $found}}
    }
    return $null
}
function ShapeAt($slide,$names) {
    $desired=[string]$names[-1]
    for ($depth=0;$depth -le $names.Count;$depth++) {
        try {return ,$slide.Shapes.Item($desired)} catch {}
        $root=$null
        foreach ($name in $names) {try {$root=$slide.Shapes.Item([string]$name);break} catch {}}
        if ($null -eq $root -or $root.Type -ne 6) {throw ('Native object unavailable: '+$desired)}
        try {return ,$root.GroupItems.Item($desired)} catch {}
        # This Office build exposes descendant leaves, but not nested group
        # handles. Explicitly ungroup ancestors in the isolated test copy.
        $owner=$root.Name;$parts=$root.Ungroup();$partNames=@()
        for ($j=1;$j -le $parts.Count;$j++) {$partNames+=$parts.Item($j).Name}
        $ancestorUngroups.Add(@{ancestor=$owner;purpose=('access '+$desired);parts=$partNames})
    }
    throw ('Native group could not be exposed: '+$desired)
}
function RenameProbe($shape,[string]$prefix) {
    if ($shape.Type -eq 6) {
        $children=$shape.Ungroup()
        for ($k=1;$k -le $children.Count;$k++) {RenameProbe $children.Item($k) $prefix}
    } else {
        if (-not $shape.Name.StartsWith($prefix)) {$shape.Name=$prefix+$shape.Name}
    }
}
function CollectBounds($collection,$records) {
    for ($j=1;$j -le $collection.Count;$j++) {
        $s=$collection.Item($j)
        if ($s.Type -eq 6) {CollectBounds $s.GroupItems $records}
        if ($s.HasTextFrame -eq -1) {
            try {$r=$s.TextFrame2.TextRange;$records.Add(@{id=$s.Name;frame=@($s.Left,$s.Top,$s.Width,$s.Height);ink=@($r.BoundLeft,$r.BoundTop,$r.BoundWidth,$r.BoundHeight);unit='pt';status='MEASURED'})}
            catch {$records.Add(@{id=$s.Name;status='UNVERIFIED';reason=$_.Exception.Message})}
        }
    }
}
function ExportEditedTextMathOwners($presentation,$plan,[string]$directory,[int]$width){
    if(@($plan.actions | Where-Object {$_.action -notin @('math','text')}).Count -gt 0){throw 'Owner-only rendering cannot verify geometric or connector edit actions'}
    $names=@($plan.actions | Select-Object -ExpandProperty id -Unique)
    if($names.Count -eq 0){throw 'No edited text/math owners'}
    $folder=Join-Path $directory 'After-owner-renders';$null=New-Item -ItemType Directory -Path $folder
    $result=[Collections.Generic.List[object]]::new()
    for($i=0;$i -lt $names.Count;$i++){
      $name=[string]$names[$i];$shape=FindShape $presentation.Slides.Item(1).Shapes $name
      if($null -eq $shape -or $shape.Width -le 0 -or $shape.Height -le 0){throw ('Edited owner cannot be rendered: '+$name)}
      $emf=Join-Path $folder ('owner-'+$i+'.emf');$png=Join-Path $folder ('owner-'+$i+'.png')
      $shape.Export($emf,5)
      $pixelWidth=[int][Math]::Max(32,[Math]::Round($shape.Width*$width/$presentation.PageSetup.SlideWidth))
      $pixelHeight=[int][Math]::Max(1,[Math]::Round($pixelWidth*$shape.Height/$shape.Width))
      WriteNativeEmfPixels $emf $png $pixelWidth $pixelHeight
      $operations=@();for($j=0;$j -lt $plan.actions.Count;$j++){if($plan.actions[$j].id -eq $name){$operations+=$j}}
      $result.Add(@{object=$name;operation_indices=$operations;frame_pt=@($shape.Left,$shape.Top,$shape.Width,$shape.Height);canvas_px=@($pixelWidth,$pixelHeight);
        emf=('After-owner-renders/owner-'+$i+'.emf');preview=('After-owner-renders/owner-'+$i+'.png');
        emf_sha256=(Get-FileHash -LiteralPath $emf -Algorithm SHA256).Hash.ToLower();preview_sha256=(Get-FileHash -LiteralPath $png -Algorithm SHA256).Hash.ToLower()})
    }
    return ,$result
}
try {
    $app=New-Object -ComObject PowerPoint.Application
    $app.Visible=-1
    $p=$app.Presentations.Open($copy,0,0,-1)
    ActivateTaskSlide $app $p
    $slide=$p.Slides.Item(1)
    $bounds=[System.Collections.Generic.List[object]]::new();CollectBounds $slide.Shapes $bounds
    @{pptx_hash=$inputHash;backend='PowerPoint';backend_version=$app.Version;objects=$bounds} | ConvertTo-Json -Depth 10 |
      Set-Content -LiteralPath (Join-Path $OutDir 'text-bounds-before.json') -Encoding UTF8
    $beforeDir=Join-Path $OutDir 'before';$null=New-Item -ItemType Directory -Path $beforeDir
    $width=[int]$plan.preview_width;$height=[int][Math]::Round($width*$p.PageSetup.SlideHeight/$p.PageSetup.SlideWidth)
    $beforeEmfHash=$null;$beforeEmfPreviewHash=$null
    if($null -ne $plan.verified_before_render){
      if($plan.verified_before_render.pptx_hash -ne $inputHash){throw 'Cached before-render is for different native bytes'}
      $expectedFiles=@('Final.pdf','Final_preview.png','render.json','job-receipt.json','office-session.json')
      if(@($plan.verified_before_render.files.PSObject.Properties).Count -ne $expectedFiles.Count){throw 'Incomplete before-render cache'}
      $cacheTotal=0L
      foreach($name in $expectedFiles){
        $record=$plan.verified_before_render.files.$name;$file=Join-Path $beforeDir $name
        $encoded=[Convert]::FromBase64String($record.base64)
        if($record.encoding -eq 'gzip_base64'){
          $memory=[IO.MemoryStream]::new($encoded,$false);$zip=[IO.Compression.GZipStream]::new($memory,[IO.Compression.CompressionMode]::Decompress)
          $output=[IO.File]::Create($file);$buffer=New-Object byte[] 65536;$decodedSize=0L
          try{while(($read=$zip.Read($buffer,0,$buffer.Length)) -gt 0){$decodedSize+=$read;$cacheTotal+=$read;if($cacheTotal -gt 134217728){throw 'Actual render cache exceeds its declared resource bound'};$output.Write($buffer,0,$read)}}
          finally{$output.Dispose();$zip.Dispose();$memory.Dispose()}
          if($decodedSize -ne $record.size_bytes){throw 'Actual render cache size changed'}
        }elseif($null -eq $record.encoding -or $record.encoding -eq 'base64'){
          $cacheTotal+=$encoded.Length;if($cacheTotal -gt 134217728){throw 'Actual render cache exceeds its declared resource bound'}
          [IO.File]::WriteAllBytes($file,$encoded)
        }else{throw 'Unsupported actual render cache encoding'}
        if((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower() -ne $record.sha256){throw 'Cached actual before-render artifact changed'}
      }
      $beforePdfStatus='EXPORTED';$beforePdfError=$null;$beforePngStatus='EXPORTED';$beforePngError=$null
    }else{
    $beforePdfStatus='EXPORTED';$beforePdfError=$null
    try{$p.SaveCopyAs((Join-Path $beforeDir 'Final.pdf'),32,0)}catch{$beforePdfStatus='FAILED';$beforePdfError=$_.Exception.Message}
    $beforePngStatus='EXPORTED';$beforePngError=$null
    try{$slide.Export((Join-Path $beforeDir 'Final_preview.png'),'PNG',$width,$height)}catch{$beforePngStatus='FAILED';$beforePngError=$_.Exception.Message}
    if($beforePngStatus -ne 'EXPORTED' -and $beforePdfStatus -ne 'EXPORTED'){
      $emf=Join-Path $beforeDir 'Actual.emf';$png=Join-Path $beforeDir 'Final_preview.png'
      if(Test-Path -LiteralPath $png){Move-Item -LiteralPath $png -Destination ($png+'.direct-failed')}
      $slide.Export($emf,'EMF',$width,$height);WriteNativeEmfPixels $emf $png $width $height
      $beforeEmfHash=(Get-FileHash -LiteralPath $emf -Algorithm SHA256).Hash.ToLower();$beforeEmfPreviewHash=(Get-FileHash -LiteralPath $png -Algorithm SHA256).Hash.ToLower()
    }
    $fontNames=@(Get-ChildItem -LiteralPath (Join-Path $env:WINDIR 'Fonts') -File | Select-Object -ExpandProperty Name | Sort-Object)
    @{status=$(if($beforePngStatus -eq 'EXPORTED'){'PASS'}elseif($beforeEmfHash){'ACTUAL_EMF_EXPORTED'}else{'ACTUAL_PDF_EXPORTED_PENDING_PREVIEW'});scope='target_render_before_probe_mutations';backend='PowerPoint';backend_version=$app.Version;office_build=$app.Build;platform='Windows';fonts=$fontNames;pptx_hash=$inputHash;
      pdf_status=$beforePdfStatus;pdf_error=$beforePdfError;pdf_hash=$(if($beforePdfStatus -eq 'EXPORTED'){(Get-FileHash -LiteralPath (Join-Path $beforeDir 'Final.pdf') -Algorithm SHA256).Hash.ToLower()}else{$null});
      png_status=$beforePngStatus;png_error=$beforePngError;preview_hash=$(if($beforePngStatus -eq 'EXPORTED'){(Get-FileHash -LiteralPath (Join-Path $beforeDir 'Final_preview.png') -Algorithm SHA256).Hash.ToLower()}else{$null})} |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $beforeDir 'render.json') -Encoding UTF8
    }
    $p.Close();$p=$null
    $p=$app.Presentations.Open($copy,0,0,-1)
    ActivateTaskSlide $app $p;$slide=$p.Slides.Item(1)
    for ($index=0;$index -lt $plan.actions.Count;$index++) {
        $action=$plan.actions[$index]
        try {
            $shape=if ($action.action -eq 'path') {ShapeAt $slide $action.native_path} else {ShapeAt $slide $action.shape_path}
            if ($null -eq $shape) {throw 'Named shape not found'}
            if ($null -ne $action.table_cell) {$shape=$shape.Table.Cell(([int]$action.table_cell[0]+1),([int]$action.table_cell[1]+1)).Shape}
            $detail=@{}
            switch ($action.action) {
                'math' {
                    # PDF export and ancestor ungrouping can change the active
                    # view. Re-enter this task's slide before native selection.
                    ActivateTaskSlide $app $p
                    $shape.Select()
                    $before=$shape.TextFrame2.TextRange.Text
                    if ($null -ne $action.atom_edit) {
                        # Edit one actual existing mathematical atom. Never
                        # rebuild a whole prose paragraph or flatten a fraction.
                        $text=$shape.TextFrame2.TextRange.Text;$matches=0;$edited=$false
                        for($pos=0;$pos -lt $text.Length;$pos++) {
                            $span=1
                            if([char]::IsHighSurrogate($text[$pos]) -and $pos+1 -lt $text.Length){$span=2}
                            $glyph=$text.Substring($pos,$span)
                            if($glyph.Normalize([Text.NormalizationForm]::FormKC) -ne ([string]$action.atom_edit.before).Normalize([Text.NormalizationForm]::FormKC)){if($span -eq 2){$pos++};continue}
                            $shape.TextFrame.TextRange.Characters($pos+1,1).Select()
                            if(-not $app.CommandBars.GetEnabledMso('EquationLinearFormat')){if($span -eq 2){$pos++};continue}
                            $matches++
                            if($matches -eq [int]$action.atom_edit.occurrence){
                                $shape.TextFrame2.TextRange.Characters($pos+1,1).Text=[string]$action.atom_edit.after
                                $edited=$true;break
                            }
                            if($span -eq 2){$pos++}
                        }
                        if(-not $edited){throw 'Existing native mathematical atom could not be uniquely selected'}
                    } elseif ($action.existing_math) {
                        $shape.TextFrame.TextRange.Characters([int]$action.offset,[int]$action.existing_length).Select()
                        if(-not $app.CommandBars.GetEnabledMso('EquationLinearFormat')){throw 'Existing structured equation editor unavailable; retain unmet state'}
                        $lengthBefore=$shape.TextFrame2.TextRange.Text.Length
                        $app.CommandBars.ExecuteMso('EquationLinearFormat')
                        $lengthAfter=$shape.TextFrame2.TextRange.Text.Length
                        $linearLength=[int]$action.existing_length+$lengthAfter-$lengthBefore
                        if($linearLength -lt 1){throw 'Native equation linear range could not be measured'}
                        $shape.TextFrame2.TextRange.Characters([int]$action.offset,$linearLength).Text=[string]$action.linear
                        $shape.TextFrame.TextRange.Characters([int]$action.offset,([string]$action.linear).Length).Select()
                    } elseif ($null -ne $action.selection_length) {
                        if($null -ne $action.initialize_text){$shape.TextFrame2.TextRange.Text=[string]$action.initialize_text}
                        if($action.whole_shape){$shape.TextFrame.TextRange.Select()}
                        else{$shape.TextFrame.TextRange.Characters([int]$action.offset,[int]$action.selection_length).Select()}
                    } elseif ($action.whole_shape) {
                        $shape.TextFrame2.TextRange.Text=[string]$action.linear
                        $shape.TextFrame.TextRange.Select()
                    } else {
                        $range=$shape.TextFrame2.TextRange.Characters([int]$action.offset,1)
                        $range.Text=[string]$action.linear
                        $shape.TextFrame.TextRange.Characters([int]$action.offset,([string]$action.linear).Length).Select()
                    }
                    $editor='PowerPoint native EquationProfessional'
                    if ($null -eq $action.atom_edit -and -not $app.CommandBars.GetEnabledMso('EquationProfessional')) {
                        if(-not $app.CommandBars.GetEnabledMso('EquationInsertNew')){throw 'Native equation editor unavailable for selected zone'}
                        # New inline math must not inherit a bold prose run.
                        # Explicit encoded mathematical alphabets remain in the
                        # supplied UnicodeMath; the saved AST is checked later.
                        $app.ActiveWindow.Selection.TextRange.Font.Bold=0
                        $app.CommandBars.ExecuteMso('EquationInsertNew');$editor='PowerPoint native EquationInsertNew'
                    }
                    if($null -eq $action.atom_edit -and $app.CommandBars.GetEnabledMso('EquationProfessional')){$app.CommandBars.ExecuteMso('EquationProfessional')}
                    $detail=@{before=$before;after=$shape.TextFrame2.TextRange.Text;offset=$action.offset;linear=$action.linear;editor=$editor}
                }
                'text' {$shape.TextFrame.TextRange.Text=$action.text;$detail=@{text=$shape.TextFrame.TextRange.Text}}
                'path' {
                    $path=ShapeAt $slide $action.native_path
                    $points=$path.Nodes.Item(2).Points
                    $before=@($points[1,1],$points[1,2])
                    $path.Nodes.SetPosition(2,[single]($points[1,1]+1),[single]($points[1,2]+1))
                    $points=$path.Nodes.Item(2).Points
                    $detail=@{node_count=$path.Nodes.Count;before=$before;after=@($points[1,1],$points[1,2])}
                }
                'group' {
                    if ($shape.Type -ne 6) {throw 'Expected native group'}
                    $duplicate=$shape.Duplicate().Item(1);$duplicate.Name='Probe_copy_'+$action.id
                    $duplicate.IncrementLeft(5);$duplicate.ScaleWidth(1.02,0,0);$duplicate.ScaleHeight(1.02,0,0)
                    $parts=$duplicate.Ungroup();$names=@()
                    for ($j=1;$j -le $parts.Count;$j++) {$names+=$parts.Item($j).Name}
                    for ($j=1;$j -le $parts.Count;$j++) {RenameProbe $parts.Item($j) ('Probe_'+$action.id+'_')}
                    $leafName=[string]$plan.lookup_leaves.($action.id)
                    $partName='Probe_'+$action.id+'_'+$leafName
                    $part=FindShape $slide.Shapes $partName
                    if($null -eq $part){throw 'Ungrouped native leaf unavailable for style edit'}
                    if($part.Type -eq 9 -or ($part.Type -eq 5 -and $part.Fill.Visible -ne -1)){
                        $part.Line.ForeColor.RGB=255;$property='line';$changed=($part.Line.ForeColor.RGB -eq 255)
                    }else{
                        $part.Fill.Solid();$part.Fill.ForeColor.RGB=255;$property='fill';$changed=($part.Fill.ForeColor.RGB -eq 255)
                    }
                    $detail=@{part_count=$parts.Count;parts=$names;part_fill_changed=$changed;edited_part=$partName;edited_property=$property;expected_rgb='FF0000'}
                }
                'connector' {
                    $node=ShapeAt $slide $action.node_path
                    $before=@($shape.Left,$shape.Top,$shape.Width,$shape.Height)
                    $node.IncrementLeft(5)
                    $begin=$shape.ConnectorFormat.BeginConnected;$end=$shape.ConnectorFormat.EndConnected
                    $detail=@{before=$before;after=@($shape.Left,$shape.Top,$shape.Width,$shape.Height);begin_connected=$begin;end_connected=$end}
                    if($begin -eq -1){$detail.source=$shape.ConnectorFormat.BeginConnectedShape.Name}
                    if($end -eq -1){$detail.target=$shape.ConnectorFormat.EndConnectedShape.Name}
                }
                default {throw 'Unsupported probe action'}
            }
            $records.Add(@{operation_index=$index;object=$action.id;action=$action.action;status='EXECUTED';detail=$detail})
        } catch {$records.Add(@{operation_index=$index;object=$action.id;action=$action.action;status='UNVERIFIED';reason=$_.Exception.Message})}
        @{status='IN_PROGRESS';input_sha256=$inputHash;probe_script_hash=$scriptHash;operations=$records} |
          ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $OutDir 'operations.partial.json') -Encoding UTF8
    }
    $p.Save();$p.Close();$p=$null
    $p=$app.Presentations.Open($copy,0,0,-1)
    ActivateTaskSlide $app $p
    $afterPdfStatus='EXPORTED';$afterPdfError=$null
    try{$p.SaveCopyAs((Join-Path $OutDir 'After.pdf'),32,0)}catch{$afterPdfStatus='FAILED';$afterPdfError=$_.Exception.Message}
    $width=[int]$plan.preview_width
    $afterPngStatus='EXPORTED';$afterPngError=$null
    $afterEmfHash=$null;$afterEmfPreviewHash=$null;$afterEmfError=$null;$afterOwnerRenders=$null
    try{$p.Slides.Item(1).Export((Join-Path $OutDir 'After.png'),'PNG',$width,[int][Math]::Round($width*$p.PageSetup.SlideHeight/$p.PageSetup.SlideWidth))}catch{$afterPngStatus='FAILED';$afterPngError=$_.Exception.Message}
    if($afterPngStatus -ne 'EXPORTED' -and $afterPdfStatus -ne 'EXPORTED'){
      $emf=Join-Path $OutDir 'After.emf';$png=Join-Path $OutDir 'After.png'
      if(Test-Path -LiteralPath $png){Move-Item -LiteralPath $png -Destination ($png+'.direct-failed')}
      try{
        $p.Slides.Item(1).Export($emf,'EMF',$width,[int][Math]::Round($width*$p.PageSetup.SlideHeight/$p.PageSetup.SlideWidth))
        WriteNativeEmfPixels $emf $png $width ([int][Math]::Round($width*$p.PageSetup.SlideHeight/$p.PageSetup.SlideWidth))
        $afterEmfHash=(Get-FileHash -LiteralPath $emf -Algorithm SHA256).Hash.ToLower();$afterEmfPreviewHash=(Get-FileHash -LiteralPath $png -Algorithm SHA256).Hash.ToLower()
      }catch{
        $afterEmfError=$_.Exception.Message
        $afterOwnerRenders=ExportEditedTextMathOwners $p $plan $OutDir $width
      }
    }
    $p.Close();$p=$null
    @{status='EXECUTED_REQUIRES_INDEPENDENT_VERIFICATION';office_version=$app.Version;office_build=$app.Build;input_sha256=$inputHash;probe_script_hash=$scriptHash;ancestor_ungroups=$ancestorUngroups;after_pdf_status=$afterPdfStatus;after_pdf_error=$afterPdfError;
      before_png_sha256=$(if($beforePngStatus -eq 'EXPORTED'){(Get-FileHash -LiteralPath (Join-Path $beforeDir 'Final_preview.png') -Algorithm SHA256).Hash.ToLower()}else{$null});
      before_pdf_sha256=$(if($beforePdfStatus -eq 'EXPORTED'){(Get-FileHash -LiteralPath (Join-Path $beforeDir 'Final.pdf') -Algorithm SHA256).Hash.ToLower()}else{$null});
      before_emf_sha256=$beforeEmfHash;before_emf_preview_sha256=$beforeEmfPreviewHash;
      after_png_status=$afterPngStatus;after_png_error=$afterPngError;
      after_png_sha256=$(if($afterPngStatus -eq 'EXPORTED'){(Get-FileHash -LiteralPath (Join-Path $OutDir 'After.png') -Algorithm SHA256).Hash.ToLower()}else{$null});
      after_pdf_sha256=$(if($afterPdfStatus -eq 'EXPORTED'){(Get-FileHash -LiteralPath (Join-Path $OutDir 'After.pdf') -Algorithm SHA256).Hash.ToLower()}else{$null});
      after_emf_sha256=$afterEmfHash;after_emf_preview_sha256=$afterEmfPreviewHash;
      after_emf_error=$afterEmfError;after_owner_renders=$afterOwnerRenders;
      output_sha256=(Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash.ToLower();operations=$records} |
       ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $OutDir 'operations.json') -Encoding UTF8
} finally {if ($null -ne $p) {$p.Close()}}
