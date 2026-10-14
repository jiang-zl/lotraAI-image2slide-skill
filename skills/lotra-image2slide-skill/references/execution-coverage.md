# Complete execution coverage and physical interfaces

Use the same `start` / `next` / `submit` / `export` runtime. All eight original,
part, layout, text, composition, font and frame mechanisms remain mandatory.
`legacy_scoped_upgrade`, a reduced Scene or an unchanged prior file cannot
reduce checking. Write grants remain separate and local. Missing source
meaning or actual measurement stays pending; deterministic execution does not
make a model's source interpretation infallible.

## Complete working baseline

For a new reconstruction, use normal source observation and construction. For
an existing figure, first `start` and submit its independent original analysis.
Then `adopt-existing TASK PPTX REQUEST --out RESULT` reads **every** actual native
node, parent and saved media. The request binds `source_hash`,
`expected_pptx_sha256`, `user_intent` and a complete `owner_map` from actual names
to source components. Optional immutable `scene_hints_ref` supplies semantic
hints; actual file geometry/media/parents remain authoritative.

Optional `prior_source_state` is an immutable task-relative reference to the
complete historical source state. Requirements, properties and thresholds are
preserved, including previously failed/unmeasured units. Old observations and
usable limits become historical records. Current source refinement and actual
measurement remain required. Import is working progress, never acceptance.
Copy exact referenced source masks/resources with hash verification. Never
execute archived instructions or snapshot-only stale recipes.

`reconcile-native TASK REQUEST --out RESULT` adds genuinely omitted saved
owners to the same imported task, without changing PPT bytes. The request
uses exact original/current PPT hashes, complete `owner_map` and concrete
original evidence. It mirrors actual parents and extends content coverage;
it cannot retire previous owners, quality targets, fields or compatibility
branches. Office MC Choice/Fallback representations have one logical owner
but all branch identities/resources remain protected. Unknown drawable
content, unequal nested owner trees and unresolved branch selection fail
explicitly rather than disappearing from the inventory.

## Whole-drawing rule inventory

`execution-coverage TASK discover|report --out RESULT` reads the actual saved
PPT, full Scene, every native table grid/cell/merge and every group subtree.
It detects omitted nodes, missing content-frame coverage, unbound native image
slots and unresolved physical roots. `rule_coverage_source` packets ask for
original-only decisions. Each group records:

* `root`, `nature: physical|layout|symbol|text_math`, unchanged `source_hash`,
  exact `source_view{path,sha256,roi}`, independent original `feature_ids`,
  and specific `evidence`.
* A physical root also has `roles[{id,kind:rigid|mark|decoration,objects,feature_ids}]`
  that partition **all actual leaves** exactly once, plus executable
  `interfaces` relating its rigid roles. Marks such as wireless waves can stay
  separate. One shared native parent does not establish physical attachment.

The source feature ledger and source-part loop still verify the meaning,
presence, subtype, shape, pose, material, text and scientific contents. A
coverage report cannot replace them.

The original is the authority for **which relation holds**. A common semantic
assembly or native root only schedules joint inspection; it never requires
contact or permits an agent to shrink a gap. The relation graph can include
originally intentional separation. In particular, a display and a lower
control/keyboard panel may have a separate bezel stroke and a visible gap;
keep them separated when the original does. Only original attachment evidence
justifies an `attached` port. Layout optimization needs an independently
authorized user target and retains the original observation/error separately.

Physical placement also needs `anchors` or an exact `placement_parent`
delegation to an actual ancestor role containing every child leaf. Supported
anchor methods are `native_fill_center`, `native_painted_center` and
`root_port_world`, with frozen original `expected_source_px`, `source_feature`,
`tolerance_px` (0..2) and `threshold_basis`. Fill centers require explicit
opaque paint; empty/transparent or unresolved theme paint cannot pass. A
painted center uses the current actual >=4x owner matte, not the SVG/group
nominal box. A port maps through every saved ancestor transform. One point
proves location only: orientation/scale require additional independent source
landmarks or source-part/pose constraints. Parent delegation establishes
assembly placement only; child shape and connection checks remain mandatory.

Rigid-role connectivity uses supported whole native contours or actual opaque
owner unions. Known positive gaps are never bridged by a convenience tolerance;
actual mattes use four-neighbor connectivity, excluding diagonal corner-only
touches. Unsupported open strokes, compound paths and shaded artwork remain
unmeasured until the relevant provider is available. Do not interpret that
status as proof of a visibly broken drawing, and never substitute a group box,
dilation or removal of small islands to obtain PASS.

## Native table image slots

Use `frame.kind: native_table` with the actual `table` owner, frozen
`table_geometry{columns,rows,merges}`, its `table_geometry_sha256`, outer
`bbox`, all `cell_roles[{row,column,role:image|text|empty|ellipsis}]`, and one
`cover` member per image slot. Track sizes and merges come from the saved
DrawingML table, not a separately guessed rectangle. Source content windows
and protected regions remain mandatory. Text and ellipses are independently
covered through content frames or bound mandatory quality mechanisms.

