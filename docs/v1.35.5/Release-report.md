# lotraAI Image2Slide 1.35.5

Repair the complete-bundle download route: the manifest, archive name and result
use the current product version, and verified unchanged parts retain their
original release filenames/URLs. Synchronize the skill packager version with the
coordinator during template generation, so the current source and final skill ZIP
can be built and verified by the supplied packager.

Every iteration now requires a version-consistency gate in the development
AGENTS.md. The maintained gate checks both repositories' current metadata,
README identities, installer pins, catalog records, loose assets, the actual
skill ZIP and complete ZIP including the nested skill. Version-drift regressions
reject stale packager, channel, README and embedded ZIP versions. Shell LF and
Windows PowerShell parser gates still inspect final distributed bytes.

Correct current publication guidance, product tables, 19-part download notes and
historical validation attribution. Stable HTTP tool identifiers no longer carry
an obsolete product version. The runtime Python entry changes only that
diagnostic header; runtime 1.14.0 binaries and existing resource archives do not
change. Workflow_version remains 1.35.2 and design_revision remains 8.

Windows/Linux first/repeat complete-bundle installs, maintained README commands
and full-bundle downloads have separate current receipts in
Installation-checks.json. Final-distribution-checks.json and Version-consistency.json
bind parser/version conclusions to final bytes. Physical macOS qualification,
reconstruction, formula rendering, Office interactive editing and performance
effects are not claimed by this installer patch.

The source and runtime repositories use dev and 1.35.5; the formal source tag is
v1.35.5. Existing v1.35.4 tag and attachments are preserved. Reuse unchanged
resource assets and complete-bundle parts; upload only the changed tail part,
small skill payload, installation entries and current metadata/evidence. No new
runtime binary Release is created. Local user modifications, active runtime,
private data, fonts/knowledge/tasks and global skills are preserved.
