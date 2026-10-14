# Run, review, recover, and deliver

Run these commands with the isolated interpreter and installed entrypoint described in [README](../README.md). The examples use `python -B /path/sci-rebuild/scripts/sci_rebuild.py`; replace `python` with that interpreter. `WORK`, `SCENE`, `PPTX`, `RENDER`, and `REVIEW` below stand for the actual paths recorded by `compile-task`, not prescribed filenames.

## Compile without repeating image understanding

`compile-task WORK SCENE` calls `resume-task`, validates the frozen resources, probes the current Office/font environment, builds/inspects the saved PPT, renders it, and prepares review crops. An analyzed v1.0.2 Scene requires `--drawing-plan PLAN` or `WORK/drawing-plan.json`; an unplanned analyzed build is rejected. Timings and cache decisions appear in `WORK/session.json`; the selected artifact paths appear in `WORK/latest-build.json` after the default workflow.

With `--drawing-plan PLAN`, `compile-task` reads `WORK/actions.json` when present, or accepts an explicit `--action-journal FILE`. `next-drawing-action WORK PLAN --out WORK/next.json` returns one ready action or a precise saved/interrupted/dependency/budget state. It carries only the target nodes and current action, reducing repeated full-Scene context. It does not run an app or silently advance a candidate.

The build and render caches include implementation/resource hashes and current platform information. A cache lookup rechecks every saved artifact. A missing environment identity disables caching instead of assuming equivalence. Review preparation currently creates a fresh review directory even if the PPT/render are cached. A local patch preserves the other Scene objects; serializing the resulting whole deck does not mean the host must re-recognize the whole image.

`--file-only` provides a file-core result when Office is absent. `--no-review` only defers comparison preparation. Neither option establishes visual or native-operation acceptance.

## Inspect the saved file and its actual render

For a manually selected candidate outside `compile-task`:

```sh
python -B /path/sci-rebuild/scripts/sci_rebuild.py inspect SCENE PPTX --out WORK/structure.json
python -B /path/sci-rebuild/scripts/sci_rebuild.py render PPTX --backend powerpoint --width 1600 --out WORK/new-render
python -B /path/sci-rebuild/scripts/sci_rebuild.py prepare-review SCENE PPTX RENDER/Final_preview.png RENDER/render.json --out WORK/new-review
```

`--width` controls the rendered preview width; use the source canvas width for direct inspection. Review preparation resizes once to the source canvas and rejects an aspect-ratio mismatch. The CLI's default renderer without `--backend powerpoint` is LibreOffice; using it requires Impress and Poppler and remains a separate platform result.

Actually view the full page, the contact sheets, and any crops needed to resolve small text, symbols, crossings, or occlusion. The manifest contains all 94 grid windows, object targets, complete connector corridors, six global dimensions, and an independent source-only target. Preparing those files is not reviewing them.

An observations file contains `binding`, `manifest_hash`, `evaluator:{id,version}`, and an `observations` array. Each observation names a manifest `target_id`, required `criterion`, fixed-rubric `level` (`0`–`3` or null), a concrete `note`, and `evidence_refs`. Copy the exact `{path,sha256,roi}` records for both reference and candidate from that target's manifest crops. The ROI here is the manifest's crop rectangle, not a new guessed box. Record each sheet/crop actually viewed. Unseen or unresolved criteria stay null or absent.

```sh
python -B /path/sci-rebuild/scripts/sci_rebuild.py import-review SCENE PPTX RENDER/Final_preview.png RENDER/render.json REVIEW WORK/observations.json --out WORK/imported-review.json
python -B /path/sci-rebuild/scripts/sci_rebuild.py qa SCENE PPTX RENDER/Final_preview.png RENDER/render.json --out WORK/qa.json
```

`import-review` validates exact crop bytes and current binding, rejects contradictory defects or duplicated criteria, and reports missing reviews. Its result remains `UNVERIFIED`: raw rubric values are not calibrated acceptance scores. The existing `qa` output and imported reviews are separate artifacts; importing observations does not silently change a `qa` result into PASS.

## Apply a bounded local repair

```sh
python -B /path/sci-rebuild/scripts/sci_rebuild.py init-state SCENE --out WORK/new-state
python -B /path/sci-rebuild/scripts/sci_rebuild.py apply-patch WORK/new-state WORK/patch.json WORK/grant.json --resources WORK
```

The coordinator supplies the grant separately from the worker patch. The patch binds the base revision/hash and affected dependency versions. Content, structure, style, and placement locks remain distinct. Parent membership changes need the corresponding permissions. Apply group layout changes to the affected descendants explicitly.

A rollback is a new revision with new dependency evidence; it does not revive old previews or QA. `core.state.rollback_patch` exposes that operation through the Python API. `record-candidate` maintains each object's archive and exploratory local IoU best:

