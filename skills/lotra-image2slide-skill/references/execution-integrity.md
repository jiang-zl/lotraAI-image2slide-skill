# v1.8 execution integrity

Use the section named by the current packet. Full drawings, previous readings and intermediate evidence stay on disk; do not concatenate every reference into model context. The existing `start / next / submit / sync / authorize-edit / export` interface remains the only orchestrator.

Sections: [original features](#original-feature-packets), [composition](#semantic-composition-source-packets), [preservation](#controlled-adoption-and-preservation), [repair strategy](#strategy-packets), [external edits](#external-edit-packets), [capture cache](#actual-capture-identity).

## Original feature packets

`analysis` may include `source_inventory` or immutable `source_inventory_ref{path,sha256}`. Otherwise a `source_inventory` packet precedes construction. Submit the packet ID and the original-only inventory:

```json
{
  "source_inventory": {
    "source_hash": "<unchanged original sha256>",
    "features": [{
      "id": "task-document-pen",
      "roi": [100, 140, 38, 7],
      "kind": "icon",
      "status": "observed",
      "evidence": "One thin pen, separated below the document, with its own end shape.",
      "owner": "training-documents",
      "source_part": "pen",
      "quality_property": "pen-outline-and-gap",
      "importance": "major"
    }]
  }
}
```

Coordinates and observations in this example are illustrative, not measurements for a real image. Inventory kinds are `text / formula / icon / shape / line / relation / texture / uncertain`. Status is `observed / inferred / uncertain / excluded`. Keep natural semantic features rather than mirroring every primitive. Include small meaningful details and unresolved original clues even when there is no construction owner yet.

Important observed/inferred features require a named `quality_property` in the corresponding source unit. `source_part` must have a coverage binding to that unit; text, formula and relation require their own matching profile. A visual measurement window may cover at most four times the feature ROI area (bounded local context); a whole-panel mean is not that feature's measure. This is a localization guard, not a universal image similarity target. Use the existing type-specific source minimum/stretch metrics and actual property observations. A missing owner, binding, property or required original reading remains debt and prevents silent final acceptance.

Uncertain source information stays uncertain until a raw original crop resolves it. `inferred` illustration parts require explicit semantic `constraints` and disclosure; scientific words, math and relations cannot use this inference route. Only non-figure material can be excluded with its reason; critical content cannot be excluded. Revisions retain feature IDs and previous files. Correcting original ROI/kind/evidence/importance needs `original_correction{reason,source_view}` with the existing exact-original view binding; changing the inventory alone is not drawing improvement.

The output residual observer now proposes fine connected regions, multi-scale windows and local peaks as well as coarse context. These are bounded observation proposals, not defect verdicts. Read the original and actual saved result for the proposed region, then assign a concrete discrepancy and source owner. No proposal proves completeness of model semantic understanding.

## Semantic composition source packets

Use the existing [semantic composition](semantic-composition.md) contract fields. Compilation requires one object for `opaque_core`/`opening`, two for directed `order`/`inside`/`join`, and at least two distinct instances for `same_template`. Decision contracts must match the actual proposed pair, kind and owner ancestry. For a directed decision use `roles{first,second}` to disambiguate its semantic direction; sorting a discovery pair is not a direction. An owner cannot borrow another owner's opaque/opening contract.

For `inside`, name the parent, child and, when the parent is a group, `container_body`: one closed native body shape within the parent subtree, independent of the child. The runtime projects that body's interior on a private observation copy; child paint support is captured separately. A parent group containing the child, a group frame or an open line cannot certify containment. An outline-only closed shape can supply its interior through this projection; fill/line/text changes affect the private copy only. Unsupported bodies remain pending and must receive an appropriate native representation, never a fabricated interior pass.

Repeated mothers require nonempty role bindings to their true native descendants. The comparison includes real style, text, nested parts and referenced resources; same outer frame or empty roles do not prove identical artwork. Source-permitted instance transforms remain separate from mother appearance.

## Controlled adoption and preservation

The native writer owns narrow fields and exact grants. Local edit, automatic repair, renderer refresh and initial working-baseline adoption share candidate adoption preparation and retention. Layout, textbox, composition and actual affected-unit gates protect the selected baseline. A working baseline is not final acceptance.

One dependency resolver separates exact write scope, transformed descendants, ancestors and quality/relation/layer observation dependencies. Actual rendered pixel dependencies complement native dependencies. Neither reading a dependency nor invalidating its observation permits modifying it. Satisfactory unaffected properties are inherited from actual native/pixel evidence; changed/dependent properties return to the bounded observation queue. Explicit changes in user intent require a new target binding, not an automatic exemption from an unchanged source contract.

## Strategy packets

Repair packets contain saved intermediate diagnosis: `supported / excluded / unresolved`, a stable diagnosis key and source/native evidence. Absence of a native owner cannot be repaired by reordering it. A correct order excludes that operation for the same two participants, not all possible geometry or layering defects. Source-domain errors first need source rebinding. A plausible explanation without discriminating evidence remains a hypothesis.

After two ineffective attempts in a branch, `strategy` replaces repeated identical repair. Reply with:

```json
{
  "strategy": {
    "action": "select",
    "operator": "representation",
    "cause": {
      "stage": "recipe",
      "evidence": {
        "artifact": {"path": "<task-owned existing intermediate>", "sha256": "<hash>"},
        "expected": "<specific source property>",
        "observed": "<specific saved discrepancy>"
      }
    },
    "reason": "<how this distinct operation addresses that discrepancy>"
  }
}
```

Cause stages are `source_specification / recipe / instance_geometry / z_order / parent_transform / font / render`; the example is only a data shape. Operators are `geometry / paint_order / native_style / font / representation / render / source_rebinding`. A changed causal stage requires a contrasting actual intermediate `contrast_artifact{path,sha256}`, different from the first artifact. Paint order requires `stage:z_order` and exactly two native `evidence.participants`. The subsequent repair must use the selected stage/operator and unchanged narrow permissions.

Branch identity binds issue/property/source-specification/stage/operator, not free prose or candidate filenames. Defaults allow at most two ineffective branch attempts and twelve repairs per issue (bounded configuration 1..2 and 1..32). `strategy{action:stop,reason}` prunes this issue without calling it resolved. Other independent issues continue. If all important remaining issues have no useful evidenced route or their budget is spent, the runtime returns `STALLED` with the best result and unresolved debt. Tiny/repeated no-op changes cannot earn acceptance or unlimited retries.

## External edit packets

`sync` preserves the actual user PPTX and previous snapshots. Stable same-slide native shape identity can migrate an unambiguous renamed object; it is a structural mapping, not semantic proof. Known scene/built/unit/contract bindings use the mapping overlay while original evidence remains immutable. Affected native and actual pixel dependencies lose stale quality observations and return to a bounded queue.

The selected user file starts `USER_ADOPTED_QUALITY_PENDING`. Answer `external_edit` with the actual `candidate_hash`, seen `view_hashes` and `intent_resolution:source_compatible|intent_changed|unresolved`. `intent_changed` requires `user_intent{reference,text}` from the real user request. Source-compatible edits without unresolved structural bindings can continue through observation. Added/deleted/ambiguous/regrouped owners and changed semantic expectations require explicit binding/target redefinition; they stay pending, not automatically accepted or reverted.

`USER_INTENT_PENDING` is an honest holding state, not an implemented automatic semantic merge. Do not loop on `next` unchanged: preserve the user snapshot and resolve the particular target/binding with the user and existing source-contract interfaces. This release does not infer arbitrary new scientific intent from an edited PPTX.

## Actual capture identity

Isolated owner keys follow its native subtree, ancestors, truly referenced package resources and measurement mode. Unrelated bitmap additions do not invalidate every owner; inherited layout/master/theme remains a conservative dependency. Cache validity also binds actual backend/version/build, renderer/provider script, routing fingerprint, environment epoch and sampling protocol. Text captures additionally depend on actual font-file identities/font discovery configuration. Unknown current host identity cannot validate old captures.

Geometry and container-interior observations do not depend on irrelevant text font state. A new actual render refreshes current host context; historical candidates cannot roll it back. Consuming the same valid capture receipt is idempotent. Batches keep immutable requests and resume only missing owners. Cached artifacts are not publisher signatures or proof of global semantic quality.

## Scope of the guarantee

Program checks govern controlled runtime submission/adoption/export, not arbitrary host file writes outside it. They enforce bound properties, preserve evidence and prevent known structural bypasses; they cannot make every model reading correct. No v1.8.0 drawing or performance measurement was run during this implementation release. Keep failed, pending and unmeasured statuses explicit and attribute historic evidence to its real version.
