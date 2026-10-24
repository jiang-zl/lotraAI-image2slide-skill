# Incident recovery and source review in product 1.37.5

This adds `source-review-1.37.5` for newly started tasks. Component workflow
1.35.2, design revision 8, line evidence policy 1.37.2, font workflow 1.37.4,
native Math policy 1.35.3 and runtime resources 1.14.0 remain distinct identifiers.
Old bound tasks keep their source/review policy. No state-file edits migrate them.
Retain original failures, doubts, budgets, native files and protected user fields.

## Recovery and current replies

`next` checks an existing native journal before offering a cached font/build
packet. Complete its actual pending stage through the returned recovery packet.
A journal's own not-yet-saved font dependency may continue normally; it cannot
start a second transaction. Saved font publication and waiting actual rendering
remain explicit dependencies. Do not delete pending state or bypass the journal.
After an incomplete attempt is explicitly retained for redecision, its matching
font dependency and structural grant are archived in that journal and stop
executing; independent pending work stays intact. Current recovery packets bind
the current implementation and revision. A scoped `text_body` grant installs its
authorized paragraph/run topology before accompanying leaf style edits; a font
leaf alone still cannot change topology or authorize whole-owner replacement.

Use `submission_template` and `submission_command` from the current packet.
Local replies put `operation` at the outer level; older matching inner/outer
aliases remain readable. Conflicting aliases reject before dispatch. Chunked
history behaves as the same logical list after reload, including reverse lookup
for idempotent receipts. Do not expand the entire state to work around a receipt.
New-policy source/local/recovery packets also link this reference and the current
font-preparation contract, so a changed family hint is not mistaken for a physical
font revision. Read those managed references when the corresponding decision is
needed; instructions and source data remain separately hash-bound.

## Original observation before construction

Observe the original semantic hierarchy, including containers and every text
string, surface and connection. Provide `layout_review` for `alignment`,
`containment` and `connections`: `decision` is `declared`,
`intentional_irregular` or `not_applicable`, with located `source_evidence`.
Declared relations need actual source relations/hierarchy/connection features.
An empty relation list alone does not establish that layout checks passed.

Each surface/silhouette/color-region feature declares original `form`:
`rect`, `round_rect`, `ellipse`, `freeform`, `perspective` or `texture`.
Surface units include `appearance_review` for fill, depth and corners. Decisions
are `present`, `absent`, `uncertain` or `not_applicable`, with source evidence;
visible depth refers to its owned feature IDs. Do not infer a shadow or bevel
merely because a preset supports one. Uncertain material stays a visual obligation.

Every text feature includes `text_appearance`: original `colours`,
`colour_tolerance` in (0,.25], `isolation`, `source_evidence`, and positive
source-pixel `limits` for width, height, baseline and spacing (at most 8 each).
Baseline here means observed ink bottom, without inferring a typographic baseline.
Optional `spacing_axis` is horizontal or vertical. Choose a whole-string source
window that isolates its ink from same-colour borders and neighbors. Missing or
ambiguous extraction requires an original/measurement decision, never PASS.

The declared palette and its tolerance select foreground for geometric probes.
Finding supported pixels does not establish complete text-ink coverage or colour
agreement. During source observation and first-render review, independently inspect
the original ink and current actual painting, preserving each logical colour and
emphasis span. Near-black source text and dark-blue native text can both satisfy
one broad extraction tolerance; a dimension PASS cannot settle that difference.
Retain a located colour doubt even after geometry closes. Correct an erroneous
source palette only through the prior-hash source decision and explicit rebind;
do not widen the tolerance to conceal it. A sampled dark-core median is a
diagnostic, not a universal replacement colour for anti-aliased or mixed-colour
text. Preserve the raw crop, uncertainty, original probes and unresolved parts.

Raw blank projection bands can occur inside a glyph. They are not automatically
inter-character tracking. The default raw-band comparison remains available and
its failures stay retained. After independently inspecting the original, optional
`text_appearance.spacing_groups` qualifies a distinct grouped measurement. It
contains `logical_text`, `observer` (`host_model` or `human`), `source_evidence`
and 2..256 `groups`. Each group has complete consecutive `span:[start,end]`,
an ordered disjoint original `roi` inside the text feature and `source_evidence`.
Every original ink pixel must belong to exactly one group; no stroke/noise removal
is permitted. This is an original source correction when added to an existing
observation, with the same prior hashes and unchanged width/height/baseline/spacing
limits. It is never inferred from a preferred candidate.

Actual groups use unique observed whitespace near the frozen source boundaries,
within the existing position limit. Competing boundaries require measurement
diagnosis; missing separation fails. The image is not registered or translated.
Both source and render retain raw bands alongside grouped spacing. Every group
also checks width, height, ink bottom and axis position against the same frozen
limits. Missing glyphs, extra paint, ambiguous ownership and incomplete coverage
cannot be hidden by a whole-string bbox or group crop. Semantic glyph appearance,
exact native characters and complete visual review remain separate obligations.

