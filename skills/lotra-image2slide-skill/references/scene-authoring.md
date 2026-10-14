# Author a Scene from the original image

Inspect the full source before working on local regions. Record observed text, mathematical structure, semantic objects and natural parts, directed connections, data-image regions, occlusion, and unresolved findings. Unknown content stays unresolved. Task coordinates and labels belong in task data, never in runtime code. See the [host workflow](host-workflow.md) for the source-only omission review.

## Preserve coordinates and evidence

Scene coordinates and evidence object `bbox`/`roi` values are source-pixel `[x,y,width,height]`. The canvas records `width`, `height`, `unit:"px"`, and `target_width_inches`. Preserve the source aspect ratio. A font size measured in source pixels converts to points as `pixels * target_width_inches * 72 / canvas.width`.

Resource paths are portable paths relative to the Scene file. Required top-level fields are `schema_version:"0.1"`, `revision`, `canvas`, `source`, `evidence`, `profile`, `objects`, `relations`, and `prototypes`. Each resource is `{path,sha256}`. Freeze the unchanged source and the shipped `config/quality.seed.json`. Source evidence should include `revision`, `source_hash`, and observed objects with `id`, `roi`, `evidence_status`, and `observation`. Keep independent source-only findings and ambiguities as evidence; they are not candidate scores.

Each object has `id`, `semantic_type`, `render_type`, `parent` or null, `bbox`, `content`, `style`, four-facet `versions`, four-facet `locks`, and `evidence_status` (`observed`, `inferred`, or `unresolved`). The facets are `content`, `structure`, `style`, and `placement`. Containment must be acyclic; scientific feedback connections need not be. Unknown semantics must not disappear merely because a renderer type is unsupported.

In the independent Source Analysis, mark every observed single continuous exterior with `continuous_outline:{"kind":"single","render_id":"OutlineOwner","source_evidence_refs":["located-observation-id"]}`. The owner is one native preset shape or one closed native path; its text may be another node. Callout/bubble classes require this declaration automatically; visibly bordered label boxes require the host to declare it, while an unbordered textbox does not. Do not map the exterior to separate body, pointer and seam-mask objects. If the source has genuinely disconnected contours, represent separate semantic owners rather than using that fact as an exception for a fragmented single border. See [mandatory visual closure](visual-closure.md).

An evidence correction needs a new evidence version, a source-grounded reason, and invalidation of prior dependent checks. Never change the source/profile to accommodate a failing candidate.

## Use native representations by type

| Render type | Content and boundary |
| --- | --- |
| `shape` | Native presets include `rect`, `roundRect`, `ellipse`, `cube`, `rightArrow`, `wedgeRoundRectCallout` and the other entries in `scripts/core/presets.py`; optional `adjustments` and `radius_px`. Use a preset only where its actual form matches the source. A single continuous callout border and pointer require one matching preset or one closed native `path`, with text separately editable as needed. |
| `group` | Children are natural parts with absolute source-coordinate bboxes. A meaningful panel can include its body, title, submodules, and internal connections. Names/grouping alone do not establish semantics. |
| `text` | `text` for plain text; `paragraphs` is an array of run arrays. Runs contain `text` or an actual math `ast`, with optional font/style overrides. |
| `equation` | `content.ast` produces native Office math. No picture, rich-text superscript, SVG, or LaTeX-text fallback counts as a formula. |
| `connector` | Semantic `source`/`target`, actual endpoint anchors, builtin arrowheads, and supported straight/orthogonal routes. See the port rules below. |
| `path` | Normalized `contours` with `points` and `closed`, or `geometry_ref:{path,sha256}` to a JSON asset. Produces native editable custom geometry. |
| `trace` | `geometry_ref` to a curve asset containing measured tone `layers`. Produces one semantic native Group with real path layers; they are display layers, not invented scientific parts. |
| `bezier` | Four normalized cubic control points in `content.points`; produces a genuine cubic path. It is not a promise of connector auto-routing or anchoring. |
| `photo` | Independent embedded raster with `path`/`sha256`; semantic type is `photo`, `experimental_image`, or `data_image`. Keep axes, captions, and schematic structure native. |
| `table` | `rows` is a nonempty rectangular string matrix; produces an editable native table. Real table-editor coverage remains task-dependent. |

