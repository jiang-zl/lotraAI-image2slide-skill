# Incremental task control and verified delivery in 1.37.0

This remains a portable skill: local instructions, scripts, state and receipts.
Use the prepared project launcher and current model. No mandatory harness
integration, service or model key is required. Local editable code/receipts are
not a security boundary against the host. An optional ordinary checker exposes
the delivery decision; a caller decides whether to enforce it before replying.

## Current packets

`next TASK` returns a source/revision/implementation-bound packet with an immutable
`submission_template`. Copy the template to a fresh scratch file, fill its current
decisions, then `submit TASK RESULT`. Never edit the template or source in place.
For current execution-policy packets, `action` is `submit`. `submission_command`
is an argument array for the prepared launcher and names this task plus the
scratch result file. Copy `submission_template` to its task-relative `copy_to`,
fill the required fields, then use those arguments. Phase operations such as
source_outline, bind_chunk, recovery and final audit remain template/packet
data; do not execute old direct component-workflow commands. The action,
arguments and hash-bound template remain available in compact packets.
Large dependencies use `packet_detail.py`, current managed references and full
pagination. Next/resume retains the current preconstruction packet until a
submission or implementation/environment change. Empty fields are not PASS.

Normal product entrypoints are start, next, submit, finite workflow-control
advance, export and delivery-check. Current packet source producers/diagnostics
remain available. Direct native writers cannot replace reconstruction/acceptance.
New tasks cannot disable component_first. Retain the existing source schemas and
complete validators; execution policy is independently versioned.

## Original observation in chunks

1. Submit `component_request.operation:source_outline` and `outline` with current
   source_hash/canvas, observer (host_model or human), complete_scope true, located
   observations and nonempty units. Each unit has stable id, roi, source_evidence
   and optional parent. Include every top-level region. Later source chunks can
   append newly observed descendants under existing units; scope cannot shrink.
2. Submit `operation:source_chunk`, stable chunk_id, and `observation` with up to
   32 complete units/128 features, optional spatial frames/landmarks/relations/
   footprints, observations and source_views. Unit/feature fields retain
   source-features-1.35.1 semantics. Every outlined unit needs complete
   decomposition/spatial decisions and at least one feature. Arrays use stable
   IDs; equal replay is safe, conflicting rows need an explicit correction.
   No native owners, candidate scores or candidate-derived targets are allowed.
3. When pending_units is zero, submit `operation:source_seal`. The program compiles
   the exact retained observation into the existing full source/spatial validators,
   including cross-module relations, footprints, pose and container obligations.
   Additional source_chunk submissions can fill cross-references before sealing.
   No native drawing occurs during original staging.

The packet exposes bounded pending IDs and exact counts. Its hash-bound checkpoint
retains ALL rows; select remaining IDs with the managed selector. Unprocessed rows
cannot be discarded to make a task appear complete.

## Binding in chunks

After source seal, submit `operation:bind_chunk`, chunk_id and `binding`.
`binding.scene` holds objects and applicable scene relations/prototypes/canvas or
other scene fields. `binding.contract` holds components, all feature bindings,
spatial landmark/footprint bindings, relations and applicable native constructions.
Use existing complete field schemas. Chunks may refer to future rows; final seal
checks every dependency. The program owns source/evidence/profile identities,
source_inventory, authority and policy versions, preventing smaller/legacy policies.
Mechanical defaults supply those resource identities, empty relation/prototype
arrays and a standard physical slide width. They never invent source geometry.

When all features have correspondences, submit `operation:bind_seal`. The program
assembles the source Scene and invokes the existing full bind validator: native
ownership, whole inventory, per-feature capabilities, every table cell, spatial
anchors/footprints, metrics and constructors. No drawing or qualification starts
before this complete seal. This phase boundary reduces request size without
allowing incomplete-source construction. Follow the ordinary component packets
afterwards; all existing final gates remain mandatory.

## Corrections and recovery

Snapshots and chunk identities are immutable. For a staged row correction, use a
NEW chunk_id, exact prior_checkpoint reference, and
`corrections:{"SECTION/ID":{prior_hash,reason,source_evidence}}`. Sections are units,
features, spatial.frames/landmarks/relations/footprints, scene.objects/relations/
prototypes, contract.components/feature_bindings/spatial_bindings/
spatial_footprint_bindings/relations and other keyed arrays. prior_hash is the
canonical identity of that exact prior row. Region/parent corrections additionally
use outline/UNIT_ID. No silent removals or overwrites; all prior snapshots remain.
Scalar corrections use the same prior-bound form at addresses such as
scene.canvas/target_width_inches.
After source seal, use existing explicit source correction/rebind packets, which
retain source targets, independent bests, budgets, locks and invalidation.

Schema errors keep valid prior progress. Context/turn limits mean checkpoint and
resume. Real backend failures retain stage/log/input hashes; no direct-build
fallback, PNG-for-PDF substitution or fabricated acceptance is allowed. Exhausted
finite attempts retain the best and unresolved issue. A user-requested stop is
respected. No draft delivery without the user's explicit requested scope.

## Delivery proof

Formal export requires complete components/layout/fonts/whole visual review and
independent final acceptance. It validates actual final-file rendering/native
save/reopen, publishes without overwrite and binds final bytes in the existing
private receipt. Repeat export still verifies current proof. User output remains
exactly Final_editable.pptx and Report.md.

`delivery-check TASK --directory OUTPUT --attachment PPTX` cannot create acceptance.
It checks sealed full coverage, nonempty contract/ledger, current independent
result, source/candidate/preview/implementation/environment, actual render proof,
registered official receipt and final hashes. Exit 0/allow_finish true permits
describing that attachment as verified. Exit 6/allow_finish false means resume or
report the retained blocker. The optional `scripts/check_before_finish.py TASK
--attachment PPTX` exposes the same decision; a cooperating caller enforces it.
No account, remote attestation or installed harness hook is implied.

Developer tooling is explicit: `build SCENE --developer-draft --project PROJECT
--out PROJECT/.lotraAI-build/developer-drafts/NEW/Draft_editable.pptx`, with owned
new output and applicable resources. It reports DEVELOPER_DRAFT/accepted false.
Construction success never substitutes for component/whole-artwork acceptance.