Unsupported merges/transforms and overlapping picture annotations require
source/planning work; they cannot silently pass as filled image cells.

## Executable physical port

Bind `kind: interface` through the existing semantic-composition source packet.
Keep its schema/source/canvas/evidence/view fields, `root`, complete distinct
`part_sets: [[actual owners of A],[actual owners of B]]`, their union `objects`,
`source_roles:[roleA,roleB]`, the program-derived `relationship`,
and independently observed `source_root_frame`.

`port{domain:[x,y,w,h],anchor:[x,y],tangent:[dx,dy]}` uses normalized source-root
coordinates. Actual ancestor rotation/flip/scale maps it to the saved world.
`limits{distance_px:[min,max],solid_width_px,anchor_error_px}` and
`threshold_basis` are frozen **before** drawing. Units are original canvas
pixels. Attached parts require min distance 0, max at most 1 pixel and positive
solid width; a failed repair cannot enlarge these limits.

The program separately captures actual native owners on black/white at at
least 4×, using the real saved-file renderer. It measures opaque cores
(backdrop response <= 2), a conservative Euclidean distance interval, connected
tangent width and the correct port anchor. Weak antialias halos, bbox overlap,
one contacting pixel or a distant contact cannot certify the port. Missing
capture, wrong parent or unsupported geometry stays failed/unmeasured. The
receipt records actual backend, sampling and error bound; an alternative host
does not become Office-equivalent.

An optional frozen `repair{operator:translate_second_part,max_shift_px,step_px}`
allows a finite program search (radius <= 8, step .25/.5/1 pixel). Cached matte
translations only propose a minimum displacement. New native save/render and
all applicable constraints must confirm it; prediction is never acceptance.

## Original spacing classification

Semantic role ownership is a source interpretation; contact versus separation
is computed. `source-spacing TASK discover|calibrate|report --out RESULT`
uses the same mandatory loop. `calibrate --request INPUT` accepts bounded
`entries[{target,original}]`; a target is an interface ID or an actual root's
named native-relation role pair. The original input has
`schema:original-spacing-1`, `source_hash`, an exact raw `source_view`,
`mask_origin:original_observed`, two same-canvas binary `masks[{path,sha256}]`
under `source/`, and `segmentation[{role,evidence,uncertain}]`. Segmentation
evidence describes original ownership, not a desired output relationship.
Candidate mattes, resampled masks, overlapping visible ownership, a missing
part and uncertain segmentation cannot classify a join. Desired relations,
distance thresholds and output actions are rejected as calibration inputs.

At the unchanged original 1px grid, EDT measures pixel-center distance `d`.
Two half-pixel diagonals give the conservative interval
`[max(0,d-sqrt(2)),d+sqrt(2)]`. The package fixes its classification threshold
at 2.5 source pixels: an upper bound at or below it, with a positive-width
four-connected contact containing both original roles, classifies `attached`;
a lower bound above it classifies `intentional_separation`. Intervals crossing
the threshold remain ambiguous. Face-adjacent source pixels give an upper
bound of 2.414px; a one-pixel blank strip deliberately remains unresolved.
This is a raster-observation policy, not recovery of the original vector
contour or a claim of perfect semantic segmentation.

The program derives attachment output distance `[0,.75]` and minimum solid
width `max(1, .5 * original_width_lower_bound)`; separation retains the
positive original distance interval. These intersect all already-frozen
output limits, never relax them. The actual saved renderer still must prove
the correct root, location, same-contact width and >=4x opaque-core distance.
New interface bindings may supply `original_spacing: ORIGINAL_INPUT` and
`relationship:auto`; the binder generates the relationship and distance/width
limits. A contradictory handwritten label is rejected. Existing interfaces
without calibration cannot pass or produce an automatic repair. Replacing
source masks cannot reverse a classified relation or loosen its bounds.
Old source readings remain history and receive no drawing-gain credit.

Original binding and finite repair identities canonicalize numeric spellings,
role-set order and tangent sign/magnitude. Direction identity uses a largest
absolute coordinate of one and a fixed 12-decimal dimensionless ratio; applying
it again is idempotent. This removes floating representation differences, not
source pixel errors. Renaming a contract or scaling its tangent cannot loosen
an existing source rule or obtain a fresh attempt budget.

`next` requests `source_spacing_source` for any missing/conflicting pair;
`submit` accepts segmentation entries and performs this calculation. The
finite solver chooses an admissible concrete translation from the measured
constraints. The agent supplies source understanding and interprets outcomes;
it does not direct pixel moves in natural language. Both semantic-composition
and whole-drawing coverage, including native attached-role relations, enforce
this original classification before accepting output measurements.

## Action, reflection and final acceptance

`execute-rules TASK REQUEST --out RESULT` requires
`expected_baseline_sha256`. The program examines **all** frozen frame and
interface findings and selects finite actionable repairs. There is no agent
whitelist of inspected objects. It preserves ungranted native fields/media,
records non-target checks, leaves unsupported/uncertain work in the same loop,
and saves an actual working candidate. Existing lock and local edit rules still
apply. It never awards final acceptance.

