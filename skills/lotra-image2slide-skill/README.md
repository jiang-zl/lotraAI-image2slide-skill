# lotraAI Image2Slide v1.31.0

本版状态：**IMPLEMENTED_PUBLISHED_UNTESTED**。按用户最新指示，不运行发布测试。
仅独立文字、基础形状和公式新增源参数/原生属性验收，详见
[v1.31 说明](references/native-core-v131.md)。复杂 icon、子部件、母件及重复
实例复用保持 v1.30；其他部件与旧任务流程不改。集成离线 runtime，额外提供
LibreOffice Math 公式编辑器。下文 v1.30 的测试记录属于历史基线，不证明本版。

将科研参考图重建为忠实、清晰、分层可编辑的 PPTX。Agent 理解原图并判断语义，程序负责执行、测量、保护、回滚和验收。当前版本减少重复上下文与重复执行，保留完整递归、原生编辑能力和所有质量硬约束。

使用入口为 [SKILL.md](SKILL.md)。按当前程序工作包执行，不需要把历史对话、整个数据库或全部参考文档交给模型。完整原图合同、测量和最佳版本存入项目 `.lotraAI-build`；显示包只提供当前行动需要的内容及可核验引用。

本版包含任务隔离、按字段分页读取、累计读取索引、恢复检查点、增量工作包、依赖范围计算、共享原生/图像事实、解码前数值缓存、同任务批量检查和重复失败抑制。缓存有容量与设备内存边界；失效或缺证据会重新执行。最终验收仍完整检查原图单元、保存对象和表格单元格。平台历史压缩和提示缓存由宿主决定，本 skill 不假定有该控制权。

随包提供运行程序、分类评价配置、通用构造资产、必要参考和许可证。离线 OCR/依赖资源使用独立校验的 runtime companion；由项目内 bootstrap 选择实际可运行的资源，不联网下载、不修改全局 Python、不要求额外模型密钥。详见 [运行准备](references/runtime-readiness.md)。客户包不包含私人任务、案例输出、历史数据库或开发日志。用于升级验收的可执行合同检查是运行依赖，保留在包内。

交付给重建用户的文件只有 `Final_editable.pptx` 和 `Report.md`。报告列出各部件的实际指标与 ↑/↓。PDF 仅用于真实导出验证，全部依赖完成后清理；组件与详细过程留在项目 runtime。

安装到新的版本目录，旧版和用户文件保留。`scripts/package_skill.py` 校验文件清单与 SHA-256；这些哈希是完整性校验，不是发布者签名。实际服务 token 未提供时标为未知，不能从字符减少或缓存命中推算节省比例。

## v1.30.0 reliable measurement and guarded repair scheduling

Current-task failure agendas, early saved-native capability diagnosis, complete
batch prevalidation and command spans with exclusive timing organize the
existing executors. Read references/workflow-optimization.md for finite routes
and evidence limits. Invalid edge crossings supply no width or gain; original
probe diagnosis precedes reconstruction. Mathematical digit styles retain
the same value and AST scope, while actual typography/OMML remain independent.
Pending fonts, saved renders and user intent precede an older quality loop.
`workflow-control advance` executes current source-bound math corrections or
registered finite repair plans, then returns the next real contract.

The release runs production regressions and an isolated actual Office
edit/save/reopen/render control. These controls verify the addressed mechanisms;
each new reconstruction still needs complete current whole-result acceptance.
Actual end-to-end performance and service-token savings remain unknown.

Shared task resource scopes reuse image decodes, common transformation prefixes,
ZIP/XML and PDF documents/windows. Small exact pixel payloads are found before
decode/rasterization and use the private bounded cache. Independent final gates
bypass persistent pixel and measurement-result hits. Read
[resource locality](references/resource-locality.md) for ownership, sampling and
remaining repeated paths. Resource counters describe actual operations only.
