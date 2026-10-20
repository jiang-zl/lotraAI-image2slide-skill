# lotraAI source and release maintenance

<!-- lotraAI-version-consistency:start -->
## Mandatory version consistency on every iteration

Every product version iteration MUST regenerate and verify version consistency
before packaging, tagging, publication or installation-channel activation. A
failed or missing check blocks publication; changing only README titles is not
sufficient. Preserve the current model/reasoning and all existing local edits.

1. Select one numeric product version X.Y.Z. Synchronize the source/runtime dev
   and numeric version branches, formal source tag vX.Y.Z, both READMEs, skill
   headers and agent metadata, customer inventory, packager/coordinator constants,
   manifests, runtime entry pins, current installation channels and release assets.
   Use tools/prepare_install_entries.py; generation must be repeat-safe.
2. Run tools/validate_release_versions.py on the final source, runtime checkout,
   loose release assets, skill ZIP and complete ZIP (including nested skill ZIP).
   Check actual bytes, sizes/hashes, embedded product versions, catalog URLs,
   entry pins, bundle names and manifest-defined part count/order. The skill's
   own packager must verify the final skill ZIP. Do not bypass a mismatch by
   manually relabeling a receipt or weakening its identity checks.
3. Run tools/validate_install_entries.py with sh/bash and Windows PowerShell on
   actual final distributed files. Every shell installation entry is UTF-8
   without BOM and LF. Run current Windows/Linux first/repeat bundle and README
   installation checks, plus full-bundle download/repeat checks. Historical
   receipts must remain attributed to their real version; installation is not
   artwork/rendering/Office acceptance. Physical macOS needs its own host proof.
4. Verify the public tag/branches, README commands, channels, catalogs, filenames,
   asset digests and part identities after publication. Both repositories use
   dev as default/development and numeric X.Y.Z version branches. Preserve all
   previously published tags/assets; publish corrections as a new product patch.

Product version is distinct from workflow_version, schema/design revision,
native-Math policy, Python/LibreOffice and runtime/companion resource versions.
Do not mechanically replace those independent identifiers or old task bindings.
Unchanged immutable resource assets and inherited bundle parts keep their
original filenames/URLs and hashes. Runtime binary changes require a real need;
an installer/catalog patch does not create a new runtime binary release.
Keep user data, private knowledge/fonts/tasks, active runtime, local modifications
and global skills intact. Prepared release checkouts are separate from a modified
active installed skill; never force or falsely relabel that installation.
<!-- lotraAI-version-consistency:end -->
