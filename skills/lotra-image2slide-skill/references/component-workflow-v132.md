# Component workflow v1.32.0, revision 8

Use the prepared project launcher. The ordinary route is original inventory →
typed contract → deterministic construction or bounded fitting → assembly →
base mother → optional derived variant → instances → layout → final review →
export. Office open/edit/save-reopen behavior is excluded.

Revision 8 was implemented without tests, validation runs, reconstruction or
cost/effect measurement at the user's instruction. Earlier release passes do
not qualify this revision or accept the user's original artwork.

## Protocol and construction

bind/migrate accepts source_scene, authority, contract and revision_reason.
The protocol is component-protocol-1.32.0, design_revision 8. Preserve original
inventory, independent source facts, owner mapping, user locks and old failures.
Each native owner has one component. Assemblies own roots; parts own leaves.

A component declares id, route, owners, source_units, source_evidence,
source_refs, model, parent, parameters, metrics and relationships as applicable.
fixed_parameters includes deterministic paths, Beziers, connectors, tables and
declared photo resources as well as text, shapes and genuine native equations.
Constructor consistency is consumed once and retained by signatures; fixed
color/fill/borders have no repeated pixel targets. Photos cannot replace icons.

constructor_registry routes original-only proposals through primitive_source_fit,
source_preset_fit, source_detail_fit, source_fit, source_feature_functions or
semantic_curves. source_prepare consumes a source_request and returns a located
proposal for binding, never qualification. Unknown models require a decision.
Native curve construction uses the existing semantic-curves compiler.

## Targets and bounded search

Each metric declares role, direction, unit, applicability, normalization_scale,
and threshold or source_calibration. The latter selects a predeclared type/unit
model: delta=max(lower,a*u+b*q); raw above upper requires a source decision.
Source facts can supply located intervals in matching units. q is composed of
EMU rounding, declared curve precision and applicable sampling resolution.
Initial limits are engineering policy, not statistical calibration. A failed
candidate never changes them.

A tunable parameter specifies source bounds, initial/minimum step and literal
native binding. parameter_metric_map associates it with target dimensions.
The registry supplies associations only for supported geometric bindings and
metrics; other missing associations require a model decision.

Search prioritizes the largest necessary violation, source analytic values,
then probes at most six related variables and selects at most three using
normalized sensitivity. Coupled variables permit a damped bounded least-squares
step. Two consistent improving directions enlarge steps by at most 1.25, capped
at a quarter of the source interval. No improvement halves to source precision.
Ordering is hard constraints, maximum violation, total violation, ordered errors.
The first adequate result exits.

Search-state checkpoints retain evaluated points and rounds: 96 evaluations,
24 rounds per source/model, at most three source-supported models per unchanged
component source region. Rebinding does not reset consumed model choices.
A numeric result is committed once through the native journal. Actual display
disagreement requires model/measurement diagnosis rather than repeated search.

## Shared actions

next and advance share component_actions.available and component_search.rank_actions.
Recovery precedes measurement/source decisions, missing structure, fitting,
assembly, instances, layout and final. Mother/child readiness, source facts,
allowed writes, unresolved dependencies and user locks determine eligibility.
advance can progress independent executable components during another decision.

Within stage/criticality/risk, positive valid probes precede unknown probes,
then known non-improving probes. Ties use source proximity, confirmed reuse
divided by static work, and stable id. Direct field facts have proximity 0,
other source references 1. Probe evidence must match the current signature.
No measured time, history gain/cost, provider-token or effect statistics drive
this workflow. Numeric state remains solely for solving and recovery.

Static work: fixed/instance 1; relations 1+ceil(n/8); fitting
1+ceil(active variables/3). advance defaults to four actions, maximum eight,
stopping at host/display/recovery boundaries. It never runs the whole audit.

## Mothers, variants and style

Parts and internal relations qualify the base mother. A variant depends on
that base and source overrides; the base never depends on variants. Instances
reference their base, optional variant and source-supported pose.

