# lotraAI Image2Slide 1.35.2

This patch closes eight findings from the 1.35.1 static review. Spatial fitting
and layout now share frozen constructors and committed bounded parameters.
Existing native field grants and transactions enforce repair phase authority
across edit, numeric commit, instance/reprojection and rollback paths. Failed
checks persist as source/measurement decisions; pending decisions, source rebinds,
source-apply plans and incomplete phase schedules block final review/audit/accept.

The patch also selects version-correct packet references, rejects unsupported
shape/text/ancestor 3D extraction, separates actual world-transform dependencies
from relative painter order, and checks visible geometry/control hulls before
projecting through a horizon. Native shapes, fills and outlines retain priority.

The change reuses the existing compiler, bounded search, ledger, grants, journal
and final gates. Component design_revision remains 8; new workflow_version is
1.35.2. Source observation schemas remain source-features-1.35.1/spatial-1.35.1.
Old source facts, quality bounds, independent bests, user locks, original files,
private tasks/fonts/knowledge, global skills and published tags are preserved.

Implementation and source/rule static review are complete. Tests, syntax/AST/
import/CLI checks, runtime startup, reconstruction, rendering, Office behavior
and performance/effect measurements were not run at the user's explicit request.
This release makes no runtime or user-artwork acceptance claim. Packaging/file
identity and publication transport checks are separate from product validation.

Runtime binaries/resources remain unchanged at independently versioned 1.14.0.
Only source installers/catalogs and the stable installation-channel JSON point
to 1.35.2. No runtime Release or runtime asset upload is required. The source
Release contains the small skill update, metadata/installers and the changed
complete-bundle part; unchanged bundle parts retain their immutable URLs.

Local deliverables are production/lotraAI-image2slide-v1.35.2-bundle.zip and
production/lotraAI-image2slide-v1.35.2-update.zip. See Static-review.md for the
call-chain review and Validation-report.md for the intentionally excluded runs.
