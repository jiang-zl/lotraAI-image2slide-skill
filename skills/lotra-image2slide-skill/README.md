# lotraAI Image2Slide

**English** | [简体中文](README.zh-CN.md)

Rebuild scientific images as layered, natively editable PowerPoint slides. Optional one-time partial-PPT input.

## Quick start

Send one sentence to Codex in your project:

> Install or update lotraAI Image2Slide in this project from https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime.

Codex downloads and runs the official installer automatically. Existing installations use the same sentence.

Attach an image after installation:

> Use $lotra-image2slide-skill to rebuild this image as a natively editable PPT.

## Installation and updates

The runtime repository is the installation entry. Updates add new files, replace changed files and remove retired managed files. Unchanged active files are not rewritten or downloaded. Hash-addressed resources and compatible environments are reused. Personal knowledge, fonts, tasks, images and PPT files are preserved. Detailed logs stay in the project; the agent returns a short result.

Python/OCR resources cover Windows AMD64, Linux x86_64/aarch64 and macOS Apple Silicon/Intel. Math packages are indexed for Windows AMD64, Linux x86_64 and both macOS architectures. Linux ARM64 has core resources but no supplied Math package; the complete installer reports this limitation. macOS requires 13 or later.

The current installation revision is **1.33.0 install-r3**. Original releases and offline archives remain available. The current entry uses a file manifest rather than downloading the old full bundle for each update.

See [the workflow](https://github.com/jiang-zl/lotraAI-image2slide-skill/blob/release/skills/lotra-image2slide-skill/references/workflow-v133.md). This revision was implemented and statically reviewed without tests, installation runs, reconstruction, rendering or performance/effect measurements.
