# v1.33.0 installation and publication

Semantic version and public release tag are v1.33.0. The public source is based
on v1.32.0 publication revision 9. Component design revision remains 8.

The tested Windows x64 and WSL/Linux x64 candidate uses shared OS entrypoints,
project-local Python, managed file differences, common content caches and one
discoverable skill. The skill package also supplies install-runtime.ps1/.sh.
Clean local-bundle and local-HTTP online installation, core execution, actual
OCR inference, Math startup, repeat installation and private-data preservation
passed before publication. Online fixtures changed distribution URL literals
and their dependent hashes; they did not change installer logic or payloads.
Public GitHub download commands were checked against the then-published entry.
macOS resources and commands are provided without a native-host acceptance claim.

No reconstruction, Office editing, performance or token-effect measurement
qualifies this release. Those channels remain untested at the user's request.

The complete ZIP is transported as 18 ordered pieces of at most 128 MiB.
Platform-specific online resources share the same maintained installation core.
The public personal catalog is empty; private task images, PPTs, fonts, knowledge,
test fixtures, credentials and local paths are excluded from public source.

Only v1.33.0 is used for this version. The prepared WSL publisher retains matching
assets, uploads missing assets, verifies all declared digests and only then
activates the release channel. Exact obsolete 1.33.0 auxiliary releases and tags
are removed after successful activation. Earlier product version history remains.

## Original implementation record

The following record describes the initial development scope. The installation
checks above supersede its installation-only not-run statements. Reconstruction
and effect-measurement exclusions still apply.

# lotraAI Image2Slide 1.33.0

基线：1.32.0 design revision 8 / publication revision 9，沿用已发布 1.31 谱系。
本次状态：IMPLEMENTED_STATICALLY_REVIEWED_NOT_TESTED_PER_USER_REQUEST。

1.32 已做固定参数原生构造、有限局部拟合、子部件/母件/实例/排版、一次最终语言字体
复核和整图验收、单页半成品导入、一致性修订及公共私人模型清理；自动跨任务个人
学习与检索尚未接入，旧搜索预算按模型分开，不能视为根本解决所有长耗时/token问题。

1.33 将四条主线接入正常流程：

- 曲线使用语义函数族或分段低阶/参数函数，有限 native cubic 编码，源图冻结两档
  阈值；保留端点、趋势、关键峰、闭合/断点等特征。旧任务不自动重绘。
- 同一原图问题共享模型/数值/源图/实际原生确认预算；保留失败策略和最佳引用，
  达到可接受档可停止，耗尽而不合格时显式 unresolved，不改阈值求通过。
- 项目私有知识库在详细几何前检索、按描述符选择、程序展开；母件候选与最终接受
  case 分开，元数据索引/CAS/冷证据/幂等反馈闭环，空公共个人目录。
- 单一平台入口安装和增量更新：兼容资源先复用，缺什么下载什么，有限续传与哈希，
  runtime/OCR/Math 先行，单 skill 后注册；README 短提示词和短回执。

缓存/上下文同时修正重复正文反复回传、component resume epoch、查询正负缓存失效、
像素/数值缓存分额与单项准入；不增加效果或成本遥测，不宣称测得节省百分比。

交付：完整离线 bundle、增量 update ZIP、Windows/Linux 一键脚本及对应不可变平台
资源。版本号 1.33.0；组件兼容 schema 保持1.32/design8，新合同 workflow_version1.33。
旧版本、私有任务/字体/库、原图、Git、全局技能保留；无 Setup skill。

本轮只做实现、源代码静态审查、文件组装/发布/源安装。不执行测试、语法/import/CLI、
安装器验证、重建、渲染、Office 行为检查或性能/效果测量。打包哈希只是发布文件身份；
本机 runtime 事实继承旧回执，未重新验证；未来安装器的检查代码不等于本轮已运行。
细节见 Static-review.md 与 references/workflow-v133.md。
