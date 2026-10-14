# Adaptive original-detail refinement

Use this reference for `adaptive_source_detail` packets, `source-detail` commands,
or unexplained local differences in a complete source assembly. It is mandatory
in normal next, whole-quality run and official export, including retained old
artwork. It complements independent source recursion and all saved-layer checks.

## Decisions and evidence

Start with natural semantic objects and drawing units. The program scans every
original quality unit; content/AST and connector predicates keep their exact
existing programs. Geometry, curves, illustrative objects and texture use their
own numeric loss bands. SSIM, PSNR and edge/colour measures are diagnostics and
triage; a numerical trigger is not a claim that a new semantic object exists.

The program also searches missing original edges in overlapping 24-source-pixel
windows at stride 12 and in connected residual clusters. This can schedule a
tiny missing detail even when the large object average is good. Each work item
contains the original/current same-coordinate object, located discrepancy crops,
the original parent and nearby text/object/connection owners. Enlargement is a
display aid, not invented detail. Always observe the child and necessary context.

Return `observed_parts[{id,roi,observed,objects}]`, source-supported `relations`,
located `diagnosis`, `evidence`, `checks`, and `resolution`:

- `restore_structure`: missing/wrong observed anatomy, connection or layer;
- `appearance_only`: original structure retained with evidenced sampling,
  clarity, texture or declared appearance differences; still bind actual checks;
- `uncertain`: unresolved interpretation remains pending, never accepted.

Checks are finite `native_frame`, `native_type`, `parts_present`, `join`,
`contains`, `layer` and `source_patch` predicates. Every observed part requires
an executable check. `join` freezes the source axis, min/center/max anchors,
offset and uncertainty; touching is never imposed by a name. `source_patch`
retains its own original ROI and edge/SSIM/colour bound. Original feature
functions and original-only colour rectangle/axis-stroke fitting construct the
native geometry; the host does not manually move objects as a repair method.

Each disposition includes `source_observability.kind` and located
`source_evidence`: `clear_structure`, `blurred_illustration`,
`stochastic_texture`, `subpixel_detail`, or `unresolved`. Original blur/texture
requires original uncertainty regions. A structured icon cannot declare itself
stochastic texture. Coarse groups require all independently bound native leaves
as actual child observations; presence/type checks alone never close a suspect.
Clear structure with measured SSIM below 0.45, or PSNR below 9 dB together with
edge F1 below 0.65, fails and enters local reconstruction. These are severe-error
engineering red bands, not a normal quality target or universal research cutoff.
Type-specific primary metrics and topology/content gates remain mandatory.

Independently registered foreign source objects can be excluded from the local
comparison when they occlude the subject. The program pools an unmodified SSIM
map over fixed original support and its window halo, retains raw scan values,
and requires at least 16 valid pixels and 35 percent of the window. Insufficient
support remains failed and requires a better source ownership window. It cannot
be hidden by excluding the subject itself or by candidate-dependent alignment.
Very small original child details (short side at most 8 px, area at most 64 px)
use independent geometry/relationship checks rather than inventing an SSIM value.
At most one full default 7-pixel SSIM window fits across these tiny marks;
there is too little statistical support to use that scalar as their sole hard
gate. Their raw numbers remain reported, original feature construction and
contour/geometry remain mandatory, and the same exception cannot apply to an
entire normal-size icon or panel.
The original autocontrast/unsharp view is explicitly labelled derived and hashed;
the unchanged original remains authoritative.

Facts are retained separately from output inventory. They enter the original
tree as distinct critical features and the recursive check graph as mandatory
detail receipts. They invalidate prior result/acceptance and object context
closure. A `verified_assembly` label or approved baseline cannot close a failing
detail. The original crop hashes and the discrepancy's triggering context stay
with the facts after repair. Parents propagate actual detail failures.

## Threshold interpretation

`adaptive_detail.POLICY` is versioned. For each original unit, six fixed benign
controls (Gaussian sampling 0.35/0.6 source px, 0.35 px shifts and contrast
0.97/1.03) provide a finite source-only loss envelope. The trigger is
`min(class_cap, max(class_floor, max(control_losses)+0.035))`.
Calibration is frozen against original/ROI/class/configuration before candidate
comparison. It is not a statistical population quantile. Candidate failures may
not train or loosen their threshold.

Initial SSIM-loss / edge-loss / mean RGB error floors and caps are:

| Class | SSIM loss | Edge loss | RGB error |
|---|---|---|---|
| Geometry | 0.18–0.38 | 0.15–0.35 | 0.10–0.24 |
| Illustrative | 0.30–0.65 | 0.24–0.50 | 0.17–0.32 |
| Texture | 0.36–0.72 | 0.35–0.65 | 0.20–0.40 |
| Curve | 0.22–0.45 | 0.16–0.38 | 0.12–0.26 |

SSIM loss is `1-SSIM`; raw SSIM is preserved, including negative values. PSNR
uses data range 1 and is reported in dB; exact pixels use an explicit exact
status rather than nonfinite JSON. Thin/tiny regions may have inapplicable SSIM;
native/content and local structure checks still apply. Edges use 1.5 source-pixel
matching tolerance. Local missing-edge fraction 0.35 and resolved cluster support
are source re-observation triggers, not a semantic segmentation algorithm.

These are engineering trigger defaults, not universal acceptance cutoffs. Source
blur, intentional illustration improvement and colour/style contracts need
different interpretation. SSIM remains reported alongside other dimensions;
critical structure cannot be compensated by a higher weighted aesthetic score.

Research: [Wang et al., SSIM](https://www.live.ece.utexas.edu/publications/2004/zwang_ssim_ieeeip2004.pdf)
supports local structural comparison and explains the limits of pixel error;
[Ding et al., DISTS](https://arxiv.org/abs/2004.07728) distinguishes texture
resampling and structure; [skimage metrics](https://scikit-image.org/docs/stable/api/skimage.metrics.html)
documents explicit data ranges and metric implementations. The numerical bands
above are this skill's conservative engineering triage design, not published
research constants. DISTS is not silently claimed to be measured when unavailable.

## Cost and execution

Work batches contain at most six objects and four detail clues per object. Cache
reuse requires the same original, frozen calibration, local actual paint,
native owners and related context. Changes elsewhere do not erase unchanged
local observations. Repeated semantic families can share a source-matched
constructor; instances retain their own source/window and numeric checks.
Unresolved cases and exhausted budgets remain pending. Failed repairs use the
existing bounded execution/reflection/rollback path and its branch pruning.

```
<python> -B <skill>/scripts/sci_rebuild.py source-detail TASK scan --out SCAN.json
<python> -B <skill>/scripts/sci_rebuild.py source-detail TASK next --out PACKET.json
<python> -B <skill>/scripts/sci_rebuild.py source-detail TASK observe --request FINDINGS.json --out RECEIPT.json
<python> -B <skill>/scripts/sci_rebuild.py source-detail TASK report --out CHECK.json
```

These inspect or answer the mandatory program work; they are not an alternative
acceptance/export route. Actual saved PPT and renderer evidence must pass the
same whole-quality gate, including retained original detail facts.

Source-isolated mark fitting uses only its declared original ownership mask in
both initialization and numeric residuals. A filled-circle model produces a
circle, so a neighbouring triangle edge cannot turn a warning dot into a wide
oval. `source_function_frame` checks the exact frozen original function hash and
actual native frame within 0.03 source pixels of serialization precision; it
cannot replace the function with the candidate or broaden an old source bound.
