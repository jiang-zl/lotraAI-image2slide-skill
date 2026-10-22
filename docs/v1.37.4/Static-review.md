# 1.37.4 implementation review

Review baseline: published 1.37.3. The earlier claim that compile_scene mutates
its input was not reproduced: table normalization already copies the input.
Whole-owner font authority and exact prior-binding identity were already fixed
in 1.37.3. They are retained rather than described as new repairs.

| Contract | Implementation and independent countercheck |
| --- | --- |
| Text and emphasis | font_resolution extracts logical character/style intervals; bind compares frozen source owners and guard_saved rereads native text/colour/bold/italic. Subdivision may vary; colour loss cannot pass. |
| Complete slots | font_contract records resolved_runs and declared hints. font_resolution performs deep style-map resolution for build and native_core_checks. Saved guards independently compare all slots and original bindings. |
| Intent identity | request_value excludes ordinary hints only under the new policy. Exact requirements and explicit source revisions remain fingerprint inputs; old policy is retained until evidenced migration. |
| Feasibility | eligible and bind use style_feasible, real weight/slant faces and language/glyph/editable constraints. Synthetic fallback is explicitly evidenced and cannot evade an exact family. |
| Family groups | Source observation declares bounded style groups; family_choice consumes a current registered glyph comparison. Known group peers must have feasible real faces and cannot adopt conflicting families. Unknown style needs explicit resources and justification. |
| Preparation progress | Visible batch/IDs/step survive compaction. receive validates on a copy, adopts no partial failed response, records current-source receipts and recognizes exact acknowledged retries. Native bindings remain staged until the existing journal saves. |
| Decisions | Explicit state/route compatibility and diagnostic stops supplement existing decision actions; source-line failures retain their other blockers. Saved instances keep their qualify route. |
| Line preflight | The real writer emits an unsaved package, decoded by the native boundary reader and compared with independent frozen source line facts. No source fact or tolerance is changed to match a default. |
| Native size precision | Writer uses integer centipoints before EMU conversion. Saved XML regressions cover 18.15, 20.15, 12.34 and half-centipoint rounding, ordinary text, Math paragraph defaults and table defaults; the independent size checker is unchanged. |
| Separate marker paint | Independently saved opaque polygon/no-outline/no-effects vertices determine the full marker envelope; source size, tolerance and contact guard remain fixed. Unknown paint keeps the conservative producer. Counterexamples retain remote-glyph differences, reject enlarged/translated/hollow markers and local contact errors, and reject another owner's envelope. Actual marker anchors use actual marker vertices. |

Old-task migration archives ledger/request mappings, requires complete per-request
intent classification and current original evidence, preserves exact authority,
and locally invalidates affected qualification/font/final dependencies. It adds
no task reset or general undo/transaction framework. Native Math policy and the
independent saved/render/final gates remain intact.

Review scope includes callers in new-task creation, component construction,
deferred font review, native instances, portable resources, final qualification,
packet templates and version validation. Tests exercise genuine small font files,
glyph raster ranking, native XML and the real unsaved writer; mocked discovery
is limited to fixture resource classification. Photographic ranking uncertainty
is disclosed rather than treated as calibrated font-identity proof.
The pre-bind source_correction route reuses existing row and original correction
validators under a narrowly scoped internal observation grant. Six counterchecks
retain history/chunks, reject stale prior identities and unsupported weakening,
and prevent an ordinary binding packet from directly writing source observations.
