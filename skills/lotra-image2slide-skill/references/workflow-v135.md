# Spatial reconstruction in v1.35.0

Use this with workflow-v134.md for new or explicitly migrated spatial contracts.
All v1.34 recursive features, native priority, capability checks and omission
obligations remain. There is one normal next/submit/advance loop, one native
journal and one independent final gate. A 2D task also receives spatial
classification; adding an is_3d flag or undocumented rotation fields is inadequate.

## Source observation and recursive recognition

Submit schema source-features-1.35.0, unchanged_original basis and the existing
source hash/canvas/observer/units/features. Every unit adds spatial with mode
planar, surface, solid, mixed or uncertain; frame; placement standing, attached,
free, annotation or unknown; container boolean; observability; source_evidence.
Uncertain mode needs uncertainty. A declared unobservable_axes list needs
symmetry_evidence. Observe faces, parallel edge families, foreshortening, contact
points, holes, inner walls and occlusion junctions. A shadow alone does not
establish solid anatomy. Parent projection may be inherited; child orientation,
face-attached text and screen-facing labels are independent source decisions.

The observation's spatial object has schema spatial-1.35.0 and bounded arrays
frames, landmarks and relations. These belong to the original before owners.
All quantities are finite; every frame/landmark/relation needs source_evidence.
No screenshot registration may be fitted independently to each candidate.

## Reference frames and 3D pose

Frames use distinct id, kind and units. Exactly one canvas frame uses source_px.
Other frames name an explicit parent; cycles and singular planes are refused.

* plane under canvas/plane: origin/u/v (2-vectors), a 3x3 homography, or four
  local_corners/parent_corners correspondences. Programs solve the latter
  directly from original corners; do not ask the model to hand-compute matrices.
* plane under space3d: origin/u/v (3-vectors) embedding that plane into its parent.
* space3d: proper right-handed orthonormal rotation (3x3) and translation
  (3-vector). A root under canvas also declares projection_type and a finite
  rank-three 3x4 projection. A child space3d inherits its parent's camera.

Rotation matrices map local axes into the parent frame. Alternatively declare
euler_degrees [x,y,z] with rotation_order extrinsic_XYZ, without rotation: the
program computes Rz @ Ry @ Rx for right-handed fixed-parent axes, rather than
asking the model to hand-compute matrices. No implicit Euler order is accepted.
Units such as normalized_uv or model_unit remain attached to
the frame. Screen rotation, object rotation, camera projection, extrusion depth
and PPT paint order are different quantities. A plane homography cannot invert
a point into unique 3D depth or flatten an entire solid into one physical plane.

Landmarks have id, unit, frame, point, role, observability clear/partial,
source_evidence, independently observed source_point [x,y] and
tolerance_source_px. The declared projection must agree with source_point
before binding; saved anchors are compared against source_point, never the
construction's own projection as ground truth. Points are local to their named frame,
not implicitly page pixels or normalized path coordinates. Freeze observable
axes/face corners/base contacts; hidden speculative landmarks are prohibited.
Symmetric/unobservable rotations remain undetermined. Accept observable
projection constraints without claiming hidden geometry or true camera recovery.

## Face-local layout and semantic containers

Every semantic container with direct children needs one center_in_plane relation:
container names the unit; content_units lists all direct children; landmarks
contain each child's logical footprint; aggregate_basis is logical_footprint;
target is the required two-axis local center; target_evidence explains centered
or source-supported offset placement. Evaluate the aggregate, preserving the
children's internal spacing. Recurse at every containment level. Shadows and
protruding upper bodies do not define the contact footprint.

For a rectangular usable face normalized to a unit square, center is (0.5,0.5)
projected through that face; under perspective it is generally different from
the screen bounding-box center. Irregular regions need explicit source anchors.
Screen labels use canvas axes; surface details use their face coordinates;
standing solids use base contacts plus a separate body/axis constraint.
Geometry and optical centering remain separate. User-required centering or a
faithful source offset is settled in the original target before construction.

Source relations name id, kind, units, frame, landmarks, tolerance, unit and
source_evidence. They are hard independent constraints, never averaged away.

| kind | Contract and actual saved measurement |
|---|---|
| center_in_plane | target [u,v]; maximum two-axis aggregate-center error; frame units |
| align_in_plane | axis 0/1; coordinate spread in that face; frame units |
| contained_on_plane | usable region polygon; actual logical-footprint vertices outside region; frame units |
| supported_by | usable region and actual base/contact landmarks, with independent source-pixel landmark residuals |
| attached_to_face | usable region and actual attached-content landmarks, with separate orientation |
| same_plane | declared plane membership and actual reprojection consistency; no recovered-depth claim |
| axis_direction | two landmarks, degree bound; directed true normally; false only for source-supported undirected symmetry |
| pose_projection | at least three noncollinear landmarks; ordered axis angles and handedness; degree bound |
| extent_ratio | four landmarks defining two axes; source-projected length-ratio difference; ratio bound |
| shared_edge | four ordered endpoints; actual shared junction difference; source_px |
| occludes | front then back landmarks at a frozen shared probe; actual painted coverage and actual XML order; source_px |
| volume_contains | explicit same-frame 3D bounds; claim visible_projection_only; projected saved anchors remain mandatory |

Surface/solid units require observable orientation constraints. Standing and
attached units require their corresponding support/attachment relation.
Each landmark is also checked independently against its unchanged original
projection in source pixels. Multiple logical polygons must be decomposed into
supported simple pieces; sparse samples cannot certify a curved footprint's
entire containment. Use sufficient source-supported extrema, native structure
and actual visual review; unsupported coverage is a representation decision.

