# Offline runtime readiness

An executable path alone is not renderer readiness. Execute a minimal saved
PPTX export before long work. A restricted Linux client can reject LibreOffice's
own Unix IPC pipe even when the binary is present. Preserve the actual failure,
including input hash, exit code and stderr; it is not a drawing-quality score.
Use an available authorized host render tool. For a host that needs a separate
local worker, `scripts/local_render_service.py serve --project PROJECT
--seconds 7200` provides one finite operation. Launch it through that host's
authorized execution facility, then expose its project-local descriptor through
`LOTRAAI_LOCAL_RENDER_SERVICE`. The restricted client retains its permissions.
The worker accepts only exact project PPTX hashes, new project output folders,
finite canvas/time budgets and verified font resources; it accepts no shell
command, executable override, external linked media, semantic judgment or model
call. Linux test workers run in a separate network-disabled filesystem namespace.
The client independently rerasterizes the actual returned PDF and checks every
artifact binding. This transport does not relax any whole-result gate or claim
PowerPoint equivalence. Normal direct Office/LibreOffice rendering remains the
existing path when its actual export works.

Ship the small versioned skill together with its separately hashed runtime companion. The companion contains pinned complete wheels/locks, PP-OCRv6 tiny/small/medium detection and recognition ONNX pairs, a multilingual probe and upstream licence records. Preparation installs only into the user's project `.lotraAI-build/toolchain`; it does not download anything, mutate global Python or require another model API key.

## Preparation and normal entry

Discover trusted available host Python, including Codex workspace runtimes. Run:

```
HOST_PYTHON scripts/sci_rebuild.py runtime-bootstrap PROJECT EXTRACTED_COMPANION --out READINESS.json
HOST_PYTHON scripts/run_lotra.py --project PROJECT start ORIGINAL --project PROJECT --name TASK
```

The launcher consumes only its leading project option and preserves downstream options. Its drawing core does not depend on OCR model/provider readiness. Windows, WSL and native Linux descriptors coexist. Resources and engine hashes are checked; a known absent model can be restored automatically from its registered immutable local companion. Corrupt or foreign files are diagnosed and preserved. An interrupted installer resumes only its exact recorded owned install intent with the same companion hash, using offline pinned reinstallation. It never overwrites a foreign environment.

The prepared wheel targets are Windows AMD64 CPython 3.12; Linux x86_64 CPython 3.10/3.12 and aarch64 CPython 3.12; macOS arm64/x86_64 CPython 3.12. Official wheel metadata/dependency closure is checked for each target. Actual physical-host execution is a separate fact. The platform must satisfy the selected wheels' OS/ABI minimums. Use a supported trusted interpreter for other ABIs; preserve explicit diagnostics instead of asking the user to download a model.

The complete numeric/PPT/SVG probe renders transparent geometry and a vector PDF. Self-contained resvg wheels plus the shipped MuPDF remove mandatory system Cairo installation. An available Cairo backend is preserved; the actual backend/version is recorded and participates in cache identity. Renderer equivalence is never inferred solely from backend availability.

## Bounded device and language routes

All three matched model pairs are prepared before use. Actual readiness probes execute only tiers that fit fresh available RAM/device budgets, within one aggregate 90-second startup inference budget and a 30-second per-attempt bound. A readiness failure is saved; drawing can still use the prepared core and the available multimodal host's source-only reading. Low-resource users are not forced to load every large model just to start drawing.

Tiny is the low-resource/short-deadline default. Small is the balanced route. Medium is reserved for explicitly difficult input when its calibrated latency and RAM/device bounds fit. Tiny does not support Japanese; use a compatible small/medium route or host vision. CPU, DirectML and any other activated provider require actual local inference evidence for that tier. Unknown GPU memory/provider state selects CPU or host vision. A 2 GiB GPU uses a bounded tiny/small batch of one; no physical 2 GiB compatibility claim is inferred from running a smaller batch on a larger card.

The worker executes source crops sequentially; program tiling bounds decoded pixels, enlargement and recognition batches. Original coordinates are recovered after right-angle rotations. Overlap duplicates are removed only for the same literal at the same source geometry; conflicting readings remain evidence. ONNX scores are not calibrated probabilities.

Each collection has one finite deadline, at most one accelerator attempt plus one budget-fitting CPU fallback, persistent structured failure diagnostics and an owned process tree. Timeouts and caller cancellation terminate only workers started by that invocation. A failed refresh cannot reuse an older successful result as new evidence. The worker disallows network connections. Source, model, worker and dependency identities bind cached results.

## Source-only host reading

Use `source-reading discover/bind/report` on program-generated original-only views when OCR is unavailable or ambiguous. The available agent transcribes literals or mathematical structure; programs compare actual saved native text, case, digits, punctuation, AST/scripts and each mathematical span. No extra API is necessary. Do not label an unavailable dedicated OCR or a different model as executed. No universal OCR-versus-LLM accuracy ranking is assumed: compare matched independently scored source evidence and record the actual model.
