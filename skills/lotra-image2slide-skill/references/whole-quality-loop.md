# Whole-result quality loop (v1.14.0)

The host interprets original images, assigns semantic purposes and reviews real outcomes. Programs enumerate objects, construct bounded changes, measure actual saved artifacts, preserve protected properties and decide whether every frozen predicate passed. These roles complement each other; no deterministic program can certify a mistaken original interpretation as ground truth.

## Order and scope

1. Prepare the offline runtime; start a new source task or use `upgrade-task SOURCE DEST --out RESULT` for a versioned copy of an existing task. The migration copies referenced task resources transitively, records historical missing references, preserves the earlier task and requires a new whole policy. It never migrates an old PASS as current acceptance.
2. View the complete original. Answer original-feature, source-specification, frame, font and semantic-composition packets. Before constructing each new source part, supply `quality_intent` with `purpose`, `appearance_target`, `basis` and per-property `source_reliability`, plus the target's required frozen bounds/reference. A source target needs `source_constraints`; a design target needs `design_contract.constraints`; an approved target needs `approved_reference`. Without an approved style reference, illustrative/decorative/text/formula purposes also need `design_contract.clarity_band`. See the executable field example below. The finite purposes are illustrative, decorative, scientific, photo_identity, structure, text, formula and relation. Source declarations cannot downgrade critical text/math/relations to decorative artwork.
3. Construct the frozen frames first, then content. Shared grid coordinates give each row one height and each column one width; explicit content windows/valid masks exclude accidental source margins. Opaque semantic contours own their fills; independent strokes remain independent. Actual painted domains, native table cells and alpha coverage are checked, rather than merely comparing group bounding boxes.
4. Supply original-grid ownership masks for relevant same-root interfaces. `source-spacing` measures their uncertainty interval and classifies contact, intentional separation or ambiguity. Semantic association proposes interfaces; it does not choose contact. For details below original resolution, an explicitly inferred, approved native design may use `design_attachment` positive overlap or an actual stroked graph; it cannot be reported as pixel-resolved source contact. Group ancestry alone never establishes attachment.
5. Declare complete back-to-front direct sibling sequences with `compile-source-layers`. The program expands every discovered relevant near/overlap pair into hierarchy or concrete order checks. All siblings must be included exactly once. Original evidence is required; inferred fine order must bind the immutable approved artifact. Container groups have no own paint, while every descendant remains independently covered.
6. Save and actually render. `render-working --force` performs a new full render even when previous capture coverage is complete. Source and candidate pixels are separate immutable resources.
7. `quality-loop TASK discover --out INDEX` inventories all actual native owners and original units. The host supplies a source-bound `quality-intent-1` request to `bind`; the compiler rejects omitted objects/units, unknown purposes, unresolved reliability, stale views and invalid weight profiles. Changing a frozen policy requires its prior hash and a substantive revision reason, retained in history.
8. `source-reading TASK discover --out INDEX` provides original-only enlarged views for every text/formula unit, including native table cells and prose math. Independently bind confirmed literal text/AST. OCR supplies hypotheses; host vision or a user transcription may confirm. Never derive the expected string from the candidate.
9. `next` routes missing original typography contracts and whole native root decisions before semantic observations. These are the same mandatory registered packets used by the construction/import path; do not substitute another dictionary for the typography `contracts` registry. Fresh constructions resolve findings from their actual built component ownership, while imports use their original owner map; conflicting ownership is rejected. Already bound but failed physical measurements remain located repair findings rather than disappearing or requesting identical bindings again. `quality-loop TASK observations --out PACKET` then supplies current paired semantic views. Record concrete actual facts with outcome matched/issue/uncertain using `observe --request REQUEST`. Observations bind original view, candidate pixels, native dependencies and policy. A complete direct root can review its named descendants semantically; no numeric or literal check is inherited from a root.
10. `quality-loop TASK run --out RESULT` checks the complete result, locates failures and records program observations. The host chooses an evidenced typed repair route; programs execute concrete geometry/text/media operations. Rerender changed artwork, measure the entire result again, reflect on measured gain and preserve the best. Existing rule/strategy programs enforce finite branch budgets; two ineffective attempts prune a branch, never approve unresolved requirements. Source-text repair additionally rejects an unchanged repeated attempt.
11. Only an exact current accepted whole-result receipt permits `quality-loop TASK export --out DIRECTORY`. Acceptance binds implementation, source, native artifact, policy, readings, actual rendering and semantic observations. A code or evidence change requires rechecking.