variant declares id, mother, source_evidence and overrides[{owner,field,value}].
Only existing fields change in a private native donor; the base and unrelated
native package resources are preserved. Scientific topology and external-port
changes require a new mother. scale_policy is scale_with_geometry or
preserve_absolute_style. Nonuniform scale/reflection need transform_policy
source evidence; nonuniform style scaling needs explicit style_scale. Shear
is not silently approximated. Expectations bind base, overrides, style and pose.
External connections continue through the instance's mapped target ports.

## Dependencies, state and packets

component_dependencies catalogs route/model/type consumers. Their keys contain
only relevant source regions, models, code and policy entries. Moving an
instance retains the base. Changing a consumer marks its results and final
state dirty, without triggering final review.

Task.json and state/index.sqlite point to immutable resources/state branches.
state.json becomes a compatibility pointer. Lazy dictionaries/lists load only
accessed branches; old monolithic bytes are retained under legacy/.
Component states/contracts, source units and owner mappings have indexed
lookups. Installation alone does not migrate or execute an existing task.

Component packet bodies are capped at 8000 characters and preserve complete
executable references and existing bounded detail selectors. Compact output
cannot truncate source obligations, write authority or remaining work.

## Saved-work continuation and retained legacy rollback

Native transactions follow PLANNED → STAGED → NATIVE_SAVED → DISPLAY_PENDING →
LOCAL_RESULT_READY → ADOPTED → CLOSED. Fixed work can skip the display stage.
Files are privately staged and renamed individually; Ready.json is written
last with the complete candidate artifact manifest and planned Scene.
SQLite commits indexed roots with revision compare-and-swap. File renames
and SQLite are not represented as one cross-resource atomic operation.

recover reconciles registered Ready manifests, retaining the exact saved
candidate when only display/adoption remains. Unregistered partial files are
never promoted. Changed source/base or native fields return a located conflict
and preserve both versions. Local results discharge only their own obligations;
render failure does not reconstruct the icon or erase numeric/source work.

The pre-existing rollback operation is retained compatibility outside this
revision's image/one-shot-input work. It takes a transaction reference and compares current affected fields
against that transaction's after values before reversing its before/after
patches. Conflicting fields and user locks stop that reversal. Unrelated
objects and later edits survive; an old whole PPT never replaces the current one.

## Operations and final review

component-workflow TASK OP --request REQUEST.json --out RESULT.json supports
bind, migrate, build, source_prepare, fit, instantiate, evaluate, qualify,
layout, status, source_or_measurement_decision, repair, edit, lock, unlock,
commit, recover, rollback, advance, review, final and export.
Ordinary next/submit and quality-loop use the same implementation.
context-control TASK resume returns the component state/transaction boundary.

Complete all parts, assemblies, instances and declared relations, then layout.
Review the current actual full output for semantic completeness, geometry,
typography, relations, appearance and overall clarity. Final problems form a
repair batch; no whole review runs after each local edit. Export only
Final_editable.pptx and Report.md with the actual acceptance scope.


## Revision 8 ordinary packet protocol

These interfaces are implementation contracts; revision 8 has not been run or
validated. Keep semantic version 1.32.0 and use design_revision 8 for a new or
explicitly revised contract. Retain earlier contracts and ledgers.

- `component_recovery_work`: submit `component_request:{}` to recover the
  registered transaction. Recovery precedes initial construction, even without
  a candidate. Interrupted build attempts are retained, with at most three
  automatically allocated attempt folders; exhaustion requires inspection.
- `component_local_work`: use `submit_operation` and the explicit
  `component_batch` from this packet. Requests name `component` or `components`.
  Batches may include only the listed components, must include the packet target,
  and apply to fit/commit/instantiate, or the complete approved edit batch when repair_atomic=true.
  Atomic edit batches may include their unqualified assembly root and children;
  child-first qualification resumes after the one saved repair. Independent numeric work is gathered
  before one native commit; instance copies have one journal and final render.
