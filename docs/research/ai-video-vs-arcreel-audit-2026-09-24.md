# LinglongLab AI Video × ArcReel 深度产品与工程审计

> 审计日期：2026-09-24  
> 审计对象：LinglongLab 当前工作区中的实际 `/ai-video` 路由，以及本仓库内 `ArcReel/` 快照  
> 结论口径：优先以当前可运行代码为准；README、产品设计稿与 changelog 只作为补充证据，不把“计划”算成“已有”

## 0. 一页结论

这不是两个“AI 视频生成页面”的横向比较，而是两种产品路线的比较：

- **LinglongLab 当前更像“广告创意决策 + 镜头生成工作台”**：研究、创意方向审批、素材/角色/场景/道具结构化、镜头准备、首尾关键帧和视频提示词调试做得更细。
- **ArcReel 更像“AI 视频生产操作系统”**：它围绕状态机、产物时效、版本、批次、恢复、费用和可编辑交付构建控制面，生成模型只是其中一层。
- LinglongLab 最大的差距不是再接几个模型，而是 **生成后的生产闭环缺失**：目前没有正式的 take 选择、持久化时间线、编辑修订、最终合成、QA 和交付清单。
- LinglongLab 当前存在一个高风险完整性问题：**新视频生成成功后会自动覆盖镜头的 `generated_video_file_id`**。虽然历史文件仍可能存在，但“最新生成 = 当前采用”是隐式发生的，违背了“生成不等于采用”的生产系统原则。
- 最值得借鉴的不是 ArcReel 的整套 UI，而是它的十个底层思路：**只读工作流计划、四维状态拆分、产物 current/stale/missing/blocked、显式采用与版本恢复、批次准入、供应商 checkpoint 恢复、下载重试不重复计费、费用预检与实付账本、能力描述而非猜模型名、可编辑交付**。

推荐的产品定位不是“复制 ArcReel”，而是：

> **保留 LinglongLab 在商业广告研究、证据、品牌约束和镜头准备上的优势，补上 ArcReel 式的生产控制面，形成面向商业广告的 AI Video Production OS。**

## 1. 审计方法与成熟度口径

### 1.1 证据优先级

1. 当前活跃路由与后端源码；
2. 数据模型、任务执行和测试；
3. 本地 ArcReel 源码与产品截图；
4. 官方 README、文档和 changelog；
5. 产品设计稿，仅用于识别目标，不计入“已交付”。

### 1.2 状态标记

| 标记 | 含义 |
|---|---|
| ✅ 已验证 | 在当前代码中存在完整路径，或有直接源码证据 |
| 🟡 部分具备 | 有数据/界面/接口的一部分，但关键闭环或语义不完整 |
| 📝 已设计 | 只在产品设计或目标文档中出现 |
| ❌ 缺失 | 当前活跃代码未发现 |
| ❓ 未确认 | 证据不足，不据此下结论 |

### 1.3 重要边界

- LinglongLab 的旧 `/video-production` 路由在当前工作树中已被删除，门户实际指向 `/ai-video`，因此本报告不把旧设计稿当作现有能力。
- ArcReel 的本地目录是独立 Git 仓库快照；本报告按当前快照审计，并对关键能力尽量交叉验证到源码。
- ArcReel 最新正式版为 **v0.31.0（2026-09-23）**；本地 `main` 快照比该标签多 28 个提交。详细证据中凡属 2026-09-24 `main` 新增内容均标为“未发布主分支变化”，不把它算成所有 ArcReel 部署都已具备的稳定能力。
- “有表/有字段”不等于“产品闭环已完成”。例如 LinglongLab 有 `TimelineClip` 模型，但活跃 timeline API 是空占位，前端也明确显示不可编辑，因此仍判定为缺失。
- 本报告不评价各家生成模型的画质，也不猜测或修改任何外部模型 ID、区域或端点配置。

## 2. 产品 DNA：两者首先解决的不是同一个问题

| 维度 | LinglongLab AI Video | ArcReel | 判断 |
|---|---|---|---|
| 首要用户任务 | 从广告研究、素材和脚本进入可生成镜头 | 从小说/剧本/商品材料进入可恢复、可交付的视频项目 | LinglongLab 更“广告决策前置”；ArcReel 更“全流程生产” |
| 核心对象 | Project、Chapter、Shot、Entity、Frame、GenerationTask | Project、Episode/Unit、Storyboard/Grid/Reference Video、Version、Task、Usage、Presentation | ArcReel 的生产与运营对象更完整 |
| 核心护城河方向 | 商业证据、创意方向治理、镜头结构化与提示词控制 | 工作流状态机、版本/时效、任务恢复、费用、交付 | 应组合，不应二选一 |
| 用户心智 | “帮我把广告镜头准备好并生成” | “帮我把整部视频项目生产出来并可恢复/导出” | LinglongLab 的链路终点更早 |
| Agent 角色 | 当前是项目上下文聊天与建议 | 计划驱动的工具执行者，并有持久会话/记忆/外部 Agent 接口 | ArcReel 的 Agent 更接近生产调度器 |
| 交付定义 | 设计稿有 MP4/manifest/QA；当前未落地 | 合成视频、Jianying 可编辑草稿、演示/素材包 | ArcReel 更接近真实交付物 |

## 3. 端到端生产链审计

按 `brief → assets → approved plan → shot → keyframe → take → selected take → edit revision → QA → delivery` 检查：

