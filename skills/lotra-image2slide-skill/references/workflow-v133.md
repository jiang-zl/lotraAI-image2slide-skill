# v1.33 normal workflow and data contracts

This extends component-protocol-1.32.0 design_revision 8 with
`workflow_version: "1.33.0"`. The old schema identifier is a compatibility
identifier, not the release version. New bind defaults to 1.33; an already
bound legacy contract retains its missing workflow_version until the host
explicitly submits a revised contract with 1.33 and a revision_reason.
Continue using the component-workflow-v132.md ownership/relations/phase rules.
Every assembly also freezes semantic_class and its source-observed view; bind
requires these fields so an ordinary new task can populate the private lifecycle.

## Original observation and early reuse

If the project private catalog has eligible cases, next emits
component_contract_source target knowledge_outline. Submit component_request
with source_hash and semantic_outline. Each outline row has id (source unit),
semantic_class, view, source_evidence, optional required_parts or part_counts,
topology, style_tags and edit_operations. It does not contain detailed geometry.
Program groups repeated queries, returns a hash-bound task menu and proceeds to
the ordinary source contract. An empty catalog adds no host round trip.

Read the menu only as needed with existing task selectors. Candidates contain
id, parts, limitations, editing operations and recipe reference; no full recipe.
The host may select none. A selected binding on the bind request contains
knowledge_id, source_unit, instance_id, current bbox, source_evidence, optional
parent, owner_map and per-owner style_overrides (fill/stroke/line_width/rotation).
Programs verify the menu/current catalog and instantiate registered data-only
native_template entities before Scene validation. Do not include the generated
objects twice in source_scene. Include their actual generated owner names in
the complete component ownership contract, including imported partial-PPT names
through explicit owner_map. Structural adaptations use a current revised Scene.
Old qualifications never qualify current owners; parts/mother/current render
must pass normal checks. Current source decisions override candidate style.

## Functional curve contract

Every new scientific/observed/signal curve uses content.function_spec. Declared
straight segments/corners and analytic radio/ellipse arcs keep their native
constructors. A function_spec contains samples_ref (a task JSON resource),
source_evidence, semantics, source_uncertainty_px,
critical_feature_separation_px, optional representation_precision_px (default
0.05), constraints, and source-observed cycles/damping/transition_t/pulses where
applicable. Samples contain source_hash, coordinate_space source_px, and ordered
points. Programs may extract points; the host should not transcribe dense pixels.
`source_curves.observed_curve(...,task=TASK,function_spec=SPEC)` extracts a
color-isolated x-valued waveform and writes that evidence automatically. Dark,
overlapped or non-single-valued curves require independently isolated ordered
source samples; do not infer a missing waveform from a random signal.

Supported semantics/families:

| Semantics | Finite families in order |
|---|---|
| periodic | finite Fourier, trend + envelope harmonics, piecewise cubic |
| damped | damped harmonics, trend + envelope harmonics, piecewise cubic |
| monotone | PCHIP, piecewise cubic |
| pulse / step | source-located pulse / segmented step, piecewise cubic |
| unknown | low-degree piecewise cubic, parametric cubic |
| loop | ordered parametric cubic |

Fourier is a representation, not proof of a physical signal law. `cycles` is a
source-observed relative count, never invented Hz. Each fitted family has finite
complexities 2/4/8/16/32 and shares the original-problem total budget. Curves with
real breaks are separate pieces; do not bridge a step. Explicit corners may be
separate owners/functions. Closed/non-single-valued outlines use x(t),y(t), not a
forced y=f(x) graph. No global high-degree polynomial is used.

Constraints are source-supported point(t,point,tolerance_px), monotone(axis,
direction), range(axis,min,max), closed, and peak_count(axis,sign,prominence_px,
min,max). Each has source_evidence. Semantic cases require explicit features;
all curves also retain observed endpoints. Unknown tiny wiggles are not hard.
Source model shape error, native encoding error and actual saved appearance are
separate. Function fitting/encoding never produces a component qualification.

Before searching, preferred_px=clip(source uncertainty + representation
precision,0.3,1.5); acceptable_px=min(2*preferred,3,0.15*critical feature separation).
If uncertainty exceeds acceptable or acceptable<preferred, return source
ambiguity. Native encoding tolerance=preferred/4; maximum 128 cubic segments.
Both tiers use the same semantic gates. These are declared initial source_px
policy limits, not experimentally selected universal quality claims.