Sealing checks original route/colour support and offers located boundary,
short-line and text diagnostics. `original_diagnostics` references the full
hash-bound report and source overlay. Axis/containment/port candidates are hints;
confirm their semantics or retain observed intentional offsets. Diagnostics cannot
alter bboxes, center ports, regularize spacing, broaden limits or rewrite the source.
Correct a source observation through the current prior-hash correction packet.
Retain original facts and valid probes, and rebind all actual dependents.

## Native text, materials and fonts

Compatible font family/name IDs 1/2 define PowerPoint typeface/style linkage;
typographic IDs 16/17 remain separate metadata. Physical face hash/index and
regular/bold/italic/boldItalic embedding slots must remain unique per family.
A heavy regular face need not receive a second native bold. Mixed-script physical
style splits preserve logical source runs, literal characters and colour/emphasis
intervals; every saved physical run remains bound to its original location.

Text may declare `logical_text` and `text_layout` with source evidence,
`direction` (`horizontal`, `east_asian_vertical`, `vertical`, `vertical_270`)
and explicit logical-character `soft_breaks` offsets. Only those exact native
paragraph boundaries normalize. Original hard breaks, lists, spaces and literals
stay authoritative. Prefer one editable East Asian vertical text body when shown
by the original. Check actual painting on the selected backend.

Source-supported `shadow_effect` contains RGB colour, normalized opacity,
`blur_pt` (0..36), `offset_pt` (two coordinates in -72..72), and optional
`rotate_with_shape`. `soft_edge_pt` is 0..6. These are editable DrawingML effects;
saved XML checks and actual appearance checks are separate. Existing native
gradient stops, directions, radii and surface constructions still apply.

## First actual render and short connections

Subprocess UNO rendering binds a finite completion acknowledgement to its own
job, fixed client, immutable inputs and exact output hashes. The controller
verifies it before and after stopping its own processes. An operation may finish
before a synchronous UNO close returns. Missing or stale acknowledgements,
modified output/input bytes, pre-existing outputs and actual timeout stay FAIL.
Do not adopt artifacts from an old failed request merely because a PDF exists.
Final LibreOffice delivery keeps its actual save of an owned copy and reopens
that saved PPTX through the same declared project editor and completion protocol.
Its renderer identity must match the configured executable. Reopen PDFs retain
their exact input/hash ownership when audit evidence moves; the canonical PPTX
is never roundtripped. Failed saves, reopen failures and stale outputs stay FAIL.
For project-bound jobs, save/reopen and editor profiles use the prepared
`.lotraAI-build/editor-profiles` root instead of nesting application internals
under a long chosen output path. Actual saved/PDF outputs still exercise that
chosen destination. A redirected or unprepared private root is rejected; early
server exit is retained immediately rather than disguised as a connection wait.

New review-policy tasks render their first saved native result before layout.
Native consistency can be QUALIFIED while local appearance is pending. The
shared action generator then returns `review_local`; this is the ordinary
`component_local_work` reply, with an evidence reference bound to current source,
PPTX, preview, component, feature basis, observer and every required feature.
Read the original and actual crop. A generated plan description cannot supply
the visual observation. Current text-ink probes and rendered lines execute too.
Include original-to-render colour and emphasis in the per-feature observation,
alongside shape, missing/extra details and text geometry. A mask-support or
geometry result alone cannot supply the appearance verdict.
Reuse and final layout wait for this closure. Unrelated retained component bests
are preserved; own measurement/placement changes invalidate only their dependents.
This local review does not run the whole-page visual audit after every edit.

Marker observation windows and object foreground ownership are distinct.
Disconnected neighboring text cannot become marker paint. Enlarged, missing,
translated, hollow or extra connected paint remains checked; distance witnesses
retain source coordinates. A close junction or absent isolated shaft uses a
complete explicitly declared source graph joint-paint producer when qualified.
Every short arm remains present in that comparison. Missing peers, mixed
unresolved support or an attached undeclared shape require a measurement/source
decision. A joint envelope is not reported as an isolated shaft-width chord.
Current line route, marker, topology and saved native constraints remain mandatory.

The original branch-plan report keeps every feature/segment ID. A native bent
connector is a two-terminal polyline. Bus branches require explicit separate
native owners or a properly bound source graph; no third terminal is invented.
Crossings do not authorize shared-edge reuse. No automatic snapping is performed.

## Explicit photographed-slide target

Before start, identify the semantic content contour. A source-bound
`semantic_region` plan crops its integer bounding envelope without interpolation,
deskew or invented aspect ratio. Preserve inside/outside scope and the raw photo;
an ambiguous contour uses the complete `source_projection`, the program default.
Whole-photo reconstruction remains a valid fallback. Read
[semantic target and typography](typography-before-render-v1375.md) for the plan
and mandatory unit/half-point/source-size checks before rendering.
Optional `--target-plan JSON` separately selects
`capture-target-1.37.5` with the exact raw source hash and `kind:slide_surface`.
Provide TL/TR/BR/BL source corners, explicit output size, original-metadata or
user authority for aspect ratio, bounded raw uncertainty, original observations
and an authorization file reference. The quadrilateral alone does not recover
the original slide ratio. Unsupported super-resolution is rejected.

