# lotraAI Image2Slide 1.36.0

Use a capability-qualified local presentation application before the declared
LibreOffice fallback. One common source/geometry/font/OMML generator now emits
Office-compatible native freeform routes rather than custom geometry inside
p:cxnSp. Attached endpoint bindings are never silently discarded. Both saved
structure inspectors check the exact source route and bounds.

Windows PowerPoint and WPS use bounded local COM adapters; the macOS PowerPoint
AppleScript adapter remains experimental until its actual host probe passes.
Readiness requires real PDF export, native PPTX save, edit, save and reopen of
an owned fixture with genuine Office Math. Every final PPTX has its own native
save/reopen gate, independent of the actual PDF and whole-artwork gates. Auto
may use one declared LibreOffice fallback after an actual native PDF failure,
retaining the native failure and naming the real backend. An explicit backend
choice is binding. Existing user files and shared Office sessions are protected.

Core resources are prepared before native qualification. A qualified local
application can satisfy native Math/render/save requirements without installing
LibreOffice. Otherwise the existing independently versioned Math resources are
used, with owned profiles and process-local TEMP/TMP/TMPDIR. A PNG never stands
in for a failed PDF. LO-only export reports target Office as UNVERIFIED.

Users can select a delivery root, with project root as default. Each export
reserves output-slide-YYYY-MM-DD-HHMMSS-mmm, stages on that same volume, verifies
the actual final file, and publishes through an atomic no-replace rename.
Repeated resume uses the same destination; explicit --new-export creates a new
delivery. Only Final_editable.pptx and Report.md are exposed. Task/audit data
remains private in .lotraAI-build and common.safe_path is not widened.

Product/core/packager/installer/current documentation and distributions use
1.36.0. Workflow_version 1.35.2, design_revision 8, the LO Math policy 1.35.3 and
runtime/companion 1.14.0 remain independent. Runtime binary/resource assets are
unchanged. Reuse verified historical bundle parts; upload only the new tail,
skill payload, necessary entries, catalogs and evidence. Source/runtime default
branch remains dev, version branches 1.36.0, formal source tag v1.36.0.

Keep v1.35.4 and v1.35.5 tags/assets, user sources/deliverables, private resources,
the active custom local skill and all global skills. No forced local activation.
Windows PowerPoint and LibreOffice fixtures have actual host evidence. Linux
qualification and final installer/distribution checks are required before release.
Physical WPS/macOS qualification is pending; mocks and WSL do not establish it.
No external user artwork is accepted by these release fixtures. In particular,
the diagnostic repair of a legacy invalid connector changes its old LO display
and is not delivered as an accepted replacement for the user's original.
