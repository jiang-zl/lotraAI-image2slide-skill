# Visual agent loop — v1.0.3 runtime protocol

This is the default result-driven orchestration. Reuse existing analysis, native drawing, repair, masked image editing, rendering, metrics and desktop modules. Do not build a second renderer, fixed defect classifier or mandatory full-spec test campaign. The host actually observes images and executes tool calls; Python returns bounded work and maintains state. It does not secretly call another model or claim autonomous visual perception.

## 1. Establish source and constraints once

Use an isolated WORK directory and the installed package's Python environment. Keep all registered candidate inputs within WORK, with relative paths; source resources referenced by Scene must resolve from its directory. Initialize the existing session, including explicit task time and candidate limits, then start:

```sh
python -B SKILL/scripts/sci_rebuild.py init-task SOURCE --workdir WORK --output FINAL.pptx --seconds 1800 --candidates 12
python -B SKILL/scripts/sci_rebuild.py visual-loop WORK start
```

These numbers are an example budget, not required rounds. An optional start request can set `max_stalled_attempts` (integer 1–10, default 3); freeze it before trying repairs. Resuming `start` reads the existing state rather than resetting progress or resources. Explicitly stopped tasks are not automatically resumed with a new budget.

Independently inspect source semantics and layout; then use the existing source-analysis, `compile-instructions`, Scene and `plan-drawing` formats. Record every meaningful component, source coordinates, family representation, natural parts, hidden completeness and intended editing scope. A blurry illustrative asset requires an HD reconstruction action, not an unchanged crop. Relevant source omission, semantic, contour and native rules still apply. Optional metrics/score profiles use fixed object-specific priorities chosen before comparing alternatives.

## 2. Register an actual saved candidate

Draw, save and render through existing tools. The default host may directly follow the per-object drawing plan; `next-drawing-action` remains available for claimed deterministic actions and now hands off to this result loop. There is no need to perform every historical editor operation on every repair.

Run `visual-loop WORK candidate --request REQUEST.json` with this request (paths relative to WORK):

```json
{
  "scene": "initial/scene.json",
  "plan": "initial/drawing-plan.json",
  "pptx": "initial/candidate.pptx",
  "preview": "initial/preview.png",
  "render_receipt": "initial/render.json"
}
```

The plan must bind this Scene and the original source. The receipt must bind the actual saved PPT/preview and identify its renderer. Use identical renderer, dimensions and environment for incremental repairs. Registered files remain immutable; all subsequent edits go to fresh paths. A saved PPT snapshot and render are compared with existing anchors before selection. A rejected candidate never overwrites the previous selection.

The result returns a candidate ID and at most eight views. A `status` request retrieves the next batch. Views include the whole slide, a 3×3 source scan, upper semantic modules, previously located defects, and each saved bitmap as a whole asset and in context. The source scan can reveal something absent from the Scene. Identical already-satisfactory crops can be reused; whole-slide composition is freshly observed. Escalate ambiguous areas with targeted source enlargement, existing ROI/layer/component tools or finer grids, rather than running all 94 legacy windows routinely.

## 3. Observe and record unknown deficiencies

Actually view each requested source/candidate pair. Source pixels need not equal generated semantic detail. Treat pixel difference, IoU, SSIM, PSNR, frequency/edge and spacing measures as evidence appropriate to the owner; do not classify every difference as a defect. A native scientific diagram prioritizes meaning/topology and placement. A painterly face prioritizes identity/composition, contours and coherent texture. A clipped environment prioritizes complete semantic structure, clean edges and clear reusable layers.

Submit `observe` with the returned candidate ID. Batches accumulate; omitted views do not pass:

```json
{
  "candidate_id": "ID_FROM_CANDIDATE",
  "observer": {"kind": "host_model"},
  "views": [
    {"view_id": "VIEW_FROM_WORK_ORDER", "status": "defect", "note": "Lower road in the source is absent below the central block."}
  ],
  "findings": [
    {"id": "missing-lower-road", "view_id": "VIEW_FROM_WORK_ORDER", "owner": null,
     "kind": "missing_structure", "severity": "major", "roi": [100, 200, 140, 40],
     "expected": "A continuous horizontal road connects the two vertical roads.",
     "actual": "The reconstruction has ground fill in that corridor."}
  ],
  "complete": false
}
```

Coordinates above are illustrative; use actual source xywh. `kind` is open vocabulary, not an exhaustive supported-defect enum. Null `owner` means a source region is not mapped yet, not permission to ignore it. Each defect/uncertain view needs a located finding. Stable issue IDs persist until actual repair observation closes them. Do not lower severity to obtain acceptance.

On the final observation batch set `complete: true`, and supply all seven `assessment` keys, each with `status: satisfactory|defect|uncertain` and a concrete `note`:

