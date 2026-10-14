# Historical baseline and release evaluation

Freeze every user-supplied reference and historical deck by content hash before repair. `core.benchmark.freeze` stores content-addressed copies and a case manifest. Preserve all historical candidates, including versions that are stronger on different objectives. Cases with no historical deck are marked explicitly.

For the project's v1.0.1 lineage, retain the user-labeled v0.1, v0.2, v0.3
and v1.0.0 decks as distinct historical evidence. Carry forward whichever
version is strongest for each semantic scope: an eligible texture baseline
painting texture, an eligible editable baseline native city/vehicle parts, and
the useful single-page, semantic/component workflows across all versions.
Do not equate the newest historical file with the strongest baseline. Preserve
v0.1 artifacts without inventing an advantage that has not been measured.

Render saved PPT files in the same PowerPoint build, at the same predetermined resolution, with a current font identity. Font identities include file content hashes. For image metrics use a fixed reference, crop plan, masks, preprocessing and measurement implementation. A foreground mask describes object pixels; an evaluation mask limits which pixels contribute to residual/color/SSIM/edge metrics. Do not confuse the two. SSIM has no result where the mask contains no complete window. Linear sRGB luminance replaces the older RGB-channel-mean diagnostic; do not compare those versions numerically.

`environment_identity` binds the actual exported preview dimensions as well as
the Office/font environment. Pass the hashed preview when using historical
receipts without dimensions. Exporting at a different resolution and resampling
to the same source canvas does not establish equivalent antialiasing. Re-render
under the fixed export resolution before making a superiority claim.

Compare each old version with the candidate, not only a chosen weak deck or whole-page mean. Report raw quality vectors alongside scientific correctness, topology, native editing, component completeness and export gates. `compare_case` distinguishes VERIFIED_SUPERIOR, NONREGRESSING_WITH_TIES, NOT_PROVEN_SUPERIOR and NOT_ACCEPTED. A tie is not a win; a missing measurement is not zero. A gate may only be PASS with actual applicable evidence.

When an older editable owner is known, freeze a `baseline-representation-1`
contract for the corresponding source ROI and the saved-PPT owner paths. Set
`baseline_pptx_sha256`, `baseline_owners`, `candidate_owners`, and a justified
`minimum_candidate_native_leaves` before evaluating the new candidate.
Selectors are exact saved shape paths (including descendants) or a prefix
ending in `*`; avoid broad selectors that include unrelated content. Run
`audit-baseline-representation CONTRACT.json OLD.pptx NEW.pptx --out REPORT.json`.
It reopens both PPTs, counts native and picture leaves inside each selected
semantic owner, and rejects a picture hidden inside a named group or a
candidate below the frozen native-detail floor. A passing audit says only
`PASS_REPRESENTATION_FLOOR_ONLY`; it does not assert visual fidelity or actual
editor operations. A reported raster regression cannot be waived by a high
whole-slide SSIM. If a genuine allowed raster exception is being considered,
run the separately calibrated same-protocol comparison and retain both
decisions for review rather than mutating this historical report.

If the older deck already has useful flat native parts, do not redraw them
blindly. Freeze a `native-owner-grouping-1` contract with that PPT hash,
top-level semantic shape-name selectors, expected selected native count, and a
new group name. `group-saved-native-owner CONTRACT.json OLD.pptx --pptx-out
CANDIDATE.pptx --out GROUPING.json` creates a task-owned candidate without
touching the old file. It rejects pictures/nested groups and checks that every
native leaf and every unselected saved shape retains its product properties.
Render both saved PPTs with the same settings, then run
`check-native-group-parity GROUPING.json OLD.pptx OLD_RENDER.json CANDIDATE.pptx
CANDIDATE_RENDER.json --out PARITY.json`. A pure regrouping should preserve
the entire page pixel for pixel under this screening renderer. The grouped
owner can then be copied and edited as a semantic module, but actual
PowerPoint move/edit/save/reopen must still be observed before claiming that
editor promise. This route applies when a historical editable PPT is supplied;
it does not turn an image-only input into native parts by itself.

Run local and parent/context checks after every representation change. A visually improved component that harms a label, connection, boundary or another object cannot be promoted as a context best. Thresholds must come from a frozen justified protocol or independent calibration, never tuned to make the current candidate pass. Keep discrete renderer uncertainty separate from semantic regressions.

All expected cases must be present in the release matrix. `release_gate` verifies benchmark completeness; this does not replace package, dependency, Office editing and final-delivery checks. Input examples used during optimization are development regression cases, not unseen generalization evidence. Report actual host model/token usage only when available; model compatibility and clean-session execution require real runs.