When the user delegates the target decision, `user_authority` may authorize an
estimated working plane. Preserve that actual delegation and source-bound
reasoning in the authority file; never relabel an inferred ratio as supplied
original metadata. Use multiple independent source observations, retain the
assumptions/uncertainty and check held-out locations. A quadrilateral or a
customary 16:9 preset alone is insufficient evidence. The host model interprets
the original; programs retain and verify the exact mapping and source bytes.

The task preserves raw original bytes and the authorization, derived target,
forward/inverse homography and propagated uncertainty. All normal coordinates
refer to that explicit target. `reconstruction_target` is a managed immutable
reference; the final gate independently recomputes mapping and derived pixels.
It never supplies artwork acceptance or relaxes source quality limits. Partial
PPT input cannot be silently moved to a rectified coordinate domain. Existing
tasks require a separate explicit target decision; their old evidence is retained.

Parts and local appearance precede layout, one deferred font review, whole-page
original-to-output omission review, independent final audit, formal export and
exact-byte delivery-check. Exclusions, old receipts and synthetic fixtures do
not accept the current external artwork.

If a focused source correction discovers a missing obligation in the previously
sealed observation outside that component, its rejected proposal is retained as
a diagnostic and is not adopted. The existing original-decision phase then
issues `component_contract_source / source_features` with
`spatial_source_decision.kind:source_preflight`, an exact `prior_observation`,
the current original-only failure resource and its affected consumers. Follow
that packet before retrying the original focused correction. This uses the
existing finite source-read budgets; it does not reset them or authorize native
writes. Existing tasks without `source-review-1.37.5` retain their old policy.

Submit a complete retained `observation`, `prior_observation`, `revision_reason`
and `corrections` entries such as `units/ID`, `features/ID` or
`layout_review/DOMAIN`, each with `prior_hash`, reason and located source_evidence.
Only diagnosed material domains, diagnosed features/layout domains and explicit
new features of the diagnosed unit may change. Keep every unrelated unit,
feature, spatial fact and quality bound. Missing material applicability belongs
in the original unit's `appearance_review`; observed depth must name its actual
source feature IDs. All original checks must pass before adoption. The original
observation and failures remain in history, then the ordinary explicit rebind
invalidates actual consumers before construction or acceptance resumes.

The native renderer verifies complete serialized SFNT/EOT header checksums.
For ordinary text, a private import copy may resolve localized compatible name-ID-1
aliases of the exact embedded physical face against the actual editor font inventory.
It preserves all non-font XML bytes and canonical PPTX bytes, never merges
typographic families or substitutes another face. Real text portions, nested shapes
and every table cell are inspected; missing native aliases or absent bound PDF
font families block rendering. PDF family observations do not replace per-feature
appearance, font identity, Math, native edit or whole-artwork acceptance.

Extended font comparison retains the prior physical face as evidence. That
comparison-only baseline cannot suppress a currently scoped, explicitly
source-supported synthetic choice; current binding eligibility stays strict.

The declared native Math renderer resolves only a namespace-bound, supported
a14 OMML primary compatibility branch in its private import copy. Genuine
native Math object coverage is checked; a raster fallback is never Math PASS.
Unsupported/unbound/ambiguous or fallback-only Math branches need a decision.
The owned application-saved-copy reopen observes imported native Math styles
without claiming original style retention. Normal source rendering retains its
explicit-style requirement. Canonical PPTX and raw saved-copy bytes stay intact.
The saved-copy adapter paints the imported Math model at its intrinsic visual
area in the private document to avoid stretching a formula into the saved text
box. It records both extents and does not claim saved source geometry, size or
font retention. Actual native object coverage is not whole-artwork acceptance.

### Source size recovery before native construction

If physical-font size preflight fails after all font bindings are staged,
`next` returns `typography_source` instead of throwing an unreachable error.
The hash-bound packet retains the failed preflight, pending Scene and at most
four current font requests. Use its ordinary `submit` template and return
`typography_changes:[{request_id,samples:[{text,roi,domain:task_source}],source_evidence}]`.
Each request accepts 1..12 independently observed original glyphs or continuous
single-line phrases of at most 32 characters, inside its frozen owner and script.
These size samples are separate from the font-family gallery's single-character
samples. Confirm any cached OCR locator on the original; never fit normalized
OCR pixels. Keep all font-family choices and their staged physical bindings.

The program records source samples and uses the existing finite physical-size
model. It adopts only a half-point estimate in the common supported interval of
every applicable script at that native location. An already supported estimate
is retained; otherwise finite fit errors rank supported alternatives. Ambiguous
identification and its entire interval remain explicit, while a supported
construction estimate may proceed to mandatory actual-render qualification.
Unsupported or contradictory fits remain failures. Sampling cannot change text, font identity,
colour, alignment, geometry, measurement plane, physical canvas or quality
bounds. Each request retains at most three submitted sample revisions, without
resetting task history or budgets. A native repair still needs its original
field grant; already saved native work cannot be silently rewritten. All
source/native/actual-render and final gates remain mandatory.
