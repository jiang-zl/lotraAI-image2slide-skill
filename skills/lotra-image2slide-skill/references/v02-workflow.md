# v0.2 execution and evidence

Use the installed `scripts/sci_rebuild.py` for all commands. Paths below are placeholders, not another installed skill.

## Source observations and instructions

`source-analysis-1` records source path/hash, identity_px canvas, host/human author, scientific theme, user constraints, independent ROI observations, semantic nodes and relations. Nodes declare S0–S4 level, T01–T11 type, R0–R4 role, class, view, styles, evidence status/refs, render IDs, wrapper IDs, edit targets, parent and decomposition reason. Split only when the next part has observed geometry or independent edit value. Every render fragment has exactly one owner. Scientific edges may have cycles.

```sh
python -B scripts/sci_rebuild.py validate-analysis WORK/source-analysis.json --scene WORK/scene.json
python -B scripts/sci_rebuild.py compile-instructions WORK/source-analysis.json WORK/backend.json --knowledge WORK/knowledge.json --out WORK/orders
python -B scripts/sci_rebuild.py build WORK/scene.json --out WORK/candidate.pptx
python -B scripts/sci_rebuild.py check-hierarchy WORK/source-analysis.json WORK/scene.json WORK/candidate.pptx --out WORK/hierarchy.json
```

`backend.json` lists actual native presets, supported repair operations, capabilities and verified edit operations. Do not list untested editor behavior as verified. `config/contracts.json` supplies compatible hard constraints, parameter intersections, metrics, operations and parent checks. The compiler rejects conflicts and records missing operations.

Knowledge entries contain id, kind (method/hypothesis), object_id, source_hash, evidence_refs, requires_facts, expected_change, metric_refs and concrete actions. Actions carry op, target render IDs and parameters. Source facts remain in observations. Extra knowledge-created parts require separately confirmed new source evidence. Compiler acceptance means evidence_compatible, not benefit. Preserve rejected suggestions and an unchanged comparison candidate. `core.contracts.record_utility` requires common source/plan/backend and independent hard/context evidence before declaring helped.

## Fixed-domain measurements

`typed-plan-1` contains source path/hash, exact canvas and targets with integer source ROI and protocol. Use fixed background, foreground selection, edge threshold, boundary tolerance, SSIM window and histogram bins. Record why each is appropriate; diagnostic defaults are not acceptance thresholds. All candidates use the same plan, colorspace, renderer and font environment. No candidate-dependent alignment or reference-mask changes.

```sh
python -B scripts/sci_rebuild.py render WORK/candidate.pptx --out WORK/render --width SOURCE_WIDTH
python -B scripts/sci_rebuild.py measure-typed WORK/plan.json WORK/render/Final_preview.png --pptx WORK/candidate.pptx --render-receipt WORK/render/render.json --out WORK/measurements.json
```

Implemented image diagnostics: region IoU, boundary F1, symmetric Chamfer, Hausdorff/HD95, CIEDE2000, internal-edge F1, RGB residual, SSIM/PSNR, ink bounds and histogram distance. Saved-file inspection provides text, AST, shape/part mappings and connector references. Hierarchy checks provide required parts, mapped content, declared contact bounds, ordering/overlap witnesses and endpoint direction. Pixel occlusion, true glyph readability, semantic recognizability and complete editing remain host/target checks. Unimplemented perception metrics do not return placeholder values. Empty edges, missing reference content and unsupported operations remain explicitly missing.

A repair record identifies defect/object/part/relation, source evidence/ROI, observed difference, severity, suspected cause, allowed parameters, expected change, affected old/new regions, recheck plan, acceptance and rollback. Use `propose-repair`, then state/grant/patch operations. Do not run arbitrary knowledge text as code. `register-iteration` retains measured candidates without awarding global acceptance to itself.

## macOS and host-controlled PowerPoint evidence

When an automatic Office bridge is unavailable, use the available host computer-use tool to open a task-owned copy, export its PDF and perform edits. Preserve tool observations in a task log with app/version, input hash, action, before/after evidence and output hash. Rasterize the exported PDF through `core.render.rasterize_pdf` on the source canvas. Record its provenance as a host-export receipt. This receipt authenticates file binding, not the editor action by itself; preserve both.

