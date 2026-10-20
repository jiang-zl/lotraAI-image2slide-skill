# 安装与更新

[English](installation.md) · [返回首页](../README.zh-CN.md)

在 Codex 中打开工作项目，发送：

> 请从 https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime 在当前项目安装或更新 lotraAI Image2Slide。

运行资源和主 skill 由同一入口准备。首次安装按当前平台获取资源；后续更新新增、替换和删除对应的受管理文件，未变化的生效文件不重复下载或写入。个人知识库、字体、任务、原图、PPT 和全局技能保留。

手动命令、Windows/Linux/macOS 资源范围、完整包下载和已有解压包安装，统一以 [runtime 安装说明](https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/blob/dev/docs/installation.zh-CN.md)为准。

安装后附上图片，使用：

> 用 $lotra-image2slide-skill 将这张图重建为可编辑 PPT。

参见[使用指南](usage.zh-CN.md)。实际资源与能力记录在工作项目 `.lotraAI-build/Bundle-install.json` 中。

## macOS 公式后端（1.35.3）

由保留原签名的 LibreOffice 主应用，在新建的项目私有配置中执行固定 Python／UNO 工作器；安装器不直接启动受父进程约束的内嵌解释器。应用签名与系统安全设置保持原样。安装启动检查与正式导出使用同一工作器，每次安装尝试都进行新的原生 Math 启动检查。

如果此前只安装了技能文件，在同一项目重新运行维护安装入口即可继续准备；已验证资源保留。诊断以本次 `Failure.json`、`Math-backend-failure.json` 及其引用的 `backend-result.json` 为准，记录阶段、命令、退出状态和日志路径。尚未到达的核心阶段标记为 `NOT_RUN`。启动检查成功不代表实际文档渲染或整图质量验收。

GitHub Release 下载增加有限次数的官方资产 API 备用通道，仍校验相同的大小、SHA-256、范围响应和缓存归属。macOS Math DMG 继续使用固定的上游地址。Apple Silicon 与 Intel 的 macOS 实机检查仍待完成，Windows 结果不作为两种 Mac 架构的通过证据。

## 1.35.4 安装入口

所有 shell 安装入口使用无 BOM 的 UTF-8 与 LF。维护者从固定模板生成入口，并对最终附件、skill ZIP 和完整包中的实际脚本执行解析检查。Windows 入口同时检查 Windows PowerShell 解析与真实安装。runtime 二进制与资源包保持不变。
