# 1.35.5 installer and version review

One coordinator product VERSION governs the complete-bundle manifest, output
archive name and returned version. Part filenames bind their exact manifest
index while allowing numeric historical release versions. Content sizes and
SHA-256 remain pinned, changed caches/outputs stay protected, and repeat output
is not rewritten. The supplied skill packager and customer inventory now agree.

The canonical entry generator synchronizes public/runtime/skill OS entries,
local coordinator and skill packager versions without repeated substring
accumulation. Final checks verify idempotence and actual Git payload bytes.
The release gate checks current fields and exact content pins instead of replacing
independent workflow, schema, Math or binary resource versions.

Current documentation identifies 1.35.5 and the manifest-owned 19 parts. Older
publishers and test receipts are explicitly historical. Version consistency is
a mandatory per-iteration publication gate in source and private development
AGENTS.md. Existing local source edits are not imported into this clean release.
Runtime native implementation and resource bytes remain unchanged.
