# LinglongLab AI Video — ArcReel 功能对齐与超越计划

> 状态：广告核心 P0 与 P1 集成层完成；其余增强继续执行  
> 建立日期：2026-09-24  
> 对齐基线：ArcReel v0.31.0；`main` 未发布能力单独标记，不作为稳定版必选项  
> 实施原则：复刻可观察行为与生产语义，不直接复制 AGPL-3.0 源码；如公司取得 ArcReel 商业授权，可另行评估代码级复用

## 1. 目标

在保留 LinglongLab 广告研究、证据治理、镜头准备与首/关键/尾帧控制优势的前提下，实现与 ArcReel **广告视频核心生产能力**基本一致的 AI Video 产品，并在商品真实性、确定性品牌后期和广告交付 QA 上超过 ArcReel。

当前阶段不追求 ArcReel 全功能复刻。通用长视频、企业协作、NLE 和完整迁移不进入完成标准；ComfyUI、自定义 endpoint/market、MCP、外部 Agent 和复杂记忆保留为广告核心闭环后的 P1。

完成标准不是“页面上有入口”，而是用户能在活跃 `/ai-video` 路径中完成并重新加载以下生产链：

```text
Brief → Assets → Approved Plan → Shot → Keyframe → Take
→ Selected Take → Edit Revision → QA → Delivery
```

每个环节必须可追溯、可审阅、可重试，并保留输入、版本、任务、费用和操作主体。

### 1.1 当前广告视频核心范围（P0）

只有以下九个结果属于当前目标：

1. 广告 Brief：商品、受众、卖点、平台、市场、目标时长、画幅、CTA、Legal 和禁用表达。
2. 广告资产：商品原图真实性锚点、Logo、品牌规则、人物/场景/道具和参考素材。
3. 正式脚本与 Shot Plan：可编辑、可批准、可追溯到研究方向和商品卖点。
4. Keyframe：生成/上传多个候选，明确批准一个版本，支持首/关键/尾帧控制。
5. Video Take：按镜头生成、批量预检、费用确认、显式采用、失败恢复且不静默覆盖。
6. 广告剪辑：镜头排序、裁切、转场、字幕、旁白、音乐/SFX、Logo、CTA、Legal、End Card。
7. 确定性渲染：从批准的 EditRevision 和固定 manifest 产出可复现 MP4。
8. 广告 QA 与交付：时长/画幅/黑帧/静帧/音量/字幕安全区/CTA/Legal 检查，Final 必须通过 QA。
9. 生产可靠性：幂等、checkpoint、批次准入、任务状态、用量和费用可见。

### 1.2 次优先广告增强（P1）

- Reference Video：只提取 hook、节奏、镜头语言和 CTA 结构，不复制品牌身份。
- 2×2 / 3×3 Keyframe Grid 和候选拆分。
- 同一母版输出 16:9、9:16、1:1 等平台版本。
- 独立 TTS、角色声音、字幕和音乐生成的产品化工作流。
- 商品卖点、claim evidence 和交付版本的端到端关联。
- 自定义 endpoint、ComfyUI workflow 和可审阅 endpoint market。
- MCP、外部 Agent、用户/项目记忆和确定性工具合同。

### 1.3 当前明确不做

- 组织/RBAC、客户评论、多人审批和企业级租户治理。
- EPUB 和长视频分集；当前只保留广告所需的 brief/脚本输入。
- 多 NLE 生态；不制作 Jianying/Premiere/Final Cut Pro 工程文件 adapter，只交付标准 MP4、字幕和 manifest。
- 全局资产市场、复杂资产分叉、通用角色年龄/形态生态。
- 跨产品/跨部署的完整历史 ZIP 导入迁移平台、示例市场和高级运维控制台。

基础数据库 schema migration、项目备份和失败回滚仍属于必要工程安全能力，不等于上述用户可见的“完整迁移平台”。

## 2. 状态标记

