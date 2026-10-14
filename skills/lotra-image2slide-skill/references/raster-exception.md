## v1.0.3 semantic HD route

For blurry illustrative layers, use `appearance_policy: semantic_hd_replace` as specified in [the agent protocol](visual-agent-loop.md). This route reuses same-context saved-native/raster comparison but accepts a complete source-compatible clearer asset without requiring original low-resolution PPI or blurry pixel similarity to improve. Native text, math, meaningful marks and required internal native editing remain non-negotiable. Mere resampling cannot satisfy the bound host clarity/semantic observations. The literal-fidelity comparison below remains for source-faithful assets.

# Measured raster exception for a semantic layer

Start with an input-specific semantic owner and a bounded native construction.
Text, formulae, scientific relations, semantic marks, and any component that
promises internal native editing cannot take this exception. A source crop of
the whole icon does not become an acceptable replacement for its parts.
For any cut-out bitmap, the independent [visual-closure gate](visual-closure.md)
also requires actual clarity enhancement before semantic completion and rejects
unintended transparency holes. Passing this raster comparison alone cannot
waive those requirements or a missing source feature.

For a permitted environmental or decorative layer, freeze an
`raster-exception-1` contract **before either candidate is built**. Bind the
source image and exact ROI, original raster information source, semantic owner,
native and raster methods, native shape budget, protected foreground paths,
intended maximum reuse inches, effective-information PPI floor, calibrated
score profile, and minimum primary gain. Keep the calibration anchors and
profile revision with the task. The source image and profile must be the same
for both candidates; missing metrics cannot be silently imputed.

Build two saved PPTs with the same slide shell and unrelated objects. The
native owner must contain actual non-picture shapes. The raster owner is one
independent picture layer. Render both saved PPTs at the same canvas using the
same backend, version, executable, environment, and fonts. The command
`compare-raster-exception CONTRACT.json NATIVE.pptx NATIVE_RENDER.json
RASTER.pptx RASTER_RENDER.json --out RESULT.json` reopens the PPTs and
receipts, recalculates metrics on the frozen ROI, checks unaffected foreground,
and computes information PPI from the original source pixels and saved media
at the declared reuse size. A larger bitmap created by upsampling does not
increase information PPI.

Its only positive result is `ELIGIBLE_FOR_SEMANTIC_AND_EDITOR_REVIEW`. That
means a measured visual advantage passed the frozen noncompensating gates; it
does not prove the layer is semantically correct, reusable, or edit-safe in
PowerPoint. `REJECTED_RASTER_EXCEPTION` means keep the native candidate or
revise the drawing method under a new plan. An invalid native comparator,
missing source binding, changed render protocol, or a poor vector rendering
caused by tile seams is **not** evidence for raster superiority. Native mosaics
include an exact owner-mask seam underlay; inspect the actual saved rendering
before comparison. Do not adjust the profile, ROI, or gain floor after seeing
candidate scores. A new profile revision requires remeasuring both candidates.
