# Verify native representations in the target editor

A native shape or XML tag establishes a representation, not successful use in Office. Check the original saved file and its actual render, then test relevant operations on an isolated copy. Never edit an unrelated document or close a shared application to make a probe run.

## Retain natural parts and real paths

Use a native Cube where its geometry matches the observed object. A custom icon needs semantic object → natural parts → native primitives/paths. A body, controls, and frame can be meaningful parts; arbitrary fragments named as parts are not evidence of meaning. Shared-parameter custom-face prototypes and inferred hidden structure are not generally implemented. Keep observed and inferred regions separate.

A `path` is editable DrawingML custom geometry. A waveform `trace` is a native Group containing measured path-tone layers of one observed signal appearance. Its display layers do not claim additional scientific parts. The task-native probe can exercise a selected path in each trace; inspect its action list and results rather than claiming every vertex was individually tested.

## Keep formulas in a real editor

The math backend writes DrawingML `a14:m` with structured Office math. It supports inline and standalone expressions, explicit subscripts/superscripts, accents, fractions, radicals, sums, matrices/cases, and delimiters. There is no rich-text, picture, or SVG substitute. MathType/AxMath are not implemented adapters in this package.

Use `native-plan`, `native-check`, and `verify-native` for the current figure. The plan starts from actual saved mathematical zones. The Windows probe changes mathematical content through the actual equation editor, saves and reopens its temporary copy, and supplies altered files and operation records. The independent verifier compares the expected altered AST with the saved result. A raw `EXECUTED` event or the continued existence of `a14:m` is insufficient.

The comparison recognizes documented Office math normalization while retaining variables, operators, indices, and delimiter scope. Original content must still be reviewed against the source separately: the deliberately altered test copy is not the deliverable. Unsupported mathematical editing or unresolved scientific text remains blocked/unverified.

## Limit connection claims to measured behavior

Straight and supported orthogonal connectors use native `line`/`bentConnector2`–`bentConnector5` presets with builtin arrowheads and native start/end connection references. Visible rectangles, rounded rectangles, ellipses, and pictures can carry width/height-relative custom port guides. Use the declared site numbering and visible anchor-part mapping in [Scene authoring](scene-authoring.md).

The per-task plan moves applicable source nodes once and checks saved endpoint changes for the covered connections. A static matching arrow does not establish movement behavior. Unanchored line junctions remain explicit limitations. Routes outside the supported segment/geometry subset fail instead of being presented as equivalent freeform connectors. Aligned U-routes may have recorded subpixel endpoint quantization; report it and inspect the saved route.

Bezier objects remain genuine cubic geometry with a separate edit scope. The fixed M0 probe supplies a curve-operation route for that fixture. Do not assume that it automatically tested every arbitrary curve, table, or group transformation in a new figure.

## Export editable components and honest copies

`export-components` copies explicitly selected semantic groups from the saved deck to separate component pages. Embedded data-image relationships in selected mixed components are preserved; external links or unsupported relationship types are rejected. Confirm that internal parts and intended labels/connections are inside the component and outside labels are excluded.

`export-component-assets` uses target PowerPoint to produce applicable PNG/SVG copies. These copies never replace the editable master. SVG export availability remains Office/version-dependent. A mixed component or PDF is mixed vector/raster, even though its schematic objects remain native.

## Preserve platform evidence

Windows/WSL tools use the installed PowerPoint application and temporary test copies. The bridge's per-process `-ExecutionPolicy Bypass` does not change global execution-policy settings. The queue, timeouts, and recovery protocol are described in [operations](operations.md). M0 results can establish unchanged capability routes, but cannot substitute for a new figure's content, render, topology, or operation coverage.

A macOS host-assisted test must open a separate copy, move/copy/scale a meaningful group, ungroup to natural parts, recolor a part, move an anchored node, edit relevant curve points and an actual equation, save/reopen, and export an actual render. Record exact file hashes, Office version, fonts, operations, and untested cases. This is a manual protocol; documenting it is not a tested macOS adapter or a platform PASS.

A local `paint_order` change uses the unchanged next native sibling as a donor read-only anchor; only explicitly granted nodes move. Keep one continuous native support behind its source foreground rather than splitting its hidden segment. A donor alone is not enough to infer final sibling order. Plain lxml elements use insert/append before extLst, not python-pptx-only methods.
