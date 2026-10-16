# lotraAI

**Reconstruct scientific figures as layered, editable PowerPoint slides.**

[English](README.md) · [简体中文](README.zh-CN.md)

lotraAI combines the current agent's understanding of a reference image with project-local reconstruction programs. It is designed for scientific system diagrams, method overviews, and technical workflows. Text, shapes, connections, and semantic groups use native slide objects; mathematical expressions use structured Office Math; photographic content remains appropriately scoped image content.

[Quick Start](#quick-start) · [Examples](#examples) · [Usage](docs/usage.md) · [Installation](docs/installation.md) · [Get the complete bundle](docs/download.md)

## Quick Start

### 1. Ask Codex to install the skill and prepare its runtime

Open your working project in Codex and send this one sentence for either installation or updates:

~~~text
Install or update lotraAI Image2Slide in this project from https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime.
~~~

Codex runs the maintained installer, prepares Python, dependencies, OCR and Math for your platform, then registers the single `lotra-image2slide-skill`. The program handles downloading, resume, verification and part assembly.

Already have the complete ZIP? Supply the file or its absolute local path, then send:

~~~text
Install or update Image2Slide in this project using the supplied lotraAI-image2slide-v1.34.0-bundle.zip.
~~~

Runtime resources and private task state stay in the project's `.lotraAI-build` directory. See the [installation guide](docs/installation.md) for manual commands and platform requirements, or the [download guide](docs/download.md) for complete bundles.

### 2. Attach a reference image and start reconstructing

~~~text
Use $lotra-image2slide-skill to rebuild this image as an editable PPT.
~~~

The current agent interprets the image; the programs execute, check and export the reconstruction. The workflow delivers `Final_editable.pptx` and a `Report.md` recording what was completed.

## Download and install by operating system

Alternatively, open a terminal in your Image2Slide working project and run the command for your system. The entry selects the operating system and architecture automatically and serves both first installation and updates.

**Windows (PowerShell)**

```powershell
$url = 'https://raw.githubusercontent.com/jiang-zl/lotraAI-image2slide-skill/release/install-lotra.ps1'
curl.exe -fL --retry 2 --connect-timeout 20 $url -o install-lotra.ps1
if ($LASTEXITCODE -eq 7) { curl.exe --noproxy '*' -fL --retry 2 --connect-timeout 20 $url -o install-lotra.ps1 }
if ($LASTEXITCODE -eq 0) { powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-lotra.ps1 -Project (Get-Location).Path }
```

**macOS (Terminal, Apple Silicon / Intel)**

```sh
curl -fL --retry 2 'https://raw.githubusercontent.com/jiang-zl/lotraAI-image2slide-skill/release/install-lotra.sh' -o install-lotra.sh && sh install-lotra.sh "$PWD"
```

**Linux / WSL (Terminal)**

```sh
curl -fL --retry 2 'https://raw.githubusercontent.com/jiang-zl/lotraAI-image2slide-skill/release/install-lotra.sh' -o install-lotra.sh && sh install-lotra.sh "$PWD"
```

The skill package also includes `scripts/install-runtime.ps1` and `scripts/install-runtime.sh` to prepare or update a chosen project's runtime. All entries share the same installer, resource verification, cache and differential synchronization. See the installation guide for arguments and installation from an extracted bundle.

## What it does

- **Organizes objects by meaning.** Native text, shapes, paths, connections and groups represent the diagram's structure for subsequent editing. Chinese and English text use their corresponding font collections.
- **Keeps mathematics structured.** Expressions use source structure and genuine Office Math, retaining their internal mathematical relationships.
- **Handles component detail.** Complex icons are built from shapes and parts, then grouped for editing. Completed constructions can be reused for repeated elements in the figure.
- **Reconstructs curves with functions.** Curves with mathematical meaning retain their relevant features; general curves use piecewise approximations that preserve important trends, turns and discontinuities.
- **Builds your own reusable methods.** Eligible constructions from accepted work enter a private local knowledge library for later retrieval. Every new figure is still judged against its own original.
- **Prepares dependencies locally.** The installer prepares Python, OCR and supporting resources inside the project, without an additional model API key. The host controls how the current agent service runs.

Complex icons are observed recursively before construction. Native shapes, fills and outlines take priority; source-declared surfaces and bounded native curves cover projection, thickness, holes and occlusion. Original feature coverage, native structure and actual appearance are checked separately.

## Examples

These three author-supplied case studies each include a reference image, a PowerPoint screenshot, and a detail view. Click any image for its original size. Screenshots illustrate the reconstruction structure; native PPTX files and the generating version of each case were not supplied with these images.


### 1. Edge federated learning

A server–client–device diagram with long-tail data volumes, heterogeneous classes, and noisy observations.

| Original | Reconstructed PowerPoint | Reconstruction highlights |
|:---:|:---:|:---:|
| <a href="docs/assets/examples/01-edge-federated-learning/original.jpg"><img src="docs/assets/examples/01-edge-federated-learning/original.jpg" alt="Edge federated learning — Original" width="100%"></a> | <a href="docs/assets/examples/01-edge-federated-learning/reconstruction.jpg"><img src="docs/assets/examples/01-edge-federated-learning/reconstruction.jpg" alt="Edge federated learning — Reconstructed PowerPoint" width="100%"></a> | <a href="docs/assets/examples/01-edge-federated-learning/highlights.jpg"><img src="docs/assets/examples/01-edge-federated-learning/highlights.jpg" alt="Edge federated learning — Reconstruction highlights" width="100%"></a> |

- The PowerPoint screenshot shows separately selected labels, bars, data-class markers, client computers, and communication arrows.
- The detail image separates vehicle bodies, windows, mirrors, radio arcs, and map layers into visible component groups.

[Read the case study](docs/examples/01-edge-federated-learning.md)

### 2. Sensing and communication system

A three-layer system overview combining sensing images, a data-valuation table, mathematical labels, resource allocation, and model training.

| Original | Reconstructed PowerPoint | Reconstruction highlights |
|:---:|:---:|:---:|
| <a href="docs/assets/examples/02-sensing-communication/original.jpg"><img src="docs/assets/examples/02-sensing-communication/original.jpg" alt="Sensing and communication system — Original" width="100%"></a> | <a href="docs/assets/examples/02-sensing-communication/reconstruction.jpg"><img src="docs/assets/examples/02-sensing-communication/reconstruction.jpg" alt="Sensing and communication system — Reconstructed PowerPoint" width="100%"></a> | <a href="docs/assets/examples/02-sensing-communication/highlights.jpg"><img src="docs/assets/examples/02-sensing-communication/highlights.jpg" alt="Sensing and communication system — Reconstruction highlights" width="100%"></a> |

- The reconstruction screenshot exposes the layer panels, table layout, labels, arrows, and training-network elements as separate selections.
- The detail image shows camera housings, lenses, supports, and wireless symbols separately, alongside individual photo tiles. Photographs remain image content.

[Read the case study](docs/examples/02-sensing-communication.md)

### 3. Signal reconstruction workflow

A training-and-inference pipeline with SPGA, STFT, CTFR, time–frequency masks, and a hybrid guidance loss.

| Original | Reconstructed PowerPoint | Reconstruction highlights |
|:---:|:---:|:---:|
| <a href="docs/assets/examples/03-signal-reconstruction/original.jpg"><img src="docs/assets/examples/03-signal-reconstruction/original.jpg" alt="Signal reconstruction workflow — Original" width="100%"></a> | <a href="docs/assets/examples/03-signal-reconstruction/reconstruction.jpg"><img src="docs/assets/examples/03-signal-reconstruction/reconstruction.jpg" alt="Signal reconstruction workflow — Reconstructed PowerPoint" width="100%"></a> | <a href="docs/assets/examples/03-signal-reconstruction/highlights.jpg"><img src="docs/assets/examples/03-signal-reconstruction/highlights.jpg" alt="Signal reconstruction workflow — Reconstruction highlights" width="100%"></a> |

- The reconstruction shows the training/inference split and nested guidance-loss panels around the waveform and spectrogram content.
- The selection screenshot exposes module boxes, labels, arrows, mathematical annotations, and feedback paths as separate objects.

[Read the case study](docs/examples/03-signal-reconstruction.md)


## Using it in practice

If you have a partial slide, attach it together with its original image and send:

~~~text
Use $lotra-image2slide-skill to continue rebuilding from this partial PPT, following the original image.
~~~

After an interruption, ask the agent to resume the existing task in the same working project. Keep the original and `.lotraAI-build` available. See the [usage guide](docs/usage.md).

## v1.34.0

Complex icons now begin with a recursive observation of the original's parts, visible features and relations. Native shapes, fills and outlines take priority; shared surfaces and finite native curves preserve projection, thickness, inner walls and variable-width detail. Feature coverage, native consistency and actual appearance are checked separately. Functional curves, finite shared convergence and private method reuse continue from 1.34.0.

Installation and updates use the same entry and managed-file synchronization: add new files, replace changed contents and remove retired managed files. Unchanged active files are neither downloaded nor rewritten. Personal knowledge, fonts, tasks, originals and PPTs stay local; public packages do not preload the author's personal knowledge library.

Resources cover Windows x64, Linux x64, and macOS on Apple Silicon and Intel. macOS requires 13 or later and a separate initial Math download. Linux ARM64 still lacks a complete Math package. See the [installation guide](docs/installation.md) for the supplied routes.

Windows x64 and WSL/Linux x64 installation/startup and local HTTP update/repeat checks passed. Focused counterexamples, actual native-constructor rendering and a synthetic accepted workflow were also exercised. These checks do not accept external user art or establish general reconstruction effects. Installation, actual rendering and artwork acceptance remain separate; historical gallery screenshots are not v1.34.0 benchmarks. See the [changelog](CHANGELOG.md) and [validation notes](docs/validation.md).

## Documentation and source

| Entry | Contents |
| --- | --- |
| [Installation](docs/installation.md) | Automatic setup, differential updates, bundles and platform requirements |
| [Usage](docs/usage.md) | Image reconstruction, partial-slide import and resuming work |
| [Examples](docs/examples/README.md) | Originals, reconstruction screenshots and component details |
| [Workflow](skills/lotra-image2slide-skill/references/workflow-v134.md) | The 1.34.0 reconstruction and reuse rules |
| [Skill source](skills/lotra-image2slide-skill/SKILL.md) | The complete v1.34.0 main-skill payload |
| [Provenance and licensing](NOTICE.md) | Project source, third-party components, and example assets |

For feedback, include the operating system, product version, attempted operation, and relevant diagnostic. Share a reviewed reference image or excerpt when needed. Private task data remains under your control in the working project.
