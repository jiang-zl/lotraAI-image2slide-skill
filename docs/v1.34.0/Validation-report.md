# v1.34.0 validation scope

Validation date: 2026-10-16. The user authorized implementation and validation
for this release. Earlier releases' no-test descriptions are historical and do
not describe these checks. This report distinguishes program correctness,
installation, actual rendering and artwork acceptance.

| Channel | Evidence and scope |
| --- | --- |
| Behavioral checks | 42 positive/counterexample tests passed: original observation/recursion, missing features/extra owners, representation capability, native surfaces, saved-pixel probes, invalid measurements, final omission coverage, legacy policy, source-free paint order, managed selector isolation, native table cell correspondences, legacy feature-ledger interfaces and exact export comparison canvases |
| Syntax/import | 297 Python files parsed; 16 changed/new/retained core modules imported using the prepared runtime; version is 1.34.0 |
| Skill structure/package | Skill creator structure validation and customer payload inventory checks run; final manifest/payload identities are in publication.json and the bundle/catalog |
| Windows x64 installation | New local complete-bundle installation passed; dependencies, actual OCR proof references, Math version/UNO import, CLI, one skill/no Setup and installed-file hashes checked |
| WSL/Linux x64 installation | Same new complete-bundle installation and startup checks passed |
| Normal online update/repeat | Windows and Linux normal coordinator entries downloaded through local HTTP mirrors; only URL literals/derived pins differ from production. Updates/repeats passed; private sentinels retained and unchanged managed files were not rewritten |
| Native constructor rendering | Actual saved v1.34 PPT rendered with prepared Linux LibreOffice. Annular inner/outer walls, full hole without radial seam, curved variable-width band and projective detail inspected. Shared prism geometry was also exercised by the independent trial |
| Independent forward trial | A source-observed synthetic case completed normal start/next/submit, bind, native build, render, local qualification, layout, one font review, whole review, independent audit and accepted export. It used nine source units/features/components and six relations. Two incomplete local feature-review submissions were actually rejected |
| Current frozen snapshot repeat | The final r6 snapshot completed the current component audit and normal accepted export. Nine source-feature and nine original-unit omission checks were supplied; an incomplete generic PASS was rejected. Export rerendered both comparison sides at 2000×1250 using PowerPoint 16.0 target_render_only, with exact RGBA and three-scale PDF equality plus byte-identical native XML/fonts |
| Office editing behavior | NOT RUN / EXCLUDED: open/edit/save-reopen behavior is not counted as PASS |
| Performance/token effect | NOT RUN; no effect or savings claim |

Six publisher guard checks passed without credentials or uploads. They cover
declared part offsets, path confinement, conflicting remote digests, local-only
checking, historical-resource preservation and complete repository groups.

The initial independent snapshot exposed the shipped .sh allowlist issue. The
second snapshot completed a synthetic accepted export after that fix. It also
exposed outer CLI compact references that were not registered for managed
selection. The final source fixes that envelope path and includes positive and
isolation-negative selector tests. Original failure records are preserved.

The current-snapshot trial exposed an export comparator defect: a 1600-pixel
accepted preview was reused against a fresh 2000-pixel export preview solely
because the host and PPTX matched. Export correctly stopped at its exact pixel
comparison. The corrected validator only reuses a comparator whose actual page
dimensions all match; otherwise it actually rerenders the original at the same
2000-pixel target. Native XML/font byte equality, PDF fingerprints at three
scales and exact RGBA comparisons are retained. No resizing or relaxed threshold
is used. The three added regression checks include a real pixel-change rejection.

Final frozen identities are recorded for reproducibility:

| Item | SHA-256 |
| --- | --- |
| Skill MANIFEST.json | b537d0d83c0b75cd4d448ad2ee137b0029f4978adcb6b63e147e5e92ece27e67 |
| Component implementation | b50af25c536d4c730d4dc8ff2cf4f98d66a87cdb7349936717fc3e7ed2106a31 |
| Export validator | 6bbbf321a2ab8b517ea1e65dcaebfea59c4f60f1b8b3f9fcce31d88a5fec67c5 |
| Final component audit | 360c83bd90142a46d2dae1fa2e076b26c76e35561692d1560b9c78bc2eb41f59 |
| Accepted export receipt | 0d928aef2b5be786157e29da7951535708eac2a1f0fe3e6d49b801ba9a7f1585 |
| Synthetic delivered PPTX | 9002c37e2fc6c70fa4212506a6ed6a0fcfbeb92f928b881e4619ddf8ae73d989 |

Only the export validator changed from r5 to r6; the component implementation,
original, saved PPTX and current whole-artwork acceptance basis stayed identical.
Normal next retained that valid audit, and normal export independently bound the
new validator hash. Both r6 comparison-owned PDFs were actually disposed after
successful observation (7909 bytes each). Failed r5 evidence remains retained.

Three Windows LibreOffice export attempts timed out or failed during the trial.
They are not reclassified by Linux rendering success. The same Linux preview
also failed exact fresh rasterization in the Windows environment, so the same
final packet was audited successfully in its original prepared Linux rasterizer
environment without changing PPTX, PDF, preview, receipts or comparison bounds.
Cross-environment bitwise rasterization equivalence is not established.

The normal second-snapshot export internally selected PowerPoint for temporary
PDF size-equivalence rendering. Those two exports proved before/after native
and pixel equivalence in that scope and their temporary PDFs were disposed.
The formal original-to-output visual acceptance remained bound to the Linux
alternative render. This is not an Office editing behavior test or a general
PowerPoint fidelity claim.

The simple synthetic trial has no text, formulas, tables or tunable numeric
targets. It does not qualify all component classes, font matching, formula
rendering, personal-learning effects or external user artwork. The newly added
probes have focused saved-image/counterexample checks; synthetic results do not
accept a user's entire reconstruction.

macOS resource identities are prepared, but macOS hosts were not tested. Linux
ARM64 core resources do not imply a complete supplied Math/rendering channel.
The runtime binaries retain their independent 1.14.0 identities. Public GitHub
installation of v1.34.0 remains pending the user's manual runtime upload; local
HTTP checks are not described as a public end-to-end installation.
