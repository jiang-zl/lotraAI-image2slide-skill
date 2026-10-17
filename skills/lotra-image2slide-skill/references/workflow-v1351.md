# Spatial contracts and repair in v1.35.1

Use this for new contracts and explicit migration from earlier policies. It
supersedes v1.35.0 schema names, sparse-footprint certification and spatial
repair scheduling. Retain workflow-v135.md geometry/observation rules and v1.34
feature ownership, capability preflight, recursive stops and native priority.
Existing bound tasks keep their declared workflow until an explicit
`migrate_spatial: true` rebind. Do not reconstruct or migrate a user task merely
because this implementation was updated.

## Original observation and reference frames

Submit `source-features-1.35.1` with spatial schema `spatial-1.35.1`. Bind a
component contract with `workflow_version: 1.35.1`, `design_revision: 8`.
The original is observed before native ownership. Model decisions cover
meaning, decomposition, visibility, symmetry, reference-frame interpretation,
anchor correspondence and representation. Programs execute numerical geometry,
finite searches, scoped native writes and measurements.

Each frame adds `owner_unit`, naming the original semantic unit whose canvas,
space or usable face it defines. Units are explicit nonempty strings. A rigid
space3d parent/child chain uses the same coordinate unit; normalize coordinates
before binding rather than silently interpreting millimetres as centimetres.
Plane origin vectors use parent units; u/v basis vectors express parent units
per local unit. Root-space translation is in the model's spatial unit, even
though the camera projects it onto a source-pixel canvas.

Orthographic/axonometric root matrices have a nonzero constant homogeneous
denominator. Perspective matrices have a depth-dependent denominator. Matrix
rank alone does not establish the declared projection family. Stylized views
remain explicit original interpretations. Euler angles retain extrinsic_XYZ;
hidden depth or rotation is never recovered from one screenshot by declaration.

## Measured relation subjects

Every relation retains frozen source landmarks, frame, units and bounds.
Membership in `units` alone does not satisfy an object's measurement obligation.

* axis_direction, pose_projection and extent_ratio name `subject`; all their
  landmarks belong to that subject. Pose starts with roles `pose_origin` then
  two distinct `pose_u`, `pose_v` or `pose_w` axes, noncollinear in the original.
* supported_by, attached_to_face and contained_on_plane name distinct `subject`
  and `reference`, exactly matching their two units. Their plane's owner_unit is
  the reference. Subject points use contact_vertex for support and
  surface_vertex for attachment/containment. A standing/attached spatial unit
  must itself be the subject of its required relation.
* shared_edge names ordered `subjects: [A,B]`; its four endpoints belong to
  A,A,B,B. occludes uses subjects [front,back] and corresponding two landmarks.
* align_in_plane, same_plane and volume_contains list measured `subjects`;
  every listed subject contributes its own landmarks.
* center_in_plane names its semantic container and all direct content units.
  Its plane belongs to the container. Preserve original offsets or an explicit
  user-supported centered target, and preserve internal child arrangement.

Surface/solid units need their own observable orientation relation. Required
landmarks are actual saved leaf/path anchors through all ancestor transforms.
No other unit's points, unsupported native 3D effect or missing extractor can
supply a passing measurement for this subject.

## Complete logical and contact footprints

The original spatial observation also freezes `footprints`. A footprint has:

```
{"id":"icon-contact", "unit":"icon", "frame":"platform-face",
 "role":"contact", "features":["base-domain"],
 "coverage":"complete_logical_domain",
 "geometry":{"kind":"ellipse","center":[0.5,0.5],"radii":[0.1,0.08]},
 "precision":0.0001, "tolerance":0.002,
 "source_evidence":"the original base contact boundary on the platform"}
```

Geometry is independently observed as a compact polygon (`outer` and optional
`holes`), ellipse (`center`, `radii`) or bounded path (`contours` of closed native
moveTo/lnTo/quadBezTo/cubicBezTo commands). It is not copied from a proposed PPT.
All dimensions and precision are in that plane's units. Use a precision fine
enough for the frozen discrepancy and relation bounds. Hidden unsupported
contact geometry stays a decision, never invented visible evidence.

The contract adds `spatial_footprint_bindings`, each naming footprint, owners,
method and source_evidence. Owners must be exactly all native leaves bound to
the footprint's original features. native_domain reads the complete saved
contour; native_text_frame is restricted to real native text/math/table logical
frames. A group envelope, partial owner list or arbitrary shape box cannot
stand in for the content domain.

center_in_plane, align_in_plane, contained_on_plane, supported_by and
attached_to_face list `footprints`. These cover exactly the measured subjects
in the same plane. Standing units use contact footprints, attached units use
attached footprints, and other content uses logical footprints. align_in_plane
also declares `alignment_anchor: min|center|max` and axis 0/1.
Usable-face relations retain region and may add region_holes, explicit original
hole polygons subtracted from that usable face before complete containment.

