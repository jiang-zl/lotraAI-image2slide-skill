param(
    [Parameter(Mandatory=$true)][string]$InputPptx,
    [Parameter(Mandatory=$true)][string]$OutDir
)
$ErrorActionPreference = 'Stop'
# This probe opens only an isolated copy. Never Quit the app or close other decks.
if (Test-Path -LiteralPath $OutDir) { throw 'Output directory already exists' }
$null = New-Item -ItemType Directory -Path $OutDir
$copy = Join-Path $OutDir 'Office_roundtrip.pptx'
Copy-Item -LiteralPath $InputPptx -Destination $copy
$records = [System.Collections.Generic.List[object]]::new()
$presentation = $null
$app = $null
function Probe([string]$id, [scriptblock]$action) {
    try {
        $detail = & $action
        $records.Add(@{ operation=$id; status='EXECUTED'; detail=$detail })
    } catch {
        $records.Add(@{ operation=$id; status='UNVERIFIED'; reason=$_.Exception.Message })
    }
}
try {
    $app = New-Object -ComObject PowerPoint.Application
    $presentation = $app.Presentations.Open($copy, 0, 0, 0)
    $slide = $presentation.Slides.Item(1)
    $officeVersion = $app.Version
    $officeBuild = $app.Build
    $presentation.SaveCopyAs((Join-Path $OutDir 'Before.pdf'), 32, 0)
    $slide.Export((Join-Path $OutDir 'Before.png'), 'PNG', 1440, 810)
    Probe 'text_edit' {
        $s = $slide.Shapes.Item('Title')
        $s.TextFrame.TextRange.Text = 'Native API edit persisted'
        @{ text=$s.TextFrame.TextRange.Text }
    }
    Probe 'group_move_copy_scale_ungroup_part_fill' {
        $group = $slide.Shapes.Item('Device')
        if ($group.Type -ne 6) { throw 'Device is not native Group' }
        $copyGroup = $group.Duplicate().Item(1)
        $copyGroup.Name = 'Device_copy'
        $copyGroup.IncrementLeft(6)
        $copyGroup.ScaleWidth(1.05, 0, 0)
        $copyGroup.ScaleHeight(1.05, 0, 0)
        $parts = $copyGroup.Ungroup()
        $names = @()
        for ($i=1; $i -le $parts.Count; $i++) { $names += $parts.Item($i).Name }
        $parts.Item(1).Fill.ForeColor.RGB = 255
        @{ parts=$names; first_part_color=$parts.Item(1).Fill.ForeColor.RGB }
    }
    Probe 'connector_move_follow' {
        $line = $slide.Shapes.Item('Link')
        $before = @($line.Left, $line.Top, $line.Width, $line.Height)
        $slide.Shapes.Item('EndpointA').IncrementTop(18)
        $line.RerouteConnections()
        @{ before=$before; after=@($line.Left, $line.Top, $line.Width, $line.Height);
           begin_connected=$line.ConnectorFormat.BeginConnected; end_connected=$line.ConnectorFormat.EndConnected;
           source=$line.ConnectorFormat.BeginConnectedShape.Name; target=$line.ConnectorFormat.EndConnectedShape.Name }
    }
    Probe 'bezier_edit_point' {
        $curve = $slide.Shapes.Item('Curve')
        $count = $curve.Nodes.Count
        if ($count -lt 2) { throw 'No editable curve nodes' }
        $points = $curve.Nodes.Item(2).Points
        $curve.Nodes.SetPosition(2, [single]($points[1,1] + 4), [single]($points[1,2] + 2))
        @{ node_count=$count }
    }
    foreach ($suffix in @('scripts','fraction','sum','root','accent','matrix','cases')) {
        Probe ('formula_character_edit_' + $suffix) {
            $shape = $slide.Shapes.Item('Equation_' + $suffix)
            $range = $shape.TextFrame2.TextRange
            $before = $range.Text
            $range.Characters(1,1).Text = 'g'
            @{ object=('Equation_' + $suffix); before=$before; after=$range.Text;
               method='PowerPoint.TextFrame2.TextRange.Characters'; editor_entry_ui='UNVERIFIED' }
        }
    }
    $presentation.Save()
    $presentation.Close()
    $presentation = $app.Presentations.Open($copy, 0, 0, 0)
    $slide = $presentation.Slides.Item(1)
    $reopened = @()
    for ($i=1; $i -le $slide.Shapes.Count; $i++) {
        $s = $slide.Shapes.Item($i)
        $text = $null
        if ($s.HasTextFrame -eq -1) { $text = $s.TextFrame2.TextRange.Text }
        $reopened += @{ name=$s.Name; type=$s.Type; text=$text }
    }
    $presentation.SaveCopyAs((Join-Path $OutDir 'After.pdf'), 32, 0)
    $slide.Export((Join-Path $OutDir 'After.png'), 'PNG', 1440, 810)
    $presentation.Close()
    $presentation = $null
    @{ status='EXECUTED_REQUIRES_INDEPENDENT_VERIFICATION'; platform='Windows'; office_version=$officeVersion;
       office_build=$officeBuild; input_sha256=(Get-FileHash -LiteralPath $InputPptx -Algorithm SHA256).Hash.ToLower();
       output_sha256=(Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash.ToLower();
       operations=$records; reopened=$reopened; fonts='Recorded in saved deck; host inventory not collected';
       limitations=@('API mutation does not establish interactive formula editor entry','All modified probe artifacts are internal, not final reconstruction')
    } | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $OutDir 'operations.json') -Encoding UTF8
} catch {
    @{ status='BLOCKED'; reason=$_.Exception.Message; operations=$records } |
        ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $OutDir 'operations.json') -Encoding UTF8
    throw
} finally {
    if ($null -ne $presentation) { $presentation.Close() }
    # Deliberately do not call Application.Quit: existing user presentations may be open.
}