Mark reusable groups with `component:true`, including explicitly chosen nested groups. Set `component:false` on context-only groups; legacy unmarked root groups are selected by the exporter. Include only the component's own natural parts and internal labels/connections. Selected mixed components can retain embedded image relationships; unsupported external links are rejected. Root `z_order` controls painting order; the builder creates native endpoint objects before dependent connectors and recomputes group extents.

### Original identity photographs

Use independent native `photo` objects for unchanged original identity photos. Freeze each source part's integer `roi` and `quality_intent.purpose:photo_identity` before construction. A raw method can include photo placeholders plus `source_photos:[{object:PHOTO_ID,part:FROZEN_PART_ID,source_roi:[x,y,w,h],source_note:ORIGINAL_WINDOW_EVIDENCE}]`. The program verifies the current original and frozen ROI, crops its decoded pixels without enhancement, creates the hash-bound resource and derives that part's object binding. Every cell remains independently selectable and obeys the shared frame/cover plan. Never wrap a photo in thousands of coloured SVG rectangles merely to bypass the raster gate.

This path preserves existing source photos; it does not authorize generated or enhanced illustration assets, whole-figure screenshots or scientific labels as photos. Those representations retain their own content/editability and actual quality-trial requirements. Source grid cells require distinct atomic objects even if two original windows intentionally have the same pixels. The original-only valid content window and the final native picture frame remain separately checked.

For an analyzed complex raster (`environment_asset` or `illustration_asset`), `content.cutout_workflow` must declare `kind:"cutout"` or `kind:"uncut"`. A cutout binds the before/enhanced/final asset sequence and mandatory reviews described in [visual closure](visual-closure.md). A transparent asset cannot claim `uncut`; an opaque crop still needs a source-grounded uncut reason and source evidence. The renderer and builder recheck the referenced bytes instead of trusting a method name.

Common style fields are `font`, `font_size` in points, `bold`, `italic`, `color`, `align` (`left`, `center`, `right`), `valign`, `wrap`, `line_spacing`, `rotation` in degrees, `fill`/`stroke` as hex or null, `line_width` in points, `dash`, and `gradient:[top_hex,bottom_hex]`. No implicit shadow is required. Check actual multiline baselines and neighboring shapes: a fitting textbox extent does not prove its glyphs avoid an adjacent border or symbol.

## Encode mathematical structure

Supported AST operators include `token`, `seq`, `sub`, `sup`, `scripts`, `accent`, `fraction`, `sqrt`, `sum`, `matrix`, `cases`, and `delimited`. The script forms name their `base` and `sub`/`sup`; an accent has `body` and `mark`. Hat uses U+0302. `delimited` has `left`, `right`, and `body`, preserving argument/index scope.

An inline mathematical label can use:

```json
{
  "paragraphs": [
    [{"text": "Estimated signal "}, {"ast": {"op": "accent", "mark": "̂", "body": {"op": "token", "text": "x"}}}]
  ]
}
```

Mathematical-token whitespace is normalized as layout. An explicit `normal:true` token preserves normal-text spaces. Signs, variables, indices, and delimiter scope remain scientific content. Do not use normal tokens to conceal unsupported math. A saved native math zone must still undergo an actual editor change, save, reopen, and independent structure/render check.

## Attach connectors to visible objects

A routed connector uses absolute `content.points` with `coordinate_space:"canvas"`. `source` and `target` are semantic object IDs. `source_anchor_object` and `target_anchor_object` may refer to the corresponding visible frame/body within a group. A scene dependency by itself is not a native connection.

Site numbers are `0` top, `1` left, `2` bottom, and `3` right for this route. Add `content.connection_sites:[[u,v],...]` to a visible rectangle, rounded rectangle, ellipse, or picture; added sites start at index `4`. Values are normalized to that object's bbox. For example, `[1,0.25]` places a port on its right side one quarter down. A justified outside site can preserve a visible label/axis gap; record that purpose.

The backend writes width/height-dependent native geometry guides for these ports, so their positions scale with the visible object. They are actual connection sites on that shape/picture, not hidden proxy rectangles. Do not substitute raw path-coordinate constants for those guides. Validate node movement on the saved Office file, including any grouped anchor part.

Use `source_anchor:false` or `target_anchor:false` for a genuinely unsupported free endpoint or visible line-to-line junction and record the limitation. Axis annotations can omit semantic endpoints. Never invent a hidden anchor object to obtain an apparent PASS.

