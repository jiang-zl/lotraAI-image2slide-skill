# v1.31.0: scoped native text, shape and formula contract

This release is based on v1.30.0. Only explicitly selected standalone text,
primitive shapes and formula text frames use this contract. Group descendants,
icons and repeated icon instances, tables/cells, connectors, charts, curves,
scenes and photos retain the original execution and acceptance paths. A reusable
icon remains a qualified native mother plus current source instance checks.
Do not rebuild it or loosen its child, geometry, material or multi-scale rules.

## Source and construction

1. Read the original through the existing registered task. Identify exact text,
   mathematical AST, primitive type, dimensions, location, colour and typography.
   OCR suggests text; the current agent resolves ambiguity against the original.
2. Freeze one actual font resource per source font class/style. Song-family
   lookalikes are not separate raster-fitting trials. If the source clearly
   differs, record that decision. Never claim raster font metadata is known.
3. Use native editable text boxes. Round font size half-up to 0.5 pt, including
   explicit run sizes, before building. Freeze the resulting source parameters.
   Formulae are structured AST -> real OMML, including inline math. Plain text,
   vector outlines, SVG and images cannot stand in for editable equations.
4. Bind the selected standalone owners using the existing prepared launcher:

   `native-core TASK bind --request REQUEST.json --out RECEIPT.json`

   The request has `source_sha256`, `owners` (unique object IDs), `scene` (the
   existing complete Scene schema), `source_reading` (original-only rationale)
   and `font_decisions` (class, actual resource, style and uncertainty). Shape-only
   contracts use an explicit `not_applicable` font decision. `scene.source` must
   retain the unchanged original. Every selected object has a supported native
   render type (`text`, `shape`, `equation`) and no parent. Grouped owners remain
   in the old workflow, even if their descendants happen to be primitive shapes.
5. Construct selected objects from `native-core/Frozen-scene.json`. This file
   contains the half-point font parameters. Continue all other source contracts,
   font embedding and native construction through the v1.30 commands.

## What is checked

| Type | Required native facts |
| --- | --- |
| Text | exact literal/paragraph/run content, explicit actual script font, half-point size, bold/italic, colour, saved dimensions, then position/parent/layer |
| Shape | primitive and content parameters, dimensions, fill, stroke, line width/dash/opacity, then position/parent/layer |
| Formula | exact AST and genuine saved OMML, mathematical font/style/size/colour, ordinary prose preserved, dimensions, then position and layer |

The existing native checker reads the actual saved PPTX. Source parameters and
native properties are checked separately. No text glyph F1, foreground mask,
edge F1, density or pixel SSIM is required for enrolled owners. A whole mixed
icon policy is never silently converted into this contract. Existing semantic,
containment, connections, visibility and final whole-figure gates still apply.
Optional displayed soft scores may use nearest 5% bins; these are not used to
round exact text, AST, counts or native facts into correctness.

`native-core TASK check --out REPORT.json` checks current selected owners.
`--request` may supply `owners` for an affected subset. Every enrolled body must
pass before the placement phase can start. A passing phase locks its actual
native signature. Later changes to that signature fail; they are not new trial
opportunities. Identical owner/phase inputs reuse their evidence. A neighbouring
body change does not invalidate an unrelated body's native check. Final audit
calls the checker again independently. Old icon/global checks are not removed.

Three distinct evaluated candidates per owner/phase are allowed. Exhaustion
returns a source/parameter decision boundary, never PASS. There is no automatic
font family search and no new adaptive scheduler in this release. The wider
experimental all-type controller and its tests are excluded from publication.

## Structured formula editor and runtime

`formula-render INPUT.pptx --project PROJECT --out NEW_PRIVATE_DIRECTORY`

This additive command uses the declared project-local LibreOffice runtime and
its bundled Python/UNO bridge. OMML is imported into LibreOffice Math's structured
equation editor. Mixed text/math spans are separated only in a private rendering
copy to preserve inline display during import. The canonical editable PPTX is
unchanged. Ordinary text and icons are not rewritten. A missing native Math
runtime is a capability stop; this command does not try COM, AppleScript or
alternative hosts. Windows x86-64 and Linux x86-64 renderer payloads are supplied.
Other Python-runtime platforms are retained but have no bundled Math renderer.

The receipt is `alternative_render_only`: an actual PDF/preview, not proof of
interactive Microsoft Office editing. It does not replace existing icon host
requirements. Uniform formula base style and unrotated equation frames are
supported; unsupported formula frames report a capability error instead of
flattening. Do not count an editor failure as successful formula verification.

## Release status

The user explicitly requested no further tests and prompt publication after
narrowing the scope. This release is `IMPLEMENTED_PUBLISHED_UNTESTED`. Package
hashes and protected-file comparisons establish packaging/scope integrity only.
Earlier experimental tests, previews and timings are not release validation.
No end-to-end time reduction or service-token saving percentage is asserted.
