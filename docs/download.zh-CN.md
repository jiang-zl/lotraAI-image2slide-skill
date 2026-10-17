# 下载完整 bundle

[English](download.md) · [安装](installation.zh-CN.md)

当前完整文件为 `lotraAI-image2slide-v1.35.2-bundle.zip`。大小、整包 SHA-256 与 18 个有序分块以 [完整包清单](https://github.com/jiang-zl/lotraAI-image2slide-skill/releases/download/v1.35.2/v1.35.2-bundle.json)为准。

## 让 Codex 下载并合并

把 [runtime 仓库](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime)交给 Codex，发送：

~~~text
下载 lotraAI Image2Slide 的完整安装包到当前项目。
~~~

程序负责续传、逐块校验、合并和整包校验。普通安装与更新也可直接使用：

~~~text
请从 https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime 在当前项目安装或更新 lotraAI Image2Slide。
~~~

首次按平台获取资源，后续按文件差分更新。已有完整 ZIP 可直接交给 Codex，解压包可使用包内安装器；参见 [runtime 安装说明](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/blob/release/docs/installation.zh-CN.md)。macOS Math DMG 需首次单独联网获取，未包含在完整 bundle 中。
