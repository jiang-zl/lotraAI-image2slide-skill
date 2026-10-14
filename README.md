# lotraAI

**Reconstruct scientific figures as layered, editable PowerPoint slides.**

[English](README.md) · [简体中文](README.zh-CN.md)

lotraAI combines the current agent's understanding of a reference image with project-local reconstruction programs. It is designed for scientific system diagrams, method overviews, and technical workflows. Text, shapes, connections, and semantic groups use native slide objects; mathematical expressions use structured Office Math; photographic content remains appropriately scoped image content.

[Quick Start](#quick-start) · [Examples](#examples) · [Usage](docs/usage.md) · [Installation](docs/installation.md) · [Get the complete bundle](docs/download.md)

## Quick Start

### 1. Ask Codex to install the skill and download its runtime

Give Codex this repository URL and the prompt below. Codex can download the matching runtime resources, verify the complete bundle, and install it into the current project for you.

~~~bash
Install lotraAI Image2Slide v1.31.0 in the current project from:
https://github.com/jiang-zl/lotraAI-image2slide-skill

Automatically download its matching runtime resources from:
https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime
Read the v1.31.0 manifest and use the download helper to obtain,
reassemble, and verify the complete bundle. Extract it and use its
bundled installer to prepare Python, dependencies, OCR, and Math
under .lotraAI-build before registering lotra-image2slide-skill.
Report the skill entry and actual runtime readiness when finished.
~~~

Codex handles downloading and installation; you do not need to fetch each runtime resource manually. The [version manifest](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/blob/release/releases/v1.31.0.json) and [download helper](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/blob/release/tools/fetch_bundle.py) are in the runtime repository.

**Runtime availability:** the skill and runtime releases are published separately. Codex should check that the matching runtime assets are public before downloading. If the assets are still being uploaded, provide a local complete bundle or use a project with the matching runtime already prepared. The skill source alone does not prepare the runtime. See the [download guide](docs/download.md).

Already have the complete ZIP? Place it in the current project or give Codex its absolute local path, then send:

~~~bash
Please extract the complete lotraAI-image2slide-v1.31.0-bundle.zip I provided.
Use its bundled installer to install the skill into the current project,
named lotra-image2slide-skill. Prepare the included runtime resources
(Python, dependencies, OCR, and Math) before registering the main skill.
When finished, report the skill entry and runtime readiness.
~~~

The complete ZIP includes both the skill and runtime resources. Installation registers the single `lotra-image2slide-skill`; runtime resources and private task state live in the project's `.lotraAI-build` directory.

### 2. Attach a reference image and start reconstructing

~~~text
Use $lotra-image2slide-skill to reconstruct this reference image as an editable
PowerPoint slide. Preserve the original text, equations, hierarchy, connections,
and semantic grouping.
~~~

The current agent interprets the image; the programs execute, check, and export the reconstruction. The workflow delivers `Final_editable.pptx` and a `Report.md` containing measured component results.

For manual installation commands, see the [installation guide](docs/installation.md).

## What it does

- **Organizes objects by meaning.** Native text, shapes, paths, connections, and groups represent the diagram's structure for subsequent editing.
- **Keeps mathematics structured.** Expressions use source structure and genuine Office Math. The added Math rendering route and Microsoft Office editing checks are separate capabilities.
- **Handles component detail.** Icons and their descendants retain the existing recursive identification, construction, and verification workflow.
- **Protects scoped changes.** Task contracts identify what to preserve and which objects and relations need checking after a local revision.
- **Prepares dependencies locally.** The complete bundle prepares Python, OCR, and supporting resources inside the project, without an additional model API key. The host controls how the current agent service runs.

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

For a local revision, state the change and the attributes to preserve:

~~~text
Adjust only the spacing between the right-hand modules and their arrows.
Preserve the text, equations, icon anatomy, and all other regions.
~~~

After an interruption, ask the agent to resume the registered task in the same working project. The project retains the original and workflow state. See the [usage guide](docs/usage.md).

## v1.31.0

This release adds source-parameter and native-property contracts for explicitly bound standalone text, primitive shapes, and equations. Complex icons, icon descendants, repeated instances, and other component types retain the existing workflow. The added LibreOffice Math resources cover Windows/Linux x86-64; Python resources for other platforms do not imply availability of this Math installation route.

The release retains its `NOT_RUN_PER_USER_REQUEST` functional-validation status. Installation readiness, actual document rendering, native editing, and whole-reconstruction acceptance are recorded separately; the supplied screenshots do not change this release status. See the [changelog](CHANGELOG.md) and [validation notes](docs/validation.md).

## Documentation and source

| Entry | Contents |
| --- | --- |
| [Installation](docs/installation.md) | Complete-bundle setup, platform requirements, and receipts |
| [Usage](docs/usage.md) | Reconstruction, scoped revisions, and resuming work |
| [Troubleshooting](docs/troubleshooting.md) | Installation, fonts, rendering, and runtime diagnostics |
| [Publication](docs/publication.md) | Repository responsibilities and public-download configuration |
| [Skill source](skills/lotra-image2slide-skill/SKILL.md) | The complete v1.31.0 main-skill payload |
| [Provenance and licensing](NOTICE.md) | Project source, third-party components, and example assets |

For feedback, include the operating system, product version, attempted operation, and relevant diagnostic. Share a reviewed reference image or excerpt when needed. Private task data remains under your control in the working project.
