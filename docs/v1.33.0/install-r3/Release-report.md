# lotraAI Image2Slide 1.33.0 install-r3

Keep the runtime repository as the automatic installation entry. Users give
Codex one sentence for first installation and later differential updates:

> 请从 https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime 在当前项目安装或更新 lotraAI Image2Slide。

The installer computes a managed file delta: add new files, replace changed
files, remove retired owned files, and leave unchanged active files untouched.
Downloads are addressed by content hashes; companion member byte ranges avoid
fetching an unchanged full platform archive. Existing private knowledge, fonts,
tasks, images/PPT files, global skills and historical versions are preserved.

Core resource indexes cover Windows AMD64, Linux x86_64/aarch64, macOS ARM64 and
macOS Intel. Math resources cover Windows AMD64, Linux x86_64 and both macOS
architectures. macOS uses official pinned LibreOffice disk images in the project
private directory. Linux ARM64 still lacks a supplied complete Math package and
reports that limitation. All platform statements describe source/resource scope,
not new host validation.

Semantic version remains 1.33.0; installation/publication revision is 3. The new
immutable tag is v1.33.0-install-r3. Original v1.33.0 tags and archives are retained.
Both repositories retain English and Chinese README guides with the same short
installation/update prompt. Runtime binary version remains 1.14.0.

Implemented and statically reviewed without product tests, syntax/import/CLI
checks, installer validation, reconstruction, rendering, Office behavior checks
or performance/effect measurements, as requested. Publication asset/ref identity
records are separate from product acceptance. No token/time savings percentage
is claimed.
