# 1.35.1 九处空间问题的实现与规则静态复核

审查对象：从已发布 1.35.0 派生的 1.35.1 源码、主 skill、空间规则和
component schema。这里只记录设计和调用链阅读，不是运行测试、语法检查、
导入检查、CLI 检查、重建、渲染或 Office 行为验证。

状态：IMPLEMENTED_STATICALLY_REVIEWED_UNTESTED。
以下九项在本轮静态审查范围内已建立对应约束和正常流程入口；这一结论不代表
执行结果或用户原图已通过验收。

| 问题 | 修改与静态依据 | 正常流程落点 |
|---|---|---|
| 1. 三维构件局部修订调用旧构造器 | native_surfaces.compile_spec 是共同分派；revise_scene 对旧、新冻结空间图分别编译并校验 owner 范围。component_revision.decide 不再直接调用 planar-only construct。共同参考系重绑也产生受限的原生 source-apply 计划。 | bind / focused decision / source rebind / numeric recompilation / native journal |
| 2. 重投影决策未持久化 | reproject 保存实例与母件的 SOURCE_DECISION_REQUIRED、当前源图/PPTX 身份及母件检查。母件优先获得 constructor_recapture 决策；显式范围可包含其派生家族。journal 的 post_save 可重放实例记录。 | next/submit source decision -> guarded revision -> reproject -> saved native confirmation |
| 3. 关系有对象 ID 却没有测量该对象 | spatial_observation 校验 subject/reference/ordered subjects 与每个锚点的实际所属单元；支撑/贴附角色独立校验；每个 surface/solid 的姿态和所有 standing/attached 的支撑义务由它自己作为被检对象满足。 | observe_source -> bind -> every local native check -> final spatial gate |
| 4. 点集冒充完整内容足迹 | 独立原图 footprints 与原生 footprint bindings 覆盖全部声明域的叶节点；保存后读取完整闭合域，保留孔洞与不相连部分；正齐次曲线控制包络做有界细分。面内聚合、两轴中心、边/中心对齐和完整区域包含不再只检查少量锚点。 | source targets -> saved-native footprint extraction -> local/layout/final metrics -> component metric table |
| 5. 父组件失效扩散到无关兄弟 | 直接变动单位作为关系失效种子；父资格变脏不再反向展开全部后代。外部关系在布局与最终门禁重新计算，不撤销未改邻居的固有资格。实际祖先原生变换进入测量签名；构造器规范和几何身份进入对应部件依赖。旧 best 按原合约保留。 | source bind reuse / refresh / impact / local repair / final readiness |
| 6. 缺少空间参数数值修复 | spatial_parameters adapter 在冻结范围内改变参考系或构造输入并统一重投影，程序派生全部适用原图空间硬目标；原图测量图、阈值、拓扑、可见性、材质不随试算变化。使用现有共享预算、checkpoint、有限搜索、batch commit 与原生确认。 | fit -> bounded_search -> component_batch -> component_constructor journal -> evaluate/qualify |
| 7. 修复顺序依赖可选标签 | 空间失败和阶段来自当前保存结果。姿态失败必须有 shared_frame/local_pose 诊断；共享参考系进入持久原图决策。字段按程序判定阶段分组，后续授权在 ledger 中等待；先前阶段须由当前保存测量确认，再校验等待字段未被改动并激活下一阶段。未完成阶段阻止 final。 | repair plan -> field grants -> edit journal post_save -> next phase check -> final readiness |
| 8. 母件同构遗漏面拓扑 | 新 polyhedron 的 anatomy_faces 与 anatomy_edges 是局部稳定结构；可见面仅引用该结构。canonical 对新合约同时约束顶点、面连接和额外边。可见面/材质/绘制次序保持独立。 | construct / manifest / validate_instances / current mother-body check / instance_of |
| 9. 投影名称和单位欠约束 | 新参考系检查平行投影的常数分母、透视投影的深度分母、非退化秩、正确旋转以及刚体父子同一单位。参数绑定同时检查坐标域与角度/坐标/基向量系数单位。 | observe_source / bind / constructor compilation / spatial numeric trial |

## 第二轮沿调用链发现并补齐的接线

- 初始 bind、局部修订、共同参考系重绑和有限拟合使用相同空间构造分派。
  改变规范后的旧编译 owner 会形成具体的受限写入计划，不会停在碰撞检查。
- 重新提取母件构造参数的决策必须落到母件，并显式覆盖依赖的实例家族。
  只给实例返回错误不能修订母件；旧原生 best 保存在原合约上下文中。
- 新观察与 spatial schema 必须同版；新任务不能声明旧策略来绕过完整足迹。
  旧已绑定任务继续使用旧策略，需要用户显式迁移后才使用新约束。
- 平面贴附文字也必须自己满足贴附关系，不能因 mode 为 planar 而借用其他
  单元的支撑关系。原生文字、完整字体和真正 OMML 规则继续保留。
- 完整域一致性使用相互保守覆盖；不把离散 Hausdorff 顶点采样当作完整证明。
  曲线误差进入中心/对齐和覆盖边界，精度不足归为测量诊断。
- 未填充的试算边不能沿用基线填充区域来证明遮挡；无法测量的区域不会通过。
- 空间目标指标接入现有 metric schema、测量适配器、shared budget、fit、batch
  和 saved-native 确认。原生源图/实际显示复核不接受数值代理作为最终证据。
- 分阶段修复的 saved 标记和实例状态在原生 journal 中记录，诊断/用户字段
  冲突也持久化。stage 尚未关闭时不能直接进入最终验收。
- 局部资格签名保留内部空间关系；跨组件关系是布局依赖。对应构造参数身份和
  真实原生祖先位姿参与其消费者身份，避免漏掉变化或全页撤销独立资格。
- 正常布局和独立最终验收都重新测量 anchors、footprints、relations，交付
  指标表列出三个通道；模型仍必须对原图每个单元和关系作当前实际显示判断。

## 保持的边界

原生 preset、紧凑组合/共享面和有界路径按适用性依次选择。没有增加像素铺图、
另一个模型/provider、全局 skill、独立验收引擎或新的 runtime 资源依赖。

不可观察的真实三维、未知相机、隐藏体积仍不被宣称已恢复。缺失提取器、精度
不足、源图不确定和有限预算耗尽不会被记作 PASS。静态阅读不能证明程序已经
运行正确，亦不能证明效果、耗时或 token 改善。运行验证按用户要求没有执行。
