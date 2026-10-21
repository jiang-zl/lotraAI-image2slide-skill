# 1.36.0 installation validation

Current receipts are required; historical versions do not qualify this release.
Read Installation-checks.json, Backend-and-delivery-checks.json,
Final-distribution-checks.json and Version-consistency.json for exact byte-bound
results. Fixtures are not acceptance of the user's artwork.

| Channel | Scope |
| --- | --- |
| Focused regressions | 96 checks: 17 installer/transport, 20 Math/backend/rollback, 42 native/source counterexamples, 10 backend/delivery/geometry, 7 release consistency |
| Windows PowerPoint | Actual fixture PDF, genuine Office Math, native save, edit/save/reopen, native descendant preservation; independent final-file check |
| Windows LibreOffice | Actual formula PDF, PPTX save and actual reopen/export; owned process-local temporary directories |
| Linux / WSL | Actual existing Linux runtime/LO resources, native Linux filesystem install and fallback fixture PDF/save/reopen; does not qualify physical macOS |
| Delivery | Final optimized PPTX actual same-backend equivalence, user-root stage/hash/no-replace publication, exact two-file output and unchanged repeat |
| Installer | Windows/Linux first/repeat local bundle and README paths, core/Math capability separation, one skill and user-sentinel preservation |
| Native-first install | Local Office fixture can qualify without an installed LO tree; null UNO-import claim for local application mode |
| Final package | Supplied skill packager validates its ZIP; all distributed entry bytes use LF for shell and parse on their relevant OS; new native PowerShell worker has its own parser check |
| Version identity | Source/runtime/current READMEs/channels, core/packager/installer, payload, nested ZIPs, parts and public asset identities checked together |
| Runtime resources | Immutable 1.14.0 binary/resource/catalog platform records retained, no new runtime binary Release |
| WPS and physical macOS | NOT_RUN on physical hosts; adapters require that actual host's complete capability probe |
| External artwork and performance/token effects | NOT_RUN; no acceptance or performance claim |

Large immutable archives may be preseeded in hash-verified caches. First-install
success descriptors must be absent; repeat checks preserve skill bytes/mtimes.
Public README commands and final public attachment/channel bytes are verified
after publication. Any transport-specific retry remains separate evidence.
