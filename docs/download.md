# Download the complete bundle

[简体中文](download.zh-CN.md) · [Installation](installation.md)

The current complete file is `lotraAI-image2slide-v1.37.4-bundle.zip`. Its size, whole-archive SHA-256 and 19 ordered parts are recorded in the [complete-bundle manifest](https://github.com/jiang-zl/lotraAI-image2slide-skill/releases/download/v1.37.4/v1.37.4-bundle.json).

## Ask Codex to download and assemble

Give Codex the [runtime repository](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime) and send:

~~~text
Download the complete lotraAI Image2Slide installation bundle into this project.
~~~

The program handles resume, per-part verification, assembly and whole-archive verification. For ordinary installation or updates, send:

~~~text
Install or update lotraAI Image2Slide in this project from https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime.
~~~

First installation selects your platform resources; later updates synchronize managed files by content. A complete ZIP can be supplied directly to Codex, and an extracted bundle can use its bundled installer. See the [runtime installation guide](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/blob/dev/docs/installation.md). The macOS Math DMG requires a separate initial online download and is not embedded in the complete bundle.