## Policy and scores

`authority` is a task-local immutable user-request record. `approved`, when applicable, binds the actual earlier PPTX, preview, render receipt, original hash and precise approval scope. Every item supplies exact native `objects`, original `quality_units`, fixed source `roi`, program-generated `source_view`, meaningful source facts/evidence, purpose, representation and reliability. `appearance_target` is approved/baseline, source, design or source_content.

For a new source part, its pre-construction `quality_intent` must contain the same purpose, target, reliability and bounds as its final policy. Source targets require `source_constraints`; design targets require `design_contract.constraints`; approved targets require `approved_reference: {pptx: SHA256, preview: SHA256}`. Without an approved reference, illustrative/decorative/text/formula purposes also require `design_contract.clarity_band: [POSITIVE_LOW, HIGH]`. These are source/design decisions made before drawing, not measured values chosen from a candidate. The final compiler rejects changed bounds, authority or reliability; an explicit source correction preserves the earlier interpretation and its evidence.

Image constraint entries have `id` plus finite `min` and/or `max`. Supported IDs are `ssim`, `boundary_f1`, `clarity_second`, `clarity_ratio`, `color_histogram_tv` and `mean_absolute_rgb_error`. Structural/native/content predicates use the separate frame, interface and content programs; do not invent an unsupported image metric name. The clarity band is an actual-size energy interval calibrated from an intended style/reference at that source canvas, not a universal blur threshold. See the controlled study for its limits.

`discover` supplies the exact `source_hash`, `inventory_hash`, native names/parents and each unit's frozen `quality_intent` and program-generated `source_view`. Copy these fields; do not fabricate view hashes or inspect implementation code to obtain them. The following illustrates the shape of a declaration and final request. Numbers are illustrative schema values, not default acceptance thresholds: determine bounds from the original/reference and freeze them before constructing the part. A real request must cover every discovered native object and original unit, including groups; one item below does not represent a complete multi-object figure.

```json
{
  "quality_intent": {
    "purpose": "scientific",
    "appearance_target": "source",
    "basis": "The trace encodes measured values; preserve its shape and colour.",
    "source_reliability": {"trace": "observed", "colour": "approximate"},
    "source_constraints": [{"id": "boundary_f1", "min": 0.9}]
  }
}
```

```json
{
  "schema": "quality-intent-1",
  "source_hash": "COPY_FROM_DISCOVER",
  "inventory_hash": "COPY_FROM_DISCOVER",
  "authority": {"path": "source/User-request.txt", "sha256": "HASH_OF_SAVED_REQUEST"},
  "reason": "Evaluate the complete result against the original scientific trace.",
  "items": [{
    "id": "trace-policy",
    "purpose": "scientific",
    "representation": "native",
    "appearance_target": "source",
    "objects": ["EXACT_NATIVE_NAME"],
    "quality_units": ["EXACT_DISCOVERED_UNIT_ID"],
    "roi": [0, 0, 100, 60],
    "source_view": {"path": "COPY_DISCOVERED_VIEW_PATH", "sha256": "COPY_VIEW_HASH", "source_hash": "COPY_SOURCE_HASH", "roi": [0, 0, 100, 60], "scale": 2},
    "source_evidence": "Original-only trace view examined before drawing.",
    "source_facts": ["One connected blue trace has two local peaks."],
    "source_reliability": {"trace": "observed", "colour": "approximate"},
    "source_constraints": [{"id": "boundary_f1", "min": 0.9}]
  }]
}
```

For an approved target, add top-level `approved` with immutable task-local `pptx`, `preview`, `render` resource objects, `source_hash` and a precise `approval_basis`; the declaration's `approved_reference` contains the same PPTX/preview SHA256 strings. For source/design text targets without that reference, keep the declaration's positive clarity band in the final item. After a source-confirmed literal correction, retain these fields and add `source_content_correction: {unit: UNIT_ID, reading_hash: HASH_OF_READING_RECORD, inherited_appearance_target: ORIGINAL_TARGET}`. `source-text-repair TASK REQUEST --out RESULT` constructs only the confirmed rich runs; never substitute a candidate-derived reading.

