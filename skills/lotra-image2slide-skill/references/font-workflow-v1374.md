# Source-supported font preparation and recovery

New tasks bind `font-workflow-1.37.4`; old tasks retain their font identity policy.
The current packet is the executable contract. Use its visible `request_ids`,
`batch_id`, `required_step`, template and submit command. Read detailed requests,
comparisons and group members through the returned hash-bound references.

## Finite preparation

Each packet names one missing step. Submit one payload type, limited to its IDs:

- `source_style`: independently observe the original and submit `font_constraints`
  with `style_classes` or an evidenced bounded `resource_ids` set. Use the same
  portable `style_group` ID for source-supported peers of the same script and
  typographic role. A colour change alone does not split a font group. Genuine
  face differences may create separate evidenced groups within one owner.
- `resource_decision`: retain exact user families. Use prepared real resources
  or explicitly request `synthetic_style:true` with separate `style_description`,
  reason and original evidence. Real weight/slant faces take precedence. An
  unavailable face remains a resource decision; do not substitute another family.
- `glyph_samples`: submit isolated `{character,roi}` samples from each current
  original owner. Samples cannot come from generated text or another case.
- `family_choice`: use the registered comparison's candidate families, original
  observations and current `comparison_ref` to submit an evidenced `family`
  through `font_constraints`. This selects a family for the source style group;
  each run still binds a feasible real weight/slant face. Numeric glyph screening
  is not calibrated proof of exact photographic font identity. Keep inference
  approximate and retain alternatives. A single eligible family needs no extra
  family-choice step.
- `bind`: submit the current `font_bindings`, comparison and source evidence.
  Revisions carry the current prior hash and source authority. Keep decisions
  staged until the native save journal adopts them.

Evidence is a returned task-local `{path,sha256}` resource containing the current
`source_hash`, `observer:host_model|human` and located `observations`. Narrowing
also requires `reason`. `unknown` style requires explicit resource IDs and
`unknown_style_justification`; unknown metadata is not evidence of sans lettering.
No global YaHei/Arial preset or page-majority rule replaces original observation.

Related changes are checked atomically. A rejected response returns
`font_submission.applied:false`, rejected IDs and reasons while retaining the
current packet. Record local progress only after an applied receipt. An exact
retry of an acknowledged response reads its stored receipt without repeating
the mutation. After interruption or a lost reply, call `next`/managed resume;
program state determines the remaining step, not a driver's sampled/constrained
flags. Active native bindings and staged decisions remain distinct.

## Intent, complete slots and text protection

Ordinary `style.font` and declared `font_faces` are construction hints. A hint
can influence comparison context without invalidating an adopted legal binding.
Exact frozen task `font_requests` and registered source metadata remain strong
authority. A source declaration can express script-specific requirements as
`font_intent:{required_families:{ea:...},revision:...}`; it cannot invent user or
source-metadata provenance. A changed exact requirement needs scoped revision.
For a newly observed raster family decision without an exact identity claim,
use an authorized `font_intent:{revision:...}` source revision and repeat the
current style/group preparation. The revision is a bounded source-decision ID;
changing an ordinary hint alone does not request a replacement family.

Compilation preserves declared hints separately in `font_plan` and resolves a
complete `latin/ea/cs` map for every ordinary run/cell. Writer and expected native
attributes use this verified plan. Mathematical fonts retain the genuine OMML
policy. Never edit `style.font` merely to satisfy a fallback-slot error.

Original text and logical colour/bold/italic intervals are preserved independently
of font selection and native run subdivision. Do not merge colour spans to obtain
a font PASS. Saved checks reread actual text, emphasis, all planned slots and
bound resources; rendering and independent original-to-output review still apply.

## Deferred review, old tasks and line failures

Keep the one deferred font review after parts and layout. Extended comparisons
may show other eligible families; a family replacement needs an evidenced group
decision in `phase:prepare`, using a revised source-supported `style_group` when
the existing group is revised. Change all peers that remain in that group
coherently, retain user locks and source intervals, then complete normal local
rechecks. No whole-page review is required after every font action.

An old font packet offers an explicit whole-task `font_policy_migration` and
hash-bound inputs. Independently classify every request as a construction hint
or retained exact identity in the provided intent-map schema. Exact authority
cannot become a hint; raster observation cannot invent exact metadata. Migration
retains the prior ledger and request mapping, stages compatible identities and
revalidates samples. New style/group preparation, current native checks and final
gates remain required. Do not reset tasks or hand-edit pending grants.

`SOURCE_LINE_CONSTRAINT_REQUIRED` returns a current source/native/measurement
decision action. Read every blocker. Repair invalid measurements before drawing;
repair a conflicting native plan to match the original. Unknown/incompatible
component states return a diagnostic stop instead of automatic evaluation.
If a sealed original observation is found incorrect before the component contract
has sealed, the binding packet offers `source_correction`. Submit bounded source
rows with its exact checkpoint, prior observation, prior row hashes, revision
reason and located source evidence. Existing source/spatial correction guards
retain obligations and quality bounds; old observations and binding chunks stay
in history. This is a source decision, never permission to redefine the original
to fit a failing native plan.
After contract sealing, a focused `source_or_measurement_decision` packet also
offers `source_feature_correction`. Its `source_correction` carries the current
prior observation and complete corrected feature rows with prior hashes. Only
the selected component subtree's existing source features can change. The
existing original-domain, line-limit and spatial guards still run, observation
history is retained, and the next explicit contract rebind precedes native work.

Before construction, the real writer's unsaved emission is checked against frozen
line routes, defaults, joins/caps, markers, topology and terminal sites. A
`LINE_PLAN_CONSTRAINT_REQUIRED` diagnostic names the line/criterion and private
report. Correct the plan through the current packet. Never change original facts
or widen tolerances to agree with a writer default. This preflight is separate
from saved-byte, actual-render and every-line final acceptance.
Visible shaft-to-shaft contacts use source `attachment.kind:line_junction` with
an open line target and an explicit incident junction at that terminal. Current
peer geometry and reciprocal source topology remain required. Unlike a closed
shape port, this contact does not claim automatic native connector rerouting;
use the documented unanchored junction representation, without hidden anchors.
Preflight reports are registered current task dependencies even when validation
rejects the plan; read their returned hashes through the managed selector.

Current component packets provide `current_candidate` with the exact saved PPTX
and Scene references, plus render/preview references when they exist. A first
candidate can have no selected `baseline`; use its current references for layout
evidence. An absent render is still absent evidence, never a visual PASS.
Scoped native saves retain untouched legacy nodes when compilation merely
expands equivalent font-slot maps. Effective slots and bound resource identities
must agree; real font, resource, text or emphasis changes outside the grant are
rejected and require their own focused source/native revision.

Font discovery retains an immutable project-local catalogue for each descriptor.
Other render/backend commands may update the discovery cache without replacing
the task's frozen catalogue. A legacy task whose shared catalogue was replaced
uses the existing normal capability refresh on `next`; old bindings, source and
native bytes stay retained. Current resource/renderer checks and any required
re-render still apply. Snapshot tampering and changed font files are not a PASS.

Native text, mixed-Math paragraph defaults and table defaults quantize font size
once to DrawingML hundredths of a point. A supported 18.15 pt intent therefore
serializes as `sz=1815`; saved-size checks retain their independent integer read.