- `source_or_measurement_decision`: require `component`, `source_hash`,
  `pptx_hash`, `revision_reason`, `authority:{path,sha256}` and either a full
  `replacement_component` or `replacements:[full component definitions]`.
  Replacements are limited to the selected component's subtree; new descendants
  need explicit parents. Optional `remove_components`, `relations` and
  `source_inventory` may only change that subtree's source facts. Optional
  `source_scene:{path,sha256}` revises the source contract; optional
  `apply_scene:{path,sha256}` explicitly proposes the actual native correction.
  Optional rebuild_owners explicitly regenerates granted owners whose native body
  differs although the Scene fields are already correct. Native preflight and
  normalized source-contract checks precede activation. Apply Scene, whole-owner
  grants and rebuild intent are saved with the new contract so next can resume.
  Unrelated objects and existing protections are retained. This is a decision, not a pass.
- `component_repair_work`: final failures are first `PLAN_REQUIRED`. Submit
  current source/pptx hashes and `items:[{component,failures,reason,fields}]`;
  fields are `{owner,field:[literal path segments]}`. Every failure must be
  covered; each field must belong to its component. Empty field path grants that
  whole owner, never an unrelated owner. User locks still win. The next local
  packet uses `edit`, with a hash-bound proposed `scene`; optional
  `rebuild_owners` requires whole-owner repair grants for native resource repair.
  Local readiness and layout must be restored before another complete review.
- Historical compatibility only (outside the revision 8 image/import scope):
  `component_user_mapping`: normal `sync TASK EDITED.pptx` adopts the file and
  records component field locks. Additions, removals and aliases require an
  explicit revised bind request with `pptx_hash`, `authority_kind:user_intent`,
  source_scene, contract, authority and revision_reason. The revised owner
  inventory must match the adopted native file. Existing field locks, orphan
  locks and prior native files survive; quality is still pending.
- Explicit `lock`/`unlock` commands require current `pptx_hash`, `authority:user`,
  retained `evidence`, a reason and `locks:[{component,owner,field}]`. An inferred
  model repair cannot supply user authorization or discard an existing lock.
- Font-delivery work remains the normal `tool_font_embedding` packet. Its
  provider receipt binds an immutable input and a separate output; only font
  resources transfer to a new private candidate. Native/display recovery uses
  that candidate rather than rebuilding the icon.

For mother qualification, `required_relations` may contain only internal
relations among its descendants. An instance consumes its own `instance_of`
relation; external connections/spacing belong to layout. Supplying cross-phase
relations is rejected at bind, rather than creating a hidden prerequisite loop.

Source/measurement decisions, component mutations and rendering have independent
boundaries. Public requests cannot contain private `_transaction`, `_candidate`
or `_folder` fields. Those objects are created only by the journal/batch code.

## Measurement, budget and dependency boundaries

Besides generic appearance/boundary metrics, geometric producers are registered
as keypoint_distance, endpoint_distance, centerline_distance, curve_distance
and line_width_error. Their metric definitions require unit `source_px` and a
measurement object such as:

```json
{
  "adapter": "endpoint_distance",
  "coordinate_space": "component_roi",
  "window": [0, 0, 60, 40],
  "source_points": [[5.5, 20.5], [54.5, 20.5]],
  "expected_count": 2,
  "statistic": "max",
  "foreground": {"mode": "dark", "threshold": 0.4},
  "source_evidence": "Replace this example with independently observed original endpoints"
}
```

All coordinates/windows/selectors come from the unchanged original, before
candidate observation. Color mode uses a frozen normalized RGB and distance
threshold. Line-width measurement supplies `source_width` instead of points.
Unsupported producers fail during bind; missing observed features stay invalid.
The same producer consumes cheap previews and saved actual render ROIs. It does
not align a candidate to hide source placement errors. Pixel/skeleton resolution
remains part of the explicitly chosen uncertainty policy.

The 96-evaluation/24-round budget is persisted separately from search checkpoints.
Changing initial values, targets or implementation does not reset that same
region/model budget. A measurement attempt reserves budget before evaluation.
Search checkpoints preserve steps, stability and exhausted variables in addition
to sampled values/rounds. Actual current numeric probes feed the shared action
ranker; they are not measured cost/effect statistics or provider-token telemetry.