## Bind and native construction

Use workflow_version 1.35.0 and design_revision 8. source_inventory preserves
the independent units including spatial. feature_bindings retain v1.34 rules.
spatial_bindings map each original landmark to one corresponding actual leaf:

```
{"landmark":"base_left", "owner":"icon.base",
 "anchor":{"kind":"frame_point","point":[0,1]},
 "source_evidence":"the saved local lower-left base anchor"}
```

frame_point is a normalized saved-local frame point transformed through all
actual saved ancestors; it is not an axis-aligned page-box anchor. A path_point
instead names path, command and point integer indices of an actual native path.
Use path anchors for semantic vertices that are not frame corners. Never bind
an arbitrary virtual frame point as evidence of visible paint. Occlusion also
requires actual painted coverage, then saved-render feature review.

The binder derives spatial, spatial_units, spatial_basis and scoped per-component
spatial_context/basis from the frozen source. Callers cannot substitute candidate
metadata. Frames and their ancestors participate in dependencies and cache keys.

Native priority stays preset -> compact native composite/shared surfaces ->
bounded native paths/cubics. A 3D effect is optional; unsupported native-3D saved
geometry cannot be certified by its ordinary 2D frame. Choose projected editable
surfaces when the inspection backend cannot support the needed 3D effect.
Text remains native text, math remains OMML. Resolve unsupported text-plane
projection explicitly; converting text to outlines/raster does not satisfy text.

Existing planar/elliptic/extruded constructors accept frame_ref pointing to a
frozen plane. The compiler resolves the full plane matrix, including a plane
embedded in a 3D scene, before bounded native-curve projection. For solids:

* spatial_prism uses a local 2D footprint at z=0, a noncoplanar 3-vector depth,
  top_style, explicitly visible walls with edge/id/style, optional observed
  base_style, and explicit paint_order. All faces share constructed 3D vertices.
* spatial_polyhedron uses up to 128 shared local 3D vertices and explicitly
  observed planar faces with id/indices/style/role. visible_edges reference
  vertex pairs; paint_order covers each observed face and edge once.

Both use a space3d frame_ref. They compile to ordinary native path owners and
normal component/feature coverage. Hidden faces are never inferred merely to
close a model. Separate fill boundaries from visible edges; suppress duplicate
strokes and preserve source holes/inner walls rather than covering them over.

## Qualification, mothers and spatial instances

Source interpretation, saved native realization and actual appearance are
separate channels. Fixed primitives receive native/spatial checks; their visual
confirmation remains at assembly/final. Every complex assembly/instance still
needs the current actual render and every required feature comparison.

An instance declares spatial_instance.route and source_evidence:

* native_affine_copy needs projection_equivalence_evidence: the source supports
  the same view, visible faces and occlusion under a native affine transform.
* reproject_constructor names construction_ids and constructor_map mapping
  qualified mother construction IDs to target IDs. Reuse local anatomy, then
  project into the target source frame. Existing instance_of relations inspect
  the resulting target native anatomy plus actual spatial anchors. This route
  uses the ordinary guarded native constructor/journal and operation reproject;
  it is not placed in the affine-copy transaction batch.

Qualified local geometry cannot be replaced by raw copied page polygons when
the view/perspective changes. Per-instance fonts and original feature checks
remain. Constructors/visible face changes require original support and normal
capability/ownership checks; unsupported variants return a focused decision.

## Finite repair, invalidation and final acceptance

Normal next/submit packets expose spatial basis, unit/frame/relation IDs and
repair order. Full resources use existing hash-bound managed selectors and
pagination. Programs build and fit finite source-supported parameters; the
model decides meaning, visibility, projection family, anchor correspondence,
uncertainty and representation. No new model, provider or runtime dependency.

Diagnose invalid native anchors/singular frames/unsupported effects before
granting drawing repairs. Classify shared frame/camera versus local pose, then
support/face layout, shared geometry, occlusion and material/text. Repair items
can name spatial_relations; orientation repairs need frame_pose_diagnosis.
Existing field grants, locks, journal recovery and finite budgets remain.

An original spatial revision goes through observe_source with revision_reason
and spatial_corrections [{resource,reason,source_evidence}]. Resource keys are
unit:ID, frames:ID, landmarks:ID and relations:ID. Retain every changed original
decision and bounds; a candidate never becomes its own target. Rebind through
the current packet. Old tasks migrate only with explicit migrate_spatial true.

Reference-frame changes invalidate every consuming component through its scoped
ancestor identities; shared spatial neighbours and affected mothers/instances
are rechecked. Local paint remains local apart from visibility neighbours. Do
not discard independent bests or run whole-page audit after every local edit.

One deferred font review precedes whole review. Local complex evidence and final
whole evidence add spatial_review with spatial_basis, basis
original_to_saved_render, unit_checks [{unit,verdict,observations}] and
relation_checks [{relation,verdict,observations}]. Local review covers its units
and internal relations; final review covers every original unit and relation,
including mixed/2D classifications. Evidence also retains normal current
source_hash/pptx_hash/preview_hash/observer. Invisible parts cannot pass by ID.

The independent final spatial_native gate freshly reads saved bytes and checks
all source landmarks/relations, while spatial visual review checks the actual
render. Existing feature probes, six visual dimensions, every-unit omission
review, fonts, editability, layout and export gates remain mandatory. Invalid,
unresolved or excluded checks are never passing zeros. Hidden_3d_verified stays
false: acceptance concerns the observable original projection, not unseen volume.

This release was implemented and statically reviewed without tests, syntax,
import/CLI checks, reconstruction or rendering, by explicit user request.
Publication/package identity is not runtime or artwork acceptance.
