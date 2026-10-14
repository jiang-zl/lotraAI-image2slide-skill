# lotraAI

**将科研参考图重建为分层、可编辑的 PowerPoint。**

[English](README.md) · [中文版](README.zh-CN.md)

lotraAI 将当前 agent 对原图的理解与项目内的重建程序结合起来，用于科研系统图、方法流程图和结构示意图。文字、形状、连接与语义分组按原生对象组织；公式使用结构化 Office Math；照片等图像内容保留为适当范围的图片对象。

[快速开始](#快速开始) · [案例](#案例) · [使用指南](docs/usage.zh-CN.md) · [安装说明](docs/installation.zh-CN.md) · [下载完整包](docs/download.zh-CN.md)

## 快速开始

### 1. 让 Codex 安装 skill，并自动下载运行资源

把本仓库地址和下面的提示词交给 Codex。Codex 可以替你下载匹配的 runtime 资源、校验完整包，并安装到当前项目。

~~~bash
请从以下仓库为当前项目安装 lotraAI Image2Slide v1.31.0：
https://github.com/jiang-zl/lotraAI-image2slide-skill

请自行从以下仓库下载匹配的 runtime 资源：
https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime
读取 v1.31.0 版本清单，使用下载程序获取全部分块、合并并校验完整 bundle。
解压后调用包内安装器，先将 Python、依赖、OCR 和 Math 准备到 .lotraAI-build，
再登记 skill，命名为 lotra-image2slide-skill。
完成后报告 skill 入口和实际运行时准备情况。
~~~

下载和安装可以交给 Codex 完成，无需逐项手动下载 runtime 资源。[版本清单](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/blob/release/releases/v1.31.0.json)和[下载程序](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/blob/release/tools/fetch_bundle.py)位于 runtime 仓库。

**运行包可用性：** skill 与 runtime 分开发布。Codex 应先确认对应 runtime 附件已公开，再开始下载。若附件仍在上传，可以提供本地完整包，或使用已经准备好匹配 runtime 的项目。仅下载 skill 源码不会完成运行时准备。详见[下载说明](docs/download.zh-CN.md)。

如果已有完整 ZIP，将它放到当前项目中，或提供本地绝对路径，再发送：

~~~bash
帮我解压提供的完整包 lotraAI-image2slide-v1.31.0-bundle.zip，
使用包内安装器，将其中的 skill 安装到当前项目，命名为 lotra-image2slide-skill。
请先准备包内的 runtime 资源（Python、依赖、OCR 和 Math），再登记主 skill。
完成后告诉我 skill 入口和运行时准备情况。
~~~

完整 ZIP 包含 skill 和 runtime 资源。安装只登记一个 `lotra-image2slide-skill`；运行资源和私有任务状态位于项目 `.lotraAI-build`。

### 2. 附上原图开始重建

~~~text
使用 $lotra-image2slide-skill，将这张参考图重建成可编辑 PowerPoint。
保留原文、公式、层次和连接关系；保持图中的语义分组。
~~~

当前 agent 负责解释原图，程序负责执行、检查与导出。工作流交付 `Final_editable.pptx` 和列出实际部件指标的 `Report.md`。

手动安装命令见[安装说明](docs/installation.zh-CN.md)。

## 能做什么

- **按语义组织对象。** 用原生文字、形状、路径、连接和分组表达图中的结构，便于后续调整。
- **保留结构化公式。** 数学表达使用源结构与真正的 Office Math；本版新增 Math 渲染路径与实际 Microsoft Office 编辑验证分别说明。
- **细化图标部件。** 图标及其子部件沿用既有递归识别、构建与检查流程。
- **保护局部修改。** 在任务合同中明确保留范围，继续修改时检查受影响的对象与关系。
- **项目内准备依赖。** 完整包在本地准备 Python、OCR 和相关程序资源；无需额外模型 API key。当前 agent 服务的运行方式由宿主决定。

## 案例

以下三组案例由作者提供，每组包含原图、PowerPoint 截图和亮点图。点击图片查看原尺寸。截图用于展示重建结构；原生 PPTX 文件和各案例的实际生成版本未随这些图片提供。


### 1. 边缘联邦学习系统

包含服务器、客户端与终端设备三层结构，呈现数据规模长尾、类别异构与观测噪声。

| 原图 | 重建 PowerPoint | 重建亮点 |
|:---:|:---:|:---:|
| <a href="docs/assets/examples/01-edge-federated-learning/original.jpg"><img src="docs/assets/examples/01-edge-federated-learning/original.jpg" alt="边缘联邦学习系统 — 原图" width="100%"></a> | <a href="docs/assets/examples/01-edge-federated-learning/reconstruction.jpg"><img src="docs/assets/examples/01-edge-federated-learning/reconstruction.jpg" alt="边缘联邦学习系统 — 重建 PowerPoint" width="100%"></a> | <a href="docs/assets/examples/01-edge-federated-learning/highlights.jpg"><img src="docs/assets/examples/01-edge-federated-learning/highlights.jpg" alt="边缘联邦学习系统 — 重建亮点" width="100%"></a> |

- PowerPoint 截图展示可分别选择的文字、数据条、类别标记、客户端电脑和通信箭头。
- 亮点图展示车辆车身、车窗、后视镜、无线信号弧线与地图图层的部件拆分。

[查看案例说明](docs/examples/01-edge-federated-learning.zh-CN.md)

### 2. 感知与通信系统

由终端、通信、边缘服务器三层组成，包含感知图像、数据估值表、数学标注、资源分配与模型训练。

| 原图 | 重建 PowerPoint | 重建亮点 |
|:---:|:---:|:---:|
| <a href="docs/assets/examples/02-sensing-communication/original.jpg"><img src="docs/assets/examples/02-sensing-communication/original.jpg" alt="感知与通信系统 — 原图" width="100%"></a> | <a href="docs/assets/examples/02-sensing-communication/reconstruction.jpg"><img src="docs/assets/examples/02-sensing-communication/reconstruction.jpg" alt="感知与通信系统 — 重建 PowerPoint" width="100%"></a> | <a href="docs/assets/examples/02-sensing-communication/highlights.jpg"><img src="docs/assets/examples/02-sensing-communication/highlights.jpg" alt="感知与通信系统 — 重建亮点" width="100%"></a> |

- 重建截图展示分层面板、表格布局、标签、箭头与训练网络元素的独立选择状态。
- 亮点图展开摄像机外壳、镜头、支架和无线标记，并展示可独立选取的照片；照片本身仍属于图像内容。

[查看案例说明](docs/examples/02-sensing-communication.zh-CN.md)

### 3. 信号重建训练与推理流程

覆盖 SPGA、STFT、CTFR、时频掩码和混合引导损失的训练与推理流程。

| 原图 | 重建 PowerPoint | 重建亮点 |
|:---:|:---:|:---:|
| <a href="docs/assets/examples/03-signal-reconstruction/original.jpg"><img src="docs/assets/examples/03-signal-reconstruction/original.jpg" alt="信号重建训练与推理流程 — 原图" width="100%"></a> | <a href="docs/assets/examples/03-signal-reconstruction/reconstruction.jpg"><img src="docs/assets/examples/03-signal-reconstruction/reconstruction.jpg" alt="信号重建训练与推理流程 — 重建 PowerPoint" width="100%"></a> | <a href="docs/assets/examples/03-signal-reconstruction/highlights.jpg"><img src="docs/assets/examples/03-signal-reconstruction/highlights.jpg" alt="信号重建训练与推理流程 — 重建亮点" width="100%"></a> |

- 重建展示保留训练/推理分区，以及围绕波形、频谱内容组织的多层损失面板。
- 选择状态截图展示模块框、标签、箭头、数学标注与反馈路径的独立对象结构。

[查看案例说明](docs/examples/03-signal-reconstruction.zh-CN.md)


## 使用方式

除了整图重建，也可以明确指定局部修改和保留范围：

~~~text
只调整右侧模块与箭头的间距。保留文字、公式、图标内部结构以及其他区域。
~~~

任务中断后，在同一个工作项目中要求继续当前注册任务。原图和工作流状态保存在项目内，具体操作见[使用指南](docs/usage.zh-CN.md)。

## v1.31.0

本版为显式绑定的独立文字、基础形状和公式增加源参数与原生属性合同。复杂图标、图标子对象、重复实例及其他组件继续使用既有流程。新增 LibreOffice Math 资源面向 Windows/Linux x86-64；其他平台的 Python 资源不代表此 Math 安装路径已具备。

本版保留 `NOT_RUN_PER_USER_REQUEST` 的功能验证状态。安装准备、实际文档渲染、原生编辑与整图验收分别记录；上述案例截图不改变本版状态。详见[版本记录](CHANGELOG.md)和[验证状态](docs/validation.md)。

## 文档与项目结构

| 入口 | 内容 |
| --- | --- |
| [安装](docs/installation.zh-CN.md) | 完整包安装、平台要求、安装收据 |
| [使用](docs/usage.zh-CN.md) | 整图重建、局部修改、恢复任务 |
| [故障排查](docs/troubleshooting.zh-CN.md) | 安装、字体、渲染与运行时诊断 |
| [发布准备](docs/publication.md) | 两仓库职责和公开下载配置 |
| [skill 源码](skills/lotra-image2slide-skill/SKILL.md) | 当前 v1.31.0 的完整主载荷 |
| [来源与许可](NOTICE.md) | 项目源码、第三方组件和案例素材 |

需要反馈时，请描述系统、产品版本、具体操作和相关诊断；按需提供经过检查的原图或片段。项目内的私有任务数据由你管理。