A genuine edit round trip changes the formula in the equation editor, saves/reopens, and independently inspects the resulting OMML and rendering. For groups, inspect real child changes after move/scale/ungroup and saving. For connectors, inspect reference identity and changed endpoint position after node movement. Do not label a scripted OOXML edit as a PowerPoint operation. If UI access fails, keep the editable output and a precise UNVERIFIED entry while continuing independent work.

## Packaging identity

The product registry name is `lotraai-image2slide` and version is `0.2.0`. `agents/openai.yaml` is included by the package whitelist. Install into a new directory; existing directories cannot be overwritten by the installer. Verify archive and installed manifest using `package_skill.verify_archive` and `verify_installation`. The historical development folder/CLI filename is not a dependency on another installed skill. Customer inputs, task coordinates and development logs are excluded from release.

## Host target render receipt

On macOS the host opens the exact saved candidate in PowerPoint and uses local Best for Printing PDF export. Record the application/build, exact document path, input PPTX hash, exported PDF hash, actual observed UI actions and `export_mode: local_print_pdf`; call `import-host-render PPTX PDF OBSERVATION --width SOURCE_WIDTH --out NEW_DIR`. This binds the observation and fixed PDF rasterization to the file. It does not prove any editing operation. Never fill observations for UI actions that were not performed.

The current host receipt normalizes the backend to `PowerPoint` and reports PASS only for `host_observed_target_render_only`. QA rechecks the observation bindings and rerasterizes the bound PDF before accepting that channel; native editing, semantic review and overall acceptance remain separate. Old `RECORDED` receipts must be reimported from their preserved actual observation and PDF, not relabeled by hand. Keep the PDF available at the recorded path. A Quartz PDF producer or an empty creator field is normal for macOS printing and is not independent proof of the originating app.

Font gallery ranking reads actual PDF font names. If `font_selection_verified` is false, every candidate uses a substitute or has missing font evidence; the minimum pixel error is only a proxy result. Render the gallery in target PowerPoint before choosing the final font. Perceptual appearance and full-context collision checks still follow selection.

## Geometry refinements exercised in v0.2

- `fit_circle` closes ROI-edge foreground before selecting the exterior. Crossed circles with attached arrows can otherwise return an internal hole. If the source mask represents the **outer stroke**, declare `source_fit.boundary: outer_stroke` and `stroke_width_px`; the proposed native ellipse is inset to its stroke centerline. Review fit residuals, nearby arrowheads, and the full parent after fitting; clipping does not become ground truth.
- Parameter repair routes preset/adjustments/contours/table geometry/arrow dimensions into content, and font/color parameters into style. Unimplemented parameter destinations raise an error. A solid color fit removes a stale gradient that would override its fill.
- Fitted ports keep native endpoint bindings. Existing orthogonal first/last bends adapt to the new port coordinates; arbitrary collision-free rerouting remains outside this limited adjustment.
- For a source-observed polyline junction, a `touches` relation can declare `contact_point`, `path_ids`, and `max_gap_px`. The hierarchy checker measures saved path segments, not overlapping bounding boxes. Curves without supported samples remain unverified.
- A `contains` relation can optionally declare an observed **convex** `enclosure_polygon`, child `path_ids`, and `max_outside_px`. This checks actual saved polyline centerlines. It does not claim arbitrary silhouette clipping, stroke containment, or containment of tall natural objects whose ground contacts are inside a region.
- When a new defect exposes a missing necessary check, save a new evaluation version and re-evaluate both prior and new candidates. Keep the original plan/results; never add a favorable check only to the new candidate.

## Portable render typography and math comparison

On macOS, an isolated bundled LibreOffice process may ignore fonts visible to PowerPoint. A task-owned `FONTCONFIG_FILE` may list the existing font directories; do not copy licensed fonts into the product or change global configuration. Render old/new candidates with the same explicit configuration. The render receipt records its path and hash; inspect PDF font names as well. Correct font discovery does not prove PowerPoint equation rendering or editing: LibreOffice may omit inline native math or stretch equation boxes. Use a real PowerPoint render before semantic/typographic acceptance.

The structure checker canonicalizes nested/singleton `seq` wrappers because their OMML serialization is a flat sequence of siblings. It still preserves token order, script position, fractions, delimiters, and explicit normal-text whitespace. A successful structural comparison is not an actual equation edit roundtrip.