| 生产节点 | LinglongLab | ArcReel | 关键差异 |
|---|---|---|---|
| Brief / 研究 | ✅ 有 research/preset 入口、sources、findings、creative directions 和批准门 | 🟡 支持源材料、模式和项目规划，但没有同等强度的商业证据与 claim 治理 | **LinglongLab 优势** |
| Assets | ✅ 角色、场景、道具、服装、图片和项目/镜头关联 | ✅ 角色、场景、道具、商品、参考视频、派生图、语音绑定 | ArcReel 类型更广；LinglongLab 镜头关联更细 |
| Approved plan | 🟡 研究方向可批准，但脚本/镜头计划没有不可变修订与正式锁定 | ✅ 正式脚本计划、审核门、修订基线和下游失效 | ArcReel 更能回答“现在按哪版生产” |
| Shot | ✅ 镜头、动作节拍、对白、摄影语义、实体链接、准备状态 | ✅ 分镜/视频单元、角色对白、广告段落类型、时间线编辑 | 两者都有，LinglongLab 的生成前准备更细 |
| Keyframe | 🟡 首/关键/尾帧、多参考模式、任务与文件都有；缺正式 revision/approval | ✅ 分镜图/宫格/图片编辑、版本历史与恢复 | LinglongLab 控制方式灵活；ArcReel 生命周期完整 |
| Take | ✅ 可按镜头生成多个视频文件并查看历史 | ✅ 视频任务、版本、任务状态与费用记录 | 均可生成；ArcReel 管理语义更成熟 |
| Selected take | ❌ 新生成结果隐式写成当前视频；无明确“采用此 take”体验 | ✅ 版本/选择/恢复语义贯穿交付读模型 | **LinglongLab P0 缺口** |
| Edit revision | ❌ 前端明确说明没有持久化 timeline API | 🟡 可编辑脚本/分镜时间线并可合成、出 Jianying；不是完整 NLE | **LinglongLab 生产链在此断裂** |
| QA | ❌ 没有最终交付 QA | 🟡 有审核门、问题/阻断和诊断；未发现完整自动化成片 QA agent | 两边都还有空间，LinglongLab 更弱 |
| Delivery | ❌ 当前无正式渲染、交付包、manifest | ✅ 合成、Jianying 草稿、presentation ZIP、项目 ZIP | **ArcReel 显著领先** |

### 3.1 最早的结构性断点

如果按严格生产合同判断，LinglongLab 最早的结构性问题出现在 **approved plan**：研究方向虽可批准，但脚本、镜头计划、关键帧都没有“不可变修订 + 正式采用 + 输入指纹”。这意味着下游生成无法稳定回答：

- 这个视频是基于哪版脚本、哪版镜头参数、哪张正式关键帧生成的？
- 上游发生变化后，这个视频是 current 还是 stale？
- 旧产物能否继续使用，还是必须重做？
- 谁在什么时候明确采用了哪一版？

最危险的即时问题则在 **selected take**：新 take 自动成为当前 take，选择权没有被建模。

## 4. 详细能力矩阵

### 4.1 项目创建、研究与输入

| 能力 | LinglongLab | ArcReel | 差距/建议 |
|---|---|---|---|
| 广告研究入口 | ✅ research 与 preset 双入口 | ❌ 未见同等结构化研究门 | 保留为 LinglongLab 差异化核心 |
| 来源、发现、创意方向 | ✅ 结构化保存，方向需批准才能进入生产 | 🟡 接受源材料并由 Agent 规划，但研究证据不是一等对象 | 不要被 ArcReel 的“全流程”稀释这层治理 |
| 原始材料导入 | 🟡 当前以项目文本/文件为主 | ✅ `.txt/.md/.docx/.epub/.pdf`，并支持项目归档导入 | LinglongLab 应补统一 ingest、解析状态和来源定位 |
| 长内容拆集 | 🟡 Chapter 存在，可抽取/拆镜头 | ✅ Episode planning、范围账本、增量规划 | 引入 source range + episode/segment ledger |
| 广告模式 | ✅ 产品意图原生偏广告 | ✅ 有 ad mode、商品参考、目标时长、广告镜头类型 | ArcReel 的 ad mode 可参考，但其证据治理弱于 LinglongLab |
| 叙事/剧集模式 | 🟡 Chapter/角色/场景可支撑，但没有明确模式合同 | ✅ narration/drama/ad 明确分流 | 若 LinglongLab 目标仍是广告，不必全量复制 |
| 生成模式 | 🟡 首/尾/关键帧和 text-only 等参考组合 | ✅ storyboard/reference-video；storyboard 下可选 grid | LinglongLab 的“参考组合”与 ArcReel 的“工作流模式”属于不同层，应同时建模 |
| 目标时长约束 | 🟡 镜头 duration 有，但项目级预算/时长闭环弱 | ✅ 项目目标时长进入规划与成本 | 增加项目/广告级时长预算与误差指标 |
| 项目导入导出 | ❌ 无全历史 ZIP | ✅ 项目 ZIP 导入导出、迁移和自愈 | P1，兼具备份、协作和可移植性价值 |

### 4.2 脚本、计划与变更控制

| 能力 | LinglongLab | ArcReel | 差距/建议 |
|---|---|---|---|
| 脚本抽取/优化/拆镜头 | ✅ 多个专用链和异步任务 | ✅ Agent/工作流规划与脚本审核 | LinglongLab 的生成前智能更丰富 |
| 抽取候选确认 | ✅ 素材和对白候选有 pending/linked/ignored 或 accepted/ignored | 🟡 有审核门，但 LinglongLab 的候选确认更显式 | **LinglongLab 优势，应统一成通用 review item** |
| 脚本正式版 | ❌ 当前对象可变，无 ScriptRevision/lock | ✅ 正式计划与草稿分离、revision 基线 | P0：任何付费生成前必须有稳定 basis |
| 镜头计划修订 | ❌ 无不可变 ShotPlanRevision | ✅ 修改、审核、重规划会驱动下游时效 | P0 |
| 局部修改 | 🟡 可改单镜头，但无法可靠计算受影响下游 | ✅ changed-only prompt generation，未变部分保留 | 引入 field-level input fingerprint / dependency graph |
| 失效传播 | ❌ 无统一 stale 语义 | ✅ 旧产物保留但标 stale，不自动重生成 | 这是 ArcReel 最值得借鉴的思路之一 |
| 正式/草稿隔离 | 🟡 研究有状态；镜头/提示词/帧缺少统一草稿区 | ✅ formal、draft、pending authoring 等语义更清楚 | 防止半成品污染正式生产链 |
| 回滚 | ❌ 无通用版本恢复 | ✅ 多类资源版本查询与恢复 | P1；先覆盖 plan/keyframe/take/edit |

