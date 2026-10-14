# Source-relative ink spacing

A text box, formula frame, or icon group may not intersect its neighbor's
frame even when the visible glyphs, strokes, or arrowheads collide. Measure
the **visible ink** of two semantic entities against the same pair in the
source image. Record source-observed gaps and intentional contacts before
repair. Do not penalize a source overlap merely because it is compact.

For each important pair, freeze a `ink-spacing-1` contract containing the
source image, the actual saved-PPT preview and its verified render receipt,
four binary full-canvas masks (`source_a`, `source_b`, `candidate_a`,
`candidate_b`), mask provenance, source intent (`separate` or
`observed_overlap`), and pixel tolerances for crowding, expansion and extra
overlap. Bind each candidate mask to saved PPT object path(s) and an extraction
ROI. The checker rejects a candidate object that escapes that ROI; cropping
off moved glyphs must not make a collision disappear. Use `check-ink-spacing
CONTRACT.json --out REPORT.json` and inspect the raw source/candidate gap and
overlap along with the status. A successful mask-only test is diagnostic; a
verified alternate render with saved-object bounds is still limited to those
pairs. It does not replace full-page layout review or actual PowerPoint
equation/text editing.

Generate masks from source observation or object-isolated rendering under a
documented, fixed segmentation rule. A broad rectangle is not a glyph mask.
Check the resulting masks visually. If two entities share a color and overlap,
composite segmentation may not tell which owns a pixel; isolate their native
objects or leave that pair UNVERIFIED. If source text, formulae, and arrows
cannot be separated reliably, do not invent a precise gap score. Changing
candidate crop, threshold, or tolerance after viewing its result requires a
new plan revision and complete remeasurement.
\nThe saved-render spacing route accepts actual PowerPoint through the existing host-render verifier and alternative LibreOffice through its own verifier. It retains backend-specific scope in the report. Candidate ROI bounds compose real nested group transforms from the saved native inventory; child-local coordinates do not stand in for slide positions. This is per-owned-mask spacing evidence, not all-slide acceptance.\n