| 标记 | 含义 |
|---|---|
| `[x]` | 已有且通过当前活跃路径验证 |
| `[-]` | 部分具备，缺少关键闭环 |
| `[ ]` | 尚未实现 |
| `[>]` | 当前正在实现 |
| `[—]` | 经产品决策明确不做 |
| `LinglongLab+` | 目标应明显优于 ArcReel |

## 3. 功能复刻清单

### 3.1 项目、输入与工作流模式

- `[x]` 项目、章节、镜头和项目文件。
- `[—]` EPUB/长内容统一导入不在广告 P0 范围。
- `[x]` 广告/短片项目入口与广告 Brief。
- `[-]` 生成模式：Storyboard、Reference Video；LinglongLab 已有多种帧参考组合，但尚未形成模式级合同。
- `[ ]` Grid Storyboard：2×2、3×3，并按实际需求扩展 4×4、5×5。
- `[x]` 项目级目标时长、画幅、风格、默认模型、预算和生成策略。
- `[x]` 服务端权威 `WorkflowPlan`：步骤、阻断、审核门、产物状态和 `next_action`。
- `[—]` 完整历史 ZIP 迁移平台明确不做。

### 3.2 研究、脚本与计划

- `[x]` 研究/preset 入口、来源、发现、创意方向和批准门。
- `[x]` 脚本分析、优化、拆镜头、素材/对白候选确认。
- `[x]` `ScriptRevision`：草稿、正式版、批准人与批准时间。
- `[x]` `ShotPlanRevision`：从持久化 Shot Card 生成快照，人工批准并保留来源范围。
- `[ ]` 内容审核与视觉提示词编写分层。
- `[-]` 结构化广告脚本支持 hook/proof/payoff/CTA、对白/旁白和时间节拍；镜头增删使用现有 Shot 工作台。
- `[ ]` 只重写受影响镜头的提示词，未变化产物保持可用。
- `[—]` 长内容分集账本不在范围。

### 3.3 资产与一致性

- `[x]` 角色、场景、道具、服装、图片和项目/镜头关联。
- `[x]` 一等 `Product` 及项目级商品事实、claims 和禁用修改。
- `[x]` 商品原图真实性锚点 + 带 lineage 的标准化商品资产双层模型。
- `[ ]` 角色衍生：换装、年龄、形态等持续外观版本。
- `[ ]` 全局资产库到项目独立副本。
- `[ ]` 图片指令编辑生成新版本，不覆盖原图和原提示词。
- `[-]` 资产候选、选择、恢复和人工上传替换已具备；视觉对照组件仍可增强。
- `[-]` 参考图上限校验；需根据模型 capability 显式阻断或提示裁剪，禁止静默丢弃。

### 3.4 Prompt 与生成输入

- `[x]` 首帧、关键帧、尾帧和组合参考模式。
- `[x]` Shot prompt preview、guidance、mapping、质量检查和调试上下文。
- `[-]` Prompt template 管理；缺完整的步骤/模式变体和模板版本。
- `[ ]` 生成前展示最终 provider payload、全部参考图和预计费用。
- `[ ]` 风格库及用户自定义风格。
- `[ ]` 模型 capability 驱动参数：尾帧、参考数量、时长、分辨率、音频、取消和恢复。

### 3.5 Keyframe、Video Take 与版本

- `[x]` 关键帧生成只新增候选；显式选用同步正式帧并创建/批准不可变 revision。
- `[x]` 每次视频生成只新增 `VideoTake`，不得自动覆盖当前选择。
- `[x]` 显式“采用 take”，同一镜头只能有一个正式选择，并允许切换回来。
- `[x]` 已选 take 与候选 take 在 UI 中清晰区分。
- `[ ]` 显式废弃、恢复、比较和人工上传 take。
- `[x]` `ArtifactRevision`、`ArtifactSelection`、`InputFingerprint`。
- `[x]` `current / stale / missing / blocked` 产物时效。
- `[x]` 上游变化只标 stale，不删除、覆盖或自动付费重做。

### 3.6 任务、批次与恢复

