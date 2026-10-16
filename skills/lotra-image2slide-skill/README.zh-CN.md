# lotraAI Image2Slide

[English](README.md) | **简体中文**

将科研图片重建为分层、原生可编辑的 PowerPoint，也支持一次性导入半成品 PPT 作为起点。

## Quick start

在项目中，将这一句话交给 Codex，首次安装和后续更新都适用：

> 请从 https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime 在当前项目安装或更新 lotraAI Image2Slide。

Codex 自动取得并调用正式安装程序，你无需自己下载、合并或安装 runtime。

安装后附上原图：

> 用 $lotra-image2slide-skill 将这张图重建为可编辑 PPT。

## 下载与差分更新

首次安装按当前系统和架构选择资源。大资源可以分块下载，由程序自动续传、校验和合并。已有安装按文件清单差分同步：新增新文件、替换变化文件、移除新版已删除的受管理文件；未变化的生效文件不重复下载、不重新写入。文件改名时也优先复用本地相同内容。个人知识库、字体、任务、原图和 PPT 保留在私有 `.lotraAI-build` 中。

完整 bundle 继续提供有序分块，用于本地安装、离线保存和恢复，与正常安装共用正式下载器和内容缓存；日常更新无需下载完整 bundle。参见 [runtime 安装与完整包](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime)。

## 平台与发布范围

产品版本仍为 **1.33.0**。Python/OCR 资源覆盖 Windows AMD64、Linux x86_64/aarch64、macOS Apple Silicon 和 Intel。完整 Math 准备已有 Windows AMD64、Linux x86_64 和两种 macOS 架构的资源路线。macOS 要求 13 或更新版本，需要首次联网取得固定哈希的 Math 磁盘镜像；该镜像未包含在完整 bundle 中。Linux ARM64 有核心资源，尚无随包完整 Math，安装器会明确报告该限制。

本次完成实现与静态代码审查。按用户要求，未运行产品测试、语法/import/CLI 检查、安装、重建/渲染或性能与效果测量。发布哈希用于标识分发内容，不代表运行时或重建质量验收。历史标签与归档保留。

详细流程见[工作流说明](https://github.com/jiang-zl/lotraAI-image2slide-skill/blob/release/skills/lotra-image2slide-skill/references/workflow-v133.md)。
