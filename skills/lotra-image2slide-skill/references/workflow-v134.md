# v1.34 source features and native surface workflow

Use this reference for new tasks and explicit migrations to workflow_version
1.34.0. Component schema/design_revision remains component-protocol-1.32.0 / 8.
Already-bound contracts retain their policy. Do not select an older policy for
a new task or downgrade a v1.34 contract to avoid unresolved source features.
The v1.33 functions, shared original-problem budgets, private knowledge lifecycle
and incremental runtime preparation remain in [v1.33 operations](workflow-v133.md).
Ownership, native journal, mother/instance phases and scoped repairs remain in
[component operations](component-workflow-v132.md).

## Observe before choosing owners

Ordinary next first requests component_contract_source / source_features.
Submit component_request.observation, or use component-workflow observe_source.
The program retains an immutable original-only observation before native binding:

```json
{
  "schema": "source-features-1.34.0",
  "source_hash": "CURRENT_ORIGINAL_SHA256",
  "canvas": [100, 100],
  "basis": "unchanged_original",
  "observer": "host_model",
  "observations": "Located observations from the unchanged original.",
  "units": [{
    "id": "part", "roi": [0, 0, 100, 100],
    "source_evidence": "Original object location and interpretation.",
    "decomposition": {"state": "leaf", "reason": "All visible structure is expressible by the chosen semantic parts."}
  }],
  "features": [{
    "id": "part.outline", "unit": "part", "kind": "silhouette",
    "roi": [0, 0, 100, 100], "observability": "clear", "required": true,
    "source_evidence": "Original visible contour.",
    "requirements": ["editable", "closed_contour"]
  }]
}
```

Replace the example with current-source facts. Units form an acyclic semantic
tree using parent. decomposition is split, leaf or unresolved, with a reason;
split must have actual children. Stop when a supported constructor can preserve
all observable structural/detail/material information and a meaningful check is
possible. Do not invent anatomy or split anti-aliasing into semantic objects.

Features cover silhouette, surface, internal_line, color_region, hole, symbol,
text, math, curve, band, detail, relation and genuine texture. Visibility is
clear, partial or unresolved. Required unresolved features/units cannot qualify.
Optional features need not_required_reason; they remain in correspondence and
the independent omission review. Observations contain no candidate/native owner
fields. Preserve located source evidence, uncertainty and original hash.

Feature metrics are optional where independently measurable. They are frozen
target records with measurement coordinates relative to that feature's ROI;
use registered component/surface producers and predeclared thresholds. A metric
cannot disappear, loosen, or become optional after failure. Correcting original
facts requires revision_reason and source_corrections[{feature,source_evidence}],
retains both observations and does not reset original-problem budgets.

## Bind the simplest adequate native representation

The source_inventory in bind retains the observed units, parent, ROI, evidence
and decomposition decisions. Each feature has one feature_bindings entry:

```json
{
  "feature": "part.outline", "component": "part",
  "owners": ["native.part"],
  "representation": {"family": "preset"}
}
```

Every paint owner needs original feature correspondence. Assemblies may bind
their actual descendants; groups do not waive leaf coverage. Programs attach
source_features, feature_bindings and feature_basis to scoped component rows.
Read only current rows/resources through managed detail selectors.

Native tables retain their existing structured cells. A text feature bound to a
table owner uses family native_text plus representation.table_cell [row,column]
and the exact original literal in feature.text. Every populated native table
cell needs its own text correspondence; one table/grid binding cannot waive
cell contents. Table grid/material features may use native_composite with their
source-supported preset limitation. Existing cell/font/merge checks still apply.

Prefer preset geometry with fill/outline, then compact native composites or
shared surfaces, then finite native paths/cubics. Native_text, native_math and
native_connector are typed routes. Native_composite/native_surface require a
source-supported simpler_options rejection for preset. Native_path/native_cubic
also explain why a simpler composite is inadequate. Each rejection has family,
reason and source_evidence. Geometry/material/edit requirements take precedence
over object count. Do not replace one difficult part's whole parent with raster.

Requirements supported by capability preflight are editable, closed_contour,
smooth_contour, corners, hole, color_partition, variable_width, inner_wall,
shared_edges, surface_shading, projection, occlusion, text, math and
independent_parts. They are checked against actual owner types/styles and
registered construction outputs, not an unchecked claimed capability list.
Capability checks establish representational support, not semantic truth.
Bitmap exceptions are restricted to declared texture/photo purposes and cannot
silently satisfy native icon requirements. Dense color strips are not a compact
semantic reconstruction; pixel samples are measurements, not drawing commands.

