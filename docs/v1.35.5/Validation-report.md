# 1.35.5 installation validation

Only current 1.35.5 receipts qualify this patch. Prior 1.35.3 Math/backend and
1.35.4 installation checks remain historical and keep their original versions.

| Channel | Current evidence |
| --- | --- |
| Windows regressions | 23 focused checks: seven bootstrap, ten product/packager/part bindings and six release-gate counterexamples |
| WSL/Linux regressions | The same 23 focused checks |
| Generator repeat | Current entries and coordinator/packager version constants retain identical bytes and mtimes on repeated generation |
| Final distribution versions | tools/validate_release_versions.py checks source/runtime, current docs, pins, catalog hashes and actual ZIP members; see Version-consistency.json |
| Final shell/PowerShell parsing | Actual loose assets, skill ZIP, complete ZIP and nested skill members are parsed; see Final-distribution-checks.json |
| Complete-bundle installations | Current Windows/Linux first/repeat receipts, core and Math startup readiness, one main skill and sentinel preservation: Installation-checks.json |
| README installation commands | Exact current public command blocks are checked after source/channel publication; first/repeat results: Installation-checks.json |
| Complete-bundle downloads | Actual current manifest, inherited part identities, hash-addressed cache and first/repeat output preservation: Installation-checks.json |
| Runtime resources | Existing runtime 1.14.0, engines, companion, OCR and Math archive records are unchanged; no binary upload |
| Physical macOS | NOT_RUN; Linux parsing is not Mac hardware qualification |
| Reconstruction/formula rendering/Office interactive editing | NOT_RUN for this patch |
| Performance/provider-token effects | NOT_RUN |

Large unchanged archives may be preseeded in a hash-verified fixture cache;
installation success descriptors are absent before first installs. Windows
public checks use process-level direct networking where required, without
changing saved proxy settings. Linux uses owned native WSL filesystem projects.
Actual final public identities are verified separately from local fixture checks.