Programs combine complete subject domains for centering and alignment. They
check complete coverage in the usable region, including concavities, holes and
edges between vertices. Native curves are flattened by bounded subdivision of
positive homogeneous Bezier control hulls, preserving a conservative precision
bound. Source agreement uses conservative mutual whole-domain coverage.
Reported zero coverage violation means this bounded predicate held; it is not
a claim of zero pixel difference. Precision is included in center/alignment
bounds. Unsupported presets, open paths, singular projections or exhausted
precision return MEASUREMENT_REQUIRED, not passing samples.

Native priority remains preset -> compact composite/shared surfaces -> bounded
native paths. Rectangles, ellipses and supported simple presets retain direct
native extraction. Use a focused representation decision when an extractor is
missing; do not fall back to dense pixels. Text remains text and math is OMML.

## Shared construction and canonical mothers

Initial bind, focused constructor revision and numerical recompilation use
native_surfaces.compile_spec with the frozen spatial graph. Revising a spatial
constructor never calls the older planar-only constructor directly. Program
recompilation supplies a scoped source/native plan; the existing native grant,
font handling and journal apply it without replacing unrelated owners.
A common-frame observation rebind also recompiles its actual constructor
consumers and exposes their guarded source-apply plan through normal packets.
It cannot leave old compiled owners colliding or ask a model to redraw them.

spatial_polyhedron adds `anatomy_faces`, a source-supported catalog of id,
indices and source_evidence. A visible face references that catalog with
face_ref (or its same id) and unchanged indices. Additional source-supported
canonical edges use anatomy_edges. Vertex coordinates and stable face/edge
incidence form canonical anatomy; visibility, material and painter order remain
separate original decisions. New view-specific faces cannot silently redefine
the qualified mother. Hidden faces are not invented to complete a model.

If a fitted qualified mother differs from the earlier constructor plan, the
reproject operation persists SOURCE_DECISION_REQUIRED for the instance and
donor. The packet targets the donor before its copies. Submit the explicit
`constructor_recapture` decision with current source-supported constructor
parameters; this decision may cover its derived mother family, never unrelated
resources. Previous native bests are retained with their original contract.
Reprojection then uses qualified current anatomy and the ordinary saved-native
journal. Recovery replays its instance and phase transitions idempotently.

## Coupled finite spatial parameters

For a local_fit native resource group use `fit.adapter: spatial_parameters`.
The row's spatial_fit names construction_ids and bindings from parameter name
to `{resource: frames|constructions, id, field}`. All compiled constructor owners
must belong exactly to the numeric group. Each parameter declares state, value,
unit, coordinate_space (the bound resource ID), source_evidence and, if tunable,
the original bounds and positive minimum_step.

Allowed numerical fields include explicit Euler pose/translation, source-plane
bases/corners, projection coefficients, extrusion depth and shared vertices or
bounded curve geometry. Rotation angles use degree. Projection coefficients use
projection_coefficient. Coordinates use their declared frame units; plane u/v
coefficients use parent_unit/local_unit. Topology, visibility, text and material
are outside numerical fitting. A frame parameter cannot alter constructors
outside the chosen resource group: shared-camera decisions return to source.

Programs derive all relevant original anchor, full-footprint and internal
relation target metrics. Callers cannot replace or loosen them. Trial frames
only generate candidate geometry; the original measurement graph, source points,
regions, targets and bounds stay unchanged. Trials reuse the existing finite
search, shared original-problem budget, checkpoint and retained-best rules.
Numeric success commits through the existing native batch/journal and requires
actual saved-native confirmation and the normal real-render/visual gates.
The numeric surrogate is never submitted as saved-native or appearance evidence.

## Invalidation, phased repair and acceptance

Directly changed units seed spatial relationship invalidation. A parent becoming
dirty does not imply that every descendant or sibling changed. Unchanged
neighbour anatomy retains its qualification and best; current relationships
are remeasured in containing assembly/layout and final gates. A real ancestor
native transform invalidates affected measurements. Cross-component relations
are layout dependencies, not unrelated child anatomy signatures.

Final repair reads current saved spatial measurements. It derives failed
relations and phases even when the caller omits spatial_relations. When supplied,
that list must equal the current measured failures for the component. Pose
failures require typed shared_frame/local_pose diagnosis. Shared-frame repair
persists an original-observation decision, then explicit rebind of consumers.

Repair fields are explicit and nonoverlapping. Geometry/pose/support phases
precede shared geometry, painter order and material/text. Later field grants
remain deferred in the ordinary ledger; no whole-owner grant bypasses this
order. The saved-native journal marks the applied phase. Current native spatial
checks must certify earlier phases before later grants activate. Deferred
fields are checked against their original planned values to preserve user edits.
Invalid measurements return diagnosis; unresolved phases retain the best.
No final acceptance is possible while a phase schedule remains incomplete.

One deferred font review and normal whole visual review remain. Final audit
freshly measures all original anchors, complete footprints and typed relations
from saved bytes, plus current spatial_review for every unit/relation. The
component metric table includes all three channels. Source basis, native
consistency and actual appearance remain separate. Hidden_3d_verified stays false.

This patch is implemented and statically reviewed only. Tests, syntax/import/
CLI checks, reconstruction and rendering are excluded by the user's request.
Packaging identities and source synchronization do not establish runtime or
artwork acceptance. Runtime binaries and resources remain independently versioned.
