# lotraAI Image2Slide 1.35.3

The macOS Math backend now runs a fixed Python/UNO worker inside the signed
LibreOffice application, rather than starting its constrained bundled Python
from the project process. Installation startup checks and actual document export
share the same bounded backend. Official application signatures and system
security settings are preserved; workers and new profiles are project-private.

The worker retains native OMML import, native Math formulas, explicit fonts and
sizes, immutable canonical PPTX bytes, per-job input identities and output
receipts. It accepts only startup or export operations. Windows and Linux keep
the external UNO route. Startup probes run afresh on install/repeat; historical
import receipts do not certify the new route. Failures record their phase and
leave unexecuted core checks as NOT_RUN. The old offline compatibility path uses
the same probe instead of its Windows/Linux-only platform expression.

GitHub Release downloads can use the exact official asset API after bounded
failures. Asset names, sizes, content hashes, range responses and owned caches
retain their existing checks. OS bootstrap engine fallbacks use verified fixed
asset IDs. macOS Math DMGs retain the pinned upstream download.

Product version is 1.35.3. The spatial reconstruction policy remains
workflow_version 1.35.2, design_revision 8; old task contracts are preserved.
Runtime binaries remain 1.14.0 and existing Python/OCR/LibreOffice resource bytes
are reused. No new runtime binary release, Setup skill, global install, provider
key, personal data or user-artwork benchmark is introduced.

Focused tests and Windows/WSL formula exports were executed. The hosted route
was actually exercised on Windows, which does not qualify macOS launch/security
behavior. Apple Silicon and Intel physical-host validation remain pending.
See Validation-report.md for the exact scope. This release is a compatibility
implementation with bounded evidence, not a claim of completed Mac acceptance.

Repository defaults/development use dev; numeric version branches use 1.35.3;
the formal product tag is v1.35.3. The maintained installation channel is
activated only after the matching public catalog and assets are verified.
