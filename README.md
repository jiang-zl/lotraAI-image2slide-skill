# lotraAI Image2Slide v1.33.0

将科研图片重建成分层、可编辑的 PowerPoint。支持原图＋一次性半成品 PPT 导入。
本版接入函数曲线、同一原图问题的共享收敛预算、个人知识库闭环和增量安装。
当前发布状态：IMPLEMENTED_STATICALLY_REVIEWED_NOT_TESTED_PER_USER_REQUEST。

## Quick start：让 Agent 安装

把下面一段交给当前项目中的 Agent 即可。只需读取本 README 的当前入口，程序
自行下载、续传、校验和准备环境；不需要让模型逐段下载或通读 runtime 清单。

首次安装提示词：

> 将 lotraAI Image2Slide v1.33.0 安装到当前项目。使用官方 install-lotra.ps1（Windows）或 install-lotra.sh（Linux）一键入口，自动准备匹配的 Python、OCR 和 Math runtime。安装完成后只报告 skill 入口、实际就绪状态和详细日志位置，不展开安装日志，不创建 Setup skill，不修改全局环境。

已安装旧版的增量更新提示词：

> 将当前项目的 lotraAI Image2Slide 增量更新到 v1.33.0。使用官方相同的一键入口，优先复用经哈希与资源兼容性确认的现有 runtime，只下载技能更新包和缺失资源；保留个人知识库、字体、任务、原图、旧版本和项目其他指令。完成后只报告版本、skill 入口、runtime 实际状态和日志位置。

官方固定版本发布入口：[v1.33.0 release](https://github.com/jiang-zl/lotraAI-image2slide-skill/releases/tag/v1.33.0)。
下载该 release 的 `install-lotra.ps1` 或 `install-lotra.sh`，在已有项目目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-lotra.ps1 -Project "C:\path\to\project"
# 已安装旧版时，执行相同命令；程序自动走增量更新。
```

```sh
sh install-lotra.sh /path/to/project
```

Windows AMD64 和 Linux x86_64 提供完整 runtime 路线。其他平台未提供完整 Math
资源时会明确停止，不会注册一个缺少环境的 skill。首次安装需下载对应平台资源；
同 runtime 的更新主要下载小体积 update ZIP。断点和已校验文件保存在项目私有目录，
失败后重跑同一命令。网络资源需要所在 Agent/宿主允许访问 GitHub。

离线方式：下载完整 `lotraAI-image2slide-v1.33.0-bundle.zip` 解压，运行其中
`installer/install.ps1 -Project PROJECT` 或 `sh installer/install.sh PROJECT`。
`lotraAI-image2slide-v1.33.0-update.zip` 是源代码/安装器增量包，首次安装时会联网补齐
所需 runtime；它不是完整离线包。不要单独安装内层技能 ZIP 后把环境准备留给模型。

## 重建

> 使用 $lotra-image2slide-skill 将这张原图重建为原生可编辑 PPT。按正常工作包完成部件、母件复用、排版和最终一次字体及整图复核。优先使用与当前原图兼容的个人方法；曲线按语义函数化，未知曲线使用分段低阶拟合，语义不变且差异在冻结的可接受范围内即可。

已存在任务先恢复，不重新从头生成。新旧任务状态与源图证据保持独立；旧任务只有
显式迁移后才使用 v1.33 新合同。个人库首次为空，使用后逐步建立自己的可复用方法，
不附带开发者的小车模型或私人历史。中文、英文按对应语言字体集合选择。

使用 [SKILL.md](skills/lotra-image2slide-skill/SKILL.md)，完整当前数据约定见 [v1.33 工作流](skills/lotra-image2slide-skill/references/workflow-v133.md)。
模型只处理当前源图语义与必要决策，程序处理几何、有限搜索、状态、引用和资源准备。
默认工具回执简短，完整证据保留在项目 .lotraAI-build。发布时未运行测试、验证、
重建、渲染或性能/效果测量；代码接入和静态审查不能证明实际节省百分比。
