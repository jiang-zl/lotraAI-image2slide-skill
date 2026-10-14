param(
 [Parameter(Mandatory=$true)][string]$InputPptx,
 [Parameter(Mandatory=$true)][string]$ExpectedHash,
 [Parameter(Mandatory=$true)][string]$OutDir
)
$ErrorActionPreference='Stop'
$inputHash=(Get-FileHash -LiteralPath $InputPptx -Algorithm SHA256).Hash.ToLower()
if($inputHash -ne $ExpectedHash){throw 'Component probe input hash mismatch'}
if(Test-Path -LiteralPath $OutDir){throw 'Probe output exists'}
$null=New-Item -ItemType Directory -Path $OutDir
$testCopy=Join-Path $OutDir 'Native_reuse_test.pptx'
Copy-Item -LiteralPath $InputPptx -Destination $testCopy
$p=$null
$records=[System.Collections.Generic.List[object]]::new()
function FirstLeaf($collection){
 for($i=1;$i -le $collection.Count;$i++){
  $s=$collection.Item($i)
  if($s.Type -eq 6){$found=FirstLeaf $s.GroupItems;if($null -ne $found){return ,$found}}
  else{return ,$s}
 }
 return $null
}
function FindName($collection,[string]$name){
 for($i=1;$i -le $collection.Count;$i++){
  $s=$collection.Item($i)
  if($s.Name -eq $name){return ,$s}
  if($s.Type -eq 6){$found=FindName $s.GroupItems $name;if($null -ne $found){return ,$found}}
 }
 return $null
}
try{
 $app=New-Object -ComObject PowerPoint.Application
 $p=$app.Presentations.Open($testCopy,0,0,0)
 for($i=1;$i -le $p.Slides.Count;$i++){
  $slide=$p.Slides.Item($i)
  if($slide.Shapes.Count -ne 1){throw ('Expected one component owner per slide: '+$i)}
  $original=$slide.Shapes.Item(1)
  $record=[ordered]@{slide=$i;owner=$original.Name;original_shape_type=$original.Type;operations=@();status='IN_PROGRESS'}
  $png=Join-Path $OutDir ('Component_'+$i+'.png')
  try{$original.Export($png,2);$record.preview=@{path=[IO.Path]::GetFileName($png);sha256=(Get-FileHash -LiteralPath $png -Algorithm SHA256).Hash.ToLower();status='EXPORTED'}}
  catch{$record.preview=@{status='UNVERIFIED';reason=$_.Exception.Message}}
  $svg=Join-Path $OutDir ('Component_'+$i+'.svg')
  try{$original.Export($svg,6);$record.svg=@{path=[IO.Path]::GetFileName($svg);sha256=(Get-FileHash -LiteralPath $svg -Algorithm SHA256).Hash.ToLower();status='EXPORTED_REQUIRES_CONTENT_CHECK'}}
  catch{$record.svg=@{status='UNVERIFIED';reason=$_.Exception.Message}}
  try{
   $before=@([double]$original.Left,[double]$original.Top,[double]$original.Width,[double]$original.Height)
   $duplicate=$original.Duplicate().Item(1);$name='Reuse_probe_'+$i;$duplicate.Name=$name
   $duplicate.IncrementLeft(12);$duplicate.IncrementTop(8)
   $duplicate.ScaleWidth(1.1,0,0);$duplicate.ScaleHeight(.9,0,0)
   $after=@([double]$duplicate.Left,[double]$duplicate.Top,[double]$duplicate.Width,[double]$duplicate.Height)
   $record.operations+=@{kind='copy_move_resize';name=$name;before=$before;expected_saved=$after;status='EXECUTED'}
   if($original.Type -eq 6){
    $partCopy=$original.Duplicate().Item(1);$partCopy.Name='Parts_probe_'+$i
    $parts=$partCopy.Ungroup();$names=@()
    for($j=1;$j -le $parts.Count;$j++){$parts.Item($j).Name='Parts_'+$i+'_'+$j;$names+=$parts.Item($j).Name}
    $record.operations+=@{kind='ungroup';part_names=$names;part_count=$parts.Count;status='EXECUTED'}
    $leaf=FirstLeaf $parts
   }else{$leaf=$duplicate}
   if($null -ne $leaf){
    $previousLeafName=$leaf.Name
    $leaf.Name='Leaf_probe_'+$i
    $record.edited_leaf_type=[int]$leaf.Type
    foreach($previousOperation in $record.operations){
     if($previousOperation.kind -eq 'ungroup'){
      $previousOperation.part_names=@($previousOperation.part_names | ForEach-Object {if($_ -eq $previousLeafName){$leaf.Name}else{$_}})
     }
    }
    if($leaf.Type -eq 13){
     $leaf.PictureFormat.CropLeft=[single]($leaf.PictureFormat.CropLeft+1)
     $record.operations+=@{kind='crop_picture';name=$leaf.Name;expected_saved=[double]$leaf.PictureFormat.CropLeft;status='EXECUTED'}
     # Exercise a reusable image replacement as a separate task-copy instance.
     # The exported asset is inserted with native AddPicture, then saved/reopened.
     # This proves replacement/import, not editability inside raster pixels.
     $replacement=$slide.Shapes.AddPicture($png,0,-1,[single]$original.Left,[single]$original.Top,[single]$original.Width,[single]$original.Height)
     $replacement.Name='Replacement_probe_'+$i
     $record.operations+=@{kind='import_replacement_picture';name=$replacement.Name;
      expected_saved=@([double]$replacement.Left,[double]$replacement.Top,[double]$replacement.Width,[double]$replacement.Height);
      source_asset=[IO.Path]::GetFileName($png);source_sha256=(Get-FileHash -LiteralPath $png -Algorithm SHA256).Hash.ToLower();status='EXECUTED'}
    }elseif($leaf.HasTextFrame -eq -1 -and $leaf.TextFrame.HasText -eq -1){
     $leaf.TextFrame.TextRange.Text='Native text edit probe'
     $record.operations+=@{kind='edit_text';name=$leaf.Name;expected_saved='Native text edit probe';status='EXECUTED'}
    }elseif($leaf.Type -eq 9 -or ($leaf.Type -eq 5 -and $leaf.Fill.Visible -ne -1)){
     $leaf.Line.ForeColor.RGB=255
     $record.operations+=@{kind='edit_line';name=$leaf.Name;expected_saved=255;status='EXECUTED'}
    }else{
     $leaf.Fill.Solid()
     $leaf.Fill.ForeColor.RGB=255
     $record.operations+=@{kind='edit_fill';name=$leaf.Name;expected_saved=255;status='EXECUTED'}
     try{
      # AutoShapes may report a node count while returning null Points. Their
      # fill/preset is editable; freeform node editing applies only to type 5.
      if($leaf.Type -eq 5 -and $leaf.Nodes.Count -gt 1){
       $points=$leaf.Nodes.Item(2).Points
       $leaf.Nodes.SetPosition(2,[single]($points[1,1]+1),[single]($points[1,2]+1))
       $points=$leaf.Nodes.Item(2).Points
       $record.operations+=@{kind='edit_path_node';name=$leaf.Name;node_index=2;expected_saved=@([double]$points[1,1],[double]$points[1,2]);status='EXECUTED'}
      }
     }catch{$record.operations+=@{kind='edit_path_node';name=$leaf.Name;status='UNVERIFIED';reason=$_.Exception.Message}}
    }
   }
   $record.status='EXECUTED_REOPEN_PENDING'
  }catch{$record.status='UNVERIFIED';$record.reason=$_.Exception.Message;$record.operation_error=$_.Exception.Message;$record.failure_location=$_.InvocationInfo.PositionMessage}
  $records.Add($record)
  @{status='IN_PROGRESS';source_hash=$inputHash;components=$records} | ConvertTo-Json -Depth 18 | Set-Content -LiteralPath (Join-Path $OutDir 'probe.partial.json') -Encoding UTF8
 }
 $p.Save();$p.Close();$p=$null
 $p=$app.Presentations.Open($testCopy,-1,0,0)
 foreach($record in $records){
  $slide=$p.Slides.Item([int]$record.slide)
  foreach($op in $record.operations){
   if($op.status -ne 'EXECUTED'){continue}
   try{
    if($op.kind -eq 'ungroup'){
     $found=0
     foreach($name in $op.part_names){try{$null=$slide.Shapes.Item([string]$name);$found++}catch{}}
     $op.reopen_status=if($found -eq $op.part_count){'PASS'}else{'FAIL'}
     $op.actual_saved_parts=$found
    }else{
     $shape=FindName $slide.Shapes $op.name
     if($null -eq $shape){throw ('Saved edited object missing: '+$op.name)}
     switch($op.kind){
      'copy_move_resize'{$actual=@([double]$shape.Left,[double]$shape.Top,[double]$shape.Width,[double]$shape.Height);$ok=$true;for($k=0;$k -lt 4;$k++){if([Math]::Abs($actual[$k]-$op.expected_saved[$k]) -gt .02){$ok=$false}}}
      'crop_picture'{$actual=[double]$shape.PictureFormat.CropLeft;$ok=[Math]::Abs($actual-$op.expected_saved) -lt .02}
      'import_replacement_picture'{$actual=@([double]$shape.Left,[double]$shape.Top,[double]$shape.Width,[double]$shape.Height);$ok=$shape.Type -eq 13;for($k=0;$k -lt 4;$k++){if([Math]::Abs($actual[$k]-$op.expected_saved[$k]) -gt .02){$ok=$false}}}
      'edit_text'{$actual=$shape.TextFrame.TextRange.Text;$ok=$actual -eq $op.expected_saved}
      'edit_fill'{$actual=$shape.Fill.ForeColor.RGB;$ok=$actual -eq $op.expected_saved}
      'edit_line'{$actual=$shape.Line.ForeColor.RGB;$ok=$actual -eq $op.expected_saved}
      'edit_path_node'{$points=$shape.Nodes.Item([int]$op.node_index).Points;$actual=@([double]$points[1,1],[double]$points[1,2]);$ok=([Math]::Abs($actual[0]-$op.expected_saved[0]) -lt .05 -and [Math]::Abs($actual[1]-$op.expected_saved[1]) -lt .05)}
     }
     $op.actual_saved=$actual;$op.reopen_status=if($ok){'PASS'}else{'FAIL'}
    }
   }catch{$op.reopen_status='UNVERIFIED';$op.reopen_reason=$_.Exception.Message}
  }
  $record.status=if(-not $record.operation_error -and $record.operations.Count -gt 0 -and @($record.operations | Where-Object {$_.reopen_status -ne 'PASS'}).Count -eq 0){'PASS_LISTED_OPERATIONS'}else{'UNVERIFIED_OR_FAILED'}
 }
 $p.Close();$p=$null
 if((Get-FileHash -LiteralPath $InputPptx -Algorithm SHA256).Hash.ToLower() -ne $inputHash){throw 'Source component deck changed'}
 @{status='MEASURED_REQUIRES_COVERAGE_REVIEW';scope='Only the listed actual copy/move/resize/ungroup/leaf edits, saved and reopened; no equation-editor or image-completion claim';
   input_hash=$inputHash;output_hash=(Get-FileHash -LiteralPath $testCopy -Algorithm SHA256).Hash.ToLower();
   script_hash=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLower();
   office_version=$app.Version;office_build=$app.Build;components=$records} | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $OutDir 'probe.json') -Encoding UTF8
}finally{if($null -ne $p){$p.Close()}}