### 4.3 素材、角色一致性与关键帧

| 能力 | LinglongLab | ArcReel | 差距/建议 |
|---|---|---|---|
| 角色/场景/道具 | ✅ | ✅ | 基础能力相当 |
| 服装时间线 | ✅ 有 costume timeline/分析 | 🟡 角色状态和衍生资产丰富 | LinglongLab 的服装语义是广告/剧情连续性优势 |
| 商品/品牌参考 | 🟡 可通过 prop/assets 表达，缺专用 Product 合同 | ✅ Product、商品参考、商品锚定镜头 | LinglongLab 应把 Product 从普通 prop 升为一等对象 |
| 参考视频 | 🟡 可把文件作为生成参考，但无完整 reference-video 工作流 | ✅ 导入、单元切分、直生视频、时效与恢复 | 若客户常以样片复刻节奏，这是 P1 |
| 宫格分镜 | ❌ | ✅ 2×2 至 5×5、拆分、版本和任务 | 适合低成本批量视觉探索；不是所有广告都需要 |
| 首/中/尾帧组合 | ✅ first/key/last 及组合参考模式 | 🟡 以 storyboard/grid/reference-video 为主 | **LinglongLab 的控制粒度更强** |
| Prompt preview | ✅ 有映射、guidance、debug、quality 等预览 | ✅ 有实际 payload、样式模板、36 种风格 | LinglongLab 应补“最终发送 payload”与模板版本 |
| 图片指令编辑 | 🟡 可重生成、提示词调整；未见正式 edit history | ✅ 图像指令编辑和版本历史 | P1 |
| 关键帧采用 | 🟡 任务链接可标记采用/废弃，但缺一等 revision 与清晰 UI | ✅ 版本/选择进入读模型与交付 | 统一成 AssetRevision + Selection，不要靠 tags |
| 文件溯源 | ✅ FileUsage、任务链接、项目/镜头关联 | ✅ manifest、版本和 basis | LinglongLab 已有基础，应升级而不是重建 |

### 4.4 视频生成、take 管理与批次

| 能力 | LinglongLab | ArcReel | 差距/建议 |
|---|---|---|---|
| 单镜头生成 | ✅ | ✅ | 基础相当 |
| 多镜头批量生成 | 🟡 UI 可多选并发起，但无正式批次对象和结果分区 | ✅ generation batch，有 admission、requested IDs、轮询和结果分区 | P0/P1 之间，取决于生产规模 |
| 生成历史 | ✅ 任务/文件可保留多个结果 | ✅ 任务、版本、费用、输入和响应更完整 | LinglongLab 要把“历史文件”升级为“take 集合” |
| 显式采用 take | ❌ | ✅/🟡 ArcReel 有选中版本与恢复链路 | **立即修复：生成成功不得自动采用** |
| 废弃但保留 | 🟡 task link 有 accepted/todo/rejected，但视频 UI 未接通 | ✅ 保留付费历史，旧产物不因重生成被抹掉 | 接通现有 link 语义可较快补齐 |
| 批次原子准入 | ❌ | ✅ 先检查整批条件，不让半批意外开始付费 | P1；对高成本视频尤其重要 |
| 结果分区 | ❌ | ✅ succeeded/failed/blocked/skipped | 让 UI、Agent 和重试都使用同一语义 |
| 指定目标重生成 | 🟡 以 UI 选中镜头为主，API 合同不统一 | ✅ 非空 requested_ids = 显式目标；省略 = 仅缺失；空列表非法 | 非常值得直接采用这一 API 语义 |
| 取消 | ✅ 支持 cancel flag/状态 | 🟡 ArcReel 通常只取消排队任务；运行中结果仍保存 | LinglongLab 需要明确 provider 能力边界和实际退款语义 |
| 幂等性/去重 | 🟡 有任务记录，但重复点击仍可创建付费任务 | ✅ 多处有幂等/恢复/准入防护 | P0：至少对 submit 使用 idempotency key |

### 4.5 任务系统、恢复与可靠性

| 能力 | LinglongLab | ArcReel | 差距/建议 |
|---|---|---|---|
| 异步任务表 | ✅ pending/running/streaming/succeeded/failed/cancelled、进度、错误、结果 | ✅ 持久队列与更细的 provider 状态 | LinglongLab 有良好起点 |
| 不同模态队列/并发 | 🟡 executor registry 有，但未见完整用户级容量与模态队列治理 | ✅ 文本/图片/视频/音频并发和持久化队列 | P1 |
| 重启恢复 | 🟡 DB 任务可保留，但没有完整 provider checkpoint 恢复合同 | ✅ 启动恢复、上游 job ID、恢复失败分类 | **生产可靠性核心差距** |
| 供应商已完成但下载失败 | ❌ 未见独立 download-only retry | ✅ 可只重试下载，不重新提交、不重复计费 | P0/P1，高成本场景价值很大 |
| Provider checkpoint | 🟡 某些集成有外部 job 轮询，但没有统一抽象 | ✅ submit/poll/download/resume 进入统一生成上下文 | 应抽象为 `ProviderExecutionCheckpoint` |
| 失败分类 | 🟡 error message/result payload | ✅ 机器码、可重试性、恢复/过期/端点变化等分类 | P1；决定自动恢复和客服诊断能力 |
| SSE / 项目事件 | 🟡 前端主要轮询；部分任务状态接口 | ✅ 项目事件与 SSE 驱动刷新 | 可减少大工作台轮询复杂度 |
| 任务诊断 | 🟡 日志存在，用户界面弱 | ✅ 设置/用量/任务诊断更系统 | P1 |
| 断点后费用结算 | ❌ | ✅ resume 后账本回填/结算 | 与恢复和成本账本必须一起做 |

### 4.6 成本、配额与运营可观测性

