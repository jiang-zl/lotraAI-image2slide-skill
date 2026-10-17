# 1.35.2 static implementation and skill review

Scope: read source text, contracts, rules and normal callers. No product code,
syntax/AST/import/CLI check, test, reconstruction or renderer was executed.
Status: IMPLEMENTED_STATICALLY_REVIEWED_UNTESTED. This is not a runtime PASS.

| Finding | Reviewed implementation and continuation |
| --- | --- |
| Spatial fit/layout mismatch | spatial_fit.layout_scene reconstructs initial or committed bounded parameter geometry from the frozen source; numeric journal retains that fit's input signature. component_relations.source_placement checks that saved native body and projected frames; layout and independent final audit call the same function. Actual original anchors/footprints/relations and render gates remain. |
| Write-phase bypass | spatial_repair.guard_fields/guard_scene are used before fit/commit/instance/reprojection and in native construction/transaction begin/rollback. Transactions journal authorized phase saves and grant consumption. Packets enforce the selected operation; source decisions remain available. Geometry phases use measured owners/shared constructor resources. Later activation checks earlier obligations, including stages omitted by a plan. Recovery resumes the existing journal. |
| Pending obligations bypassing acceptance | ready_for_final receives state and checks pending decisions, shared-frame decisions, observation rebinds, structural/source-apply grants and incomplete schedules. Visual review, audit, accept and export use it; advance stops before unrelated automatic work. Shared-frame diagnosis is recorded in both state and the existing ledger. |
| Failure/decision packet loops | evaluate/qualify/layout/repair/final invalid measurements persist source/measurement decisions and hash-bound check references. next emits a decision-capable packet, without requiring child qualification first. Valid rebind preserves historical bests, clears superseded decision state and requires current rechecks/replanning. Numeric spatial failure does not override hard/native/source failures. |
| Stale rule references | spatial_frames.reference selects workflow-v1352.md for 1.35.2 and matching retained references for older contracts. Both normal coordinator and spatial packets use it. SKILL and schema/policy explicitly retain 1.35.1 observation schemas with new workflow_version 1.35.2. |
| Unsupported native 3D measurement | boundary_geometry.require_projected inspects the saved leaf, text body and ancestor 3D settings before matrix/frame extraction. Spatial anchors and native_text_frame/domain extraction call the same guard. Unsupported geometry remains invalid and follows measurement diagnosis. |
| Sibling over-invalidation | component signatures use actual saved world transforms, not absolute XML indices or serialized ancestor boxes. Relevant occludes/layer_before pairs separately compare actual relative painter order; unrelated anatomy signatures and retained bests remain independent. True parent transforms still invalidate descendants. |
| Perspective domain validity | Frames.project_domain validates finite homogeneous values of each visible face/edge before division. Planar projected contours validate their bounded control hulls. Horizon crossings/unresolved hulls return source/representation decisions. Existing matrix-family, unit, typed-subject, full-domain and canonical-topology guards remain. |

Group-container follow-through additionally traces actual native descendants
when assigning transform phases. The complete measured batch is gated before
its first activation as well as between saves, so a child can discharge an
assembly obligation without forcing unrelated group fields into that phase.
Post-save journaling retains every completed batch member, including a member
whose obligation was resolved by another owner's edit in the same batch.
Global invalid measurements use the existing full-contract decision packet;
local decisions stay scoped to their component. This preserves a repair route
when independent roots participate in the failed measurement.

Static follow-through covered bind/compile, fit/search/commit, actual saved
measurement, local qualification, source decisions/rebind, repair plan/activation,
native journal post-save/recovery/rollback, next/submit/advance and final review/
audit/accept/export. No additional generic transaction or workflow framework,
provider, dependency, model key or telemetry was introduced. Stage repair uses
scoped edits; numerical operations cannot independently skip the phase sequence.

Boundary decisions remain intentional: unsupported native 3D extractors are not
implemented by treating their 2D boxes as projected geometry; conservative curve
control-hull horizon checks can require a focused representation decision.
Single-image evidence never establishes hidden 3D truth. A later execution run
is still needed to establish product/runtime/artwork behavior.

Repository naming maintenance keeps product version 1.35.2: default/development
branch dev and version branch 1.35.2 share the current commit; formal version
tags have no extra suffix. README and maintained installer channel/pins follow
these branch names. Runtime binaries/resources and spatial product core are
unchanged. No product execution or tests were performed for this maintenance.
