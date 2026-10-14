# Windows Office program export, independent of desktop input

For saved-file drawing/paper export, `core.office_bridge` calls the existing `run_office_job.ps1` and `render_office.ps1`. Capability discovery checks known installed paths or explicit project configuration, on Windows or WSL. The wrapper stages exact bytes locally, opens its own copy read-only/without a window, exports PDF/PNG and native text ink bounds, then closes only that copy. It never quits a shared Office application or changes machine policy. Actual receipts identify Office version/build and input/output hashes. Export is not proof of interactive editing behaviour.

Use `.lotraAI-build/toolchain/runtime.json` to configure `windows_office` paths or disable that adapter; `render_preference: libreoffice` explicitly selects the alternate renderer. Non-WSL Linux/macOS use available native builders/alternative renders and configured host tools. Connected editor routes remain host-specific; never assert universal Office availability.

v1.9.0 privately caches installed font metadata/file hashes, known directories and actual renderer files. Windows/WSL resources follow the Windows Office route; Linux/macOS retain their own identities. Existing Mac PowerPoint application metadata is discovered separately from a connected editor capability. Cheap resource/configuration stamps refresh changed environments; no recurring GUI probes or forced software/font installs. Cache data is `.lotraAI-build/toolchain`, not the skill package. [Font delivery](font-portability.md) uses direct complete static TrueType resources or an existing compatible provider. A provider save can change layout, so only its font parts are transferred; native slide content stays from the controlled candidate. Use [path boundaries](path-portability.md) before host conversion.

Windows Office is preferred when its installed program is discovered. A concrete failure preserves the staged work and its cause for inspection; do not blindly retry, kill shared apps, or replace an Office result with a pretend success. SVG export filters vary by installation. Paper export uses an Office-native private layout carrier with unique frozen slot identities and reinserts the original pure SVG masters at those exact transforms/paint positions. Compatibility-image recompression must not be resolved by guessing photographic similarity. Original PPTX is untouched. Residual raster resources are explicitly counted.

For drawing reviews, localized work packets expose at most eight actual Office text/equation ink boxes, bound to their receipt. Use these facts to diagnose widths/clearances; preserve source layout and satisfactory properties. Interactive editor operations below are needed only for an actual requested desktop edit, not a mandatory functional-testing campaign.

# Target-editor Computer Use for WSL and other hosts

The task directory may be in Linux while the useful editor is on Windows or macOS. Treat filesystem access, desktop control, native editability and a saved visual result as four separate capabilities. Never infer an app's availability from the OS alone.

An UNC task file may open in PowerPoint Protected View. Keep that original intact; copy its verified bytes to a Windows local task directory and edit the local copy through the available Computer Use surface. Do not click an editing-enable control to bypass the view. Recheck the actual app inventory when a different Computer Use route becomes available; a previous empty inventory does not describe all host routes.

1. **Preflight the actual GUI surface when an interactive edit is needed.** Query the host's available native windows/apps and their titles before choosing a route. In WSL, make a task-owned PPTX copy under a path the Windows desktop can open (`\\wsl.localhost\<distribution>\...` or a verified mounted drive). Check that Windows sees the exact copy and record its SHA-256. On macOS use a verified absolute path. If GUI Computer Use reports no native app/window, record that GUI limitation separately. Discover configured/installed Office program export independently; a GUI failure does not imply COM/Office export failure. Never synthesize a PowerPoint success from LibreOffice.
2. **Keep one writer.** The coordinator alone may operate the selected task copy in the desktop editor. Do not close, save, or switch unrelated user documents. A stalled COM/automation bridge is a capability failure; inspect its concrete state before any retry. Do not blindly repeat the same timed-out command or kill the shared app.
3. **Act from current observations.** Read a fresh accessibility state or screenshot after opening, selecting, changing and saving. Use a named selection pane for small covered members; visually confirm the exact selection before typing or moving. UI indexes and focus are ephemeral. A text caret may silently turn a planned geometric move into a text insertion. Record the intended old/new leaf and the app action; never use the action log alone as proof.
4. **Save, close the task copy, reopen it and probe behavior.** For native text/formula, edit the declared run/equation; for grouped icon parts, move/color/copy the promised member; for connections, move the endpoint node and inspect all affected connectors; for an allowed picture layer, replace/crop/duplicate that independent picture. Record app/build, operation, task-copy input/output hashes and located screenshots. Verify the promised object still supports the operation after reopening. Illustrator/other editor edits can prepare a donor, but their exported artwork is not proof of PowerPoint-native editability until the PPT itself is checked.
5. **Compare the actual product.** Run saved-object comparison and a same-size target-render comparison against the frozen working baseline. Check every protected sibling, text style, relation, formula, mask and source-relative spacing. For local edits, use the original cumulative anchor, frozen W/R/C/P contract and predeclared renderer support. A changed action with unintended text/style or out-of-mask pixels is a failed candidate, even if the requested leaf also changed. Keep the previous selected version.

Record `NO_NATIVE_SURFACE`, `TASK_COPY_OPENED`, `EDIT_OCCURRED`, `SAVED`, `REOPENED`, `PRODUCT_PASS`, `RENDER_PASS` and `NATIVE_OPERATION_PASS` separately; no early stage implies a later one. If the host is unavailable, state which capability was absent and keep target-editor acceptance `UNVERIFIED`. Resume from immutable task artifacts when a suitable host is connected.

