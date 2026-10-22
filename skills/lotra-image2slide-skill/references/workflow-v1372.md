# Evidence-driven checks, product 1.37.2

New tasks bind `evidence-checks-1.37.2`; old tasks retain their policy. This is
independent of execution policy 1.37.0, source workflow 1.35.2, design revision 8,
Math policy 1.35.3 and runtime 1.14.0. Continue the registered `next`/`submit`
loop. Programs select methods from actual evidence, never model type, claimed
confidence or a user-selected low-quality mode.

## Acceptance obligations and method cost

All required obligations remain mandatory. A clear line uses independent saved
geometry/style/contact/topology checks, a normal per-segment saved-render check
and readable original/render review. When those suffice, optional refinement
stops. Invalid approximation bounds or insufficient pixel support select finite,
local refinement. A valid failure cannot be replaced by another algorithm's PASS.
Refinement exhaustion, unsupported geometry and unresolved visual questions retain
WORK_REQUIRED; repair source-supported construction or resolve measurement first.

Only declared component metrics execute. Their original sampling and bounds stay
unchanged; no SSIM/histograms/edge transforms are computed merely because another
metric was requested. Raw package/image facts can share an exact-input session.
Final numeric/coverage gates independently read current bytes; prior qualification
and persistent cached PASS never replace them. This is a cost control design,
not a measured claim about provider tokens or every external harness.

## Original line descriptor

Every `internal_line` or `curve`, plus any other feature representing a standalone
line, must contain `line` before source sealing. Shape outlines remain contour
obligations. A line cannot become optional. The descriptor contains original
facts only; do not insert owners, candidate routes or output-derived masks.

Required fields:

| Field | Original fact |
|---|---|
| `schema` | `source-line-1.37.2` |
| `role` | relationship, leader, dimension, axis, data_curve, boundary, decoration or internal_edge |
| `coordinate_space` | `source_canvas`, in original pixels |
| `direction` | undirected, forward, reverse or both; distinct from parameter order |
| `path` | kind straight, polyline, curve, closed or filled_arrow; ordered, contiguous `segments` |
| `ends` | two ordered terminals; zero for a closed path |
| `stroke` | width and opacity intervals, RGB, cap, join, compound and dash |
| `limits` | route, endpoint, marker, width, normalized colour and signed angle bounds with source evidence |
| `topology` | explicit junctions, crossings and shared arrays, including confirmed empty arrays |
| `visibility` | `hidden` intervals confirmed from the original, or an empty array |
| `source_evidence` | located observation of the unchanged original |

Segments use `{kind:line, points:[[x,y],[x,y]]}`, quadratic (3 controls), cubic
(4 controls), or arc (`center`, positive `radii`, `start_degrees`, nonzero
`sweep_degrees` bounded to one revolution). Original coordinates are explicit;
no native transform is allowed. Filled arrows additionally freeze their complete
original `path.outline`. An editable polygon/freeform is an available native
representation when a preset has no qualified extractor. Unsupported presets,
3D/effects or disjoint unassigned subpaths do not receive a diagonal/bbox fallback.

Each terminal contains `point`, `marker` and `attachment`. Marker fields:
`type` (none, arrow, triangle, stealth, diamond, oval, bar, custom), `filled`,
`anchor_role` (path_endpoint, tip, center), original `anchor`, `width:[lo,hi]`,
`length:[lo,hi]`; bar/custom require a source `contour`. Confirmed none uses
zero dimensions. Distinguish open and filled markers and both start/end markers.

Attachment fields: `kind`, `distance:[lo,hi]`, `source_evidence`, and original
target `feature` unless free. Kinds: boundary_touch, intentional_gap, inside_port,
marker_center_on_boundary, circle_half_embedded, free. Free needs a reason;
relationships cannot have free terminals. State actual contact/gap/port facts;
an editable freeform association does not claim automatic connector rerouting.

Stroke fields: `width:[lo,hi]` in source pixels, `opacity:[lo,hi]` in [0,1],
`colour:RRGGBB`, cap flat/round/square, join round/bevel/miter, compound
single/double/thickThin/thinThick/triple. Dash has `kind` (solid or DrawingML
preset/custom) and, when non-solid, alternating on/off `pattern` intervals in
source pixels. Native Scene supports `line_compound`, `line_cap`, `line_join`,
`stroke_alpha`, preset `dash`, or `custom_dash:[[on,gap],...]` in stroke-width
units. Standard start/end markers have independent `*_width` and `*_length`.
Translucent strokes also supply independently observed `paint_colour` for the
composited source pixels; native colour/opacity and visible paint are checked
separately. Dash intervals are checked against ordered complete original/render
runs; partial terminal runs cannot supply a fabricated full pattern.

Topology records contain stable `id`, source `point`, all incident original
line `features` and `source_evidence`, copied reciprocally to each incident line.
Crossings also state kind crossing/bridge/occlusion. A crossing is not silently
made a junction. Hidden records contain source `segment` index, normalized arc
length `range:[lo,hi]`, original `occluder` feature and source evidence. Do not
infer or add occlusion merely because a candidate is missing paint.

