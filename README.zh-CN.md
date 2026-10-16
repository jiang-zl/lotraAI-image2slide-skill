# lotraAI Image2Slide

[English](README.md) | **简体中文**

将科研图片重建为分层、原生可编辑的 PowerPoint，也支持一次性导入半成品 PPT。

## Quick start

在项目中，把这一句话交给 Codex：

> 请从 https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime 在当前项目安装或更新 lotraAI Image2Slide。

Codex 自动下载并调用官方安装程序。已安装用户也用同一句话更新。

安装后附上原图：

> 用 $lotra-image2slide-skill 将这张图重建为原生可编辑 PPT。

## 安装与差分更新

Runtime 仓库是统一安装入口。程序新增新文件、替换变更文件、移除新版已删除的受管理文件；未变的生效文件不重复下载或写入。按哈希复用资源和兼容环境，保留个人知识库、字体、任务、原图和 PPT。详细日志留在项目中，Agent 只返回简短结果。

Python/OCR 资源覆盖 Windows AMD64、Linux x86_64/aarch64、macOS Apple Silicon 和 Intel。Math 清单覆盖 Windows AMD64、Linux x86_64 和两种 macOS 架构。Linux ARM64 有核心资源，尚无随包 Math，完整安装会明确报告该限制。macOS 要求 13 或更新版本。

当前安装修订为 **1.33.0 install-r3**。历史版本与离线归档保留，当前入口使用文件清单进行差分更新。

详细规则见[工作流](https://github.com/jiang-zl/lotraAI-image2slide-skill/blob/release/skills/lotra-image2slide-skill/references/workflow-v133.md)。本修订完成实现与静态审查，未运行测试、安装、重建、渲染或性能与效果测量。