Qualification dependencies include the real protocol, qualification and schema
consumers. Search and local qualification use the same contract-frozen policy;
changing installed defaults does not silently rewrite earlier source targets.
Focused contract/source-unit/native-owner indexes are namespaced by contract
hash and consumed by ordinary operations. Global inventory/signature/final
operations still inspect the required full object set; no measured speedup is
claimed. Model/source changes propagate through assemblies and instances while
page pose remains a separate facet.

Trace-generated tone children belong to their source trace owner. They are
included in native ownership/signatures and use group transforms. An SVG embedded
as a picture is not supported as a deterministic editable native component;
decompose it into native shapes/paths/Beziers before binding. This boundary is
enforced by the constructor registry and fixed-type protocol.


## Revision 8 integrated closure

Read [Chinese/English font collections](font-collections-v132.md) for mandatory
preparation, script-specific binding, program ranking and the one deferred
font-review packet. The catalog policy is a distributed asset; real common
font files are retained in each project's private runtime archive before use.

Shared `component_fields` paths govern locks, grants, transaction diffs and
rollback. Fixed-length arrays use stable indices such as `["bbox",0]`; changed
topologies remain atomic. The typed native planner uses leaf edits, table cells,
group frames, scoped media and explicit subtree replacement. A whole subtree
requires all semantic descendants; generated trace layers follow exact compiler
ownership. It cannot silently import unrelated media or capture another owner.

Source decisions retain both removed old owners and incoming owners in a
contract-bound structural grant. The submitted decided Scene is retained before
apply. Final/layout repair plans cover located failures with distinct component
items; narrow grants are consumed after the journaled save. An independent
repair may retain another field grant only when its original native owner,
source and component row remain unchanged. User locks are canonicalized by
owner/field; moved orphan locks are transferred rather than copied, and explicit
user unlock removes all copies and retains its evidence/history.

The transaction persists intended statuses, grant consumption and font-review
completion before Ready. Recovery idempotently restores those transitions,
including numeric and instance confirmation states. Interrupted complete
preimages can be adopted by their content identity; incomplete copies are
retained under distinct names. Exhausted native/provider attempts expose
inspection/source-decision actions rather than resetting budgets or repeatedly
writing the same partial path. A retained failed candidate is not qualified.

`next` and `advance` use the same component action generator. Layout failure
queues a scoped repair plan. After current final visual PASS, normal `next`
issues `component_final_audit`; submitting it runs final audit and acceptance.
Font review is required in the final route, including direct final entrypoints.
No complete-page audit occurs during numeric, constructor or instance updates.

Consumer identities include actual helper modules, schema, frozen policy and
renderer environment where consumed. Renderer changes discard old display
evidence and final acceptance while retaining fixed constructor facts. Current
probes bind their source region, numeric model, measurements, implementation
and current signature. A stale probe cannot influence action ranking. Focused
contract/source-unit/native-owner indexes have actual consumers; graph-wide
dependency work may still scan the contract, without a speed-up claim.

Search reservations remain persistent across initial values and parameter/code
revisions within the same source-region/model budget. A completed valid passing
checkpoint is recovered before the no-new-measurement budget gate. Mutable
budget paths are not presented as immutable resource hashes. Only a current
fit basis and native signature may be committed.

Keypoint distance requires named corner/intersection/endpoint locators and
one-to-one corresponding detections. A nearby boundary pixel is not a keypoint.
Endpoint distance uses one-to-one assignment. Line width compares original and
candidate pixels with the same pixel-cell normal-chord estimator; it does not
compare `2*EDT` with an unrelated manually measured width. Missing/ambiguous
features invalidate a measurement rather than passing it. These producers run
through both the numeric surrogate and actual saved-render measurement path.

Revision 8 is source implementation, source installation and packaging only.
Tests, syntax/import/CLI checks, runtime validation, reconstruction and effect
measurements were deliberately not run. Earlier receipts do not qualify it.


## Revision 8 scope and normal partial-PPT input

Use start IMAGE --pptx PARTIAL.pptx with the prepared project launcher. The image
remains the source authority. Before binding, read the uploaded slide inventory;
use its exact logical owner names and target_width_inches in source_scene, and
include all missing image parts and their intended relations. The build packet
uses component_import.adopt through the ordinary constructor. adopt-existing
also delegates to this same component route. No legacy analysis object is needed.

