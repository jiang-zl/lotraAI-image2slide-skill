> Publication update: this is the original reconstruction call-chain static review.
> Subsequent Windows x64 and WSL/Linux x64 installation checks are recorded in
> Release-report.md. Those checks do not qualify reconstruction or Office editing.

# v1.33.0 静态调用链审查

范围：实际 Python/PowerShell/shell 源代码与发布清单阅读。未运行测试、语法编译、
import/CLI、安装器、重建、渲染、Office 行为检查或性能/效果测量。
“接入”只描述代码生产者、保存位置、消费者及失败分支，不表示运行验证通过。

| 入口 / 约束 | 生产者与保存 | 实际消费者 / 失败分支 |
|---|---|---|
| 新任务 / 半成品 PPT | 原有 start/source/import；bind 新增 workflow_version | next/submit/advance 仍共用 component_workflow、现有原生 journal 与单页导入 |
| 源图早期个人检索 | next_action → knowledge_outline → outline，任务菜单哈希引用 | submit_result → expand → normalize/validate → bind；空个人库跳过额外轮次 |
| 描述符与选中展开 | knowledge.sqlite 元数据索引、cores CAS | expand 校验当前菜单/原图/状态/构造哈希，程序实例化后交给完整所有权合同 |
| 函数曲线 | bind 先 prepare(execute=False) 冻结目标，再完整合同校验，再 prepare 编译 | semantic_curves 跳过已编译函数；原生 writer 使用有限 cubic contours |
| 科学语义 | samples_ref 源图哈希；相对周期/显式特征；自动端点 | 数值 semantic gates；actual_checks 与实际 curve_distance、原生结构、固定 paint 联合评估 |
| 两档阈值 | 源图 uncertainty/precision/feature separation → curve_profile → targets | solver/metric_result 使用冻结 acceptable 上限，记录 preferred/acceptable；无效测量和语义失败不补偿 |
| 跨模型共享 | problem_control 独立 Problems.json，以源单元、继承、同区/class 保留身份 | curve family、generic fit measure、source decision、actual evaluate 均扣同问题预算；换模型/参数不重置 |
| 失败策略 / 停止 | fit basis + strategy/report ref；有限模型/数字/源图/实际次数 | 重复失败返回引用；next 显式 unresolved，保留 best；禁止追分放宽目标 |
| 部件 / 母件闭环 | qualify → capture_qualified 存 candidate | final accept → case；旧 evidence 不授权当前 QUALIFIED；promoted 仍需多例手动证据 |
| export 旁路 | component_final.accept 统一调用 accepted | run 和直接 export 都到同一 accept；归档/反馈重复调用幂等 |
| 负反馈 | evaluate 当前有效局部失败与选中 owner 关联 | local_feedback 写 source/native/result identity；排名次要参考，非 token 帮助标签 |
| 旧库兼容 | 一次性元数据索引，后续 capture/promote/use/revoke 同步 | descriptor cache catalog revision 失效；不删除旧 entry/history/source |
| 库去重和隐私 | 归一化注册几何核心独立于名称/证据；项目私有库 | 精确 class/view/parts/counts/topology/edit 过滤；只显式共享用户路径；公共默认空 |
| 上下文恢复 | resume 在 component 分支之前增加 epoch | 同 epoch 稳定 ALREADY_READ；fresh 显式恢复正文；执行端保留完整合同 |
| 原始资源缓存 | 精确文件/变换/依赖；去除无关上下文显示策略哈希 | 像素/数值分额，单项准入，LRU 只删可重算行；final 独立证据原有旁路保留 |
| 一键与增量 | pinned update ZIP → 原生 bootstrap → online coordinator | 哈希兼容既有 companion/engine，缺失平台资源有限续传，offline 同入口读本地资源 |
| runtime 先行 | stage_skill → core/OCR prepare → Math UNO import | 成功后 publish/register；默认短 JSON，详细日志磁盘引用，实际 render/edit NOT_RUN |
| 失败恢复 | publication preimage/journal 与 owned 旧技能归档 | 捕获失败执行 rollback；未知修改不覆盖；私有库/字体/任务不在替换范围 |
| 发布 | customer-package 显式新文件；内外两层源文件及 manifest 同步 | 1.32 包保留；版本 1.33、兼容 schema8、空个人目录、无 Setup/global 修改 |

审查中修正了原型的阈值冻结时机、直接 export 漏归档、函数曲线误路由通用 fit、
offline 误走网络、Windows 安装器旧版本常量、UNO 扩展路径、引用正文交替重发、
component resume 提前返回未增加 epoch、模型预算独立、旧库反馈全文回传等冲突。

设计边界：只考虑 image 与一次性半成品 PPT。颜色/形状/文本等确定参数沿用固定
构造；不加入实时编辑监听、账户系统、云向量库、通用 undo/事务框架、多页编辑器。
宿主历史压缩、provider 缓存及实际 token/time 收益不在本次可确认范围。
真实源图解读、独立取样和最终视觉观察仍由当前宿主模型/用户完成。

结论：本次源代码阅读未留下已识别而未处理的主流程接入缺口；这是静态审查结论，
并非无缺陷保证，也不替代明确未执行的运行检查。

发布前补充阅读：源合同强制 assembly class/view，避免空库首次任务永远不归档；
非单值参数曲线的实际确认走云点/拓扑门，不能误用 x 列波形；安装注册追加受管当前
版本规则以消解旧 AGENTS 的选中版本声明；有限代理故障恢复及已完成安装回滚隔离。
补查内层 package_skill.parse_manifest/customer_policy/receipt 与 core 报告版本时，
发现产品版本常量仍为1.32，已改为1.33后重新组装并源发布。兼容合同 schema、字体
集合政策版本和 runtime 1.14 的常量按其数据身份保留，不作为产品版本盲目替换。
原问题继承在函数编译之前完成，原有 local problem 分解为 assembly/子件时，子件
继承此前祖先问题的预算；不能先在新身份下消耗一轮再在提交阶段发现旧身份。
实际曲线指标的独立 source_points 可以由 samples_ref 在程序内展开，避免模型再传
一份密集坐标列表；原图哈希和 ROI 坐标归一化仍由代码检查。
