## v1.0.3 result-quality default

Ordinary reconstruction uses [visual-agent-loop.md](visual-agent-loop.md): observe actual output, discover located deficiencies, repair and accumulate protection. The seven result dimensions and substantive-issue queue determine its scoped deliverable exit. Legacy full-spec evidence tables below remain available only for that explicit broader task; missing software-validation campaigns do not themselves trigger extra drawing rounds. Never turn an unobserved drawing dimension into satisfactory. Blurry illustrative source pixels may be replaced semantically; literal pixel metrics are advisory for that policy.

# Fixed evidence, quality and transactions

Hard channels are content, topology, native structure and real editor operations, object/part coverage, semantic/source-only review and critical occlusion. Local metrics and global aesthetics are separate. Mandatory FAIL or UNVERIFIED vetoes product acceptance.

Six global weights remain Layout .25, Visual Balance .15, Alignment/Spacing .20, Layer/Occlusion .10, Color/Style .10, Readability .20. The shipped profile has null local thresholds, global threshold and dimension floors. Do not replace null with zero, renormalize available dimensions or declare profile calibration from passing synthetic tests.

Metrics operate at fixed canvas coordinates. Foreground IoU excludes white background; both masks empty yields null, one empty yields zero. CER preserves case, signs and Unicode distinctions. Chamfer is the average of both mean nearest-boundary distances divided by the fixed reference diagonal. Layout measures absolute centers as well as relative displacement so whole-scene shifts remain detectable. Balance compares visible contrast mass; it does not force symmetry.

Width-fixed raster exports quantize the ideal height to its floor or ceiling (for example 1600 × 742.5 becomes 1600 × 743). Actual Office export also produced height 1249 for an ideal 1249.5437, even though the bridge requested the rounded height. QA therefore permits only those two adjacent integers and records the exact frame transform before one whole-canvas resize. It does not permit an additional full pixel, independent object alignment, a flexible aspect tolerance, cropped borders, or padded canvases.

The 3×3, 6×6 and half-cell-offset 7×7 grids produce 94 windows. Pixel boundaries use floor with clipped edge cells. Each scheme independently covers the whole canvas once. The 12% context halo never contributes duplicate core coverage. Object close-ups, full connector corridors and source-only omission review are still required beyond these grids. Generating windows or raw measurements is not equivalent to reviewing them.

Rubric observations, when available, need evaluator/version, source/render hashes, object/window ID, ROI, concrete defect, severity and raw level. Missing observation is null. The fixed four-level rubric is 0 severe error, 1 clear repairable error, 2 readable with localized shortcomings, 3 no located defect; level/3 is not an accuracy probability. Per-dimension mixing/scales require offline calibration.

Scene versions track content/structure/style/placement separately. Source/profile/evidence hashes remain frozen. Worker patches cannot edit locks or resources. The coordinator's separate grant sets IDs, fields, role, translation bound and scale permission. Membership changes need old/new parent authorization and unlocked structure. Group layout currently requires explicit child patches, preventing implicit edits to locked descendants.

Old/new dependency closures invalidate relevant evidence. The file writer locks once and rechecks no-overwrite inside the lock. State commits serialize an immutable revision and then atomically replace its pointer; no chain of renames is falsely called a multi-file transaction. Recovery keeps orphaned pending revisions inactive. A rollback restores prior content via a new version; it does not revive an old QA receipt.

Keep best_local, best_in_scene, best_working_scene and best_feasible_scene conceptually separate. This release provides transaction/rollback primitives, candidate registries and host-directed semantic/context review; it does not autonomously establish semantic truth or calibrate acceptance from exploratory IoU ranking. Never concatenate incompatible per-object bests. Rank independently measured candidates at fixed profile/dependency versions and repeat after affected neighbors change. Follow the [reflection loop](reflection-loop.md) to choose an actual repair and a bounded recheck scope.

Budget exhaustion is PAUSED_RESOURCE_LIMIT; a stalled unacceptable candidate is STALLED_NOT_ACCEPTED; a missing capability is BLOCKED. None means ACCEPTED. Hashes bind identity, not semantic truth or evaluator honesty. Same-process checker and candidate access is not formal adversarial isolation.


Review imports consume the exact prepared manifest and source/candidate crop hashes, plus the current source/Scene/PPT/render/implementation binding. The host must actually view every scored target. Unseen criteria stay null or absent. A previous observation may be reused only with explicit evidence that its relevant crop bytes and dependencies remain unchanged; never relabel a stale receipt as current. `import-review` reports coverage and raw rubric values without promoting the independent `qa` output.

Source-pixel bbox/roi evidence uses `[x,y,width,height]`; prepared review crop rectangles use `[left,top,right,bottom]`. Keep these conventions explicit. Cropped text at a grid boundary is not necessarily missing text: inspect the halo and the full object. Conversely, a textbox that fits numerically can still crowd a symbol or neighboring border in the real render.