Input is one native slide. Unknown owner mappings require correction of the
source contract before adoption; no names or source ownership are guessed.
Native slide dimensions must match the image canvas and target width before
adoption. A new group can wrap declared contiguous flat siblings in their
existing parent; arbitrary regrouping of existing nested groups is outside this input route.
Existing nontext native bodies are retained. Source-bound text/table/formula
owners are normalized once, preserving actual input positions and native IDs;
missing parts and explicit grouping are constructed on the imported baseline.
The pending completion Scene is persisted before construction and replayed by
the next build packet or existing native transaction recovery. Import does not
inherit source-quality approval. Every part then uses the same qualification,
layout, font review, final visual and export path as an image-only task.
advance stops at a pending import completion instead of measuring unfinished input.

Endpoint counts must equal the entire independent source endpoint set, and
both sides of assignment must be exhausted. Probe ranking uses the currently
observed native signature; a native body change discards old probes. Table
consumers include font-contract and embedding code identities. JSON null remains
a present value in field differences. General structural undo is not expanded.

Only the five necessary groups are in scope: font normalization; final font
closure; atomic icon repair; small metric/dependency guards; reconstruction
preflight and saved-work continuation. Existing user-edit compatibility is
retained without developing monitoring, fine-grained locks or universal undo.


## Revision 8 consistent input and measurement contracts

The semantic version remains 1.32.0. New/rebound source contracts use internal
design_revision 8; next/build/advance request migration of older source plans.
Retain old native work, source plans, search budgets and resources during migration.

1. `native_input.scene_dimensions` defines the rounded EMU dimensions used by
   construction, source precision calibration and import. Import and native
   merge both compare only positive cx/cy within one EMU. The baseline's
   presentation size-classification/type attribute is preserved.
2. `tables.normalize_scene` supplies the same empty cell-style matrix before
   source freeze, construction and font compilation. Source comparisons and
   source font hydration use the same table normalization. Font requests are
   read-only; they do not add defaults to the input Scene as a side effect.
3. `component_variants.variant_scene` is shared by source preflight and the
   private donor. A literal or bold/italic override must produce the target's
   exact location/role/literal/style requests. Before building the donor,
   `component_font_instances.bind_variant_scene` rekeys those already bound
   target resources into the private mother. It does not select a new family.
   The real mother remains unchanged; final instances keep their own source
   font intent and the one deferred font review remains required.
4. Measurement signatures include intrinsic data plus native page placement,
   parent/assembly context and pose. Refresh, action ranking, fit basis,
   checkpoints, immediate probes and numeric commit use this same signature.
   An obsolete numeric result is returned to local recheck. Search budgets
   remain keyed by source region/model/adapter/bindings, independently of the
   new measurement context. The existing save journal retains the actual
   numeric result candidate, so an unchanged committed model discrepancy can
   still be diagnosed without replaying the same search.
5. Partial-input text/table/equation owners keep uploaded x/y but use frozen
   source width/height. Source row heights and column widths therefore stay
   consistent with the source table box. IDs and existing nontext bodies are
   retained. Layout handles placement after component construction.
6. The sole active slide is resolved using sldId/r:id and the presentation
   relationship; its part need not be named slide1.xml. A private uploaded.pptx
   preimage is retained, and drawing.pptx normalizes that active part and its
   relationships/content-type entry before the existing single-slide pipeline.
   A conflicting unrelated canonical slide1 part requires a clean one-slide
   input, with a located error before adoption. This is not a multi-page editor.

Pending font bindings and import completion continue through the existing
constructor and native journal. Ready records and post-save transitions precede
qualification. Parts, mothers, instances and layout precede one font review;
affected local qualifications/layout are restored before whole visual review,
final audit and export. Local changes do not trigger a whole-page audit.

This revision was implemented and reviewed by reading actual source call chains.
Tests, syntax/import/CLI checks, runtime validation, reconstruction, rendering
and performance/effect measurements were not run at the user's request.
