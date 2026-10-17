# 1.35.2 validation scope

The user authorized implementation, static source/rule review, source/package
synchronization and publication, and explicitly excluded tests and reconstruction.

| Channel | Status |
| --- | --- |
| Source/rule call-chain review | Performed statically; see Static-review.md |
| Managed source, package inventories and hashes | Recorded by packaging/source publication tools |
| GitHub assets and stable metadata identities | Recorded separately in Publication.json |
| Unit/regression/fixture tests | NOT_RUN_PER_USER_REQUEST |
| Syntax/AST/import/CLI/product startup checks | NOT_RUN_PER_USER_REQUEST |
| Runtime startup or installation checks | NOT_RUN_PER_USER_REQUEST |
| Original image reconstruction | NOT_RUN_PER_USER_REQUEST |
| Rendering and Office behavior | NOT_RUN_PER_USER_REQUEST |
| Performance/token effects | NOT_RUN |
| Whole user-artwork acceptance | NOT_CLAIMED |

No old receipt qualifies this patch. Runtime binaries, companion resources and
prepared environment records are inherited, unchanged and not revalidated.