PowerPoint may reserialize unrelated OOXML parts and add text proofing markup on any save. When strict package comparison flags this, save a second, byte-identical source copy in the same Office session **without editing**. Require the no-op copy to preserve all saved product properties and the full alternate render. Then compare the edited copy against this control: only their shared package rewrite can be attributed to Office. The host must separately witness the actual no-op operation, text selection, edit, save, close and reopen. `verify_local_change(..., office_noop_pptx=...)` checks saved product properties; it never proves the editor action or visual quality by itself. A changed font size, actual bold/italic state, geometry, sibling, or extra package part still fails or remains unverified.

## Executable action handoff

The runtime cannot call a particular desktop tool on behalf of every host. The
agent first observes its **currently connected** official Computer Use surface
and writes `WORK/host-capabilities.json` as task data. Use this compact shape:

```json
{"schema_version":"host-capabilities-1","hosts":[{"host_id":"windows-local","os":"Windows","session":"observed-session","observed_at":0,"expires_at":0,"operations":{"native_edit":{"level":"CONTROLLABLE","app_id":"actual PowerPoint app id","tool":"actual official Computer Use route"}}}]}
```

Replace the zero timestamps with the current observation and a short expiry;
never copy an old app ID or claim a capability level that the tool did not
show. `OBSERVABLE` is insufficient for an edit; the route must currently be
`CONTROLLABLE` or stronger. A path editor can declare `path_edit`, and a picture editor
`picture_edit`, but the returned PPT must still be the planned task-owned
native-edit output. A discovered app alone is insufficient for dispatch.

Create `WORK/desktop-request.json` with `schema_version:
desktop-action-request-1`, the frozen plan's `action_id`, a stable
`operation_id`, `edit_kind`, `host_id`, task-relative `input_pptx`,
`input_scene`, `output_pptx`, the two input SHA-256 values, `target_owner`,
`allowed_change`, `protected_scope`, `expected_change`, and `on_failure`.
The request also contains `protection`. For a native leaf, use
`{"kind":"native_leaf","preparation":{"path":"...","sha256":"..."}}` and
optionally a frozen `office_noop_pptx` file reference. `allowed_change` must
equal the preparation's exact `write_set`; `target_owner` must be one of its
objects. For an allowed picture layer, use
`{"kind":"picture_layer","picture_request":{"path":"...","sha256":"..."},"replacement_receipt":{"path":"...","sha256":"..."}}`;
`allowed_change` names its one shape ID and `media_sha256`. Both routes are
recomputed against the actual saved PPT during import and later audit.
Optional `host_input_path` and `host_output_path` carry the actual Windows or
macOS path; the workspace-relative paths remain the identity source. The plan
action must declare `native_edit` and `Candidate.pptx` plus
`desktop-result.json` as expected outputs.

```sh
python -B SKILL/scripts/sci_rebuild.py claim-drawing-action WORK WORK/drawing-plan.json ACTION_ID OPERATION_ID WORK/action-inputs.json --route 'HOST_ID|APP_ID|OFFICIAL_TOOL' --output-targets WORK/output-targets.json
python -B SKILL/scripts/sci_rebuild.py prepare-desktop-action WORK WORK/drawing-plan.json WORK/host-capabilities.json WORK/desktop-request.json --out WORK/desktop-envelope.json
```

`action-inputs.json` maps `pptx` and `scene` to the absolute task-owned input
files; the envelope is created **after** the claim. The route is exactly the
three currently observed host/app/tool IDs separated by `|`. `output-targets.json` maps
`Candidate.pptx` and `desktop-result.json` to new task-owned output paths.
Claiming the action reserves a candidate slot and prevents a second unresolved
action from starting. If the UI call times out, inspect the frozen output paths
and reconcile the interrupted action before another click; a new operation ID
must not be used as a blind retry.

After the real app operation, write `WORK/desktop-observation.json` with
`schema_version: desktop-observation-1`, the same operation/plan/host/app/tool
IDs, ordered event strings `TASK_COPY_OPENED`, `EDIT_OCCURRED`, `SAVED`,
`REOPENED`, the saved `output_sha256`, located `window_observations`, and
`target_after`. Its `product_check` is `{path,sha256}` for the task-relative
saved-product report generated by `check-local-ppt-protection` or
`check-local-picture-protection`. That report must say
`PASS_SAVED_PRODUCT_ONLY` and bind the saved candidate hash. Screenshots alone
do not satisfy this file binding.

```sh
python -B SKILL/scripts/sci_rebuild.py import-desktop-result WORK/desktop-envelope.json WORK/desktop-observation.json WORK/edited/Candidate.pptx --candidate-scene WORK/edited/scene.json --out WORK/desktop-result.json
python -B SKILL/scripts/sci_rebuild.py save-drawing-action WORK OPERATION_ID WORK/action-outputs.json
python -B SKILL/scripts/sci_rebuild.py check-drawing-action WORK OPERATION_ID --out WORK/edited/action-check.json
```

Omit `--candidate-scene` if the edit cannot yet be represented in Scene. The
import then records `SAVED_PPT_AUTHORITATIVE_SCENE_SYNC_REQUIRED`; that saved
PPT remains a candidate, and `compile-task` blocks a rebuild from the old
Scene. After checking and sealing the action, create a Scene matching the
saved PPT and run `reconcile-desktop-scene WORK WORK/desktop-result.json
WORK/reconciled-scene.json --out WORK/desktop-reconciliation.json`. This adds a
new immutable reconciliation receipt and updates only the task's pending
pointer; it does not rewrite the original editor observation or action result.
An imported return is not automatic final selection or a visual-quality claim.
If the Scene changed, compile a new drawing-plan revision for later work;
keep the earlier action's plan and receipt immutable.