| Key | Drawing-result question |
|---|---|
| `source_coverage` | Are the source's meaningful parts present, including parts outside the Scene inventory? |
| `text_math_semantics` | Are text, formulae, counts, connections and scientific meaning correct? |
| `layout_spacing` | Are source coordinates, ink spacing, alignment, layer order and full composition satisfactory? |
| `clarity_texture` | Are all illustrations clear at intended reuse size, without blur, mosaic or destructive texture? |
| `complete_reusable_layers` | Are isolated layers complete and semantically coherent, including occluded portions and distinct stacked instances? |
| `native_editability` | Does saved construction meet the promised native text, math, shapes, connectors and module edit scope? |
| `protected_content` | Are previous approved/frozen regions and non-target content preserved? |

Initial imperfect work can be selected as the working baseline. Later repair observations also need `outcome: helped|neutral|harmful|tradeoff` and `improvement_note`. New damage must be recorded with `introduced: true`; uncertainty about regression is not a supported improvement. A repair can help without resolving its entire issue. `resolved` entries require `{id, view_id, note}` and a satisfactory view from the actual repair. Neither neutral repetition nor new substantive damage earns selection credit.

## 4. Accumulate freezing, then repair only a small scope

Satisfactory observed module/bitmap-context views and newly resolved owners freeze automatically when no open finding overlaps the owner. `satisfied_owners: [{owner, note}]` can freeze additional observed semantic components. A mask can narrow pixel protection: `{path, sha256}` referencing a nonempty binary PNG at the actual render dimensions and within the owner's source ROI. The object itself still retains its native content/geometry promise.

An anchor retains its originating candidate, exact saved object properties, Scene properties, parent dependencies, incident relations and protected pixels. Subsequent candidates compare against those original anchors. Overlapping frozen anchors all remain effective. Failure does not move an anchor forward. Global themes, canvas changes and unrelated object movement cannot be smuggled into a local repair.

For a real user-approved anchor specify `origin: user` and `user_authorization` containing the actual instruction. Do not invent user approval. Existing LES leaf-level and image-mask rules remain applicable: a color-only request does not authorize all owner properties. The general loop's object write set cannot widen that external permission.

The next step supplies one issue, semantic mapping, relevant method options, frozen owners and remaining state. Diagnose its root cause and submit `plan-repair`:

```json
{
  "issues": ["missing-lower-road"],
  "hypothesis": "The source analysis merged the lower road with its ground layer.",
  "method": "Add one source-aligned native road path inside the existing scene.",
  "tool": "native Scene builder",
  "expected_change": "Restore road continuity without moving devices, labels or other roads.",
  "write_objects": [],
  "allow_new_parts": true,
  "roi": [100, 200, 140, 40]
}
```

List every existing object that will change in `write_objects`; new parts require `allow_new_parts`. Optionally provide a binary `mask` resource inside that ROI. Include only the smallest actual dependency closure, not the entire page. New scientific facts remain prohibited. For a missing semantic owner, update analysis and drawing plan to explain the new part; regenerate the plan binding for the new Scene. For a method switch within a family, preserve its agreed representation policy.

The controller reserves a candidate slot and returns unique `output_paths`. Execute with existing repair/build/masked-image/desktop tools on a copy, then register that saved result. The controller checks non-target Scene/native content, layer order, shared context and rendered pixels before selection. For uncertain partial saves, `RECONCILE_REPAIR_OUTPUTS` asks the host to inspect/reconcile existing task outputs, not blindly repeat a desktop edit. `abandon-repair` with a reason preserves partial files/history and allows a new hypothesis; the resource charge is retained. Identical repair signatures cannot be retried.

If a new located defect really requires touching an agent-frozen owner, `reopen` requires `{owner, issue_id, reason}`. The old anchor is archived, other anchors stay intact. Reopening user-frozen content additionally requires a new actual `user_authorization`; otherwise report the conflict. Do not unfreeze merely to simplify rebuilding.

## 5. Semantic HD reconstruction policy

Choose `appearance_policy: semantic_hd_replace` in that source owner's plan choice, with `semantic_constraints` and `target_reuse_inches`. `source_faithful` remains for native science and exact content; `preserve_approved` describes protected existing appearance. Do not apply generated replacement to scientific evidence, text, formulas, encoded data or meaning-bearing marks.

Use a real available host image tool or native redraw to create a complete clearer independent asset, not a cropped screenshot pretending to be vector. Source-condition the tool with class/count, parts, viewpoint, pose, style, framing, boundaries and intended layer. Maintain source-relative placement. Fix all hidden holes semantically; complete an entire layer when necessary. For original blurry illustrative pixels, semantic continuity takes precedence over matching the blur. A full generated result need not undergo a separate literal-pixel completion step if it already contains the entire clear object, but its independent completeness must be observed.

