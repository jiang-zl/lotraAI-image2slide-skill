# 1.35.4 installation validation

This patch validates installation entries and final distribution bytes.

| Channel | Evidence |
| --- | --- |
| Windows bootstrap regressions | Seven tests passed: primary download, one API fallback, HTTP range resume, changed-cache preservation, verified-cache reuse, repeat generation and shell LF |
| Linux bootstrap regressions | The same seven tests passed on WSL/Linux |
| Generator repeat | Three consecutive renders preserve output bytes and modification times |
| Final shell distribution parsing | sh -n and bash -n inspect source/runtime entries, attachments and ZIP-contained entries; see Final-distribution-checks.json |
| Final Windows distribution parsing | Windows PowerShell Parser.ParseFile inspects source/runtime entries, attachments and ZIP-contained entries; see Final-distribution-checks.json |
| Actual Windows/Linux installation | Complete-bundle and public README command receipts are recorded in Installation-checks.json |
| Resource preservation | Runtime 1.14.0 and existing engine, companion, OCR and Math records are retained; no new runtime binary Release |
| macOS Apple Silicon/Intel | Physical-host installation/startup NOT_RUN; still pending |
| Reconstruction, formula rendering and Office interactive editing | NOT_RUN for this installation patch |
| Performance/provider-token effects | NOT_RUN |

1.35.3 Math/backend results are historical evidence and are not counted as new
1.35.4 execution. Installation readiness is distinct from rendering and artwork
acceptance. Existing user data and global skills are outside the change scope.
