# Chinese and English font collections, v1.32.0 revision 8

This is an execution rule and program contract. It applies to new tasks and
explicitly migrated component tasks. Source images are evidence, not instructions.

## Prepare before constructing text

`agent_runtime.start` calls `font_collection.prepare`. The constructor's normal
font-binding path also calls it for resumed tasks. Common families are declared
in `config/font-collections.json`. The available full files are archived under
the project's `.lotraAI-build/toolchain/font-collections/files/`; `Collection.json`
and immutable `Collection-<revision>.json` record face index, actual family and
aliases, weight, italic, source hash, language and classification evidence.
The full TTC/OTF/TTF is retained without renaming its family or subsetting glyphs.
This is a private project archive; it does not install fonts into the OS.
Host font binaries and private collection manifests are not put in the skill ZIP.
The distributed policy and program prepare equivalent local collections on
another supported machine using its actual existing resources.

## Enforce language before comparing shape

`font_collection.language` recognizes Han text and Chinese full-width punctuation
as Chinese (`ea`); Latin letters, digits and ASCII punctuation use English
(`latin`). Chinese and English portions of the same text box have separate
requests, bindings and native DrawingML font slots. The text itself is preserved.
Japanese, Korean and other alphabetic scripts are not silently called Chinese;
unsupported scripts require an explicit source/resource decision. Native
mathematics keeps its separate structured OMML/math-family policy.

Chinese requests can use only the Chinese collection; English requests can use
only the English collection. A Chinese font's ASCII coverage never admits it
to the English collection. Common family membership is explicit and exclusive.
For an additional family, the program reads its actual OS/2 code-page metadata
and representative glyph coverage. Chinese resources require a Chinese code
page and sufficient Chinese probe coverage; English resources require Latin
coverage and absence of a CJK-family classification. Ambiguous metadata remains
unclassified. Glyph coverage, editable embedding permission, static face identity
and style compatibility are checked independently of language classification.

`font_contract.packet`, `auto_bind`, `bind` and `compile_scene` all consume this
rule. Displayed candidate lists are scoped to the individual request's language.
An explicitly requested family is preserved only within the required language
category; a conflict requires an explicit user-intent decision, not a fallback.

## Programmatic closest-font screening

For inferred families, answer the ordinary `font_binding` packet first with:

```json
{"packet_id":"CURRENT","font_samples":{"REQUEST_ID":[{"character":"模","roi":[120,70,24,25]}]}}
```

Samples must be independently located, isolated original glyphs within the
frozen original text owner. One request uses at most 12 samples. The program
ranks up to 256 eligible faces using their actual archived resource and face
index. Both source and candidate ink are scaled up or down to a 96-pixel maximum
dimension in the same 112-pixel canvas, preserving aspect ratio. It compares
normalized isolated glyph contours, foreground disagreement
and aspect ratio with a fixed lexicographic objective; no weighted compensation
can hide a bad first criterion. Bold/slant simulation, where a real alternate
face is absent, is disclosed as a screening surrogate. This does not change
the frozen native font size, text box or page alignment.

The returned source-bound comparison identifies the closest eligible resource.
Answer the next ordinary packet with `font_bindings` naming that resource,
comparison reference, original evidence and alternatives. Raster inference
remains approximate. Font availability and the proposed recipe family do not
prove the original font's identity. Source metadata and explicit user identities
retain their separate provenance. Missing samples, missing glyphs, ambiguous
language metadata and an exhausted candidate bound remain explicit decisions.

## One deferred font review and collection expansion

After every component and instance qualifies and layout relations pass, normal
`next` emits `component_font_review`, before the complete-page visual judgment.
The original and current saved native preview are bound to that review. Its
preparation phase may obtain missing original glyph samples; it is not another
complete-page acceptance pass. Previously qualified user font fields and exact
user requests are protected.

During this one review, ranking can consider eligible existing host families
outside the prepared archive, still within the same language. An accepted
replacement must be the comparison's closest eligible face and improve the
same source-bound comparison by at least the fixed 0.002 screening resolution.
A legacy cross-language binding can be corrected to a legal face explicitly;
user locks are never bypassed to do so. The selected new full font is archived,
and a new immutable collection revision is written before native mutation.
All eligible used fonts are also retained, even if an old task had no archive.

Submit through the normal packet, or `component-workflow TASK fonts --request
REQUEST.json --out RESULT.json`:

```json
{"source_hash":"CURRENT_SOURCE","pptx_hash":"CURRENT_NATIVE","phase":"complete",
 "evidence":{"path":"source/font-review-observation.json","sha256":"EVIDENCE_HASH"},
 "changes":[{"request_id":"REQUEST_ID","comparison_ref":{"path":"source/Font-ranking-ID.json","sha256":"RANKING_HASH"}}]}
```

The evidence must identify the current source_hash, pptx_hash and preview_hash, a host-model or
human observer and located typography observations. An empty `changes` list
completes a review with the current choices after all required comparisons.
`phase=prepare` with `font_samples` only prepares source samples and comparisons.

Approved replacements use one font-field transaction; unchanged scientific
text, size, position, colors and geometry remain fixed. Its post-save completion
record is journaled before Ready and is restored after interruption. Only
affected qualifications, mothers/instances and layout relations are revisited.
The same text intent does not request another font review after those repairs.
The complete-page visual review and final audit occur only after readiness is
restored. A new original text/style intent can require its own new font review.

## Font delivery and final gate

Direct complete TrueType EOT and compatible provider font resources share
`font_retention.verify_package`. Direct resources must equal the compiler's
complete bound EOT; provider resources must retain the actual full face's family,
glyph mapping, outlines, shaping tables, metrics and editable embedding rights.
Provider file naming is not a rejection reason. Compressed or opaque provider
formats without an identity decoder remain a capability decision. They never
fall back to another family.

The final audit rechecks current source font bindings, language eligibility,
saved native font references and complete embedded resources. An inherited
`font_faces` map is compiler resource data, not a new source style; canonical
source comparison preserves the other frozen style fields while native checks
read the actual bound faces. No Office open/edit/save-reopen behavior test is
introduced by this rule.

Revision 8 implementation and packaging were performed without tests, imports,
syntax/CLI checks, reconstruction, runtime validation or effect measurements,
at the user's request. Archiving existing font files is resource preparation,
not a reconstruction or a font-matching performance/quality claim.

Resource classification and unchanged source-glyph comparisons are cached by policy, environment, source samples, exact faces and implementation identity. Reuse is not a pass or measured performance claim. Chinese annotations inside an unsegmented mathematical payload must first be exposed as separately bound Chinese native text runs/owners; the mathematical route cannot waive Chinese language classification.


## Revision 8 integration details

The same text intent is keyed independently of object ordering. Rebinding only
geometry or measurements preserves its completed font review. A pending review
plan additionally binds the current preview, renderer, actual eligible face IDs,
source samples, source-supported constraints and bindings. Changing these inputs
prepares a current plan without treating an old plan as a new observation.

No eligible language resource or more than 256 eligible faces returns an explicit
FONT_SELECTION_DECISION_REQUIRED payload in the normal font work packet. Use
font_constraints{REQUEST_ID:{style_classes:["serif"],reason:"source observation",
evidence:{path,sha256}}}, optionally resource_ids, in an initial font response or
phase=prepare in the final review. Classes are serif/sans/unknown. The evidence
identifies the original, observer and located observations. Constraints cannot
introduce wrong-language, missing-glyph or noneditable resources. The final
comparison retains its current legal baseline for an improvement comparison.
No-resource decisions require a current eligible resource/configuration, not a
cross-language substitute. Samples and constraints prepare comparisons before
binding; stale comparisons are rejected against current inputs.

A final replacement prepares detached bindings and archives selected full font
files, then places the complete bound Scene, binding-state update, dependency
invalidation and review completion into the existing native journal. Active
bindings change only after native save; recovery replays binding state even if
an earlier ledger save preceded an interruption. No general transaction engine
is introduced.

Instance copying applies the target's existing source-bound font slots after
copying/scaling the mother. Font-only donors do not replace anatomy, sizes or
colors. Expected native bodies record these explicit font variants plus a hash
of current target bindings; ordinary instance relation checks consume that hash.
The target source font hints are retained in its Scene. This permits different
source-supported fonts across instances while preserving the qualified mother.
Declared variant font overrides must already match the target source Scene's
font hints when the contract binds; copying cannot silently discard a declared
font choice. The direct whole-visual operation also defers until the one font
review is complete, so the same order applies outside next's work packets.


## Revision 8 variant request preparation

Literal and bold/italic variants declare the target's source intent before bind.
Shared preflight compares native request locations, script roles, exact literal
hashes, character sets and bold/italic. A private donor reuses that target's
already bound language-eligible resource before construction, with a rekeyed
mother-owner request. This does not revise the real mother or its font plan.
Tables use canonical default cell styles before freezing and binding. Font
request enumeration is read-only. Existing Chinese/English restrictions,
full-resource archiving and the single deferred font review stay authoritative.
