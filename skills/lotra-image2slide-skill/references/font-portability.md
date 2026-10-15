# Source font intent and editable portable delivery

For revision 6, first read [the mandatory Chinese/English collection rule](font-collections-v132.md). It overrides earlier unrestricted family/gallery selection. Read this file for resource provenance and `tool_font_embedding` mechanics. Existing textbox/part quality, native grants, property protection and finite repair remain in the same loop. Font resources are not a second source oracle.

## Intent before resources

Separate four facts: user or original-file font intent; observed glyph/style class; exact family/face identity; resources available to the selected host. Serif/Song style alone does not identify a specific typeface. SimSun/宋体 aliases must come from that resource's own name table; Noto Serif CJK SC is another family. Never score a requested family out of existence or replace it silently. A missing exact family remains a resource/capability issue; choose an existing suitable host or communicate it. Do not install fonts or Office automatically.

Freeze explicit user choices in `start --objectives FILE`, for example:

```json
{"font_requests":{"ea":"SimSun","latin":"Times New Roman","math":"Cambria Math"}}
```

These are user demands, not defaults for every source. Owner-specific choices use `font_requests:{owner:{ea:family,latin:family,math:family}}`. Record the actual user request in task evidence; never invent user provenance. Known identities reuse metadata; raster-inferred choices stay `approximate`, even when the concrete selected font file is exact. A source metadata claim requires a separately supplied original-file metadata reference, not pixels or the current PPTX's authoring hint.

## Binding packet

The program freezes at most eight owner/location/script requests and returns candidates scoped to the Chinese or English collection for each request. Provide isolated original glyph samples through `font_binding`; `font_collection.ranking` compares the eligible actual resources and registers the source-bound result. An inferred binding selects that result's closest eligible face. Existing `font-gallery`/`rank-fonts` remain optional legacy diagnostics and cannot replace the revision 6 language-scoped selection receipt. Exact user requests preserve their distinct provenance within the language rule. Keep the native text size, box and spacing fixed, and use bounded packet-detail selectors rather than loading the full catalog.

Reply using actual packet/resource IDs:

```json
{"packet_id":"CURRENT","font_bindings":[{"request_id":"CURRENT_REQUEST","family":"SELECTED_REAL_FAMILY","resource_id":"CATALOGUE_ID","origin":"raster_inference","status":"approximate","evidence":{"source_hash":"ORIGINAL_SHA256","roi":[0,0,1,1],"description":"Actual discriminating original glyphs"},"alternatives":["ACTUAL_OTHER_FAMILY"],"comparison_ref":{"path":"scratch/font-rank.json","sha256":"RANK_SHA256"}}]}
```

For user choices use `origin:user,status:exact` and the frozen demand; metadata choices add the supplied `source_metadata_ref`. Do not use placeholders as evidence. `synthetic_style:true` is separate from family identity: prefer real weight/slant faces, disclose supported synthetic Office styling when an exact family lacks the requested face. Raster style synthesis requires `evidence.style_description`. Native math alternate italic/upright faces share its primary family; compiler punctuation auxiliaries retain their real family. A changed bound family needs the existing native font grant, prior binding hash and a source-supported revision; ordinary placement repairs do not reopen font intent.

All native Scene text/math/cells compile Latin, East Asian and complex-script typefaces on actual runs. Table defaults and mixed mathematics use the same contract. Text-bearing imported artwork must expose independent native text owners instead of hiding them in an opaque group. A raw `build` with text needs `font_plan` from this runtime; arbitrary style strings cannot bypass bindings. Diagnostic galleries do not constitute delivery.

## Existing-host resources and cache

`core.font_resources` reads actual font name/face metadata, file hash, weight/slant, glyph coverage and embedding permission. Common resources are archived before construction in `toolchain/font-collections`; additional eligible selected resources extend that archive. Bound resources also get private immutable snapshots in `.lotraAI-build/toolchain/font-snapshots`; this is not an OS installation or a public font bundle. Resource and EOT caches track input/output identities. Source evidence and current availability remain distinct.

`core.tool_router` stores `.lotraAI-build/toolchain/environment.json` and `font-resources.json`. Windows/WSL, Linux and macOS use their existing directories/configured `font_roots`/`font_dirs`; font and executable changes refresh relevant environment context. An installed Mac PowerPoint discovery is separate from a connected controllable host. Moving a project rebases relative snapshot references; it never aliases one family to another. No recurring GUI probe is required for unchanged resources.

## Complete fonts in the PPTX

`core.font_embedding` writes complete static TrueType faces (including extracted TTC faces) as PresentationML EOT font parts with full-editable settings. Required faces are deduplicated by actual resource identity, not copied once per textbox. No intentional character subsetting; recipients need complete glyph coverage to edit new text. Ordinary native text/math remains editable, with shape/layout data retained. Private fonts never enter the public skill ZIP.

Non-direct formats use an existing compatible font provider. On Windows/WSL the runtime can use installed Office on a new owned copy; elsewhere answer `tool_font_embedding` through a currently available suitable host. Return `font_provider:{path,sha256,input_sha256}` on a separate task-local copy. The program transfers only font parts/settings/relationships from it, retaining the original native slide bytes and already compiled font resources. It checks complete faces, actual names and editable permissions. Unsupported/compressed provider encoding, variable resources, permissions, missing glyphs and file-budget limits remain explicit failures/pending, never successful substitution. A discovered app is not a successful save.

Complete font parts have a 64 MiB default resource bound; report actual added font bytes and retain explicit errors rather than silently subset. Save staged failures once and select a different evidenced route instead of retrying them blindly. `Fonts.json`/`Result.json` record concrete choices, inference, synthetic style, embedding and limits. Existing external user files remain authoritative; changed native font intent must be reconciled before a new delivery, not declared portable from a stale receipt.

Supporting PowerPoint versions can use embedded fonts; arbitrary readers may ignore them. Embedding does not prove original-font inference or identical rendering across every app. Actual glyph quality stays in the existing scoped drawing loop. [Microsoft font embedding guidance](https://support.microsoft.com/en-us/office/fonts/benefits-of-embedding-custom-fonts), [SimSun identity](https://learn.microsoft.com/en-us/typography/font-list/simsun), [font-part content types](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/1663dabc-5d98-463f-889e-bcd9b77c3d34), [EOT format](https://www.w3.org/submissions/EOT/).