```sh
python -B /path/sci-rebuild/scripts/sci_rebuild.py record-candidate SCENE ComponentID PPTX RENDER/Final_preview.png RENDER/render.json --registry WORK/candidates
```

Structural vetoes and stale dependency checks still apply. A local IoU best does not establish semantic validity or a compatible global best. Contextual/full-scene best acceptance and automatic quality-driven optimization remain incomplete.

`fit-text SCENE PPTX BOUNDS ObjectID --out WORK/text-fit-proposal.json` proposes font-size-only changes from actual PowerPoint text bounds bound to this PPTX. It does not infer text bounds from the Scene, move labels automatically, or apply its generated patch/grant. Review the proposal and source typography, apply an authorized patch, then render and inspect the affected labels and neighbors again. A line-count or crowding defect may require line spacing/placement repair instead of font shrinking.

## Verify the figure's native operations

```sh
python -B /path/sci-rebuild/scripts/sci_rebuild.py native-plan SCENE PPTX --out WORK/native-plan.json
python -B /path/sci-rebuild/scripts/sci_rebuild.py native-check PPTX WORK/native-plan.json --out WORK/new-native-check
python -B /path/sci-rebuild/scripts/sci_rebuild.py verify-native WORK/native-plan.json WORK/new-native-check --out WORK/native-result.json
```

The plan is generated from this saved deck. It includes its mathematical zones, selected semantic groups, trace-path operations, a plain-text operation, and movements for applicable source-anchored nodes. Read the actual action list: not every possible Office manipulation or unsupported endpoint is covered. The bridge operates on a temporary copy. Verification checks the altered saved structures and endpoint behavior; the original candidate's content and rendering must still pass their own checks.

The operation verifier checks every connector affected by the tested movements and all declared rigid-parent path vertices. PowerPoint may expose nested group leaves through a flat `GroupItems` collection while withholding nested group handles. The test bridge explicitly ungroups ancestors in its isolated copy to access those groups and records these operations. The original candidate retains its hierarchy. Partial operation records are recovery evidence and cannot pass a completed roundtrip.

`reuse-review SCENE PPTX PREVIEW RENDER_RECEIPT OLD_REVIEW OLD_OBSERVATIONS NEW_REVIEW --out FILE` transfers only observations with identical source, crop bytes, ROI, rubric, relevant object versions, and measurements. Changed targets need a new visual review; native checks and acceptance verdicts are never transferred this way.

Before finalization, aggregate the actual evidence:

```sh
python -B /path/sci-rebuild/scripts/sci_rebuild.py attach-qa SCENE PPTX PREVIEW RENDER_RECEIPT WORK/qa-base.json WORK/review/review-manifest.json --reviews WORK/review/reviewer.json --native-report WORK/native-result.json --native-plan WORK/native-plan.json --native-office-dir WORK/new-native-check --out WORK/qa.json
```

Create `qa-base.json` using `qa` on the same saved artifacts. `--stage-records FILE` optionally reads an array of `{kind,path,sha256}` records relative to the Scene directory; kinds are `session`, `stage`, and `patch_commit`. Missing timings remain unavailable. The aggregate records raw classified measurements and fixed rubric observations separately from calibrated scores, freshly rechecks native files, and binds all evidence for the final workbook. Its exit 3 means the full acceptance gate is unmet; it does not erase the generated evidence.

The fixed-name `office-probe` is for the included M0 probe, not arbitrary user figures. Reuse old M0 evidence only for unchanged representation capabilities. Mac and other missing native paths require the explicit protocol in [native representations](native.md), with unperformed operations marked unverified.

## Keep one Office writer and recover deliberately

Cooperating bridge calls on one Python host share a queue lock under the system temporary directory at `sci-rebuild-office-session/`. The default queue wait is 300 seconds. A queue timeout changes no document. A running Office probe also has a resource timeout, and the environment probe has its own timeout.

The local queue does not coordinate a second machine, a different WSL distribution, a native Windows process with a different temporary directory, or a user manipulating the same Office session. The coordinator must still keep one writer for the final PPT/Office session. Never start parallel native-editor jobs merely because workers can build candidate data in parallel.

After an Office process timeout, the bridge writes `needs-inspection.json` in that queue directory and an adjacent `*-timeout.json` for the requested output. Further bridge jobs are blocked. `resume-task` recovers the task journal but intentionally does not clear this Office marker.

To recover, read the recorded input/output and lock PID, inspect the task-owned PowerShell/PowerPoint activity and temporary presentation, and establish that the failed operation has stopped. Preserve the timeout/process records and any useful candidate. Close only a task-owned test copy when its ownership and saved state are known. After that inspection, an operator may archive the stale marker/lock and retry with a new output directory. There is no automatic Office-marker reset command. Do not clear a live lock, call `Application.Quit`, kill all PowerPoint processes, or close unrelated/unsaved presentations to bypass the block.

