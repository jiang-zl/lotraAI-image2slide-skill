## v1.0.3 execution precedence

Retain the applicable type/layer/module construction obligations below. For ordinary drawing, [visual-agent-loop.md](visual-agent-loop.md) controls observation, minimal repair, progressive freezing and the deliverable exit. Do not substitute a full functional acceptance campaign for actual visual improvement. Full-spec certification remains separate. Semantic HD replacement of an allowed illustration preserves known meaning rather than blurred pixels; scientific and native editing promises remain binding.

# Mandatory contract execution (v1.0.2)

The 31 cards in `config/contracts.json` are a routing and obligation catalog, **not 31 automatically proven checks**. For each observed source node, compile the applicable S/T/R cards, freeze a drawing plan, execute it, then inspect the saved PPT and the independent source comparison. A listed `hard_check` in a work order is a requirement, not evidence of fulfillment. Missing evidence stays `UNVERIFIED`; a detected contradiction is `FAIL`. Neither may be rewarded or called complete. The three concrete visual-closure gates remain in [visual-closure.md](visual-closure.md).

## Type obligations: choose from the source, then prove on the saved file

| Card | Required result | Evidence and failure route |
| --- | --- | --- |
| T01 text | Exact observed characters, native editable text | Source `expected_content.text` and saved text check. Missing source transcription is `UNVERIFIED`; mismatch is `FAIL`. Inspect glyph spacing separately. |
| T02 formula | Exact math AST and native Office math | `expected_content.ast`, saved math structure and real edit operation. A screenshot or superscript-looking text does not pass. |
| T03 geometry | Native shape fitting the source contour | Saved native shape and source-relative contour/position review. One continuous exterior follows the one-owner rule. |
| T04 connector | Observed endpoints/direction and native connector where supported | A source relation must bind the connector ID; saved anchors, heads and topology are checked. A genuinely decorative or axis mark needs an explicit source-scoped classification, not invented endpoints. |
| T05 curve/path | Native editable curve or path with observed geometry | Saved path class, control/route points and regional contour review. Do not claim connector reflow for freeform paths. |
| T06 table | Exact cells/merges in an editable table | Source `expected_content.table`, saved cell structure and editor operation where promised. Missing source table transcription is `UNVERIFIED`. |
| T07 natural object | Independently useful natural parts | Observed children, native group, critical-part coverage and isolated component review. A group named “car” with no part inventory is not proof. A source-declared complex raster terminal unit may instead have no independently valuable internal edit. |
| T08 compound region | Meaningful module boundaries and parts | Same child/coverage requirement, plus source alignment, internal text and connections. One continuous exterior is one native owner. A low-level complex raster terminal is exceptional, not a license to flatten visible foreground parts. |
| T09 data image | Source-identified data pixels and independent picture operation | Frozen source region/hash, raster permission and actual replace/crop promise. It cannot stand in for a reconstructible icon. |
| T10 chart | Native axes/labels and source-grounded visual marks | Group/trace mapping, exact text and data identity when values are known; curves without recoverable data state that limitation. |
| T11 texture | Preserve semantic marks and appearance | Source texture role, measured regional quality and native cost. Semantic texture stays vector; decorative texture can use a measured raster exception. |

Before drawing, `plan-drawing` refuses an observed node with missing type evidence or an incompatible Scene render route. The saved-file checker repeats the route, native object class and exact-content checks, and `finalize` reruns the hierarchy so direct delivery cannot skip it. A complex background/illustration photo is a **candidate exception** only if the observed node's `asset_role` matches the picture's semantic role, the task permits that raster scope, and the picture declares its raster editing boundary. It still needs a frozen native-first comparison, cutout workflow where applicable, and visual quality evidence. This exception does not turn an ordinary icon or scientific label into a photo. **No checker can infer that the host labeled the original correctly.** Independently scan source-only omissions after rendering and do not let the candidate's inventory grade itself.

## Levels, roles and workflow modules

| Cards | Mandatory execution | Evidence boundary |
| --- | --- | --- |
| S0 figure, S1 region | Preserve source canvas, global layout and region ownership | Full-slide render, source-only review, grids and parent checks; a good child score cannot cover a failed region. |
| S2 object, S3 natural part | Observe, recursively split at useful editing boundaries and keep parent/child relations | Bottom-up saved native mapping and critical-part coverage; unobserved additions and missing children fail or remain unverified. |
| S4 primitive | Use the simplest faithful native primitive | One matching preset or one closed path for a single exterior; do not globally minimize shape count because natural parts must remain editable. |
| R0 base, R1 background structure | Keep observed z order, visible paths/roads and background continuity | Saved ordering plus source/render comparison. A raster background needs the measured exception and mandatory cutout workflow if cut out. |
| R2 semantic foreground | Keep reusable icon parts and one representation policy per semantic family | Frozen drawing plan, native leaf/group check and component export. |
| R3 annotation, R4 relation overlay | Preserve scientific text, formulae, arrows and relation topology as native objects | Exact content, native connector checks and operation evidence; visual similarity cannot compensate. |
| M01 observe, M02 propose | Source-only observations first; knowledge suggestions are conditional | Located source evidence. A library recipe is a proposal, never a source fact or an executed action. |
| M03 compile, M04 draw, M05 assemble | Work order, frozen plan and actual Scene/PPT | Per-object route, required action journal, saved native objects and parent checks. |
| M06 evaluate, M07 repair, M08 global review | Typed local metrics, located defects and scoped repair; inspect the whole slide again | Bound measurement/review receipts and refreshed saved render. Missing metric/review remains unverified. |
| M09 native operations, M10 deliver | Prove promised edits in the target editor and bind final artifacts | Editor operation receipt, fresh structural/hierarchy check, visual closure, plan conformance and delivery hashes. An inaccessible editor leaves that operation unverified. |

Run only relevant conditional branches: no data-image check for a figure with no data image, no cutout workflow when no cutout exists, and no knowledge-library lookup if the task has no library. Every *applicable* rule must run. If source evidence does not support a threshold, do not fabricate one; keep a located reviewer check or `UNVERIFIED`.

## Selection incentive and repair queue

Selection is lexicographic: (1) source/content/topology/native/closure gates; (2) comparable, source-bound typed metrics and important single-metric floors; (3) simplicity and resource cost only as a tie-break **within the same semantic/editing contract**. A failed hard rule earns zero gate/improvement credit even with better SSIM, IoU or appearance. Candidate records include a bounded `selection.blocking_rules` queue from actual object and child checks. Repair those findings, re-render and re-check; do not rewrite the source, relax thresholds after seeing a failure, rename a raster as a shape, or silently discard an observed part.

## Artifact Tool boundary

OpenAI's `@oai/artifact-tool` can author preset/custom PowerPoint shapes at explicit positions and can run `autoLayout`. For this product, the **source image's pixel coordinates, semantic tree and frozen drawing plan remain authoritative**. The primary Scene builder already writes native presets and custom paths at those coordinates and verifies saved OOXML; Artifact Tool is therefore *not a runtime dependency or a second deck backend* in v1.0.2. Optional use is a one-shape geometry experiment only: freeze source ROI and intended bbox, create a shape in a task-local trial, compare its contour to the source, and transfer the selected preset/path into the primary Scene. Do not import a whole generated slide or let `autoLayout` reposition sibling modules, text, connectors or approved content. If an internal layout operation is considered, it must fit the frozen owner's bbox and pass the same outside-owner protection and saved-PPT checks. A proprietary bundled tool's absence must not break a cloned skill.
