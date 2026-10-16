# 1.33.0: installation and reconstruction evidence / 安装与重建证据

## English

Pre-publication installation checks passed on Windows x64 and WSL/Linux x64. They covered an empty project, the normal online entry using a local release mirror, installation from local complete resources, dependency imports through the actual managed worker, installation-time OCR inference, skill CLI startup, Math version/UNO imports, and repeat/update behavior with unchanged-file and private-file preservation.

The local mirror changed distribution URL literals and their derived hashes only. Installer logic and skill/runtime payloads were unchanged. Public download commands fetched the currently published scripts successfully. End-to-end installation of the new candidate through GitHub remains a separate check after its assets are published; these results do not claim that the paused release is already public.

Installation readiness, saved document rendering and whole-figure acceptance remain separate. No reference-image reconstruction, Office open/edit/save/reopen testing, or token/time effect measurements were performed in this round.

Public examples are historical author-supplied images and screenshots with unspecified generating versions and no accompanying native PPTX. They illustrate visible structure and are not 1.33.0 benchmarks or personal-knowledge seeds.

## 简体中文

Windows x64 与 WSL/Linux x64 的预发布安装检查已通过，覆盖空项目、通过本机发布镜像执行的正常在线安装、本地完整资源安装、真实受管理工作进程的依赖导入、安装时 OCR 推理、skill CLI 启动、Math 版本与 UNO 导入，以及重复安装/更新时未变化文件和私有文件的保留。

镜像只修改分发地址字面值及派生哈希，安装逻辑与 skill/runtime 载荷保持原字节。公共下载命令已成功获取当前已发布脚本；新候选通过 GitHub 的完整端到端安装须在附件公开后另行确认。这些结果不表示暂停中的发布已公开。

安装准备、保存后的文档渲染与整图验收分别记录。本轮没有执行参考图重建、Office 打开/编辑/保存/重开测试或 token/时间效果测量。

公开案例由作者提供，属于生成版本未标注、未附原生 PPTX 的历史图片与截图；用于展示可见结构，不作为 1.33.0 的实测结果，也不会预置到用户个性化知识库。
