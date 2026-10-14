# Publication layout

| Repository | Purpose |
| --- | --- |
| [lotraAI skill](https://github.com/jiang-zl/lotraAI-image2slide-skill) | Product documentation, skill source, examples, usage |
| [lotraAI runtime](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime) | Complete-bundle transport, version manifests, download helper |

Each repository publishes `1.31.0` and `release` branches. Both initially identify the same v1.31.0 publication commit within that repository. The default branch is `release`; tag `v1.31.0` identifies the GitHub Release. The skill repository's pre-existing `main` history is retained.

Three release transport parts, a version manifest, and a helper reconstruct the single complete ZIP. Assembly checks every part and the original complete ZIP. Large local artifacts and private work are ignored by Git.

The ongoing `sci-rebuild` checkout is outside this publication. Frozen skill payload files are retained byte-for-byte. Functional product validation remains `NOT_RUN_PER_USER_REQUEST`. See [validation notes](validation.md).
