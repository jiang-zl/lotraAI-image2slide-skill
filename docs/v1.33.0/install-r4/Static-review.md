# 1.33.0 common installation, parts and differential update: static review

Status: IMPLEMENTED_STATICALLY_REVIEWED_NOT_TESTED_PER_USER_REQUEST.
Scope: image reconstruction/one-shot partial PPT remains unchanged. This update
modifies installation, acquisition and publication, without changing semantic
version 1.33.0, reconstruction policies, private knowledge or fonts.

## Entry and call chains

1. Both repository README languages use one runtime-repository sentence for
   install/update. They route agents to the recorded Launcher.json or OS bootstrap.
   Windows and macOS/Linux bootstraps select owned/pinned Python and call the same
   install_lotra.py. Darwin ARM/Intel and portable shell SHA tools remain covered.
2. The entry reads conditional current-channel metadata, follows at most two
   pinned entry changes, fetches hash-pinned coordinator modules and calls one
   backend with detailed logs on disk. Only the bounded final log tail is parsed;
   model-visible output is one compact result. Missing ETags retire stale ETags.
3. A fresh companion installation obtains spec.archive for the selected platform.
   Ordered archive pieces use the common download.py with two transfer workers.
   Verified parts and full archives use the same content cache and finite retries.
   Extraction seeds file content into that cache with resumable owned partials.
4. Existing companions compare selected bytes/environment rather than archive
   wrapper/version. A matching companion returns unchanged. Changed companions
   reuse installed content, matching cached archives or local offline members;
   only absent member hashes are requested. A missing member never triggers an
   entire platform download when a prior companion manifest exists. Range-ignoring
   servers cannot silently download a whole archive for one changed member.
5. file_sync.prepare compares the old owned manifest/receipt and actual files.
   It plans add/replace/delete/keep, reuses identical renamed content and builds a
   private candidate. apply changes only add/replace/delete; keep files are not
   rewritten. Unknown/user-modified files and directories are preserved and stop
   managed synchronization. This is not an ongoing user-edit monitoring system.
6. Math/core preparation precedes active source registration. The existing scoped
   journal restores changed/deleted source, registration and selected mutable
   runtime descriptors/proofs after failure. Core resources and prepared readiness
   are distinct; new publication does not convert historical proof into new PASS.
7. Complete bundle mode fetches only its downloader/import dependencies, gets the
   separately pinned full-bundle manifest, and delegates to bundle_transport.py.
   The latter checks ordered unique part names/sizes, reuses the common SHA cache,
   validates the complete archive and exposes a guarded output path. No model
   actions per part are needed. The compatibility fetch helper delegates to this
   entry instead of maintaining a second downloader implementation.
8. Local bundle routes (install.ps1, install.sh, install.py, online.py and the
   recorded entry's --bundle-root) all reach differential.install with local root
   resources. Local skill files and the full runtime parent archive take priority
   over downloads. macOS Math is documented as a separate first-use fetch, and
   Linux ARM64 missing complete Math remains an explicit limitation.
9. The bundle contains the current coordinator/catalog/skill payload. Its external
   bundle-part manifest is added to current.json only after archive assembly;
   that digest is not embedded in its own archive, avoiding a catalog/hash cycle.
   Platform archive download records are not listed as nonexistent local payloads.
10. The standalone publisher accepts only the two authorized repositories and
    prepared 1.33.0 tags/assets. Credentials stay in memory/stdin. Exact server
    digest/size reuse, guarded incomplete draft cleanup and bounded cURL retries
    support continuation. All assets and immutable source identities precede
    current-branch advancement. Branch updates are non-forced; conflicting remote
    changes stop the operation. Cross-repository switching is resumable, not atomic.

## Corrections made during this source review

- Distinguished initial full-platform acquisition from member-level updates.
- Reused a cached matching platform archive even during later file repair.
- Routed direct Python local installation to the differential coordinator.
- Preserved mode arguments and bounded self-update hops in the entry.
- Added owned resumable archive-member seeding instead of publishing partial
  extracted files directly into the companion tree.
- Reused the common downloader for full bundles and retained the fetch entry.
- Removed stale bootstrap ETags and bounded model-facing log parsing.
- Separated the external full-bundle digest from the embedded release catalog.
- Added a credential-free, portable prepared upload plan and honest upload retry
  semantics; no byte-resumable GitHub upload claim.

## Evidence boundary

This records source/call-chain inspection, not execution qualification. No tests,
syntax/import/CLI checks, installer/clean/repeat/interruption validation, runtime
validation, reconstruction/rendering, Office behavior or performance/effect
measurements were run. Packaging and remote asset/ref identity work only identify
distribution bytes and publication state. No token/time savings are measured.
