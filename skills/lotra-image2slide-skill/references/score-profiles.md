## v1.0.3 scoring boundary

For `appearance_policy: semantic_hd_replace`, source-pixel-only similarity/error metrics cannot be promotion gates. Keep them as diagnostics; prioritize semantic match, actual clarity, coherent texture, placement and complete layers. Existing profiles still govern comparable measured alternatives. The [visual agent loop](visual-agent-loop.md) awards only supported working improvement without new damage and uses substantive result goals for delivery; no uncalibrated aggregate is an automatic success certificate.

# Fixed score profiles for candidate screening

Use `score-candidates PROFILE.json BATCH.json --out RESULT.json` only after
freezing a profile for the specific source and semantic scope. An icon, a
module, and a whole slide may require different metrics and weights; scores
from different profiles are not directly comparable. Record calibration
anchors and the profile hash in the drawing plan **before** rendering the
candidates. If a metric falls outside the frozen calibration range, create a
new profile revision and remeasure every candidate under that revision.

A profile uses `schema_version: score-profile-1`, nonempty `profile_id`,
`source_hash`, `scope_id`, and `calibration_evidence`. Each entry of `metrics`
specifies `direction: higher|lower`, fixed finite `bounds: [low, high]` and
positive `weight`. Optional raw `hard_min`/`hard_max` and normalized
`max_regression` gates are checked before scoring. For example:

```json
{
  "schema_version": "score-profile-1",
  "profile_id": "icon-texture-v1",
  "source_hash": "<64-character source SHA-256>",
  "scope_id": "server-icon",
  "calibration_evidence": ["pre-candidate calibration receipt path and hash"],
  "metrics": {
    "shape_iou": {"direction": "higher", "bounds": [0, 1], "weight": 2,
                  "hard_min": 0.8, "max_regression": 0},
    "texture_l1": {"direction": "lower", "bounds": [0, 1], "weight": 1}
  },
  "important_metrics": {
    "texture_l1": {"min_gain": 0.02, "composite_tolerance": 0.005}
  }
}
```

The batch uses `schema_version: score-batch-1`, the profile's exact
`profile_hash`, matching `source_hash` and `scope_id`, one `baseline` with
`id`/`vector`, and a `candidates` list of distinct IDs and complete raw
vectors. Normalization is fixed by the profile, never by the candidate batch.
Missing, infinite, extra, or out-of-range metrics are not imputed or removed
from the denominator. A critical floor/regression fails even if the weighted
total rises. An important metric can make a candidate worth further review
when the total is tied or within its predefined tolerance.

The output deliberately says `SCORE_CANDIDATE_ONLY`. A score candidate must
still pass scientific content, visual context, native editability, saved PPT
and user-acceptance gates before it can become a selected slide. Synthetic
profile tests establish the arithmetic and rejection behavior; they do not
calibrate real thresholds or prove image quality.

`register-iteration ... --score-profile PROFILE.json --plan-conformance REPORT.json`
uses that same frozen profile to decide whether a measured semantic candidate
replaces the registry's local best. The report must bind the exact Scene and
saved PPT. For analyzed Scenes, context-best and feasible promotion additionally
require `plan_conformance.status: PASS`; a raw metric or a profile gain cannot
promote an unexecuted drawing plan. The registry still records rejected and
unverified attempts so a later repair can use their evidence without calling
them accepted work.