| 能力 | LinglongLab | ArcReel | 差距/建议 |
|---|---|---|---|
| 生成前费用预估 | ❌ | ✅ 按实际模型、时长、音频档位、自定义价格估算 | P0/P1：视频生成需确认成本 |
| 项目预算 | ❌ | 🟡 UI 展示预计/已花/剩余，具备项目成本心智 | 建议增加软预算与超限门 |
| 实际调用账本 | ❌ | ✅ 输入、响应、任务、来源、token/秒数、币种、结算状态 | 不应只做 dashboard，要先做不可变 ledger |
| 多币种 | ❌ | ✅ | 国际供应商场景需要 |
| 成功率/趋势/构成 | ❌ | ✅ KPI、趋势、构成、需关注记录 | P2，建立在账本正确性之上 |
| 取消/失败计费语义 | ❌ | ✅ 区分取消、失败、provider 实际结算 | 直接影响毛利和客户信任 |
| Agent 成本 | ❌ | ✅ Agent 使用也进入追踪 | LinglongLab 的 Creative Agent 规模化后应纳入 |

### 4.7 编辑、音频、合成与交付

| 能力 | LinglongLab | ArcReel | 差距/建议 |
|---|---|---|---|
| 持久化 timeline | ❌ UI 明确不可用，后端路由为空 | 🟡 有分镜/脚本时间线编辑与合成数据；不是完整专业 NLE | **LinglongLab 最大用户可见缺口** |
| Timeline revision | ❌ | 🟡 版本/项目数据和 presentation basis 可追踪 | LinglongLab 需一等 `EditRevision` |
| TTS | 🟡 有 generated audio 服务，但未形成完整镜头/项目语音工作流 | ✅ 角色语音绑定、分段/整集语音、语速 | P1，广告旁白需单独产品化 |
| 字幕 | ❌ 当前无最终字幕轨道/导出 | ✅ 进入 Jianying 草稿和合成链 | P1 |
| 音乐/SFX | ❌ | 🟡 音频能力存在，但不是专业混音系统 | 先做基础轨道、ducking 和授权元数据 |
| 片头/CTA/Legal overlay | 📝 产品合同中有愿景，当前未落地 | 🟡 可合成，但没有 LinglongLab 所需的广告品牌/法务模板系统 | **这里应该做出 LinglongLab 自己的优势，而不是照抄** |
| 最终 MP4 | ❌ | 🟡 有 FFmpeg 直接合成路径，但不同创作/生成模式支持范围不一致 | P0/P1：没有交付就不是完整生产产品 |
| 可编辑交付 | ❌ | ✅ Jianying 草稿 ZIP | ArcReel 把“可继续编辑”视为交付，而不只是一条 MP4 |
| Presentation bundle | ❌ | ✅ 视频/音频版本的 presentation ZIP | 对客户 review 与归档很有价值 |
| Delivery manifest | 📝 设计稿提出，当前无 | 🟡 ArcReel 有项目/版本信息，但不完全等同广告交付 manifest | LinglongLab 应做得更严格：输入、采用版本、模型、费用、QA |
| 交付 QA | ❌ | 🟡 审核门和诊断，不是完整自动 QA | 这是双方都未完全解决的机会 |

### 4.8 Provider、模型与扩展性

| 能力 | LinglongLab | ArcReel | 差距/建议 |
|---|---|---|---|
| Provider/Model 管理 | ✅ 内置 provider、模型 CRUD、默认模型 | ✅ 多供应商、多模态、项目级 override | LinglongLab 基础具备 |
| 项目级模型 override | 🟡 主要为全局/default 和生成时选项 | ✅ 项目可固定模型配置 | 对可复现性很重要 |
| 能力声明 | 🟡 模型类别和部分选项存在 | ✅ 以 capability 决定可用模式，不靠模型名猜测 | 与 LinglongLab 的配置规则完全一致，建议强化 |
| 自定义端点 | ❌ | ✅ 自定义 endpoint、价格、测试、请求预览 | P2；企业私有模型接入价值高 |
| Endpoint marketplace | ❌ | ✅ | 只有在端点生态变大后才值得做 |
| ComfyUI workflow 导入 | ❌ | ✅ 图片/视频 workflow、节点绑定、预览与测试 | 对高级创作者有价值，不应排在生产闭环之前 |
| 请求实际 payload 预览 | 🟡 prompt preview 强，但不等于最终 provider payload | ✅ 可预览真实请求 | 对调试、审计、私有部署很重要 |
| 外部 Agent/MCP 工作流 | ❌ | ✅ 通过 workflow plan 和工具合同开放 | 可作为 LinglongLab 后续自动化层 |

### 4.9 Agent 能力

| 能力 | LinglongLab | ArcReel | 差距/建议 |
|---|---|---|---|
| 持久会话 | ✅ session/message 入库 | ✅ | 基础相当 |
| 上下文聊天 | ✅ 最近消息 + 项目研究上下文 | ✅ | LinglongLab 已有 MVP |
| 工具执行 | ❌ 当前 Agent 只回答/建议，不修改项目 | ✅ 通过 workflow plan 和细粒度工具推进 | 不要直接给 Agent 自由写库，应先有受控动作合同 |
| 只读计划查询 | ❌ | ✅ `get_workflow_plan` 不产生副作用 | **最应先复制的 Agent 架构思路** |
| 下一动作约束 | ❌ | ✅ Agent 只执行 `next_action` | 显著降低 Agent 越权与状态错乱 |
| 子 Agent 分工 | ❌ 项目 Agent 未做生产子 Agent 编排 | ✅ 规划/角色/分镜等专长 Agent | 在控制面稳定后再引入 |
| 记忆与分支 | 🟡 有消息历史，无正式长期记忆/分支 | ✅ 持久记忆和会话能力更成熟 | P2 |
| 外部 Agent | ❌ | ✅ | 适合 API-first 自动化客户 |
| 事实/证据边界 | ✅ 系统提示明确不能声称未提供的研究/资产 | 🟡 更偏项目执行 | **LinglongLab 优势，应保留为所有写操作的 policy layer** |

### 4.10 安全、多人协作与数据治理

