# Evaluation rationale and calibration

## Evidence and limits

[SSIM's authors](https://ece.uwaterloo.ca/~z70wang/research/ssim/) motivate structural image-quality comparison; SSIM remains an important fixed-frame source-correspondence measurement. It does not identify which source detail is semantically correct or which approved illustration should be preserved.

[LPIPS](https://richzhang.github.io/PerceptualSimilarity/) demonstrates that deep features can better track perceptual similarity in the authors' experiments. [DISTS](https://arxiv.org/abs/2004.07728) separates structure and texture statistics. These are reasons to avoid a single pixel-distance oracle, not evidence that either model certifies scientific meaning, native editability or icon beauty. v1.13.0 does not claim to execute these models or label its simple proxies LPIPS/DISTS.

[Collaud et al., Displays 74 (2022), 102290](https://backend.epfl-ecal-lab.ch/wp-content/uploads/2022/08/EPFLECALLab_2022-08-18_Collaud-et-al.pdf) studies icon aesthetics with multiple design attributes. [Microsoft's icon design guidance](https://learn.microsoft.com/en-us/windows/apps/design/iconography/app-icon-design) also treats shape/detail and size-dependent legibility as design concerns. We infer that semantic purpose and intended size belong in an engineering evaluation policy; neither source proves our numerical weights.

[PP-OCRv6's official documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv6/PP-OCRv6.md) describes its multilingual model families; [RapidOCR's versioned implementation and registry](https://github.com/RapidAI/RapidOCR) supplies the runtime integration. Model capability claims are upstream claims. Our release evidence consists of actual local CPU/GPU multilingual inference and independent original/native content checks, rather than quoting an upstream score as our accuracy.

## Purpose-dependent engineering policy

| Purpose | Selected dimensions | Non-compensable requirements |
|---|---|---|
| Illustrative icon | source SSIM .20, source edge F1 .10, target clarity .30, approved style .20, native construction .20 | Source subtype/pose/parts, approved properties or declared design bounds, frame/topology |
| Decorative artwork | source SSIM .10, source colour .10, target clarity .30, approved style .30, native construction .20 | Semantic role, intended appearance authority, layout and allowed edits |
| Scientific image | source SSIM .35, source edge F1 .30, source colour .15, native construction .20 | Explicit fixed source bounds, scientific values/features and source meaning |
| Identity photograph | source SSIM .40, source edge F1 .15, source colour .20, source texture .05, native construction .20 | Identity and source evidence; no invented replacement identity |
| Structure/table | source SSIM .15, source edge F1 .25, layout .25, approved style .10, native construction .25 | Shared row/column frames, valid fill, containment, protected transforms |
| Text/formula | source SSIM .10, exact content .50, target clarity .15, native construction .25 | Independent original literal/AST, case/digits/operators/scripts and all math spans |
| Relationship | source SSIM .10, relationship predicates .60, native construction .30 | Direction, role, source-classified contact/separation, physical topology |

The configuration is frozen before comparison. Exact content and binary construction/layout/relationship dimensions are transparent program predicates, not graded semantic probabilities. Raw measurements stay separate from bounded score dimensions. Source colour is one minus fixed 8-bin/channel histogram total variation; texture uses a bounded ratio of fixed Laplacian energies. They are diagnostics and cannot replace identity/semantic recognition. Clarity is a fixed actual-size Laplacian-energy proxy, bounded against an approved reference or a predeclared design interval. Its upper bound prevents rewarding unbounded sharpening/noise. Approved style uses fixed-frame SSIM and has its own hard preservation tolerance.

Hard gates run independently. A wrong digit, lost part, detached camera, gap outside a permitted interval, spill outside a closed contour or unauthorized native change cannot become acceptable through weighting. Tiny regions with fewer than three pixels on one side have inapplicable SSIM; the program reports that explicitly and retains native/content/structure checks. It never fabricates a perfect score.

## Release calibration

The developer controlled study uses six unrelated vector silhouettes (car, camera, server, radio signal, panel and valve), each with a fixed source blurred by 0.35 px and four fixed output blur levels. There is no candidate-dependent crop, alignment or source modification. Across 24 comparisons, preserving the sharp approved design lowers source SSIM only 0.00126–0.00786 relative to an exact blurred-source copy, while the illustrative composite improves 0.0430–0.0934. Copying the blur loses approved-size clarity; stronger blur is rejected by appearance requirements. A very small within-tolerance raster change may receive a similar or slightly higher ranking; we do not claim a universal optimum.

This study checks the intended mechanism and consistency with the user's explicit v1.12 icon preference. It holds fixture geometry/layout constant and is not saved-PPT protection evidence. It is not a human population study, a trained preference model, or proof that these weights generalize optimally to every future figure. Generalization instead rests on purpose declarations, complete inventories, explicit original/approved/design authority, typed hard constraints, new-figure counterexamples and honest uncertainty routing. The two actual PPT tests separately verify the complete end-to-end artifact chain.

Future changes require new source-specific evidence, representative controlled/held-out families and a versioned policy; never tune weights after seeing a failing candidate merely to make it pass.