Each curve owns its own local_fit component with an independent curve_distance
target using the existing measurement adapter: source_px, component_roi window,
source_points, statistic, foreground selector and source_evidence. Program freezes
the metric's source_points from samples_ref when omitted, so the host need not
copy a dense second coordinate list into its contract. Program freezes
both bounds and stores curve profile/evidence before native build. Local evaluate
measures the actual saved render, applies native/fixed-paint checks and semantic
features. Valid acceptable is QUALIFIED with quality_tier acceptable. It cannot
hide missing metrics or failed structure/semantics. A saved mismatch routes to a
focused source/model/measurement decision, not repeated generic numeric fitting.
For loops, saved range/geometry gates plus mandatory explicit local visual review
cover topology/closure that cannot be inferred from an x-column detector.

## Shared convergence and failure diagnosis

Original Problems.json is outside replaceable component ledgers. Identity derives
from original hash/source units, retains same-unit/revision lineage, and recognizes
renamed same-region/class problems. Splits name source_inventory.derived_from;
combining unrelated original problems cannot reset budgets. IDs, models, initial
parameters, bounds and implementation changes do not reset totals. Defaults are
3 model families, 96 numeric evaluations, 2 extra source decisions/readings and
2 actual native confirmations. Reservations precede execution and journal replay
is idempotent. Bounds remain frozen after failures. Equivalent failed fitting
strategies return retained report refs. Exhaustion retains best and reports
ORIGINAL_PROBLEM_UNRESOLVED; there is no automatic acceptance fallback.
Missing source facts, unsupported model, invalid measurement and native encoding/
saved-render disagreement require different focused corrections. Do not redraw
all known parts to repair one problem. Operational budget counts are not cost or
effect telemetry.

## Personal knowledge storage and lifecycle

Default root PROJECT/.lotraAI-build/library. An explicit objectives.personal_library
may select a user-chosen shared private root; never scan neighboring projects,
accounts or installed skill folders. Public packages ship no personal database,
case, source, preview or developer component model.

knowledge.sqlite indexes class/view/status/scope and compact metadata. Normalized
recipe cores are immutable hash-addressed JSON, independent of name and evidence;
part counts/topology/edit capability filter before adaptation/style/static
complexity and domain success history. Aliases.json is an optional explicit local
taxonomy. No vector service/model/key is added. Cold source evidence and idempotent
outcomes live in separate tables. Existing entries/ state files are retained and
indexed once; later manual capture/promotion/use/revoke sync the index directly.

Qualified assemblies with semantic_class/view and source-free native group trees
produce candidates. Final acceptance upgrades their core to private case methods
for later candidate retrieval, never general/public promotion. Literal text/math,
raster, external file dependencies and unsupported trees remain task evidence.
Manual positive/counterexample/reuse evidence remains required for promoted
methods. Current accepted reuse records an idempotent domain success; a located
current failure records an inapplicable outcome, not measured token savings.
Descriptor and negative caches depend on canonical query, visible scope, aliases,
catalog/ranking revision and output budget. Catalog/status/feedback mutations
invalidate them. At most 512 recomputable descriptor rows; they never evict cores.

Raw resource cache retains exact hashes and transform dependencies; unrelated
context display limits do not invalidate pixels. Persistent pixels and numeric
working sets have separate quotas (25%/75% of configured cache bytes/rows).
An item over min(8 MiB,1/8 cache) is not admitted. Only recomputable caches are
trimmed; immutable records, source evidence and accepted methods are retained.
Fresh-context resume increments epoch before both normal and component packets.
Same-epoch repeats return stable refs; `--fresh` explicitly rereads the body.
Host transcript compression and provider prompt caching are outside this skill.

## Installation / update / publication

The runtime repository is the one-sentence user entry. Its project-local launcher
reads the current pinned release catalog and calls the maintained installer once.
Both repository READMEs retain English and Chinese guides. No manual user download
or separate Setup skill is required.

Updates compare old/new managed file manifests and actual local content. They
download only absent content hashes, add new files, replace changed files, and
remove retired owned files. Unchanged active files are never rewritten. Candidate
views reuse unchanged local bytes. Runtime companion members use the same content
cache; stored-ZIP byte ranges retrieve missing members without a full archive.
Changed/deleted preimages and scoped registration receipts support failed-install
recovery. Personal knowledge, fonts, tasks and source inputs are outside this set.

Core platform catalogs are generated from the supplied environments and engines,
independently of the Math catalog. macOS ARM64/Intel use the shared shell entry
and pinned official Math disk images; missing Math on another platform is a
specific capability limitation, never an invented PASS. No Office behavior tests
or reconstruction runs are part of publication. Existing bound tasks retain their
policy until explicitly migrated. Installation revision 2 remains version 1.33.0.
Unowned or modified skill entries stop synchronization and are preserved. Core/OCR
preparation and Math import precede registration; document render/edit remains
NOT_RUN. These are future installer behaviors, not checks executed to qualify this
source publication. No tests, syntax/import/CLI checks, runtime validation,
reconstruction or performance/effect measurements qualify this revision.
