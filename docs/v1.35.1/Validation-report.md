# 1.35.1 validation scope

This maintenance release received source and rule static review only.

| Channel | Status |
|---|---|
| Nine reported design/implementation findings | IMPLEMENTED_STATICALLY_REVIEWED_UNTESTED |
| Normal source/build/measure/repair/qualification/final call-chain review | STATIC_REVIEW_ONLY |
| Source/package manifest and byte identities | Packaging and synchronization bookkeeping only |
| Product tests and regression fixtures | NOT_RUN_PER_USER_REQUEST |
| Syntax / AST / import / CLI checks | NOT_RUN_PER_USER_REQUEST |
| Runtime startup or installation execution | NOT_RUN_PER_USER_REQUEST |
| Original image reconstruction | NOT_RUN_PER_USER_REQUEST |
| Rendering / Office behavior | NOT_RUN_PER_USER_REQUEST |
| Performance / quality-effect / provider-token measurements | NOT_RUN |
| Whole original-artwork acceptance | NOT_CLAIMED |

The existing independently versioned runtime binaries/resources are reused;
their older capability records were not revalidated by this source patch.
Static review, successful packaging and publication do not establish executable
or artwork acceptance. No user original, reconstructed PPT or private task was
used as a release fixture. See Static-review.md and publication/source receipts.