| 能力 | LinglongLab | ArcReel | 差距/建议 |
|---|---|---|---|
| Web 鉴权 | ✅ NextAuth/代理链有用户身份 | 🟡 自托管与管理员/API key 取向 | LinglongLab 有企业入口优势 |
| 项目归属/租户隔离 | ❌ AI Video 核心表未见 user/org/tenant 字段，API 也未按转发身份过滤 | ❌ 官方明确是单管理员实例，不提供多人隔离 | **LinglongLab 若仅单租户部署是已知边界；一旦多人共用则是上线前 P0 安全问题** |
| 审计日志 | 🟡 任务和文件溯源有，用户动作审计不足 | 🟡 版本/任务/费用记录丰富，但不是完整企业审计 | LinglongLab 应记录审批、采用、回滚和导出主体 |
| 下载授权 | 🟡 依赖现有文件服务/代理 | ✅ 有下载 token、路径安全等防护 | 交付前补齐短期签名和权限继承 |
| Schema 迁移 | 🟡 常规应用迁移存在，但项目包/内容 schema 升级产品化不足 | ✅ 项目 schema 版本、迁移、备份、修复、诊断 | ArcReel 把数据长寿命当作产品能力 |
| i18n | ✅ 中/英 | ✅ 中/英/越 | 非核心差距 |
| Onboarding demo | ❌ 未见完整可操作示例项目 | ✅ demo/read-only onboarding | P2，能显著降低复杂工作台学习成本 |

## 5. ArcReel 有、LinglongLab 当前没有的功能清单

### P0：不补会直接影响生产可信度或数据安全

1. **显式 take 采用**：生成与采用分离；不能让最新结果自动替换当前结果。
2. **脚本/镜头计划/关键帧的不可变 revision 与 approval**：所有付费生成必须引用明确 basis。
3. **产物时效状态**：至少支持 `current / stale / missing / blocked`，上游变更不能静默污染下游。
4. **持久化编辑修订与基础成片导出**：没有 `EditRevision → Render → Delivery`，产品链路无法闭合。
5. **用户/组织/项目数据隔离**：现有登录身份必须进入 AI Video 查询和写入边界。
6. **生成提交幂等**：避免重复点击、网络重试或进程重启造成重复付费。

### P1：规模化生产所需

1. Generation Batch、整批 admission、分区结果与按失败目标重试。
2. Provider checkpoint、重启恢复、download-only retry。
3. 生成前费用预估、不可变实际用量账本和项目预算。
4. 版本查询、比较、恢复；先覆盖关键帧、take 和 edit。
5. TTS、字幕轨、基础音乐/音效与 Jianying/其他可编辑交付。
6. Project ZIP 导入导出、数据迁移与诊断。
7. 项目级 provider/model pinning 和最终请求 payload 记录。
8. Product 一等对象与广告商品锚定。
9. Reference-video 工作流，若真实客户需求中样片复刻占比较高。

### P2：生态和高级创作者能力

1. 宫格分镜与自动拆分。
2. 自定义 endpoint、请求预览和 endpoint marketplace。
3. ComfyUI workflow 导入与节点绑定。
4. Agent 长期记忆、分支会话、专长子 Agent。
5. 外部 Agent/MCP 自动化。
6. 费用趋势/构成 dashboard、onboarding demo、更多语言。

## 6. ArcReel 有，而 LinglongLab 更缺的是哪些“思路”

### 6.1 状态不是一个 `status` 字段，而是四条正交轴

ArcReel 实际上把状态拆成：

1. **Workflow step**：项目走到哪一步；
2. **Task/queue state**：本次执行是否排队、运行、成功、失败；
3. **Provider checkpoint**：外部服务是未提交、已提交、轮询中、已完成待下载；
4. **Artifact currency**：结果相对当前输入是 current、stale、missing 还是 blocked。

LinglongLab 目前主要有第 2 条，部分有第 1 条，几乎没有第 3、4 条。把它们揉在一个 `status` 里会导致：任务成功但产物已过期、provider 已完成但下载失败、旧产物仍可用但不是当前版等情况无法表达。

### 6.2 “生成了”不等于“采用了”

生成操作只能新增候选产物；只有用户或受控策略的明确动作才能改变正式选择。建议所有可生成资产统一为：

```text
Artifact
  └── Revision/Take 1..N
        ├── basis/input_fingerprint
        ├── generation_task_id
        ├── provider_checkpoint
        ├── currency
        └── lifecycle_status

Selection
  ├── selected_revision_id
  ├── selected_by
  ├── selected_at
  └── reason
```

这比在 `Shot` 上放一个随生成自动变化的 `generated_video_file_id` 更安全，也使回滚、审计和交付可实现。

### 6.3 工作流计划必须是只读函数

ArcReel 的 `workflow_plan` 是 UI、Agent 和自动化共同使用的“下一步真相”，查询本身不产生副作用。它回答：

- 当前步骤、门和阻断；
- 哪些产物缺失/过期；
- 下一动作及其参数；
- 哪些 requested IDs 被准入；
- 是否需要用户确认。

LinglongLab 当前把大量判断散落在 `ChapterStudio`、readiness service 和各个 API 中。建议先做一个只读 `GET /projects/{id}/production-plan`，不要先让 Creative Agent 获得自由写能力。

### 6.4 上游变化应“标过期”，而不是自动重做或删除

旧产物可能已付费、可能仍被客户喜欢、也可能仍可用于内部预览。正确语义是：

- 保留历史；
- 根据 input fingerprint 判断 current/stale；
- 明确展示影响范围；
- 由用户选择是否重生成；
- 正式交付默认只接受 current，例外必须显式豁免。

### 6.5 批次先准入，后花钱

批量视频生成不能“能跑几个先跑几个”，否则用户以为请求了 20 个镜头，实际付费 13 个，剩余 7 个因缺关键帧失败。ArcReel 的启发是：

- 先对全批执行 admission；
- 返回预计费用、可执行项和阻断项；
- 让用户选择全有或全无，或明确允许部分执行；
- 执行结果固定分为 succeeded/failed/blocked/skipped。

### 6.6 Provider 能力不能靠模型名猜

