$ErrorActionPreference='Stop'
$app=New-Object -ComObject PowerPoint.Application
$fonts=@(Get-ChildItem -LiteralPath (Join-Path $env:WINDIR 'Fonts') -File | Sort-Object Name | ForEach-Object {
    @{name=$_.Name;bytes=$_.Length;modified_utc=$_.LastWriteTimeUtc.Ticks}
})
$json=$fonts | ConvertTo-Json -Compress -Depth 4
$sha=[Security.Cryptography.SHA256]::Create()
$fontHash=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($json)))).Replace('-','').ToLower()
@{backend='PowerPoint';backend_version=$app.Version;office_build=$app.Build;platform=[Environment]::OSVersion.VersionString;
  font_inventory_hash=$fontHash;font_count=$fonts.Count;probe_scope='environment_only'} | ConvertTo-Json -Depth 6 -Compress
# Read-only environment query. Never quit the shared Office application.
