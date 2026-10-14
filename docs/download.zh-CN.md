# 下载完整 bundle

[English](download.md) · [安装](installation.zh-CN.md)


完整文件为 `lotraAI-image2slide-v1.31.0-bundle.zip`，大小 2,414,649,382 字节，包含 skill 与全部随包运行资源。SHA-256 为 `200f65a42b96dca2a0143f43f1c3583d5150958ae1fc7ac8c6dea41969fbe657`。

## 下载并合并

打开 [v1.31.0 完整包 Release](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/tag/v1.31.0)。两个 `.part001` / `.part002` 附件是同一个完整 ZIP 按顺序切出的字节分块。保存 Release 中的[下载合并程序](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/download/v1.31.0/fetch_bundle.py)，执行：

~~~sh
python3 fetch_bundle.py --output-dir ./downloads
~~~

Windows 对应命令为 `py fetch_bundle.py --output-dir .\downloads`。程序获取[版本清单](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/download/v1.31.0/v1.31.0.json)，逐块检查，合并 ZIP，并验证整包 SHA-256 后才生成正式输出文件。已有的不同文件会被保留。

也可以把 [Release 地址](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/tag/v1.31.0) 直接交给 Codex，要求它按清单和下载程序获取完整包，再解压安装。已经合并好的完整 ZIP 仍可直接交给 Codex。

合并后的唯一交付归档为 `lotraAI-image2slide-v1.31.0-bundle.zip`，内部文件与载荷不因分块传输发生变化。分块大小遵循 [GitHub 单附件限制](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas)。