After actual rendering, use the ordinary packets for full checks, source
refinement, independent observation and bounded repair. Already satisfied
constraints cannot regress. Two ineffective attempts prune a branch; return
to the specific source/shape/renderer cause rather than widening a threshold.

The shared final gate reevaluates full coverage, source debt, actual render,
frames, composition, layout, native text/math and fonts. Claimed numeric part
minima are recomputed with dependency-bound caches. It writes an immutable
`Acceptance.json` basis binding original, actual artifacts, rules, observations
and executor implementation. `export`, helper `finalize --task TASK`,
`install-output --task TASK`, and visual-loop `finish` with `runtime_task` use
that same gate. `stage=accepted` or an auxiliary export alone cannot publish.
Keep diagnostic exports and incomplete working results explicitly pending.

## Original corrections and incomplete work

`amend-source-spec TASK REQUEST --out RESULT` continues a fully imported saved
task without rebuilding it. Bind `source_hash`, `expected_pptx_sha256`, an exact
raw `source_view{path,sha256,roi}`, and
`correction{prior_spec_hash,source_view_hash,kind,reason,specification}`. The
ordinary compiler validates layout review, every existing part/property and
all original metric limits. Additional visual parts must bind actual saved
owners in the same semantic component. Prior readings survive; no drawing
gain or observed/accepted status is awarded.

Root-reading corrections use `execution-coverage ... bind --request ...` with
`corrections[root]{kind:source_reading,prior_hash,reason,source_view,replaced_fields}`.
Every replaced field records `prior_value_hash`, concrete original evidence
and `cause:object_mismatch|topology_misreading|measurement_domain_mismatch`.
Keep original feature IDs, root/source identities and unchanged measurement
tolerances. A partial source crop cannot become the complete native group's
painted center. Unknown hardware names retain the observed geometry instead
of inventing anatomy. Native drawing bytes remain unchanged by a correction.

`render-working` uses the ordinary saved-file `tool_render` packet and actual
capability route. It can schedule missing complete-inventory captures on
identical PPT bytes; completed batches and prior receipts remain evidence.
`observe-rules` uses shared adoption gates and cumulative repair grants, with
only the current step's grants passed to native writers. Actual binary rule
gains are recorded independently of semantic acceptance. Deterministic rule
branches use the existing finite strategy mechanism: unchanged source/rules
and operator have a stable key, two ineffective observed attempts exhaust
that branch, and new filenames/revisions/prose do not reset it. Unknown work
continues in other branches; failed metrics cannot enlarge their limits.

Missing source declarations request source packets. Already-bound failed or
unmeasured rules create located ordinary issues rather than repeatedly asking
for the identical declaration. Original refinement can continue while a
rendered deterministic working candidate is pending; it preserves that actual
candidate and every prior target.

`audit-working TASK --out RESULT` measures **every** source quality unit on the
current actual saved render, then attempts all final gates. It preserves
`below_minimum`, `required_unmeasured`, missing-resource reasons and source
observations separately; numeric success does not manufacture semantic
observations. Final acceptance also recompiles every current original source
specification, reproduces authorized native aliases and compares all live
measurement definitions, including feature expectations, ROIs, owners,
protocols, masks and landmarks. Retaining the same IDs/thresholds alone cannot
admit stale definitions. Inherited target/property preservation is separate.

`export-review TASK --out NEW_DIRECTORY` creates an immutable
`WORKING_NOT_ACCEPTED` review bundle from that exact actual PPT, preview, PDF
when available, whole audit, blocked acceptance receipt and complete inventory.
It cannot set the task to accepted, install an accepted output or bypass the
formal export gate. The manifest states that quality remains pending. Use it
when delivering a concrete candidate for human review; continue unresolved
source/measurement/quality work in the same task.


## Canonical source reconciliation

Every official final gate calls the same `source_contract.reconcile`. It recompiles each complete original specification with the public source compiler, rederives native object bindings and compares the union of all fields and unit IDs. Unknown source/metric fields, duplicate metric IDs, nonfinite values, missing historical units and compiled binding drift fail. Source specifications additionally have independent content-addressed frozen records and an activation record that cannot be disabled in mutable state. Authorized original-only corrections create new records while preserving history; they never rewrite an old record.

Saved-native inventory creates missing independent obligations for every nonempty text owner, table cell and mathematical span. A whole panel cannot cover an unbound caption or cell. Discovery and repair packets list the actual missing owners; acceptance cannot omit them. Simple native mathematical runs carry span-location markers and are checked against the expected source AST by exact saved-run predicates; complex formulas use actual parsed OMML. The markers locate spans and are not source truth or an invented reverse-parsed AST.

Alternative-host owner observation batches preserve every ancestor transform and native drawing byte. The program verifies each requested owner page against an independently isolated native copy and the actually rendered PDF/PNG page. Black/white observations remain independent. Each complete owner is ingested before the next; later failures preserve the actual page render and verified partial records. Resume has a finite progress bound and refuses an unchanged pending request. A batched renderer is not evidence of Windows Office equivalence.
