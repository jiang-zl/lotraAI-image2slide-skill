# Resumed goal: stability preview

Human directive: “好，恢复goal吧，稳定了给我看看，再投入deepseek做原事故验收”.
The same 1.37.4 -> 1.37.5 goal continues. Earlier no-validation instructions are
superseded for development and non-DeepSeek validation. The DeepSeek original
case and publication remain later stages; the user sees a stable candidate first.

Current work:

1. Review/test the existing unit/half-point/font-family guards and fix defects.
2. Bind an explicit measurement plane, original/target transforms and physical
   output scale; semantic cropping alone never establishes perspective correction.
3. Implement bounded actual-font glyph/phrase fitting on the 0.5 pt grid, with
   fixed geometry, source uncertainty and explicit ambiguous/unsupported outcomes.
4. Reuse existing OCR/sample evidence and source style groups; keep Chinese and
   English collections separate, Chinese display names and coarse-family first
   decisions. Preserve exact physical resources and optional finite fine review.
5. Validate normal/error/recovery cases and real native rendering. Produce a
   reviewable visual comparison and editable candidate without claiming that a
   synthetic fixture accepts the original incident image.

No DeepSeek calls, new provider keys, global installs, public release or active
installation replacement are part of this preview stage. Later original-case
acceptance remains separately attributed to its actual model/harness. Historical
e11 evidence and earlier cancelled-scope reports keep their actual dates/bytes.

Status at resumption: IN_PROGRESS. Latest source and font-family additions have
not yet been tested at the start of this stage. The goal service still returns
its historical blocked state and exposes no agent-side resume operation; this
document records the human's explicit resumption without replacing that goal.

Current checkpoint: STABILITY_PREVIEW_READY. The latest program/test bytes have
516 passing Windows regressions and 515 passing Linux regressions plus one
Windows-only sharing-lock exclusion. Added source-bound alignment intent, native
horizontal/vertical/inset checks for every paragraph/cell, standalone equation
vertical alignment and actual whole/group ink positions. Nine actual PowerPoint
aggregates pass; deliberate left/top alignment errors fail both native and paint
checks. Six controlled photographed ordinary-text owners recover known half-point
sizes; an oversized declaration is rejected before native construction.

Only the customer included-path inventory changed after the full regressions;
23 separate metadata regressions and actual same-ZIP verify/unpack/import on both
platforms cover that final metadata change. The report verifies every other
program/test hash still matches the full receipts. See the private development
validation/stability-r1/Preview-report.md and Stability-summary.json. DeepSeek,
original-art acceptance, complete public distribution/install gates and final
publication remain outstanding. Preserve all original failures and old receipts.
