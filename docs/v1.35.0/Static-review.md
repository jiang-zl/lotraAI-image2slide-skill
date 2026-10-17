# v1.35.0 static call-chain review

Scope: source reading and edits only. No tests, syntax/import/CLI checks,
reconstruction, rendering, environment startup or performance measurements.
Historical v1.34 receipts do not qualify v1.35. Source/package identity is a
publication fact, not behavioral or artwork acceptance.

| Approved design | Production call chain and static finding |
|---|---|
| Hierarchical recognition | next_action source_features -> observe/validate_observation -> spatial_frames.validate_observation. Every unit declares spatial mode, frame, placement, container and observability. |
| Recursive semantic decomposition | Existing original units/features and decomposition stops retained; source_inventory includes spatial decisions. Every semantic container declares direct-content aggregate centering. |
| Spatial reference frames and 3D pose | spatial_frames.Frames composes canvas, plane and rigid 3D frames; validates rotation handedness/orthogonality, dimensions, cycles and singularities. Original corner correspondences produce a plane matrix programmatically. |
| Original-independent targets | Each landmark freezes independently observed source_point. Source projections must agree before binding; actual saved anchors are compared against original pixels, not generated coordinates. Spatial revisions require located retained corrections. |
| Native priority and construction | component_workflow.bind -> prepare_binding -> native_surfaces.expand -> spatial_constructors. Planar/curved constructors resolve full frame_ref; shared-vertex spatial prisms/polyhedra compile to normal editable native owners. Existing capability checks reject inadequate representations. |
| Pose and face-local centering | spatial_checks reads saved DrawingML transforms/path points, then computes source-pixel residuals, plane inverse coordinates, aggregate two-axis centers, orientation/handedness, ratios, contact and edge constraints. A projected body AABB is not its base footprint. |
| Containment/occlusion/material | Typed support/attachment/region/shared-edge/occlusion relations supplement existing feature/material probes. Actual painted coverage plus XML order is checked at frozen occlusion probes; complete appearance and feature omission remain independent. Visible landmark support is not misreported as hidden-volume proof. |
| Qualified mothers and instances | Same-view copies require projection-equivalence evidence. Changed views use guarded reproject and source-bound canonical constructor maps; actual qualified mother anatomy and actual target native/spatial checks are both required. |
| Dependencies and repair | Scoped frame ancestors/relations enter component dependencies. Placement changes dirty spatial qualification; spatial neighbours and affected assemblies/copies are invalidated. Invalid measurements stop drawing grants. Typed repair phase and frame/local-pose diagnosis preserve existing finite budgets, grants and journal. |
| Final acceptance and delivery | Layout requires fresh spatial measurements. Local complex evidence and whole final evidence require spatial_review. component_final freshly recomputes spatial_native, separately checks current saved render and every unit/relation. Existing fonts/native/feature/omission/export gates retained. |
| Entry and compatibility | CLI and next/submit/advance share reproject dispatch. New contracts default to 1.35.0; old contracts retain policy until explicit migrate_spatial. Curve, original-problem budget and private knowledge gates include 1.35.0. |
| Runtime and validation boundary | Only existing Python/numpy/shapely/lxml and image/geometry resources are used. No new runtime binary, library dependency or model/provider. Product execution excluded per user request. |

The static pass also corrects the coordinate-domain mismatch in final placement
for generated rotated frames while retaining imported saved-world AABBs and
frozen uncertainty. No thresholds were widened and no user artwork was touched.

All runtime/artwork channels remain NOT_RUN_PER_USER_REQUEST for this release.
