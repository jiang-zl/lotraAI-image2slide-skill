For new v1.33 contracts, [functional curves and the current normal route](workflow-v133.md) supersede the legacy scientific-polyline exclusions below. Old tasks are retained until explicit migration.

# Smooth semantic geometry without smoothing scientific data

Use for illustration arc/rounded-outline methods only. Source blur is measurement uncertainty, not permission for polygonal output. Infer only source-supported geometric structure; retain projection, true corners, openings, width/color/radius and layer order.

`core.semantic_curves.arc` creates elliptical cubic Bezier segments of at most 45 degrees. `annular_band` creates a single closed outer/inner contour for a colored signal band. Recipes for radio, wireless terminals, towers and camera radio arcs reuse these operators rather than storing dozens of short straight segments. Native shapes remain separable/reusable; one continuous contour uses one path. Curve generation does not assign a high drawing score.

The shared compiler converts supported semantic illustration paths before `build`. Signal/radio arcs need stable observed circular support; a failed fit requires another source-supported model, not invented geometry. Explicit elliptical support is normalized to the object's original bbox:

```json
{"curve_model":{"kind":"ellipse_arc","center":[0.5,0.5],"radii":[0.45,0.4],"start_degrees":100,"end_degrees":250,"rotation":0,"source_evidence":"Actual source arc projection and endpoints"}}
```

Use existing source-supported `points` alongside that model. A `smooth_outline` model needs `source_evidence` and `corner_indices` (an empty array explicitly means fully rounded). Terminal glass/rounded vehicle bodies have bounded smooth semantics; corner indices can still preserve real kinks. Open ends, genuine holes and opaque cores keep the existing composition contract. The compiler excludes observed/scientific/chart/data-series curves; an illustration model on these is rejected. Never round peaks of a signal waveform or alter scientific observations.

`source_curves.observed_curve` accepts a semantic type/model for an explicitly declared illustration; its default remains unsmoothed observed data. Already compiled native Beziers remain unchanged. During a repair the compiler touches only allowed contour/content fields or an explicitly replaced component; shared/read dependencies do not grant writing. Satisfied bodies, colors, text, geometry and sibling spacing retain existing protections.

`curve_plan` stores source-fit deviation and construction provenance. Tangent diagnostics describe control-point joins only. They do not establish actual antialiasing, material quality, target-render equality or a new metric improvement. For real drawing tasks, use the existing independent natural-part edge/foreground/width/material measures and the relevant neighbor relations. Diagnose geometry versus blur/renderer causes; retain an observed gain only within the original grant. No extra whole-page verification loop is introduced.

For regular schematic parts, use natural-icon-models.md before smoothing. Dense source colour contours and constructed tangent continuity cannot certify regular shape or stroke width. The natural compiler chooses measured preset/analytic band families and original-supported sparse anchors; it never applies illustration smoothing to scientific data.