供应商层应声明：是否支持首帧、尾帧、多参考、音频、最大时长、异步 job、取消、恢复、幂等、实际计费回执等。业务层只依赖 capability，不根据字符串判断模型。这一点也符合 LinglongLab 仓库对外部 API 配置的治理规则。

### 6.7 “恢复”是正式执行路径，不是异常补丁

视频任务要持久化 submit request hash、provider job ID、poll checkpoint、download state 和 billing settlement key。进程重启后，应从 checkpoint 决定继续轮询、仅下载、还是安全失败；绝不能默认重新提交。

### 6.8 成本是生产状态，不是报表装饰

成本系统应分成：

- preflight estimate；
- authorization/用户确认；
- pending ledger；
- provider actual；
- settlement；
- adjustment/refund。

只有这样，批次、恢复、取消、失败和供应商回执才有一致语义。趋势图和 KPI 是最后一层。

### 6.9 可编辑交付本身就是产品价值

商业视频很少一次生成即最终。ArcReel 输出 Jianying 草稿的思路值得借鉴，但 LinglongLab 不应只绑定一个编辑器。建议先定义中立的 `EditDecisionList/TimelineRevision`，再输出：

- MP4 preview/final；
- 字幕文件；
- 素材包；
- Jianying 或其他 NLE adapter；
- machine-readable delivery manifest。

### 6.10 迁移与诊断是长期生产产品的一部分

项目数据会跨版本存活数月或数年。项目 schema 版本、迁移预检、备份、修复报告和只读诊断不是“开发工具”，而是客户资产保护能力。

## 7. LinglongLab 已经比 ArcReel 更强或更值得坚持的部分

1. **研究与生产之间有批准门**：sources、findings、creative directions 不是一段聊天文本，而是结构化状态。
2. **Agent 有事实边界**：不能在没有内容时声称看过资产或完成过外部研究，这对商业 claim 和品牌安全很重要。
3. **镜头准备更细**：素材/对白抽取候选、显式确认与忽略、实体存在性、动作节拍、摄影参数、连续性上下文和 readiness 都比“直接生成”更接近可控广告制作。
4. **首帧/关键帧/尾帧组合灵活**：这能适配更精确的 product reveal、motion continuity 和 end card 需求。
5. **提示词决策可解释性更强**：guidance、mapping、decision/reason 等已有基础，可发展为“为什么这次生成使用这些信息”的审计层。
6. **面向商业广告的潜在终局更清晰**：品牌 overlay、CTA、legal、delivery manifest 和 QA 虽未落地，但方向比 ArcReel 的通用创作流程更贴近企业交付。
7. **能与 LinglongLab 其他产品入口共存**：Image、Gaming Playable 和 AI Video 可共享客户身份、品牌资产与商业工作流，这是独立 ArcReel 很难复制的分发和数据优势。

## 8. 不建议直接照搬 ArcReel 的部分

1. **不要把通用长视频/小说生产当成 LinglongLab 主线**。如果核心客户是广告团队，narration/drama 的复杂度会稀释商业交付优势。
2. **不要先做 endpoint marketplace 或 ComfyUI，再补生产闭环**。它们会扩大组合爆炸，却不能解决选择、版本、交付和费用可信度。
3. **不要复制其完整 UI 信息密度**。ArcReel 的三栏工作台、阶段轨道和成本常驻很有价值，但 LinglongLab 当前 `ChapterStudio` 已经复杂，应先收敛信息架构。
4. **不要把 Agent 直接变成自由写库的“万能助手”**。应先有 production plan、受控 action、approval 和 idempotency。
5. **不要把 Jianying 当作唯一交付格式**。它适合中国市场，但需要中立 timeline 模型和 adapter 架构。
6. **不要误以为 ArcReel 已解决完整成片 QA**。它有审核门、阻断和诊断，但本次审计未发现覆盖品牌、字幕安全区、音量、黑帧、法务文字、时长等的统一机器可读最终 QA 系统。
7. **不要照搬其部署/许可证假设**。ArcReel 是自托管开源项目；若复用代码而非借鉴思路，需要单独进行 AGPL 和商业合规评估。本报告不是法律意见。

同时必须看到 ArcReel 自己的明确边界：

- 当前按**单管理员账户**设计，没有多人协作与 RBAC；因此它并不是企业多租户治理的现成答案。
- 内建 FFmpeg 成片能力**不覆盖所有模式**：官方文档把不同路线分流到内建合成、Jianying 草稿或下载片段后期。
- 独立 TTS 的 Web UI 主要覆盖旁白/解说；广告配音按官方流程在导出后完成。
- 运行中的任务不能通过普通取消动作中断；重启恢复也只有在保存了远端 job ID 且供应商支持续查时成立。
- Project ZIP 不包含供应商配置、任务/费用、Agent 会话与记忆，不是完整站点备份。
- 官方未提供可复现的跨模型质量、成功率、平均成本或速度 benchmark；不能仅凭功能广度推断实际生成质量。

## 9. 建议的 LinglongLab 目标架构

```text
Commercial Intelligence
  Research → Evidence → Creative Direction → Brand/Product/Claim Rules
                         │ approved
                         ▼
Production Contract
  ScriptRevision → ShotPlanRevision → KeyframeRevision → Take → Selection
         │                  │                 │             │
         └──────────── input fingerprint / currency ───────┘
                         │
                         ▼
Execution Control Plane
  Read-only WorkflowPlan → Admission → Batch → Task → ProviderCheckpoint
                  │                         │            │
                  └──────── Cost estimate / Usage ledger ┘
                         │
                         ▼
Post & Delivery
  EditRevision → Render → QA Report → Delivery Manifest → MP4/NLE/Assets
```

### 9.1 建议的一等对象