`arrow:"triangle"` places a builtin head at the target; `arrow:"none"` omits it. Add `start_arrow:"triangle"` for a double-headed comparison. Straight routes use native `line`; two through five alternating orthogonal segments use `bentConnector2` through `bentConnector5`. Duplicate/collinear intermediate points are simplified. Arbitrary many-segment or nonorthogonal routed shapes are rejected by this connector backend rather than silently becoming freeform paths.

U-shaped routes with aligned start/end coordinates need a small nonzero native extent for valid guides. The implementation records endpoint quantization; inspect the actual saved route. Do not claim zero error, universal elbow routing after node movement, or support for every PowerPoint endpoint type.

## Extract only identified observed plot data

Use the generic command after the host has identified exact plot interiors:

```sh
python -B /path/sci-rebuild/scripts/sci_rebuild.py extract-assets WORK/inputs/source.png WORK/requests.json --out WORK/new-assets
```

Requests are an array with `id`, integer `roi:[x,y,width,height]`, `kind`, and `meaning`. `data_image` crops only that data rectangle. Its Scene photo also needs `source_roi`, `purpose`, and `original_numeric_data:"unavailable"`. Such an object is independently replaceable/croppable; its internal pixels are not claimed to be native editable scientific objects or recovered numeric data. Do not relabel an icon or a complete page as a data image to bypass reconstruction.

`curve_path` extracts observed colored pixels as path contours. The default `dominant_channel` mode specifies `dominant_channel:"r"|"g"|"b"`, `min_chroma` (default 35), and `min_value` (default 100). The ROI must exclude captions, borders, axes, and unrelated objects. Add `tone_layers` from 1 to 16 to partition the selected pixels by observed chroma and represent measured colors rather than a single flat fill. Each layer retains a measured RGB median, mask/hash, and editable contours. The layer union must equal the selected mask and layers must not overlap.

For an identified overlapping-color plot on a **known white background**, use `mode:"compound_rgb"`. This mode requires `dominant_channel:"b"` or `"r"` and exactly `tone_layers:8` (or omit that field for its fixed default). To represent both display allocations, request both channels with the same ROI. It selects pixels at RGB Euclidean distance greater than 35 from white, allocates `B>=R` to the blue display and `R>B` to the red display, and uses deterministic RGB median-cut tone groups. Neutral overlap pixels go to the blue display. Legacy chroma/value filters do not apply in this mode.

This allocation describes visible composite pixels; it does **not** recover clean/noise signals or physically attribute overlapping samples. It is unsuitable without review for colored/nonuniform backgrounds. Source hash, extractor version, fixed foreground rule, palette, mask partition checks, and actual color-error measurements are recorded in the assets. These are extraction diagnostics, not proof that the PowerPoint rendering matches the source.

Example request pair for a host-identified composite plot interior:

```json
[
  {"id":"observed_blue","roi":[40,80,160,60],"kind":"curve_path","meaning":"Blue-side display allocation of the observed composite waveform; original numerical samples unavailable","mode":"compound_rgb","dominant_channel":"b","tone_layers":8},
  {"id":"observed_red","roi":[40,80,160,60],"kind":"curve_path","meaning":"Red-side display allocation of the same observed composite waveform; no physical unmixing","mode":"compound_rgb","dominant_channel":"r","tone_layers":8}
]
```

Those coordinates are illustrative input annotations, not a runtime template. Inspect every extracted mask and the actual native render. Changing an extraction mode/parameter creates a new asset version and requires affected evidence to be rechecked; do not overwrite frozen masks or alter the reference to hide a defect.

## Iterate with versioned local patches

Use the coordinator grant and dependency/lock checks in [quality rules](quality.md). `record-candidate` stores exploratory local measurements and candidate snapshots, not a semantic verdict. Apply a purposeful fix, recompile the affected Scene state, and review the changed objects, neighbors, and connections. A correct object needs no redundant repair; a budget or stalled candidate never becomes accepted merely because work stopped.


Native geometry boxes/contours use the source coordinate frame. `style.line_width`, `font_size` and tracking use PowerPoint points. Do not copy a measured source-pixel ink width into a point field. `core.native_source_units.points_per_source_pixel` reuses the actual saved slide size; `outline_proposal` emits only the existing independently bound leaf `style.line_width` grant with its explicit source/native conversion. Preserve actual group frames; anisotropic/local group transforms require a separate source-supported plan. Program-unit conversion is not quality evidence; actual own outline/material and affected gaps decide retention.