- Approved/baseline protects exact saved native properties and actual-size appearance. Source-correspondence SSIM/F1 remain reported independently.
- Source requires explicit fixed correspondence bounds. Scientific measurements and identity photographs cannot inherit an illustrative exemption.
- Design requires pre-candidate bounds. Without an approved style reference, illustrative/text/formula purposes must also freeze a positive actual-size `clarity_band`; the candidate cannot set its own target. Source SSIM, edge correspondence and colour remain measurable; semantic correctness remains a separate host obligation.
- Source_content handles one independently read native text owner. It binds the exact reading hash and literal rich runs; the constructor/guard protects every property outside those runs. For a new task with a pre-construction declaration, include `source_content_correction.inherited_appearance_target` equal to that declaration's original source/design/approved target and retain its exact design/source bounds, reliability and approved identity. This is a bounded literal repair under the inherited authority, not permission to switch aesthetic goals. The protected baseline is the actual saved pre-repair PPTX/preview/render. An obsolete wrong glyph's SSIM cannot veto a correct source-confirmed replacement. Actual rendered ink and literal/script checks remain mandatory.

The profile configuration selects different dimensions: illustrative/decorative appearance, scientific colour/edge fidelity, identity texture/colour, structure layout, exact text/math content and physical relationships. Weights are finite positive values summing to one. They are versioned engineering choices, supported by controlled comparisons and a user preference anchor, not research-proven universal aesthetic weights. See [evaluation rationale](evaluation-rationale.md).

Scores rank candidates only after every hard requirement passes. A failed or unmeasured required gate cannot be compensated. Raw historical source values and earlier thresholds are preserved as diagnostics, with explicit current binding migration where old construction names vanished. Reports distinguish MEASURED, NOT_APPLICABLE and required missing evidence; they never call missing data zero quality.

The separate `source_measurement_coverage` gate requires every original unit and numeric predicate to have a real measurement. Missing legacy literals may use the current confirmed, source-identity-verified reading; an existing contradictory literal remains a failed content predicate until an evidence-preserving source correction. Formatted scripts, math AST/spans and native table-cell styles remain independent checks. Missing or empty original masks require exact resource restoration or original-only reobservation through `source-layer-domain` and `amend-source-spec`; they cannot be converted to a diagnostic exemption. That domain program accepts a verified raw `source_view`, baseline hash and a finite `original_selector` (source palette/background, optional owned original window and explicit component seeds). It reads no candidate pixels and preserves previous source specifications and every threshold. Important below-threshold historical pixel differences remain visible alongside the active purpose-specific criteria; missing data never counts as a completed comparison.

Actual layout ink is requested automatically for unsupported geometry and glyphs. Use `render-working` to collect the program's missing owner captures, then remeasure the complete result. `source-layout-repair` executes only the bounded translations solved from frozen original relationships; no host-supplied coordinates are accepted. It retains native text/fonts/paint/shape/resources, requires actual rerendering, and records its source-bound constructor and branch reflection. Source-position repair does not change the declared aesthetic purpose or relax source intervals.

A finite original-derived text/layout correction can change a neighbouring owner's fixed ROI without changing that owner. `approved_render` reconstructs the **complete** slide from the immutable approved artwork and existing source constructors, then compares both exact actual previews from the same renderer without resizing or registration. Actual pixels outside the program-derived before/after corrected owner frames plus a fixed two-source-pixel edge margin must be identical. This proof handles context contamination; it never replaces raw fixed-ROI SSIM/clarity numbers with a perfect score. Non-target native/resource edits, foreign renderer evidence, missing/stale receipts, exterior pixel changes and failed original layout relations still block. Existing original content predicates use the same narrow mathematical-italic/NBSP encoding rule as independent source rereading; case, operators, normal/style flags and script structure remain exact.

When the exact normalized SVG, crop and frame pass but its compatibility PNG differs, `normalized-preview-repair TASK REQUEST --out RESULT` accepts only `{expected_baseline_sha256}`. The program locates failed preview owners and freezes newly normalized PNGs before saving. Exact complete-package replay protects the SVG, geometry, fonts and unrelated resources; actual rerendering and whole-result acceptance remain required. Do not relax pixel thresholds or use a model-authored fallback. Imported approved typography additionally requires fresh original literals/AST and exact saved text-body formatting (or the finite original-text correction). First reconstructions require both bound original textbox contracts and measured targets; a bound contract alone is not a pass.

## Public result

The short report answers seven goals: original recursion/content closure; signal functions/text association; whole inventory; frame/fill/boundary/spacing; exact text/math/typography; appropriate icon appearance; observations/actual render/fonts. It includes actual object/readings/observation counts and links to evidence. Structured JSON contains every native owner, source unit, raw metric, selected score dimensions, hard predicates, source readings, semantic observations, actual backend and immutable hashes. Do not bury a critical error in a mean score or present a large unexplained metric table as the primary user report.