| 对象 | 最小职责 |
|---|---|
| `ScriptRevision` | 保存不可变脚本文本、来源范围、审批状态 |
| `ShotPlanRevision` | 保存镜头定义、动作、摄影、对白和引用资产 |
| `ArtifactRevision` | 统一图片/视频/音频版本、basis、来源任务 |
| `ArtifactSelection` | 明确正式采用版本及主体/时间/原因 |
| `InputFingerprint` | 判断产物是否相对当前上游输入过期 |
| `WorkflowPlan` | 无副作用地给出步骤、门、问题、下一动作 |
| `GenerationBatch` | 记录请求集合、准入、费用确认、结果分区 |
| `ProviderExecutionCheckpoint` | 保存外部 job、轮询、下载和恢复状态 |
| `UsageLedgerEntry` | 保存估算、pending、actual、settlement |
| `EditRevision` | 保存 timeline/EDL 的不可变修订 |
| `QAReport` | 保存自动检查、人工豁免与阻断项 |
| `DeliveryManifest` | 固化最终采用版本、模型、费用、QA 与输出文件 |

## 10. 推荐实施顺序

### 0. 立即止血：生成结果不再隐式采用

- 将视频生成成功改为只创建 take；
- 不自动更新正式 selection；
- 在镜头 UI 增加“采用、预览、废弃、比较”；
- 迁移现有 `generated_video_file_id` 为初始 selection，保留兼容读取；
- 为采用动作记录用户、时间和原因。

### 1. 第一个完整垂直切片：从批准镜头到可追溯 take

一次性打通：

```text
ShotPlanRevision approved
  → KeyframeRevision generated/selected
  → VideoTake generated
  → Take explicitly selected
  → basis & currency visible
  → history/rollback verified
```

这比先扩模型或重做工作台 UI 更能建立生产可信度。

### 2. 关闭用户链路：最小编辑与交付

- 持久化 `EditRevision`；
- 镜头顺序、裁切、时长、基础音频/字幕轨；
- 后端确定性渲染；
- MP4、字幕、素材 manifest；
- 最小 QA：缺失镜头、过期产物、时长、分辨率、黑帧/静帧、音频峰值、CTA/legal presence。

### 3. 建立生产控制面

- 只读 `WorkflowPlan`；
- current/stale/missing/blocked；
- dependency fingerprint；
- UI、Agent、API 共享同一 next action；
- 上游修改只标记影响，不自动重生成。

### 4. 规模化与成本可信度

- batch admission、idempotency、结果分区；
- provider checkpoint 和重启恢复；
- download-only retry；
- 费用预估、确认、实际账本和项目预算。

### 5. 扩展生态

- 项目 ZIP 与 schema migration；
- project model pinning、自定义端点；
- reference-video、grid；
- NLE adapters；
- 受控 Agent 工具、长期记忆和外部自动化。

## 11. 建议“采用 / 延后 / 不采用”清单

| ArcReel 思路/功能 | 建议 | 原因 |
|---|---|---|
| Workflow plan + next action | 立即采用 | 同时解决 UI、Agent、API 状态分裂 |
| Artifact currency | 立即采用 | 是增量生产和可信交付的基础 |
| 显式 selection + version restore | 立即采用 | 当前已有隐式覆盖风险 |
| Provider checkpoint/resume | 立即采用 | 高成本、长耗时任务必须可恢复 |
| Cost preflight + ledger | 立即采用 | 控制客户预期和产品毛利 |
| Editable delivery | 立即采用思想，分阶段实现 | 商业视频必然需要人工收口 |
| Project ZIP/migration | 下一阶段 | 生产资产长寿命和可移植性需要 |
| Reference-video | 按客户证据排期 | 对样片复刻很强，但不是所有广告都需要 |
| Grid storyboard | 延后 | 提升探索效率，但不解决当前链路断点 |
| Custom endpoints/ComfyUI | 延后 | 先把核心生命周期和安全做好 |
| Endpoint marketplace | 暂不采用 | 过早扩大生态维护面 |
| 通用 narration/drama 全套模式 | 暂不采用 | 与广告主线可能冲突，除非战略明确扩张 |
| ArcReel UI 原样复制 | 不采用 | 产品心智和 LinglongLab 现有信息架构不同 |

## 12. 关键风险排序

| 优先级 | 风险 | 影响 |
|---|---|---|
| P0 | 最新生成视频自动成为当前视频 | 错误 take 进入下游或交付，且责任不清 |
| P0 | AI Video 数据无项目级用户/组织隔离 | 多用户环境可能发生越权读取/写入 |
| P0 | 没有正式 revision/basis/currency | 无法证明结果基于哪版输入，修改后可能误用旧产物 |
| P0 | 无编辑、QA、交付闭环 | 产品只能“生成素材”，不能“交付广告” |
| P1 | 缺幂等、批次准入和恢复 | 重复付费、半批执行、重启丢进度 |
| P1 | 缺费用估算和实际账本 | 无法向客户解释支出，也难控制毛利 |
| P1 | 文档仍以 `/video-production` 为 canonical，而活跃实现为 `/ai-video` | 产品合同、验收和实现持续漂移 |
| P2 | Provider/Agent 扩展能力较窄 | 影响生态，但不是当前首要断点 |

## 13. 对管理层最重要的判断

### 13.1 如果只做“ArcReel 已有功能补齐”，会错过什么

会把路线变成通用 AI 视频工具追赶，削弱 LinglongLab 已经出现的独特价值：商业研究可追溯、创意方向批准、资产/对白候选确认、广告镜头准备和品牌交付治理。ArcReel 应被视为生产系统设计参考，而不是产品定位模板。

### 13.2 真正可形成差异化的组合

```text
ArcReel 式生产可靠性
  + LinglongLab 式广告研究与证据治理
  + 确定性品牌/CTA/Legal 后期
  + 机器可读 QA 与 Delivery Manifest
  = 企业级广告生产系统
```

### 13.3 当前最不该做的事情

- 再增加一批模型下拉选项，却没有 selection/version/cost/recovery；
- 给 Agent 自由写项目，却没有只读计划、准入和幂等；
- 做一个看起来完整的 timeline UI，但不持久化 revision、不能稳定渲染；
- 把旧设计文档中的目标能力当成已经交付；
- 为了追 ArcReel 功能数，进入小说/长剧全模式而失去广告主线。