- `[x]` 持久异步任务、进度、成功/失败/取消请求和任务中心。
- `[-]` 图片/视频/音频执行器已分离；缺少完整的模态并发和容量策略。
- `[x]` `GenerationBatch` 与全有或全无 admission。
- `[ ]` 批次结果固定分区：succeeded/failed/blocked/skipped。
- `[-]` `requested_ids` 语义：批量请求已强制非空且逐项记录；“省略=只补缺失”快捷模式待 UI 接入。
- `[x]` 生成提交 idempotency key 和在途任务冲突检查。
- `[x]` `ProviderExecutionCheckpoint`：submit、remote job、poll、download、settlement。
- `[x]` 服务重启后有条件续跑，禁止无条件重新提交。
- `[x]` Provider 已成功但下载失败时只重试下载，不重复计费。
- `[ ]` 结构化失败码、可重试性和修复动作。
- `[ ]` 项目事件 SSE 与任务状态刷新恢复。

### 3.7 成本与用量

- `[x]` 生成前费用估算与明确确认；只读取显式 `models.params.pricing`，不猜价。
- `[x]` 项目预算、预计费用、已花费用和剩余额度。
- `[x]` Provider call 级用量账本。
- `[ ]` estimate → pending → actual → settlement → adjustment/refund。
- `[-]` 多币种和视频秒数已支持；token/图片/音频计费待扩展。
- `[x]` 任务、来源、输入、响应和失败原因深链。
- `[ ]` KPI、趋势、费用构成和异常关注。
- `[ ]` Agent 调用成本归属。

### 3.8 音频、编辑与交付

- `[-]` 后端已有生成音频基础，但没有完整 TTS 产品工作流。
- `[ ]` 角色声音、参考音频、独立 TTS 和视频原生音轨分层。
- `[x]` 字幕轨、旁白轨、音乐/SFX、基础音量、视频原生音轨与 ducking。
- `[x]` 持久化 `EditRevision` 和中立 timeline/EDL。
- `[x]` 镜头顺序、裁切、时长、转场和轨道编辑。
- `[x]` 确定性后端渲染和可复现输入 manifest。
- `[x]` 最终 MP4、SRT 字幕和生产 manifest。
- `[—]` NLE adapter 明确不做。
- `[x]` 项目版本、已选 take、实际时长在编辑与导出中使用同一 EditRevision。

### 3.9 Provider、端点与生态

- `[x]` Provider/Model CRUD、默认模型和生成时选择。
- `[ ]` 项目级模型 pinning 与可复现快照。
- `[x]` 自定义声明式 endpoint：显式提交、轮询、状态映射和结果提取；不猜测模型、路径或地域。
- `[x]` 离线响应验证、真实请求预览和需明确确认的连接测试。
- `[x]` ComfyUI API workflow 导入、节点绑定、能力推导、执行和候选产物入库。
- `[x]` 可审阅的 endpoint market；第三方源显示信任、版本与凭证去向，安装为独立本地副本。
- `[-]` endpoint JSON 模板可发布/安装且本地副本可修改；专用文件导入/导出和上游更新冲突合并暂未产品化。

### 3.10 Agent 与自动化

- `[x]` 项目 Agent 有持久会话和消息，并读取项目研究、`WorkflowPlan` 和分层记忆提供上下文建议。
- `[x]` Agent 系统合同先读 `WorkflowPlan`，将 `next_action` 作为唯一允许推进的生产动作。
- `[x]` MCP 写操作通过确定性 production/memory/integration service，不允许模型直接改库。
- `[x]` 正式批准与真实外部调用要求显式 confirm；生成/endpoint UI 在真实调用前再次确认。
- `[x]` 用户记忆与项目记忆具备类型、标签、来源、置信度、置顶、搜索和归档，并明确不替代正式项目数据。
- `[ ]` 会话分支、断线续传、消息幂等和子 Agent 事件折叠。
- `[x]` 内嵌 Agent 和外部 Agent 共用 `WorkflowPlan`、revision、artifact、integration 和 memory 状态合同。
- `[x]` MCP/API Key 自动化入口；Token 只显示一次、服务端只存哈希、scope 可撤销，Web 代理只对精确 MCP 路径放行 Bearer 并保留其他 API 的登录/内部密钥边界。

