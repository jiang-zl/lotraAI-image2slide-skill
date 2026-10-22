# Installation and updates

[简体中文](installation.zh-CN.md) · [Back to README](../README.md)

Open your working project in Codex and send:

> Install or update lotraAI Image2Slide in this project from https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime.

One entry prepares both the runtime and the main skill. First installation selects your platform resources. Later updates add, replace and retire managed files while retaining unchanged active files without downloading or rewriting them. Your knowledge library, fonts, tasks, originals, PPTs and global skills are preserved.

For manual commands, Windows/Linux/macOS resource coverage, complete-bundle downloads and installation from an extracted bundle, use the maintained [runtime installation guide](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/blob/dev/docs/installation.md).

After installation, attach your image and send:

> Use $lotra-image2slide-skill to rebuild this image as an editable PPT.

See the [usage guide](usage.md). Actual installation resources and capabilities are recorded in the working project's `.lotraAI-build/Bundle-install.json`.

## macOS Math backend (1.35.3)

The signed LibreOffice application runs a fixed Python/UNO worker in a new project-private profile; the installer does not spawn its constrained bundled interpreter. Application signatures and system security settings are preserved. The same worker is used for startup checks and actual export. A fresh native Math startup probe is required on each installation attempt.

If a prior attempt installed only the skill files, rerun the maintained installation entry in that same project. Verified resources are retained. Read the current attempt’s `Failure.json`, `Math-backend-failure.json` and referenced `backend-result.json` for phase, commands, exit status and log paths. A core stage that was never reached is `NOT_RUN`. A successful startup check does not certify document rendering or artwork quality.

GitHub release downloads have a bounded official asset-API fallback, retaining the exact byte count, SHA-256, range checks and cache ownership. macOS Math DMGs still use their pinned upstream URL. macOS Apple Silicon and Intel physical-host checks remain pending; Windows tests do not qualify either Mac architecture.

## 1.37.4 installer entries

Shell entries are UTF-8 without BOM and use LF. Maintainers generate them from
`installer/templates` with `tools/prepare_install_entries.py`, then run
`tools/validate_install_entries.py` against final attachments and ZIP members.
Windows entries are checked with Windows PowerShell as well as actual installation.
Runtime binaries and resource packages remain unchanged.

For 1.37.4 the core stage runs first. A qualified local presentation application replaces the mandatory LO installation; otherwise LO startup, actual fixture PDF and save/reopen are checked. `math_import_ready=null` in local-application mode means UNO was not imported. Auto retains one actual native PDF failure before a declared LO fallback; native save/reopen and PDF scopes stay separate. See docs/v1.37.4/Validation-report.md.
