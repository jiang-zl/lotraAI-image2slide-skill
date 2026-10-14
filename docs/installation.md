# Installation

[中文](installation.zh-CN.md) · [README](../README.md)

Use the complete v1.31.0 bundle obtained through the [download guide](download.md). A source checkout contains the skill's source; the complete bundle also contains Python engines, the offline companion, OCR resources, and the supplied Math editor.

## Linux / WSL x86-64

Use a case-sensitive Linux project directory, such as a directory under your Linux home. The dependency stack requires glibc 2.28 or later. The target project must exist and must be a directory below the home directory, rather than the home directory itself or `/`.

From the extracted bundle root:

~~~sh
PROJECT="$HOME/lotraAI-work"
mkdir -p "$PROJECT"
sh installer/install.sh "$PROJECT" codex
~~~

## Windows x86-64

From the extracted bundle root in PowerShell:

~~~powershell
$projectPath = Join-Path $env:USERPROFILE 'Documents\lotraAI-work'
New-Item -ItemType Directory -Path $projectPath -Force | Out-Null
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\installer\install.ps1 -Project $projectPath -Harness codex
~~~

## What installation prepares

The installer validates resources, stages the main skill privately, deploys the selected Python/dependencies/OCR/Math resources into the target project, and registers the main skill after preparation. The Codex project entry is `.agents/skills/lotra-image2slide-skill/SKILL.md`. Installer resources are not a second Setup skill.

Read `.lotraAI-build/Bundle-install.json` in the target project for the actual result. `core_ready`, `render_ready`, `native_edit_ready`, and `whole_drawing_acceptance` describe different things. A successful setup does not certify a reference-image reconstruction.

The bundle contains Python resources for Windows AMD64, Linux x86-64/aarch64, and macOS x86-64/arm64. The added Math editor is supplied only for Windows/Linux x86-64, and the current complete installation requires that Math resource before skill publication. macOS and Linux ARM complete installation are unavailable through this route. macOS Python resources require macOS 13 or later.

Dependency preparation uses bundled resources, with no global pip installation or additional model API key. The current agent host remains a separate prerequisite. Actual fonts and the document-rendering host are checked for each task.
