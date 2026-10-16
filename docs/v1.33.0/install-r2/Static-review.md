# 1.33.0 install-r2: static call-chain review

Status: IMPLEMENTED_STATICALLY_REVIEWED_NOT_TESTED_PER_USER_REQUEST.

Scope: restore the runtime-repository automatic install entry; implement managed
file differential synchronization; restore supplied core platform coverage and
add pinned macOS Math preparation. Scientific reconstruction contracts and
private task/knowledge/font state are retained.

## Normal call chain

1. Both English/Chinese READMEs give one runtime-repository install/update sentence.
2. The agent uses the recorded private Launcher.json command, or obtains the OS
   bootstrap from runtime/tools. No user archive download is required.
3. OS bootstrap reuses a matching owned project interpreter or a pinned Python
   archive. Shell hashing supports sha256sum and shasum; Darwin ARM/Intel branches
   remain present. No global interpreter/package/application installation occurs.
4. install_lotra.py reads a compact current channel with conditional ETag requests,
   verifies the pinned entry/catalog, reuses installer file hashes, and calls the
   maintained differential coordinator once under isolated Python. Sibling module
   imports are explicitly rooted in the owned installer directory.
5. file_sync.prepare binds old manifest plus ownership receipt, preflights actual
   old contents, and computes add/replace/delete/keep. Matching local content is
   reused even when its path changes. Only absent hashes are fetched. Candidate
   views use local references; active keep files have no write/copy/rename action.
6. Core companion comparison uses selected environment/file content rather than
   archive wrappers. Missing members come from hash-addressed cache, matching old
   companion bytes, a local offline payload, or exact stored-ZIP HTTP byte ranges.
   Range-ignoring responses cannot trigger a silent full re-download. Same-hash
   fetches serialize within a bounded worker pool. Core import/probe code identity
   and retained readiness are checked before reusing prepared environments.
7. Math sources are selected independently from core platforms. macOS ARM/Intel
   use official fixed-size/SHA-256 LibreOffice DMGs, readonly private mounting,
   app-bundle-contained links and a private app destination. Platform key Darwin
   is written for the existing portable renderer. Physical resources and successful
   UNO import have separate receipts; a failed import cannot become a reused PASS.
8. Core/OCR preparation and Math import precede active file publication. apply
   writes only adds/replacements, unlinks only retired old-owned files and prunes
   their empty directories. Manifest/control receipts follow body changes. Actual
   new ownership is checked before registration. Registration preimages are real
   byte snapshots, avoiding in-place AGENTS writes modifying a hardlinked backup.
9. A scoped journal restores changed/deleted bytes and registration on failure.
   Interrupted content-specific partial writes are resumed/removed only against
   their exact candidate bytes. Owned versioned project skill folders can be
   relocated to the canonical entry without re-downloading unchanged contents.
   Completed state is not rolled back for a later output error. Repeated current
   installs keep source files and registration unchanged and return a short result.
10. Publication exposes the new immutable revision before switching current
    branches. Previous v1.33.0 tags/archives stay bound to their original bytes.
    Private libraries, fonts, tasks, sources, credentials and global skills are
    outside the outbound file inventory and installation deletion set.

## Review corrections incorporated

- Restored missing installer-directory import path under python -I.
- Used a persistent project-wide lock identity compatible with the existing lock
  reader rather than a version-dependent or incomplete identity.
- Corrected the shared worker list scope in file-delta preparation.
- Added same-content reuse across renamed paths and coherent no-op registration.
- Kept registration preimages independent of in-place AGENTS writes.
- Bound interrupted apply/registration recovery and versioned folder relocation.
- Kept source/installer catalogs, source manifests, entry hashes and bootstraps
  regenerated together after the final source edits.
- Removed the Math-derived core platform filter and Linux-only shell gate from
  the new normal route; the old exact archived install packages remain historical.

## Boundaries

This is source inspection, not executable qualification. No product tests,
syntax/import/CLI checks, installer runs, clean/repeat/interruption validation,
reconstruction, rendering, Office behavior or performance/effect measurements
were run. Hashing and ZIP assembly identify published files only.

Windows AMD64, Linux x86_64 and both macOS architectures have resource records and
complete installation code routes in this revision. No new host acceptance is
claimed. Linux ARM64 core resources are retained/indexed, but a complete Math
package is not supplied; installation reports that specific limitation before
downloading the skill or changing its active directory.

HTTP member transport requires a range-capable server; failures remain bounded
and preserve verified cache/partial ownership. User-modified or unowned skill
folders are preserved and stop managed synchronization. This adds no ongoing
user-edit monitor or general-purpose undo system.
