# 安装说明

[English](installation.md) · [README](../README.zh-CN.md)

通过[下载说明](download.zh-CN.md)获取 v1.31.0 完整 bundle。源码仓库包含 skill 源码；完整包额外提供 Python、离线 companion、OCR 资源与当前支持的 Math 编辑器。

## Linux / WSL x86-64

选择区分大小写的 Linux 项目目录，例如 Linux 用户主目录下的子目录。依赖栈要求 glibc 2.28 或更高版本。目标项目必须先存在，不能直接选用户主目录或 `/`。

在解压后的 bundle 根目录执行：

~~~sh
PROJECT="$HOME/lotraAI-work"
mkdir -p "$PROJECT"
sh installer/install.sh "$PROJECT" codex
~~~

## Windows x86-64

在解压后的 bundle 根目录用 PowerShell 执行：

~~~powershell
$projectPath = Join-Path $env:USERPROFILE 'Documents\lotraAI-work'
New-Item -ItemType Directory -Path $projectPath -Force | Out-Null
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\installer\install.ps1 -Project $projectPath -Harness codex
~~~

## 安装结果

安装器校验资源，在私有目录暂存主 skill，准备 Python、依赖、OCR 和 Math runtime，然后登记主 skill。Codex 项目入口是 `.agents/skills/lotra-image2slide-skill/SKILL.md`。安装器资源不登记为第二个 Setup skill。

查看目标项目 `.lotraAI-build/Bundle-install.json` 获取实际结果。`core_ready`、`render_ready`、`native_edit_ready` 和 `whole_drawing_acceptance` 分别描述不同能力；安装完成不等于某张参考图已通过重建验收。

包内包含 Windows AMD64、Linux x86-64/aarch64、macOS x86-64/arm64 的 Python 资源。新增 Math 编辑器仅提供 Windows/Linux x86-64，当前完整安装流程要求此资源准备完成后才登记 skill。因此，macOS 和 Linux ARM 暂不具备这条完整安装路径；macOS Python 资源本身要求 macOS 13 或更高版本。

依赖准备使用随包资源，不需要全局 pip 安装或额外模型 API key。当前 agent 的宿主仍是独立使用前提。实际字体与文档渲染宿主在每次任务中分别检查。