## Source-declared 2.5D constructors

bind accepts optional native_constructions and expands them into ordinary Scene
owners before validation. Names are ID.part; list every generated owner in the
normal component ownership contract and feature correspondence. Existing IDs
must match the constructor; collisions preserve prior objects and require a
decision. A constructor never invents hidden walls or source paint.

| kind | Source parameters |
|---|---|
| prism | footprint vertices, depth vector, top_style, explicit visible walls [{id,edge,style,role?}] |
| extruded_contour | continuous closed contour, depth, front_style, walls [{id,first_segment,segment_count,style,role?}] |
| elliptic_solid | center, radii, depth, optional start/end_degrees and rotation, top_style, explicit walls [{id,role,span,style}] |
| annular_sector | elliptic_solid plus inner_radii; inner/outer walls and observed end_caps [{id,at,style}] |
| ellipse_stack | bounded levels [{id,center,radii,style,rotation?,role?}] |
| band | independent open upper/lower native contour commands and style; no forced constant width |
| planar_detail | points or contour, style and optional source-supported frame |

Contour commands are moveTo/lnTo/cubicBezTo/close with points arrays. Styles use
ordinary native fill, stroke, line_width and supported linear/radial gradients.
Explicit paint_order lists every generated part once. A prism's visible_edges
reference top.INDEX or bottom.INDEX and their shared vertices, with id/style.
Fill and visible edges are separate: do not double-stroke shared/hidden edges.

Coordinates are source pixels. An optional frame has source_evidence and either
origin/u/v or a 3x3 homography. Straight planar edges remain straight;
projective curved outlines use bounded native cubic encoding with frozen
precision_source_px. Singular/unsupported/over-budget geometry returns a
representation decision. A single view does not identify true hidden 3D.

## Measure the actual saved result

Programs sample/fit numerical parameters; the current model decides meaning,
visibility, decomposition, representation and ambiguity. Fixed/tunable is an
execution state, not source confidence. Preserve each parameter's source facts,
measurement or inference and uncertainty; never freeze a guess into truth.

In addition to existing boundary/keypoint/curve/width metrics, registered actual
image probes include edge_angle_error (degree), ellipse_ratio_error,
extent_ratio_error/thickness_ratio_error (ratio), face_color_error and
occlusion_color_error (normalized_rgb), face_lightness_error
(normalized_luminance), gradient_profile_error (normalized_rgb),
band_width_profile_error and junction_error (source_px), hole_count_error
(count), and feature_missing_fraction (ratio). Freeze window or windows,
source_evidence, foreground selectors and applicable probe points/rays before
candidate observation. Measurements use the same unchanged source and saved
preview coordinates; no per-candidate alignment or hidden rescaling is allowed.
Missing/clipped/ambiguous support returns invalid, never a passing zero.

Qualification records distinct source_basis, native_consistency and appearance
channels. Fixed parts retain one native parameter check; their appearance is
confirmed at complex assembly/final review rather than repeatedly chasing pixels.
Assemblies/instances cannot disable v1.34 local visual checks. Evidence binds
current source/PPTX/preview hashes and feature_basis, and contains
feature_checks[{feature,verdict,observations}] for every required current feature.
Declared feature probes are also executed against saved pixels. Parts then
mothers, actual instances and layout precede the single deferred font review.

## Final review, omissions and focused repair

Keep the six existing whole visual dimensions. Add source_feature_review with
source_observation_hash, bindings_hash (the current feature_bindings identity),
basis original_to_output, observations, complete feature_checks, complete
omission_checks[{unit,verdict,observations}], and unmapped_features (empty only
when none were found). Re-read every original unit independently of the owner
list. Program edge diagnostics locate suspicions; they cannot waive a unit or
prove semantics. Any discovered missing feature returns to an explicit source
revision and focused native journal application.

Final audit independently verifies current saved render, source basis,
correspondence, declared probes and whole judgment. Structural/content failures
cannot be averaged away by background similarity. Repair types are source
omission, inadequate representation, parameter error, invalid measurement,
native mismatch, relation error and source ambiguity. Use existing source
decisions/repair batches and shared budgets; preserve independent bests and
unrelated approved work. No whole review runs after each local edit.

Exact text, genuine OMML, language-restricted fonts and native hierarchy remain
mandatory. No Office open/edit/save-reopen behavior test is introduced. Report
unexecuted/excluded channels separately. The public personal catalog stays empty;
reuse transfers source-free methods and never another original's facts or PASS.
