# Semantic target and typography before rendering

New tasks bind `typography-preflight-1.37.5`. Existing tasks are not migrated by
a changed skill installation. Keep source failures, budgets, private files and
user locks. Product version and independent workflow/runtime IDs remain separate.

## Select the content, with a full-image fallback

Inspect the original semantic contour before `start`. If the actual slide or
figure content is distinguishable, use the existing `--target-plan` argument
with `kind:semantic_region`. Identify what belongs in the output and what is
capture/playback environment. A black slide design is content; a wall, playback
letterbox or reflection outside it is not automatically content. Preserve the
original bytes in every case. If the content contour is ambiguous, use the full
image (`source_projection`, also the program default); this is a valid fallback.

A semantic plan contains `schema:capture-target-1.37.5`, `raw_source_hash`,
`observer:host_model|human`, located `source_evidence`, original-image `contour`
(4..64 points), `content_scope` and `excluded_scope`. The program crops only the
integer bounding envelope and freezes reversible translation. It does not fill
outside a polygon, infer a clean original colour, deskew, remove internal design
shadows or guess 16:9. Outline points and scope remain original observations,
not a constructor's expected result. Partial PPT input still requires its explicit
coordinate-domain decision. `slide_surface` projective correction remains a
different route requiring actual aspect-ratio authority and uncertainty.

## One declared conversion, then a half-point grid

Source observations and frame geometry stay in source pixels. All native text,
table text and explicit Office Math base/run sizes use pt. Declare once in the
binding Scene: `typography_units:{font_size:pt}`. An explicit `source_px` input
means source-pixel **em size**, not observed ink height; the physical mapping
converts it once. A leaf `font_size_unit` may make its input unit explicit.
Unknown/missing units reject. Do not copy a 30-pixel glyph height into `30 pt`.

The shared converter uses `pt_per_source_px = target_width_inches*72/source_width`.
Binding freezes that mapping. Changing the physical canvas later requires source
rebinding rather than silently changing every glyph's apparent size. A requested
native size is rounded to the nearest 0.5 pt with decimal half-up: 12.24 -> 12.0,
12.25 -> 12.5, 12.33 -> 12.5, 12.75 -> 13.0, 0.33 -> 0.5. No banker rounding or
cumulative rounding is used. Preserve input/conversion decisions in scene history.
Explicit tracking, line spacing and paragraph indents also use the shared half-point
conversion; signed tracking remains allowed. Source ROIs, physical canvas inches,
geometry/line widths and native Math's implicit script ratios are not font sizes
and are not mechanically put on this grid.

## Dedicated source size model

For new tasks, [finite visual-family selection](font-family-gate-v1375.md)
precedes this size model. Chinese and English use separate collections; Chinese
choices have Chinese display names. A coarse 雅黑 inference is sufficient for
the family step. Bind one real eligible face for size measurement without
claiming its vendor is identified. Optional fine refinement is finite, evidence
driven and deferred; it is not a prerequisite to progressing with typography.

Establish the measurement plane before binding: `slide_surface` supplies its
verified target mapping and original aspect authority. Otherwise declare
`typography_measurement:{kind:fronto_parallel|projected_appearance,evidence:{path,sha256},source_uncertainty_px:0.5}`.
The referenced current source observation records `measurement_kind`,
`source_hash`, `observer:host_model|human` and located `observations`. A crop
does not establish perspective correction. Freeze physical canvas/measurement
basis at contract sealing; a later change needs normal source rebinding.
`projected_appearance` measures local visible scale only and cannot establish
equal original sizes across differently foreshortened parts of a photo.

The bundled OCR can locate original words/lines and propose sample positions.
Current cached anchors can yield bounded `size_sample_suggestions`; confirm
literal and ownership on the unchanged source before adopting them. An OCR box
or an internally size-normalized OCR crop is not a point-size reading.

The dedicated fitter uses original glyph/phrase ink, exact physical font bytes
and the frozen physical mapping. Actual raster ink on both sides initializes a
finite search of at most 17 half-point sizes. Compare fixed-scale ink extents,
boundaries and whole-string disagreement; no independent glyph scaling or
candidate-dependent registration is allowed. Hinting and fourfold rasterization
are two finite rendering hypotheses, with one mode shared by all samples at a
size. Propagate per-edge source uncertainty plus candidate half-pixel raster
quantization into a two-edge extent budget. This screening budget does not
replace or widen any frozen final appearance limit. Retain explicit ambiguous,
unsupported and search-bound outcomes; no fabricated calibrated confidence.
This uses geometry and actual font rasterization, with no training or new key.

