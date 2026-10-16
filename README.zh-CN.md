# lotraAI Image2Slide v1.33.0

[English](README.md) | **简体中文**

将科研图片重建为分层、原生可编辑的 PowerPoint，也支持一次性导入半成品 PPT 继续重建。

## Quick start

在目标项目中，把下面一句交给 Agent。首次安装和旧版更新使用同一入口：

> 使用官方一键入口，在当前项目安装或更新 lotraAI Image2Slide v1.33.0：https://github.com/jiang-zl/lotraAI-image2slide-skill

安装后，附上原图：

> 用 $lotra-image2slide-skill 将这张图重建为原生可编辑 PPT。

## 手动安装

从 [v1.33.0 Release](https://github.com/jiang-zl/lotraAI-image2slide-skill/releases/tag/v1.33.0) 下载 `install-lotra.ps1`（Windows）或 `install-lotra.sh`（Linux），指定项目目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-lotra.ps1 -Project "C:\path\to\project"
```

```sh
sh install-lotra.sh /path/to/project
```

Windows AMD64 和 Linux x86_64 提供完整 runtime。在线安装需要访问 GitHub。安装器自动准备 Python、OCR 和 Math 资源，复用兼容资源，并返回简短结果和日志位置。下载中断后重跑同一命令即可。

更新后的生效目录同步新版完整文件清单，新版已删除的文件退出生效目录。个人知识库、字体、任务、原图和 PPT 保留，旧技能版本归档。

小体积 update ZIP 会联网补齐缺失资源。离线使用需取得完整 bundle，运行其中的 `installer/install.ps1 -Project PROJECT` 或 `sh installer/install.sh PROJECT`。

## 工作流与发布状态

v1.33.0 接入函数曲线、共享收敛预算和个人知识复用。个人库首次为空，部件和排版完成后再进行最终字体与整图复核。

详细规则见 [SKILL.md](https://github.com/jiang-zl/lotraAI-image2slide-skill/blob/release/skills/lotra-image2slide-skill/SKILL.md) 和 [v1.33 工作流](https://github.com/jiang-zl/lotraAI-image2slide-skill/blob/release/skills/lotra-image2slide-skill/references/workflow-v133.md)。

本版已完成实现与静态审查，未运行测试、重建、渲染或性能与效果测量。
