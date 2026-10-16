# v1.33.0 installation and publication

Semantic version and public release tag are v1.33.0. The public source is based
on v1.32.0 publication revision 9. Component design revision remains 8.

The tested Windows x64 and WSL/Linux x64 candidate uses shared OS entrypoints,
project-local Python, managed file differences, common content caches and one
discoverable skill. The skill package also supplies install-runtime.ps1/.sh.
Clean local-bundle and local-HTTP online installation, core execution, actual
OCR inference, Math startup, repeat installation and private-data preservation
passed before publication. Online fixtures changed distribution URL literals
and their dependent hashes; they did not change installer logic or payloads.
Public GitHub download commands were checked against the then-published entry.
macOS resources and commands are provided without a native-host acceptance claim.

No reconstruction, Office editing, performance or token-effect measurement
qualifies this release. Those channels remain untested at the user's request.

The complete ZIP is transported as 18 ordered pieces of at most 128 MiB.
Platform-specific online resources share the same maintained installation core.
The public personal catalog is empty; private task images, PPTs, fonts, knowledge,
test fixtures, credentials and local paths are excluded from public source.

Only v1.33.0 is used for this version. The prepared WSL publisher retains matching
assets, uploads missing assets, verifies all declared digests and only then
activates the release channel. Exact obsolete 1.33.0 auxiliary releases and tags
are removed after successful activation. Earlier product version history remains.
