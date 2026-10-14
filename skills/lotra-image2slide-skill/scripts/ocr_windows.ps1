param([Parameter(Mandatory=$true)][string]$RequestFile)
$ErrorActionPreference='Stop'
$env:PSModulePath=(Join-Path $PSHOME 'Modules')+[IO.Path]::PathSeparator+$env:PSModulePath
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
Import-Module Microsoft.PowerShell.Management -ErrorAction Stop
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrResult,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime] | Out-Null
$asyncMethod=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Wait-OcrOperation($Operation,[Type]$ResultType) {
    $task=$asyncMethod.MakeGenericMethod($ResultType).Invoke($null,@($Operation))
    $task.Wait()
    return $task.Result
}
$request=Get-Content -LiteralPath $RequestFile -Raw -Encoding UTF8 | ConvertFrom-Json
$languages=@([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag })
foreach($item in $request.images) {
    $hash=(Get-FileHash -LiteralPath $item.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if($hash -ne $item.source_hash) { throw 'The staged original source hash changed' }
    $tag=@($languages | Where-Object { $_ -like ($item.language+'*') } | Select-Object -First 1)
    if($tag.Count -eq 0 -and $item.fallback_language) { $tag=@($languages | Where-Object { $_ -like ($item.fallback_language+'*') } | Select-Object -First 1) }
    if($tag.Count -eq 0) { $result=@{status='SOURCE_OCR_LANGUAGE_UNAVAILABLE';source_hash=$hash;available_languages=$languages;requested_language=$item.language} }
    else {
        $stageDir=Join-Path ([IO.Path]::GetTempPath()) ('lotraAI-source-ocr-'+[guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $stageDir | Out-Null
        $localSource=Join-Path $stageDir ('source'+[IO.Path]::GetExtension($item.path))
        Copy-Item -LiteralPath $item.path -Destination $localSource
        if((Get-FileHash -LiteralPath $localSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash) { throw 'Staged source bytes changed' }
        $file=Wait-OcrOperation ([Windows.Storage.StorageFile]::GetFileFromPathAsync($localSource)) ([Windows.Storage.StorageFile])
        $stream=Wait-OcrOperation ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        try {
            $decoder=Wait-OcrOperation ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
            $bitmap=Wait-OcrOperation ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
            try {
                if([Math]::Max($bitmap.PixelWidth,$bitmap.PixelHeight) -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension) { throw 'Source requires bounded native OCR tiles' }
                $engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($tag[0]))
                $ocr=Wait-OcrOperation ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
                $lines=@($ocr.Lines | ForEach-Object { $line=$_; @{text=$line.Text;words=@($line.Words | ForEach-Object { @{text=$_.Text;roi=@($_.BoundingRect.X,$_.BoundingRect.Y,$_.BoundingRect.Width,$_.BoundingRect.Height)} })} })
                $result=@{status='SOURCE_OCR_CANDIDATE_ANCHORS';source_hash=$hash;language=$tag[0];source_size=@($bitmap.PixelWidth,$bitmap.PixelHeight);lines=$lines;provider='Windows.Media.Ocr';limits='OCR anchors are provisional source evidence; host confirms literal content, formula meaning and ownership. No drawing or acceptance is inferred.'}
            } finally { if($bitmap) {$bitmap.Dispose()} }
        } finally { $stream.Dispose(); $resolvedStage=[IO.Path]::GetFullPath($stageDir); $resolvedTemp=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()); if(-not $resolvedStage.StartsWith($resolvedTemp,[StringComparison]::OrdinalIgnoreCase)) {throw 'Invalid OCR staging boundary'}; Remove-Item -LiteralPath $localSource; Remove-Item -LiteralPath $stageDir }
    }
    [IO.File]::WriteAllText($item.output,($result | ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
    @{case=$item.case;status=$result.status;language=$result.language;lines=$(if($result.lines){@($result.lines).Count}else{0});output=$item.output} | ConvertTo-Json -Compress
}

