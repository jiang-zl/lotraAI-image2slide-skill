# lotraAI Image2Slide v1.33.0

**English** | [简体中文](README.zh-CN.md)

Rebuild scientific images as layered, natively editable PowerPoint slides. You can also supply a partial PPT to continue from once.

## Quick start

Send this to your agent in the target project. The same entry installs the skill or updates an older version:

> Use the official one-click installer to install or update lotraAI Image2Slide v1.33.0 in this project: https://github.com/jiang-zl/lotraAI-image2slide-skill

Then attach your image:

> Use $lotra-image2slide-skill to rebuild this image as a natively editable PPT.

## Install manually

Download `install-lotra.ps1` (Windows) or `install-lotra.sh` (Linux) from the [v1.33.0 Release](https://github.com/jiang-zl/lotraAI-image2slide-skill/releases/tag/v1.33.0), then run it for your project:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-lotra.ps1 -Project "C:\path\to\project"
```

```sh
sh install-lotra.sh /path/to/project
```

Windows AMD64 and Linux x86_64 have complete runtime packages. GitHub access is required for online installation. The installer prepares Python, OCR and Math resources, reuses compatible resources, and returns a short result with a log location. After an interrupted download, rerun the same command.

Updates replace the active skill with the new version's complete file set, including removal of retired files from the active directory. Personal knowledge, fonts, tasks, source images and PPT files are preserved; previous skill versions are archived.

The small update ZIP downloads missing runtime resources. For offline use, obtain the full bundle and run its `installer/install.ps1 -Project PROJECT` or `sh installer/install.sh PROJECT`.

## Workflow and status

v1.33.0 adds function-based curves, shared convergence budgets and private knowledge reuse. The personal library starts empty. Parts and layout precede the final font and whole-slide review.

See [SKILL.md](https://github.com/jiang-zl/lotraAI-image2slide-skill/blob/release/skills/lotra-image2slide-skill/SKILL.md) and the [v1.33 workflow](https://github.com/jiang-zl/lotraAI-image2slide-skill/blob/release/skills/lotra-image2slide-skill/references/workflow-v133.md) for details.

Implemented and statically reviewed. Tests, reconstruction, rendering and performance/effect measurements were not run for this release.
