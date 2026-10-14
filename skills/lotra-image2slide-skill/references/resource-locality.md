# Resource locality

Read this when planning same-resource checks, investigating repeated image/PPT/PDF
work or interpreting `workflow-control profile`. Use current packet references;
resource grouping cannot establish semantic equivalence or authorize a mutation.

Prepare adjacent finite actions for the same original, current candidate and
explicit object owner when their current contracts permit it. `workflow-control
plan` orders located failures by dependency phase and then explicit owner resource
group. Unidentified owners remain unresolved. Prevalidated batches execute in the
submitted order under one task resource scope; they do not reorder stateful
reports, fabricate later baselines or skip any member's checks.

`scripts/core/resource_facts.py` owns shared raw resources. Every lookup freshly
hashes the actual artifact. Image dimensions use a header-only lookup; final ROI
pixels are looked up before full decoding or transformation. Common transformation
prefixes, such as preview-to-source-canvas resizing, are borrowed across child
crops. RGB, native palette/transparency and white-background composition are
distinct recipes. Original rounding, operation order, context padding, fractional
sampling boxes and requested scales remain explicit.

Read-only image borrowers expose dimensions, crop and resize. Mutating consumers
receive owned images or XML/tree copies. ZIP snapshots and parsed XML parts are
shared along with immutable decompressed package entries; XML parsing disables
network/entity resolution. Small PDF documents use
hash-bound snapshots. Each distinct HD scale still performs its actual requested
vector rasterization on a miss; a 4x image cannot stand in for 1x/2x evidence.
Borrowed PDF documents are read-only. Creation, editing, merging and actual Office
conversion continue to use their existing finite executors.

One scope uses the existing memory budget with a conservative byte estimate and
at most 256 cached entries. Active borrowers are pinned against eviction. A large
resource or exhausted capacity is processed without admission; no budget changes
coverage, targets or required sampling. All cached handles/images close on scope
exit. This bounds retained estimates, not total process RSS or a library's internal
working memory. Native geometry keeps its existing separate snapshot budget.

Only small RGB/L pixel payloads are persisted in the existing private Library
cache, with bounded raw size, compressed payload checksum and normalized exact
dependencies: task/original scope, actual resource hash, pixel recipe, provider and
common code, context policy and library versions. No semantic decision, quality
PASS, acceptance receipt or other original's records are introduced by this layer.
Cache trimming affects only recomputable rows, preserving records/blobs/evidence.
The task-scoped Library constructor is reused; SQLite connections still close
after each bounded transaction.

An independent final session creates a fresh resource scope, bypasses persistent
pixel and Library measurement-result hits, and recomputes current predicates.
It may share newly collected raw facts among its own checkers. Nested different
tasks receive separate scopes. Native descendants, source children, table cells,
icon re-identification, multi-scale material/fidelity, Office Math/fonts, every
required relation, per-object best/rollback and final local/global gates remain.
PDF lifecycle checks and disposal occur after all actual dependent consumers.

Completed resource scopes record header reads, actual decodes/transforms,
package opens/part decompressions/XML parses, PDF opens/clip rasters, cache hits, compatibility full
copy requests and evictions. The copy counter is not every internal PIL copy.
The profile aggregates these current-task counts separately from inclusive command
timings. Counts are observations, not saved-token or speedup claims. In-progress
scopes and old scopes without counters are not included.

Remaining limits: repeated current-file hashing still reads bytes; isolated CLI
processes retain only small persisted pixels, not decoded whole images or live
documents; isolated mutating XML/native consumers still copy trees; some specialist
builders, new-render validators, native capture and mask/fit paths retain their
own resource reads. Cache misses add checksum/compression/SQLite work. Never
replace mandatory current verification with a cached PASS to hide these costs.
