# lotraAI Image2Slide 1.33.0 installation and publication update

Product version remains **1.33.0**. Immutable installation publication revision
5 identifies these source/archive bytes; original v1.33.0 tags and archives are
retained. Reconstruction design/workflow versions and runtime binary version
1.14.0 are unchanged.

The runtime repository remains the one-sentence user entry for installation and
updates. Its maintained common program performs platform selection, resumable
downloads, ordered-part assembly and managed-file differential synchronization.
First installation obtains the selected platform package. Existing installations
retain member-level retrieval and reuse installed or cached bytes. New files are
added, changed files replaced, retired owned files removed and unchanged active
files retained without download/rewrite. Personal knowledge/fonts/tasks/images,
PPTs and global skills are outside that deletion scope.

The full 1.33.0 bundle is repackaged with the current installer and catalog and
published as ordered parts of at most 128 MiB. The existing fetch helper delegates
to the common downloader/cache. Local bundle installers dispatch to the same
differential coordinator. Both repositories keep English and Chinese README
guides, with the same concise install/update request.

Core resources cover Windows AMD64, Linux x86_64/aarch64 and macOS ARM/Intel.
Complete Math resource routes cover Windows AMD64, Linux x86_64 and both macOS
architectures. macOS requires 13+ and fetches a pinned Math DMG separately at first
preparation; those DMGs are not embedded in the full bundle. Linux ARM64 complete
Math remains unavailable and is reported before publishing a skill.

The prepared release includes PowerShell/Shell upload entries, one maintained
publisher and an exact asset plan. It reuses matching server assets by SHA-256
and size, restarts only failed uploads and advances current branches only when
all required assets match. GitHub Release uploads are not byte-resumable; download
clients do support resumable owned partials. Interrupted publication can be
continued by rerunning the same prepared command.

Status: IMPLEMENTED_STATICALLY_REVIEWED_NOT_TESTED_PER_USER_REQUEST. Product
tests, syntax/import/CLI checks, installer/runtime validation, reconstruction,
rendering, Office behavior and performance/effect measurements were not run.
Publication identity/hash records do not establish runtime/artwork acceptance
or measured token/time savings.

The shell entry extracts the selected engine object from compact or pretty JSON, then checks its project-relative path and executable digest. This includes old installations whose descriptors are written on one line.
