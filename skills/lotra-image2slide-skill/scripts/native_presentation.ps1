param([Parameter(Mandatory=$true)][string]$Request)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$job=Get-Content -LiteralPath $Request -Raw -Encoding UTF8 | ConvertFrom-Json
$result=[ordered]@{schema='lotra-native-job-1';status='FAILED';backend=$job.backend;stage='activate';job_id=$job.job_id}
$app=$null;$doc=$null;$check=$null
function Save-Progress([string]$stage){
    $result.stage=$stage
    $value=@{schema='lotra-native-progress-1';job_id=$job.job_id;backend=$job.backend;stage=$stage}
    [IO.File]::WriteAllText((Join-Path ([IO.Path]::GetDirectoryName([string]$job.result)) 'Progress.json'),($value | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
}
function Release-Com($value){if($null -ne $value -and [Runtime.InteropServices.Marshal]::IsComObject($value)){[void][Runtime.InteropServices.Marshal]::ReleaseComObject($value)}}
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
    Save-Progress 'activate'
    if($job.backend -eq 'PowerPoint'){$app=New-Object -ComObject PowerPoint.Application}
    elseif($job.backend -eq 'WPS'){$app=New-Object -ComObject KWPP.Application}
    else{throw 'Unsupported native presentation backend'}
    $result.backend_version=[string]$app.Version
    try{$result.office_build=[string]$app.Build}catch{$result.office_build='NOT_EXPOSED'}
    $result.user=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $result.administrator=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    Save-Progress 'open-owned-copy'
    $doc=$app.Presentations.Open([string]$job.input,-1,0,0)
    if([IO.Path]::GetFileName([string]$doc.FullName) -ine [IO.Path]::GetFileName([string]$job.input)){throw 'Native application opened a different presentation'}
    $result.slide_count=[int]$doc.Slides.Count
    if($result.slide_count -lt 1){throw 'No slides in native presentation'}
    if($job.pdf){
    Save-Progress 'pdf-export'
    # SaveCopyAs uses each application's actual PDF format and leaves its document path unchanged.
    $result.opened_path=[string]$doc.FullName
    try{$doc.SaveCopyAs([string]$job.pdf,32,0);$result.pdf_method='SaveCopyAs'}
    catch{
        $result.pdf_copy_failure=$_.Exception.Message
        # Both operations target only this private owned copy. Some Office
        # documents expose PDF through SaveAs only; both failures are recorded.
        $doc.SaveAs([string]$job.pdf,32,0);$result.pdf_method='SaveAs_owned_copy'
    }
    if(!(Test-Path -LiteralPath $job.pdf -PathType Leaf) -or (Get-Item -LiteralPath $job.pdf).Length -eq 0){throw 'PDF export produced no bytes'}
    $result.pdf_export='PASS'
    }else{$result.pdf_export='NOT_RUN'}
    if($job.roundtrip){
        Save-Progress 'save-as-pptx'
        $doc.SaveCopyAs([string]$job.roundtrip,24,-1)
        if(!(Test-Path -LiteralPath $job.roundtrip -PathType Leaf)){throw 'Native PPTX SaveCopyAs produced no file'}
        Save-Progress 'edit-save-reopen'
        $doc.Close();Release-Com $doc;$doc=$null
        $check=$app.Presentations.Open([string]$job.roundtrip,0,0,0)
        if([IO.Path]::GetFileName([string]$check.FullName) -ine [IO.Path]::GetFileName([string]$job.roundtrip)){throw 'Refuse editing a different native presentation'}
        if([int]$check.Slides.Count -ne $result.slide_count){throw 'Native roundtrip changed slide count'}
        $shape=$null;$oldName=$null;$oldLeft=$null
        if($check.Slides.Item(1).Shapes.Count -gt 0){
            $shape=$check.Slides.Item(1).Shapes.Item(1);$oldName=[string]$shape.Name
            $oldLeft=[double]$shape.Left
            $shape.Name='lotra-owned-edit-'+[string]$job.job_id
            $shape.Left=$oldLeft+1.0
        }
        if($null -eq $oldName){throw 'No native object on the first slide to exercise edit/save/reopen'}
        $check.Save();$check.Close();Release-Com $check;$check=$null
        $check=$app.Presentations.Open([string]$job.roundtrip,0,0,0)
        if($null -ne $oldName){
            $saved=$check.Slides.Item(1).Shapes.Item(1)
            if([string]$saved.Name -ne ('lotra-owned-edit-'+[string]$job.job_id)){throw 'Saved native edit did not survive reopen'}
            if([Math]::Abs([double]$saved.Left-($oldLeft+1.0)) -gt 0.02){throw 'Saved native geometry edit did not survive reopen'}
            $saved.Name=$oldName;$saved.Left=$oldLeft;Release-Com $saved
            $check.Save()
        }
        Release-Com $shape
        $check.Close();Release-Com $check;$check=$null
        $result.native_save='PASS';$result.edit_save_reopen='PASS';$result.edit_property='Left + 1pt, save/reopen, restore'
    }
    if($null -ne $doc -and $job.pdf){
        $textBounds=[System.Collections.Generic.List[object]]::new()
        MeasureText $doc.Slides.Item(1).Shapes $textBounds
        $metrics=@{backend=$job.backend;backend_version=$app.Version;objects=$textBounds}
        [IO.File]::WriteAllText((Join-Path ([IO.Path]::GetDirectoryName([string]$job.pdf)) 'text-bounds.json'),($metrics | ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
    }
    $result.stage='complete';$result.status='PASS'
}catch{
    $result.reason=$_.Exception.Message
    $result.hresult=$_.Exception.HResult
}finally{
    if($null -ne $doc){try{$doc.Close()}catch{};Release-Com $doc}
    if($null -ne $check){try{$check.Close()}catch{};Release-Com $check}
    # Office may be shared with the user. Never call Quit or terminate its process.
    Release-Com $app
    $json=$result | ConvertTo-Json -Depth 12
    [IO.File]::WriteAllText([string]$job.result,$json,[Text.UTF8Encoding]::new($false))
}
if($result.status -ne 'PASS'){exit 1}