Task resumption preserves the original deadline and candidate budget, including interrupted wall time. It cannot grant more resources. If the guard is exhausted, retain the best working files and report `PAUSED_RESOURCE_LIMIT`; that status is not success.

For a compiled drawing plan, use `core.action_journal.claim` with a stable operation ID, task-local input hashes, route and **frozen output targets before acting**. Freeze every planned output plus any expected `render.json` or `structure.json` verification artifact so interruption recovery can inspect all of them. Each new candidate-producing claim spends one slot from the same `session.json` budget used by ordinary task stages; re-reading an existing operation ID does not spend another slot or repeat the edit. A matching claimed build gives `compile-task` its frozen output path and suppresses the stage's second candidate charge; unrelated active actions block a new build. Save only the declared outputs, then call `outputs_saved` and `check-drawing-action`. It recomputes saved build/inspect/render/native edit evidence and, for `raster_compare`, `complete_hidden` and `measure`, the source-bound comparison, composition or fixed-domain measurement. Their operation receipts do not turn an eligible raster or a raw metric into visual acceptance. A failed saved check marks that action `FAILED_REPLAN_REQUIRED`; `next-drawing-action` returns its frozen `on_failure` branch and requires changed inputs or a revised plan before another claim. Pass `actions.json` explicitly to standalone `check-plan-conformance`—a journal merely present on disk is not implicit evidence. A crashed `RUNNING` action becomes `INTERRUPTED_REQUIRES_RECONCILIATION`: inspect its frozen target paths. `reconcile_interrupted` can mark an empty attempt abandoned or seal a complete saved output for fresh verification; a partial save remains blocked. Never choose a new operation ID to bypass an unresolved action. None of these checks turns an alternate renderer into a PowerPoint editor roundtrip or a semantic quality PASS.

The CLI exposes the same sequence as `claim-drawing-action` (`--output-targets FILE`), `save-drawing-action`, and `check-drawing-action`. The last command creates a task-bound receipt and rechecks supported saved actions; it cannot grant a PASS to an unsupported operation. Only one unresolved action per plan can be claimed at a time. Native desktop edits use [the explicit host envelope and saved return path](desktop-bridge.md); an editor result without a reconciled Scene blocks an old-Scene rebuild rather than erasing the edit.

For the new non-PPT actions, use exact journal keys. `raster_compare` reads `contract`, `vector_pptx`, `vector_render_receipt`, `raster_pptx`, `raster_render_receipt` and saves `comparison.json`. `complete_hidden` reads `contract`, `candidate_ref` and optionally `semantic_review`/`ground_truth_ref`, then saves `asset.png`, `completion.json` and `measurement.json`. `measure` reads `metric_plan`, `preview` and optionally `pptx`/`render_receipt`, then saves `measurements.json`. All input files and output targets belong to the task; a comparison report is recomputed rather than trusted as a text assertion. A raster comparison may be verified as an operation while its representation still needs semantic/editor review.

## Export one consistent delivery

Mark reusable groups explicitly with `component:true` and context-only groups with `component:false`. Group descendants must contain the component's actual natural parts and internal connections. Mixed components may include authorized embedded data images; external linked images and unsupported relationships are rejected.

```sh
python -B /path/sci-rebuild/scripts/sci_rebuild.py export-components SCENE PPTX --out WORK/Components
python -B /path/sci-rebuild/scripts/sci_rebuild.py export-component-assets WORK/Components/Components_editable.pptx --out WORK/component-assets
python -B /path/sci-rebuild/scripts/sci_rebuild.py finalize SCENE PPTX RENDER WORK/Components WORK/component-assets WORK/qa.json --out WORK/delivery
python -B /path/sci-rebuild/scripts/sci_rebuild.py verify-delivery WORK/delivery
python -B /path/sci-rebuild/scripts/sci_rebuild.py install-output WORK PPTX
```

`finalize` uses the shared guarded user exporter: only `Final_editable.pptx` and `Report.md` reach the user. Internal components/logs stay in runtime; actual PDF export validates rendering and is released after dependent checks. SVG/raster exceptions retain their declared editing scope. All final exits run complete resource optimization, current host comparison and delivery verification.

`install-output` promotes a candidate inside WORK to the exact destination reserved by `init-task`; it creates a recoverable backup for an existing authorized destination and refuses external changes. Use the same selected candidate for finalization and promotion. Byte-identical copies share the PPT hash; any subsequent modification requires fresh render, review, and delivery receipts.

An incomplete quality result makes `finalize` return a blocked working delivery/exit 3. `verify-delivery` verifies identities, not scientific correctness. Do not send every intermediate PPT as a final artifact or treat an integrity verdict as quality acceptance.