Keep size identification separate from a construction estimate. If several
half-point sizes satisfy the unchanged source-fit limits, retain `AMBIGUOUS`
and its complete interval. A declared half-point inside every applicable fit
may proceed as `SUPPORTED_ESTIMATE`; it does not identify the historical size.
Otherwise the ordinary source recovery selects only from the finite supported
intersection, retaining a supported current estimate before ranking alternatives.
An empty or contradictory intersection still blocks all native writes. Actual
font/whole-ink appearance and final gates must qualify the chosen estimate.

Reuse existing current `font_samples` for inferred fonts. Exact/user font choices
and Math also need independent size samples. Supply owner
`typography_samples[location]` with `source_hash`, `observer`, `source_evidence`
and 1..12 `samples:[{character,roi}]` or `samples:[{text,roi}]` for a confirmed
single-line phrase of at most 32 characters in the same request/script. Samples
use `domain:task_source` (the default), never normalized OCR coordinates.
A Math sample additionally declares
`math_level:base`; a sub/superscript cannot identify the base size. Every sample
must belong to its actual owner/script and include isolated ink with clear
background margin, not a clipped ink box. Contradictory samples, pose ambiguity,
missing source ink or changed physical font bytes return a diagnostic. The model
never manufactures confidence, widens a frozen appearance bound or silently
shrinks the text. A model recommendation is not source-font identity or final PASS.

An explicit source-supported `size_group` in these per-location records declares
equal source sizes, independently of the font-family group. Source-size groups
intersect the valid candidate sets; a failed member cannot be averaged away.
Unchanged peers are read dependencies and receive no additional native-write
grant. A group needs a shared rectified/fronto-parallel plane. Do not force
titles, body text and Math script levels into one size merely because the font
family is shared. A group uses one common supported construction estimate;
different member declarations cannot silently pass as equal. Missing or
unsupported source size remains a current decision. Nonunique identification
stays visible even when a supported estimate proceeds to actual rendering.

## Check before and immediately after writing

Binding sealing canonicalizes declared units before freezing source/native
targets. A shape-only Scene has no font/measurement obligation. The normal
component constructor enforces declared units, conversion/grid and
source-size screening before creating a native transaction. It also performs a
cheap horizontal-run advance/frame screen. Wrapped, table-cell, vertical and
formula layout not covered by that coarse screen are explicitly reported as
unscreened; their size and native attributes still have mandatory checks.

After creating each text body/equation/table and writing content and styles, the
native writer immediately checks the in-memory XML against the intended literal,
font size, font faces, colours/emphasis and genuine Math structure. Written PPTX
font checks re-read saved bytes, including the half-point native size grid, before
any whole-slide rendering. An error blocks progression and retains its current
diagnostic. Do not delete pending state or issue another transaction to escape it.

Centering has three distinct checks. Before mutation, horizontal/vertical
alignment, rotation, paragraph indents and table-cell alignment/padding must
match the frozen source-bound intent. Immediately after writing, inspect every
paragraph's actual `algn`, body vertical anchor, margins/indents, all table-cell
paragraphs/padding and both DrawingML and OMML equation justification. A native
flag or centered frame alone never proves optical centering. Standalone Math
must apply its declared vertical alignment, just like ordinary text.

The first actual render compares both axes of the complete painted text/Math
aggregate in fixed source coordinates. Each populated table cell has its own
isolated original text feature. Optional `text_appearance.limits.position`
freezes a source-pixel position tolerance; without it the existing minimum of
width/height/baseline limits is used, without widening any prior bound. Preserve
the observed source offset instead of snapping content to the geometric center.
For parent/face containers retain the existing source-owned two-axis spatial
relations and complete direct-content footprints. Those checks verify the
container/frame relation; the painted aggregate check verifies actual glyphs.
Mixed runs, multiline text and complete fractions/scripts are checked as their
source-supported aggregate. Explicit original row/glyph groups also compare both
ink-center axes, so an unchanged outer block cannot hide a shifted internal row.
Local font/size/alignment edits invalidate these
checks. First-render local closure and independent final gates both rerun them.

These early checks remove avoidable full-page render/repair iterations. They do
not prove how Office/LibreOffice actually shapes and paints the file. Current
actual rendering, local source appearance, final omission review and independent
delivery gates remain necessary; no time/token reduction is claimed as measured.
