# Local edits after the user likes the overall slide

Use this route when the request changes a small part of an existing result. The
reference image measures reconstruction fidelity; the **user-confirmed saved
result** protects work the user already likes. Saying the whole result is good
except for one detail is sufficient user intent to freeze that working baseline.
Do not invent a confirmation for a test deck. A confirmed working baseline is
not automatically full scientific, visual, or native-editor QA acceptance.

## Freeze scope before making a candidate

1. Keep the selected PPT, Scene, assets, actual preview, renderer receipt and
   environment identity intact. `freeze-approved-baseline` validates their
   hashes and the user's confirmation record. A new local instruction starts
   from the current selected version. If the user or an editor has changed the
   PPT externally, the old hash must fail; reconcile that file before another
   edit instead of rebuilding from stale Scene data.
2. Create a separate coordinator authorization for exact object IDs and scalar
   JSON-pointer paths. In the contract, name the intended old and new values.
   `prepare-local-edit` calculates the candidate Scene, write set W, read set
   R, check set C, protected set P, and old/new regions. Reading or rechecking
   a neighbor never grants permission to change it. Unlisted paths on the
   target itself remain protected. Connected-node movement needs explicit
   connector work and real editor verification; a plain bbox patch refuses it.
3. Freeze the allowed display region and renderer protocol **before** viewing
   a candidate. Keep the baseline, no-op rebuild and candidate at the same
   canvas, font inventory and renderer. Do not widen a mask after seeing a
   difference. Unknown filter, crop, rotation, parent transform, or renderer
   changes mean `UNVERIFIED`, not success. The baseline's no-op re-render must
   match across the entire page, including the proposed edit region; renderer,
   environment and measurement-profile changes cannot reuse the old receipt.

## Native PPT route

For an unambiguous existing solid RGB fill, one-run text label or isolated
shape bbox scalar, `patch-native-ppt-leaf BASE.pptx candidate-scene.json
preparation.json --out CANDIDATE.pptx` changes the named native OOXML leaf in a
new task file. It retains other runs, styles, shapes, connectors and media.
Unsupported native structures take another explicit route; never silently
flatten them. Run `check-local-ppt-protection` on the **saved** PPT: it checks
the requested old/new scalar values, all other shape properties, identity and
shared resources. A merely changed coordinate is not enough; an accidental
text character or alpha change must fail. Render and check old/new region,
adjacent objects and the full slide. Native editor save/reopen and promised
editing operations are separate gates; LibreOffice/package checks cannot
stand in for PowerPoint.

For a genuine PowerPoint UI roundtrip, compare a second same-source, same-app
no-op Office save when Office rewrites package parts or inserts proofing
markup. The no-op must preserve saved product properties and rendered pixels;
the edited copy may differ from it only in authorized product leaves and
shared Office serialization. Keep actual font, fill, geometry and sibling
changes protected. This scoped `office_noop_pptx` control needs a separate
host-observed edit/save/reopen receipt and does not certify a user-confirmed
baseline by itself.

## Allowed picture layer route

Only use this for a picture/illustration layer already allowed by the drawing
plan. Work from an RGBA or RGB PNG. Freeze a binary asset mask and any blend
alpha before generating a candidate; the editable context shown to a model is
not its write scope. `compose-local-raster-edit` makes an exact deterministic
composite. Every RGBA channel outside the asset mask must equal the baseline.
For an unrotated, uncropped, full-canvas image with an identity parent,
`freeze-picture-render-mask` can predeclare the fixed-preview filter support.
It refuses other transforms instead of guessing. Include that receipt and mask
in the final image-edit contract **before** generating a new proposal. A
failed candidate remains failed even if a later independent trial uses a
different predeclared mask. Replace only the named picture with
`replace-picture-layers`, then run `check-local-picture-protection` and actual
render protection. The crop, owner, theme, siblings and other native content
must remain unchanged. JPEG recompression cannot prove exact outside pixels.

## Acceptance, selection and recovery

`verify-local-edit-candidate` reproduces the leaf patch from the frozen
contract and separate authorization, checks Scene and saved PPT, validates the
baseline/no-op/candidate render receipts, then checks the protected pixels.
An applicable native-editor operation and a real PowerPoint target receipt are
required for `PASS_LOCAL_EDIT`; alternative rendering remains scoped evidence.
`promote-local-edit` freshly rechecks the verification, compares with the
original long-term anchor using the union of **previously frozen** write paths
and masks, stages a complete immutable bundle, and only then switches the one
selected pointer. `derive-selected-baseline` binds that selected bundle for
the next small change without claiming a new user confirmation or full QA.
Failed, unverified or interrupted candidates stay inactive. Do not repair a
failed check by altering its receipt, tolerance, baseline or mask. For a
sequence of edits, compare with both the immediately previous result and the
original protected anchor. Against the original anchor, the previous selected
preview may differ only inside masks frozen for earlier edits; the new preview
may differ only inside their union with this edit's predeclared mask. Rerun
checks whose inputs or environment changed.

The current full-slide source QA, native component exports, Office behavior,
and final delivery checks remain separate. A local preservation PASS never
upgrades an otherwise incomplete reconstruction to full acceptance.