## 14. 验证结果

对 LinglongLab 当前工作树执行了以下验证：

- Web TypeScript：`pnpm --dir apps/web exec tsc --noEmit`，通过。
- AI Video 关键后端测试：`31 passed`，覆盖 generated video service、shot preparation state、task manager 和 project research。

这些测试说明当前基础链路可用，但不会改变本报告对生命周期缺口的判断：测试验证的是现有行为，其中“生成后自动写入当前视频”正是需要重新定义的产品语义。

## 15. 证据索引

### 15.1 LinglongLab 当前实现

- 活跃路由与模块入口：[`apps/web/app/ai-video/[[...path]]/page.tsx`](../../apps/web/app/ai-video/%5B%5B...path%5D%5D/page.tsx)、[`apps/web/components/ai-video/src/App.tsx`](../../apps/web/components/ai-video/src/App.tsx)
- 门户状态：[`apps/web/app/page.tsx`](../../apps/web/app/page.tsx)
- 研究流程：[`apps/web/components/ai-video/src/pages/aiStudio/project/ProjectWorkbench/tabs/ResearchTab.tsx`](../../apps/web/components/ai-video/src/pages/aiStudio/project/ProjectWorkbench/tabs/ResearchTab.tsx)、[`apps/api/app/ai_video/models/studio_project_research.py`](../../apps/api/app/ai_video/models/studio_project_research.py)
- 项目 Agent：[`apps/api/app/ai_video/api/v1/routes/studio/project_agent.py`](../../apps/api/app/ai_video/api/v1/routes/studio/project_agent.py)、[`apps/api/app/ai_video/models/studio_project_agent.py`](../../apps/api/app/ai_video/models/studio_project_agent.py)
- 镜头工作台：[`apps/web/components/ai-video/src/pages/aiStudio/chapter/ChapterStudio.tsx`](../../apps/web/components/ai-video/src/pages/aiStudio/chapter/ChapterStudio.tsx)
- 生成后当前视频写入：[`apps/api/app/ai_video/services/film/generated_video.py`](../../apps/api/app/ai_video/services/film/generated_video.py)
- 任务与链接：[`apps/api/app/ai_video/models/task.py`](../../apps/api/app/ai_video/models/task.py)、[`apps/api/app/ai_video/models/task_links.py`](../../apps/api/app/ai_video/models/task_links.py)、[`apps/api/app/ai_video/api/v1/routes/film/task_status.py`](../../apps/api/app/ai_video/api/v1/routes/film/task_status.py)
- 文件用途与溯源：[`apps/api/app/ai_video/models/studio_file_usages.py`](../../apps/api/app/ai_video/models/studio_file_usages.py)
- 编辑器现状：[`apps/web/components/ai-video/src/pages/aiStudio/editor/VideoEditor.tsx`](../../apps/web/components/ai-video/src/pages/aiStudio/editor/VideoEditor.tsx)、[`apps/api/app/ai_video/api/v1/routes/studio/timeline.py`](../../apps/api/app/ai_video/api/v1/routes/studio/timeline.py)
- 当前目标设计：[`docs/linglonglab-video-production-workspace.md`](../linglonglab-video-production-workspace.md)、[`docs/video-production-product-design.md`](../video-production-product-design.md)

### 15.2 ArcReel 本地源码与官方文档

- 本次一手资料专项研究（含 168 个官方链接、发布版与 main 边界）：[`docs/research/arcreel-primary-source-research-2026-09-24.md`](arcreel-primary-source-research-2026-09-24.md)

- 产品能力：[`ArcReel/README.md`](../../ArcReel/README.md)、[`ArcReel/CHANGELOG.md`](../../ArcReel/CHANGELOG.md)
- 工作流说明：[`ArcReel/website/docs/guide/workflows.md`](../../ArcReel/website/docs/guide/workflows.md)
- 架构：[`ArcReel/website/docs/dev/architecture.md`](../../ArcReel/website/docs/dev/architecture.md)
- 计划驱动 Agent：[`ArcReel/skills/video-workflow/SKILL.md`](../../ArcReel/skills/video-workflow/SKILL.md)
- 工作流和产物时效：[`ArcReel/lib/workflow/workflow_state.py`](../../ArcReel/lib/workflow/workflow_state.py)、[`ArcReel/lib/workflow/workflow_plan.py`](../../ArcReel/lib/workflow/workflow_plan.py)
- 版本与恢复：[`ArcReel/server/routers/versions.py`](../../ArcReel/server/routers/versions.py)
- 任务重启恢复：[`ArcReel/lib/generation/restart_recovery.py`](../../ArcReel/lib/generation/restart_recovery.py)、[`ArcReel/lib/generation/video_resume.py`](../../ArcReel/lib/generation/video_resume.py)
- 用量与成本：[`ArcReel/server/routers/usage.py`](../../ArcReel/server/routers/usage.py)、[`ArcReel/lib/billing/ledger.py`](../../ArcReel/lib/billing/ledger.py)
- 可编辑交付：[`ArcReel/server/routers/presentations.py`](../../ArcReel/server/routers/presentations.py)、[`ArcReel/server/services/presentation/jianying_draft_service.py`](../../ArcReel/server/services/presentation/jianying_draft_service.py)
- 项目导入导出与迁移：[`ArcReel/server/routers/projects.py`](../../ArcReel/server/routers/projects.py)

## 16. 最终建议

短期目标不应是“让 LinglongLab 的功能数量接近 ArcReel”，而应是完成一条可信的生产链：

> **正式镜头计划 → 正式关键帧 → 多个 take → 显式采用 → 持久化编辑 → 确定性渲染 → QA → 可追溯交付。**

在这条链上植入 ArcReel 的状态、版本、恢复、批次和费用思想；在链条上方继续强化 LinglongLab 的研究、证据、品牌与广告决策；在链条下方做 ArcReel 尚未完全解决的广告 QA、CTA/legal 和 delivery manifest。这样得到的不是 ArcReel 的复制品，而是一个更适合企业商业视频生产的系统。