For an allowed raster object's `content`, keep existing file/provenance/edit-contract fields and add:

```json
{
  "reconstruction": {
    "appearance_policy": "semantic_hd_replace",
    "scientific_content_excluded": true,
    "semantic_constraints": ["one complete isometric city terrain; continuous roads; matching viewpoint"],
    "generation": {"method": "host_image_generation", "tool": "ACTUAL_TOOL", "prompt": "ACTUAL_SOURCE_CONDITIONED_INSTRUCTIONS"},
    "max_reuse_inches": [6, 4],
    "minimum_display_ppi": 200,
    "source_asset": {"path": "source-crop.png", "sha256": "ACTUAL_HASH"},
    "review": {"path": "hd-review.json", "sha256": "ACTUAL_HASH"}
  }
}
```

The generated file is referenced by the object's normal `path`/`sha256`. `generation.method` accepts `host_image_generation`, `native_redraw`, or `semantic_restoration`. Render native vectors directly for true vector output; a PNG of a native redraw still counts as raster. Asset size must support at least 200 generated display PPI at the declared maximum reuse dimensions. This is a payload-size floor, not proof of real perceptual sharpness. Upscaling alone does not satisfy the host review.

The bound HD review contains `source_sha256`, `asset_sha256`, `reviewer: {kind: host_model|human}` and `checks`. Each check requires `status: PASS` with an actual observation `note`: `semantic_match`, `key_parts`, `view_composition`, `clarity`, `natural_texture`, `clean_boundary`, `complete_independent_layer`. View the whole independent asset as well as the composed slide. Do not fill this record without seeing the images.

Existing raster comparison accepts `appearance_policy: semantic_hd_replace` with `generated_content`, `scientific_content_excluded: true`, `native_internal_edit_required: false`, `semantic_mark: false`, the normal native/raster owner paths and saved render inputs, and `comparison_review: {path, sha256}`. That review binds `native_pptx_hash`, `raster_pptx_hash`, `reviewer`, and observed PASS/note records for `semantic_match`, `clear_quality_gain`, `context_preserved`. It reuses existing same-context comparison support; do not invent unsupported rendering provenance. A bitmap cannot replace a component with a required native internal-edit promise.

Semantic replacement does not impose the original low-resolution PPI as a cap or require blurred source-pixel similarity to improve. SSIM/PSNR/FFT and source-pixel errors remain useful diagnostics but cannot veto a clear source-compatible reconstruction on their own. Targeted source-preserving inpainting still uses the existing completion/local-raster route when preservation is the intended policy.

## 6. Exit and cost control

| State | Meaning and next action |
|---|---|
| `DRAW_INITIAL` | Execute the source-specific drawing plan. |
| `NEEDS_OBSERVATION` | View the next small batch and provide located judgments. |
| `NEEDS_DIAGNOSIS` | Diagnose the next real deficiency; choose one bounded repair. |
| `REPAIR_READY` / `RECONCILE_REPAIR_OUTPUTS` | Execute or reconcile the current task-owned outputs. |
| `READY_TO_FINISH` | No open finding; apply `finish` to the latest result assessment. |
| `POLISH_DECISION` | Repair worthwhile minor polish or defer it explicitly. |
| `ACCEPTED_DELIVERABLE` | Seven dimensions satisfactory; no substantive unresolved issue; deliver selected output. |
| `STALLED_NOT_ACCEPTED` | Distinct attempts did not improve; preserve best work and explain the remaining limitation. |
| `PAUSED_RESOURCE_LIMIT` | Budget is exhausted; preserve state and do not call it completed. |
| `BLOCKED_CAPABILITY` | A needed actual tool/capability is unavailable; state the blocker. |

`finish --request FILE` accepts `defer_polish: {issue_id: reason}` only for open `kind: polish`, `severity: minor` issues. The reason explains why further change has negligible useful benefit or unnecessary regression cost. Substantive blur, omission, semantic error or editability loss cannot be deferred as polish. No additional candidate is necessary after the drawing already meets its goals. Explicit `stop` requires a non-accepted terminal `status` and `reason`.

Use `install-output WORK SELECTED.pptx` after acceptance. Its transactional backup/copy behavior is reused and its visual-loop binding prevents installing a different unseen candidate. Exports must derive from that selected PPT. State what was actually observed; acceptance is scoped to this drawing, not all future images or every software requirement.

Persisted state and immutable artifacts allow context compression/recovery. Reuse identical satisfactory crops; only redraw the active dependency scope. Compare actual gains on important dimensions and saved protected content. Do not introduce rewards for number of commands, iterations, shapes, filled forms or verbose explanations. A neutral attempt receives no improvement credit; a harmful attempt is rejected. The mechanism supplies discipline and recovery, not an infallible semantic judge.