Source corrections must reference `prior_line_hash`, reason and located source
evidence through the existing source correction mechanism. Bounds cannot be
widened after a candidate fails. Resolve ambiguous source facts before binding.

## Native binding and program checks

`feature_bindings` keeps existing owner/component/representation fields. When
shafts and separate markers share a feature, supply exact `line_parts` entries
`{owner,role:shaft|start_marker|end_marker}` for every owner. Otherwise all owners
must be actual native shafts. No raster/group/text proxy qualifies as a shaft.
Closed freeform filled arrows can use `terminal_sites` per owner with start/end
`{vertex:index}` or `{edge:index,fraction:0..1}` on their actual outline.

Binding compiles required route/terminals/markers/stroke/topology/visibility
obligations and the native-line census. Callers cannot supply/lower the compiled
policy. Saved decoding is independent of construction and includes ancestor
transforms, signed bends and terminal tangents. Both-direction path distances,
ordered corners, retained length and source topology prevent an aggregate long
line from hiding an inverted elbow or short missing arm. Native connector IDs
must name the actual target owners. Unknown saved lines fail the census.
Self-intersecting curved traversal is explicitly INVALID unless a qualified
ordered producer is available; equal occupied sets/length and shared-junction
landmarks cannot prove loop order. Declare independently supported simple parts
instead of accepting reordered loops or inventing an unobserved route.

Actual render uses the declared backend and current saved bytes. Each visible
source segment, shaft width/bands, dash support and marked terminal paint has
its own check. No candidate alignment or whole-panel averaging earns PASS.
Pixel uncertainty is explicit: a subpixel question may remain INVALID rather
than being called correct. A native/readiness PASS alone cannot accept appearance.

Normal terminal paint bounds conservatively compare the occupied foreground
pixel-cell sets. Only an inconclusive bound selects a tighter local cell-union
measurement, sampling complete interiors as well as boundaries with a proved
covering error and a finite allocation limit. It measures the same fixed colour
masks and source canvas; it does not infer a hidden subpixel curve or resize the
source to manufacture accuracy. A valid failure cannot select this refinement.
When current render precision can resolve a remaining inconclusive question,
the packet may offer `operation:refine_render` with its exact manifest ref. This
preserves the saved PPTX, original, limits and backend, retains the old evidence,
and requests an actual higher-resolution render, at most twice per native hash.
Irreducible original ambiguity remains a source decision, never a false PASS.

## Located review, doubts and release

The final-visual packet includes `line_review.manifest`, compact comparison pages
and a page count. Read every target/page through the managed selector, then view
the original and actual render crops. Normal crops cover clear lines; critical
points are enlarged when normal views are too small. Every open doubt receives
located enlarged views; a long/curved doubt is fully tiled, not reduced to its ends.

Include this in the normal final-visual evidence JSON:

```json
{"line_review":{"manifest":{"path":"...","sha256":"..."},
 "lines":[{"line":"source-line-id","criteria":{
  "route":"PASS","terminals":"PASS","markers":"PASS","stroke":"PASS",
  "topology":"PASS","visibility":"PASS"},"evidence_refs":[]}],
 "issues":[],"resolutions":[]}}
```

Fill each line's `evidence_refs` with the exact source/render refs for **all**
planned normal/critical/doubt views. A shared comparison may cover several
criteria; no six repeated paragraphs are needed. Values are PASS, FAIL or
UNRESOLVED. Do not generate these judgments from Scene, expected native geometry
or measurement verdicts. Hashes establish evidence identity, not proof of looking.

Record any doubt as `{id,line,criterion,finding,roi:[x,y,w,h]}` and mark that
criterion FAIL/UNRESOLVED. A missing explicit issue still creates a retained doubt.
It cannot vanish on the next review. For resolution, prepare/view its current
enlarged crops and supply `{issue,kind,observations,evidence_refs}`; kind is repair,
measurement, false_positive or source_decision. A resolution also requires the
same criterion's current valid program PASS and explicit visual PASS. Text and
aggregate diagnostics cannot waive valid failure, invalidity or stronger evidence.
Visual/measurement uncertainty alone returns to enlarged review before drawing.
An established program failure enters the existing scoped native repair process.
Program doubts are persisted when their review packet is prepared, even before
an observer submits a conclusion. A new preview or a now-passing measurement
still needs the retained doubt's explicit enlarged resolution. Visual FAIL
also enters scoped repair; UNRESOLVED requests evidence before drawing.
Native/source-plan rebinding preserves all line doubts and consumed render
refinements. A RESOLVED doubt whose source/native/render/implementation binding
changes becomes OPEN again, retaining its old resolution as history. Both review
preparation and independent validation enforce this; zero-line applicability
cannot erase an outstanding question. Rebinding never resets quality or budgets.

Final audit independently executes the complete required gate set, including
`source_lines`; zero lines require an independent source/native census. Formal
export and `delivery-check` verify those gates, current artifact identities and
the exact PPTX attachment bytes. Existence, stale ACCEPTED, partial evidence or
missing/invalid/excluded checks never authorize finished delivery.
