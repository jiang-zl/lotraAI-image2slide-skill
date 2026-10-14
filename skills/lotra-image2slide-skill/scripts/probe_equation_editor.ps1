param([Parameter(Mandatory=$true)][string]$InputPptx,[Parameter(Mandatory=$true)][string]$OutDir)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutDir) { throw 'Output already exists' }
$null = New-Item -ItemType Directory -Path $OutDir
$copy = Join-Path $OutDir 'Equation_editor_roundtrip.pptx'
Copy-Item -LiteralPath $InputPptx -Destination $copy
$p = $null
$records = [System.Collections.Generic.List[object]]::new()
try {
    $app = New-Object -ComObject PowerPoint.Application
    $p = $app.Presentations.Open($copy,0,0,-1)
    $p.Windows.Item(1).Activate()
    $slide = $p.Slides.Item(1)
    foreach ($id in @('EquationProfessional','EquationLinearFormat','EquationLinear')) {
        try { $records.Add(@{control=$id;label=$app.CommandBars.GetLabelMso($id);known=$true}) }
        catch { $records.Add(@{control=$id;known=$false;reason=$_.Exception.Message}) }
    }
    $edits=@(
        @('Equation_scripts','g_k^"max"'),
        @('Equation_fraction','1/(x/z)'),
        @('Equation_sum',(([string][char]0x2211)+'_(i=1)^n '+([string][char]0x03B2))),
        @('Equation_root',(([string][char]0x221A)+'('+([string][char]0x03B2)+'+2)')),
        @('Equation_accent',('w'+([string][char]0x0302))),
        @('Equation_matrix',(([string][char]0x25A0)+'(a&b@c&e)')),
        @('Equation_cases',('{'+([string][char]0x25A0)+'(x&x'+([string][char]0x2265)+'0@1&x<0)'+([string][char]0x2524)))
    )
    foreach ($pair in $edits) {
        $s = $slide.Shapes.Item($pair[0])
        $s.Select()
        $s.TextFrame.TextRange.Select()
        $before = $s.TextFrame2.TextRange.Text
        $s.TextFrame2.TextRange.Text = $pair[1]
        $s.TextFrame.TextRange.Select()
        $enabled = $app.CommandBars.GetEnabledMso('EquationProfessional')
        if (-not $enabled) { throw 'Native EquationProfessional command unavailable for selected math object' }
        $app.CommandBars.ExecuteMso('EquationProfessional')
        $records.Add(@{object=$pair[0];before=$before;linear_input=$pair[1];after=$s.TextFrame2.TextRange.Text;
                       editor='PowerPoint native EquationProfessional';status='EXECUTED_REQUIRES_AST_VERIFICATION'})
    }
    $p.Save()
    $p.Close()
    $p=$app.Presentations.Open($copy,0,0,0)
    $p.SaveCopyAs((Join-Path $OutDir 'After.pdf'),32,0)
    $p.Slides.Item(1).Export((Join-Path $OutDir 'After.png'),'PNG',1440,810)
    $p.Close()
    $p=$null
    @{status='EXECUTED_REQUIRES_AST_VERIFICATION';office_version=$app.Version;office_build=$app.Build;operations=$records;
      input_sha256=(Get-FileHash -LiteralPath $InputPptx -Algorithm SHA256).Hash.ToLower();
      output_sha256=(Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash.ToLower()} |
        ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $OutDir 'operations.json') -Encoding UTF8
} catch {
    @{status='BLOCKED';reason=$_.Exception.Message;operations=$records} | ConvertTo-Json -Depth 12 |
        Set-Content -LiteralPath (Join-Path $OutDir 'operations.json') -Encoding UTF8
    throw
} finally { if ($null -ne $p) { $p.Close() } }