### 3.11 安全、版本升级与运维

- `[—]` 组织、RBAC、多租户和客户评论明确不做。
- `[x]` 批准、采用、生成和交付的项目级审计事件。
- `[ ]` 下载 token、路径安全和交付权限继承。
- `[ ]` 项目 schema version、幂等迁移、迁移前备份和修复报告。
- `[ ]` 迁移失败项目只读打开并阻断生成。
- `[ ]` 示例项目、首次引导和不消耗额度的产品演示。

## 4. LinglongLab 要做得更好的部分

### 4.1 LinglongLab+：商业广告智能

- 研究来源、findings、creative directions 与生产链持续关联。
- 商品卖点、目标人群、禁用表达和 claim evidence 成为正式生产输入。
- Agent 不能声称看过未提供的资产或完成未执行的研究。
- Creative direction、shot plan 和最终交付之间可追溯。

### 4.2 LinglongLab+：确定性品牌后期

- Logo、CTA、价格、Legal、End Card 使用确定性模板渲染，而非依赖生成模型画字。
- 品牌字体、颜色、安全区和平台规格成为可验证规则。
- 同一生成素材能输出不同比例、平台和市场版本。

### 4.3 LinglongLab+：机器可读 QA

- 检查 missing/stale take、黑帧、静帧、时长、分辨率、字幕安全区、音量峰值、CTA/Legal presence。
- QA 问题带资源定位、严重级别、修复动作和人工豁免记录。
- 有阻断问题时不能产生“Final”交付，只能产生 Preview。

### 4.4 LinglongLab+：广告交付可追溯性

- 交付清单记录批准版本、采用素材、费用、QA 和输出文件。
- 不引入组织、RBAC、多租户或客户评论模型。

### 4.5 LinglongLab+：更细的镜头准备

- 保留并统一现有素材/对白候选确认、动作节拍、摄影语义、连续性上下文和 readiness。
- 让这些状态进入 `WorkflowPlan`，而不是散落在页面判断中。
- 首/关键/尾帧组合继续作为 LinglongLab 的高控制力能力。

## 5. 实施顺序与验收门

### Slice 1 — Video Take 显式选择（完成）

目标：消除“最新生成自动覆盖正式视频”的数据完整性风险。

验收条件：

- [x] 生成成功只新增候选 take，`Shot.generated_video_file_id` 不自动变化。
- [x] 已有选择在新生成成功后保持不变。
- [x] 用户可以在镜头 UI 明确采用任一 take。
- [x] 切换采用项时，旧 take 保留并可再次选择。
- [x] 同一镜头最多一个 task link 为 `accepted`。
- [x] 刷新页面后选择仍存在。
- [x] 后端服务测试和 Web TypeScript 检查通过。

当前进展（2026-09-24）：

- [x] 生成持久化已停止自动更新 `Shot.generated_video_file_id`。
- [x] 新产物继续通过 `GenerationTaskLink` 作为候选 take 保留。
- [x] 后端采用动作会锁定同镜头 take、设置唯一正式选择，并把旧选择恢复为候选。
- [x] 镜头工作台显示“候选 / 已采用 / 已废弃”，支持明确采用和切换。
- [x] 服务不变量与 API 接线测试通过；Web TypeScript 检查通过。
- [x] 活跃本地 API/Web 环境完成创建、批准和刷新恢复 smoke test。

### Slice 2 — 不可变 Plan/Keyframe Revision

- `ScriptRevision`、`ShotPlanRevision`、`KeyframeRevision`。
- 批准、采用、来源、输入指纹和回滚。
- 生成任务必须引用明确 revision。

### Slice 3 — Artifact Currency 与 Workflow Plan

