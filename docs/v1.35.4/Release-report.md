# lotraAI Image2Slide 1.35.4

Fix the shell bootstrap published in 1.35.3: every shell installation entry uses
LF, and one canonical template renders each public, runtime and skill copy.
Repeated generation preserves identical bytes and modification times instead of
adding nested conditions or repeated parameters. Git attributes explicitly retain
LF for shell scripts and shell templates. The download path has one bounded
official asset-API fallback, with the existing pinned content checks.

The publication gate parses actual loose release attachments, skill ZIP members
and complete-bundle members with Linux sh/bash and Windows PowerShell. It also
checks shell LF bytes, copy/pin identities and unchanged runtime resource records.
Bootstrap regressions exercise download, fallback, HTTP range resume, changed
cache preservation and verified cache reuse on Windows and Linux.

Windows/Linux complete-bundle installation and the public README commands are
recorded separately in Installation-checks.json. Public downloads and final
parser identities are recorded in Final-distribution-checks.json. Physical macOS
installation remains pending; Linux parsing does not qualify a physical Mac.

Product version is 1.35.4; workflow_version remains 1.35.2 and design_revision 8.
Runtime binaries remain 1.14.0. The maintained Python installation core, native
Math implementation and platform resource bytes are unchanged. Runtime repository
changes are limited to shell/PowerShell entry pins, Git attributes, documentation
and the current installation channel. No runtime binary Release is created.
Unchanged immutable bundle parts and existing resource assets are reused.

Preserve global skills, private knowledge/fonts/tasks, source images/PPTs and
historical tags. This is an installation patch: no new artwork acceptance,
Office interactive editing or performance/token claim is added.