- current/stale/missing/blocked。
- 只读 production plan、下一动作、阻断和修复建议。
- UI、Agent 和 API 统一读取。

### Slice 4 — 最小编辑和交付

- EditRevision、timeline、字幕/音频基础轨。
- 确定性渲染、Preview/Final、QAReport、DeliveryManifest。

### Slice 5 — Batch、Cost、Checkpoint

- 整批准入、费用确认、幂等、远端 job checkpoint、重启续跑和下载重试。

当前进展（2026-09-24）：

- [x] 批量视频请求使用全有或全无准入；任一镜头阻断时创建零生成任务。
- [x] 明确定价合同、逐镜头和批次费用估算、付费前确认。
- [x] 单镜头创建接口支持 `Idempotency-Key`，相同请求复用，不同请求返回冲突。
- [x] 在途视频任务冲突进入批次阻断列表。
- [x] Provider checkpoint 持久化执行阶段、外部任务、轮询与下载状态。
- [x] Provider 已完成但下载失败时保存结果，只重试下载，不重新提交生成。
- [x] 视频任务用量账本与项目聚合 API。
- [x] 关键不变量自动化测试通过。
- [x] 活跃 Web 路径已有批量预检、费用确认和项目账本 UI；真实付费提交由部署凭证环境最终验收。

### Slice 6 — ArcReel 高级域

- Reference Video、Grid、角色衍生、双层商品锚点、项目归档。
- 自定义 endpoint、ComfyUI、market、Agent memory、MCP。

当前进展（2026-09-25）：

- [x] 自定义 endpoint 的创建、编辑、离线映射校验、请求预览、显式真实测试和声明式 polling。
- [x] ComfyUI workflow 导入、节点能力识别、语义输入绑定、执行、结果下载和候选产物入库。
- [x] Endpoint market 的本地发布、信任/凭证去向展示和可编辑副本安装；模板拒绝内嵌 secret。
- [x] MCP stateless HTTP 入口、scoped API key、生产/记忆/集成工具与显式确认门。
- [x] 用户/项目两级记忆和项目 Agent 上下文注入。
- [-] 真实第三方 endpoint 的在线验收需要用户提供准确合同、环境变量凭证与额度；自动化测试使用受控 mock transport，不把猜测配置写入产品。

## 6. 决策记录

### 2026-09-24 — 行为复刻，不直接复制 AGPL 实现

ArcReel 仓库采用 AGPL-3.0，并要求修改版 UI 保留显著的 “Powered by ArcReel” 署名和原仓库链接。除非公司确认接受 AGPL 义务或已取得商业授权，本项目只使用公开产品行为、领域概念和一手文档作为规格证据，不复制 ArcReel 具体实现代码。该决策不限制功能对齐。

### 2026-09-24 — 第一垂直切片选择 Video Take

当前视频持久化逻辑在生成完成后直接写入 `Shot.generated_video_file_id`。这违反“生成不等于采用”的生产合同，并会让后续 timeline、交付和 QA 建立在不稳定选择上，因此优先修复。

## 7. 证据与相关文档

- [AI Video × ArcReel 深度审计](research/ai-video-vs-arcreel-audit-2026-09-24.md)
- [ArcReel 一手资料研究](research/arcreel-primary-source-research-2026-09-24.md)
- [LinglongLab Video Production workspace contract](linglonglab-video-production-workspace.md)
- [LinglongLab Video Production product design](video-production-product-design.md)

## 8. 每个 Slice 的关闭规则

只有同时满足以下条件，清单才能从 `[>]` 或 `[-]` 改成 `[x]`：

1. 活跃 `/ai-video` UI 可完成操作；
2. 状态持久化且刷新后可恢复；
3. API 和数据合同明确；
4. 不会静默覆盖已批准/已选择产物；
5. 有针对关键不变量的自动化测试；
6. 失败状态对用户可见且有修复路径；
7. 不依赖未确认的模型名、端点或云区域猜测。
