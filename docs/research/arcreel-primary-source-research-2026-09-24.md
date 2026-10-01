# ArcReel 一手资料研究：能力、工作流、架构与产品思路

研究日期：2026-09-24（Asia/Shanghai）  
研究目的：为 LinglongLab AI Video 与 ArcReel 的详细对比提供 ArcReel 侧的可核验证据；本文不评价 LinglongLab 当前实现，也不把 ArcReel 的代码、提示词、视觉或数据结构作为复刻方案。  
证据范围：ArcReel 官方 GitHub 仓库、官方 Release、官方文档站源文件、官方公开 skill，以及官方仓库内的产品说明、领域术语和 ADR。未使用第三方评测或营销转载。

## 1. 证据口径与版本边界

本文使用以下标记：

- **V-R（Verified — Released）**：已在官方 Release 或 `v0.31.0` 标签下的官方文档、代码、发布记录中验证。
- **V-M（Verified — Main）**：已在 2026-09-24 官方 `main` 分支验证，但晚于最新 Release；不能当作所有已部署用户都拥有的功能。
- **I（Inference）**：从多条一手证据归纳出的产品或架构判断，不是 ArcReel 官方原句。
- **U（Unknown）**：一手资料没有提供足够证据，不能确认。

截至研究时：

- 最新正式版本是 **v0.31.0，发布于 2026-09-23**；官方亮点包括自建 ComfyUI、端点市场、提示词模版与最终提示词预览、确认后剧本的时间线编辑，以及只允许取消排队任务。[官方 Release](https://github.com/ArcReel/ArcReel/releases/tag/v0.31.0)
- 本地官方仓镜像与 `origin/main` 对齐到提交 [`10f640c391912c0cd168aabdefbc36ffac9c8512`](https://github.com/ArcReel/ArcReel/commit/10f640c391912c0cd168aabdefbc36ffac9c8512)，时间为 2026-09-24 19:13:08 +08:00；它比 `v0.31.0` 多 28 个提交，而 `pyproject.toml` 仍标为 `0.31.0`。因此本文把这些变化标为 V-M，而不是下一正式版本。[v0.31.0 标签提交](https://github.com/ArcReel/ArcReel/commit/1f396602ff2e3e5a352f8e5f0405a72373e33f1b) / [main 提交历史](https://github.com/ArcReel/ArcReel/compare/v0.31.0...10f640c391912c0cd168aabdefbc36ffac9c8512)
- 当前官方定位是“开源、自托管的 AI 视频生产工作台”，面向 AI 漫剧与小说改编、旁白/解说、广告与带货短片；目标不是一次性生成一个视频，而是组织一条可审核、可中断恢复、可追踪成本、可保留版本、可继续编辑的生产链。[README](https://github.com/ArcReel/ArcReel/blob/v0.31.0/README.md#L1-L19) / [产品说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/PRODUCT.md#L18-L35) / [架构目标](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md#L12-L24)

## 2. 核心结论

### 2.1 ArcReel 实际上是什么

**V-R：ArcReel 是“生产控制面 + 媒体生成适配层 + Agent 工作流”，不是单一模型壳。**

它把用户输入、内容结构化、资产设计、脚本审核、分镜或参考视频单元、异步生成任务、费用与用量、版本与产物来源、成片/剪映导出放进同一项目工作台。官方 UI 截图能直接看到四阶段导航（准备、脚本、制作、完成）、左侧项目资产与剧集导航、中间分镜时间线和媒体详情、右侧 ArcReel Agent、顶部费用与导出入口。[官方工作台截图](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/assets/screenshots/hero.webp) / [架构总览](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md#L26-L57)

**I：ArcReel 的主要竞争力不是“能调用多少模型”，而是把不稳定、昂贵的生成过程变成有状态、可复核、可恢复的生产系统。** 供应商广度是其中一层；真正形成系统差异的是审核闸门、权威制作计划、产物时效、费用前置、队列恢复、版本回滚和可编辑交付之间的组合。

### 2.2 最值得单独对比的十二项能力

以下能力最可能形成产品级差距，而不只是界面差异：

1. **内容类型与生成模式是两个正交轴**，不是一个混合的“模板”选择。
2. **Agent 负责判断与编排，确定性工具负责写项目、建任务、合成与导出**。
3. **脚本规划与视觉提示词编写分层**，中间有显式人工确认。
4. **资产是一等对象**：角色、角色衍生、场景、道具、商品、全局资产库和项目内副本各有明确语义。
5. **分镜图生视频、参考生视频、多宫格分镜**是不同的生产组织方式，而不只是模型参数。
6. **产物清单与产物时效**区分“当前、比当前内容旧、缺失、受阻”，旧产物仍可使用，不被自动付费重做。
7. **批量视频生成先整批准入，再逐项执行**，避免一批半成品已经计费后才发现其余目标不合法。
8. **任务与供应商调用分开建模**，为取消、恢复、重复计费防护和费用归属提供基础。
9. **供应商、模型、调用端点、能力和凭证分层**，支持内置供应商、自定义声明式端点、ComfyUI 与市场。
10. **最终提示词、参考图和价格在执行前可见**，提示词模版本身也是可浏览的产品资产。
11. **内嵌 Agent 与外部 Agent 共用创作工具集和服务端制作计划**，MCP 不是旁路脚本。
12. **交付不止 MP4**：版本选择、可编辑包、剪映草稿、字幕和可选 TTS 轨道共同构成交付面。

这些结论分别由后续章节逐条给出一手证据。

## 3. 完整能力清单

### 3.1 部署、账户与目标用户

| 能力 | 状态 | 已验证事实 | 证据 |
|---|---|---|---|
| 自托管 Web 应用 | V-R | 官方快速开始以 Docker Compose 在 `localhost:1241` 启动；默认 SQLite，生产可用 PostgreSQL。默认工作流调用远程模型 API，通常不需要本机 GPU。 | [入门教程](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/getting-started.md#L32-L51) / [部署说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/ops/deployment.md) |
| 单管理员账户 | V-R | 产品当前按“单管理员账号的自托管服务”设计，没有多人协作与角色权限；PostgreSQL 提高并发和运维能力，但不提供用户隔离，不应给互不信任的用户共用一个实例。 | [PRODUCT](https://github.com/ArcReel/ArcReel/blob/v0.31.0/PRODUCT.md#L5-L14) / [入门教程](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/getting-started.md#L145-L148) |
| 登录和自动化凭证 | V-R | 支持用户名密码、会话 JWT、`arc-` 前缀 API Key；远程 MCP 始终要求 API Key。 | [架构说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md#L378-L395) / [部署说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/ops/deployment.md#L150-L180) |
| 首次引导与演示项目 | V-R | 登录后有首次使用引导和只读演示项目，可在不消耗模型额度的情况下认识项目大厅、工作台、Agent 和设置。 | [入门教程](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/getting-started.md#L175-L190) |
| 多语言 | V-R | 面向用户的文案要求所有支持语言同步；当前前端资源目录包含中文、英文、越南文。 | [PRODUCT](https://github.com/ArcReel/ArcReel/blob/v0.31.0/PRODUCT.md#L62-L67) / [i18n 目录](https://github.com/ArcReel/ArcReel/tree/v0.31.0/frontend/src/i18n) |
| 原生移动应用 | V-R（否） | 没有独立 iOS 或 Android App；手机浏览器可尝试访问，但官方不承诺完整移动编辑体验。 | [FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L293-L296) |

### 3.2 项目输入与项目创建

**V-R：文本来源与创作目标被明确拆开。**

- 文本源支持小说和成品剧本；广告/短片以商品多图、卖点、目标人群、禁用表述、品牌视觉、目标时长和平台等素材为输入。[工作流文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/workflows.md#L26-L84)
- 支持 `.txt`、`.md`、`.docx`、`.epub` 和 `.pdf`，统一抽取成 UTF-8 文本；扫描 PDF 不带 OCR，需要用户先做 OCR，旧 `.doc` 需要转为 `.docx`。[FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L202-L208)
- 项目创建时必须分别选择“创作类型”和“生成模式”，创建后不可更改。创作类型决定脚本结构，生成模式决定视频由分镜图还是资产参考图驱动。[工作流文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/workflows.md#L12-L24) / [领域术语](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L388-L424)
- 项目级设置可以覆盖全局模型、画幅比例、目标时长、视觉风格、TTS 等；不同媒体类型可选择不同供应商与模型。[供应商文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/providers.md#L67-L88)

### 3.3 三种创作类型

#### 旁白/解说（Narration）

**V-R：** 以旁白为主要信息载体，按语义停顿和朗读节奏拆分；标准流是“原文 → 旁白片段 → 画面描述 → 分镜图 → 视频片段”，旁白片段另走 TTS，再在成片或剪映草稿中汇合。适合小说推文、故事/知识内容和不强调口型的项目。[工作流文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/workflows.md#L88-L123)

#### 剧情演绎（Drama）

**V-R：** 以角色、场景、对白和动作为结构，强调角色一致性、空间关系和相邻镜头连续性；标准流是“小说/剧本 → 角色/场景/道具提取 → 分集规划 → 结构化脚本 → 资产 → 分镜 → 视频 → 成片/剪映”。[工作流文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/workflows.md#L125-L159)

#### 广告/短片（Ad）

**V-R：** 围绕明确时长、卖点、使用场景和 CTA 组织镜头，商品真实性优先；流程包含商品标准参考、广告镜头脚本、商品锚定分镜、口播/字幕和剪映草稿。官方 UI 截图中可见 `hook`、`pain_point`、`product_reveal`、`selling_point` 等段落标签，但这些是截图所示当前产品组织，不应推断为所有项目必须使用的固定营销框架。[工作流文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/workflows.md#L161-L191) / [官方广告模式截图](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/assets/screenshots/ad-mode.webp)

### 3.4 两种生成模式与一种组图策略

#### 分镜图生视频

**V-R：** 每个分镜先有分镜图，视频以该图作为首帧输入；优点是流程直观、供应商覆盖广、单镜重做容易，局限是主要约束起始画面，运动中角色与细节仍可能漂移。[工作流文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/workflows.md#L193-L217)

#### 多宫格分镜

**V-R：** 它不是第三种生成模式，而是分镜图生视频内的组图方式。系统把同一段落的多个分镜先统一生成在一张或多张多宫格图中，再切成单镜分镜图。默认按数量选择 2×2 或 3×3；4×4、5×5 仅在图像分辨率档为 4K 时可选。它提高同批角色、场景和画风一致性，但增加布局/切分复杂度并降低单格清晰度；不适用于参考生视频和广告/短片。[工作流文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/workflows.md#L219-L242)

#### 参考生视频

**V-R：** 不先生成普通分镜图，而是直接把角色、场景、道具或商品资产图作为视频参考；更适合多参考图视频模型和身份锚定，但供应商支持范围更窄、参考图数量和输入规则差异大，构图可控性可能下降。[工作流文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/workflows.md#L244-L267)

**V-R：首帧、尾帧与相邻镜头连续性。** 分镜图本身是首帧；用户可为单镜选择或上传尾帧，但仅在模型明确支持时放行。非首镜、未标记为新段落且上一张分镜已生成时，系统会把上一张分镜作为衔接参考；官方明确不承诺两个独立生成视频能因此无缝拼接。[FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L245-L263)

### 3.5 Agent 驱动的制作流程

**V-R：内嵌 Agent 不是单轮助手。** Agent Runtime 基于 Claude Agent SDK，采用“编排 Skill + 聚焦子智能体 + 确定性工具”结构：主 Agent 读取项目状态、判断下一阶段、在需要时等待确认；子智能体处理角色/场景/道具提取、分集规划、脚本规范化等聚焦任务；文件写入、任务创建、状态查询、结构化文件生成、合成和导出交给确定性工具。[架构说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md#L90-L150)

**V-R：Agent 按服务端权威制作计划推进。** 官方外部 Agent skill 明确要求先调用 `get_workflow_plan`，只按 `next_action` 执行动作；需要用户选择或确认时必须等待；生成动作返回批次后按建议间隔轮询，完成后重新读取计划。远程 MCP 不负责最终合成或导出，相关动作交回 WebUI 或内嵌宿主。[官方 video-workflow skill](https://github.com/ArcReel/ArcReel/blob/v0.31.0/skills/video-workflow/SKILL.md#L6-L23)

**V-R：Agent 有持久会话和两级记忆。** v0.29.0 引入用户记忆与项目记忆，可跨会话生效并在设置页查看/修改；领域定义把记忆限制为长期偏好、纠正、决策和外部线索，不允许拿它替代项目正式数据、进度或 transcript。[v0.29.0 发布记录](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CHANGELOG.md#L216-L247) / [记忆定义](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L640-L654)

**V-R：会话可以通过改写历史用户消息形成新分支。** 原会话保留为不可见备份，新会话承接改写点之前的前缀；这修正的是对话上下文，不回退已经写入项目或供应商产生的副作用。[ADR 0058](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0058-session-branch-prefix-fork.md)

**V-R：对话 UI 与 SDK 恢复存储分开。** SDK transcript 用于恢复 Agent 上下文；单调序号的会话事件日志是 UI 时间线唯一读源，SSE 按 cursor 续传，子智能体事件折叠成卡片。这个分层减少流式预览、重连和历史回放之间的去重猜测。[ADR 0029](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0029-sdk-transcript-mirrored-to-db.md) / [ADR 0048](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0048-session-event-log-single-ui-read-source.md)

### 3.6 脚本规划、审核与增量编辑

**V-R：内容和视觉提示词分成两个阶段。** “脚本规划”负责场景/片段边界、角色/场景/道具、台词/画外音/对应原文等内容层；“提示词编写”只补视觉层。脚本规划与提示词编写之间有阻塞式人工确认，避免未审核内容进入昂贵的视觉生成。[ADR 0041](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0041-script-pipeline-script-plan-prompt-authoring-review-gate.md) / [领域定义](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L470-L512)

**V-R：确认动作会物化正式脚本。** v0.31.0 中，内容确认把整集脚本规划转换为正式脚本；确认后脚本规划只读，后续内容编辑在时间线进行。手工新增分镜会标记为“待编写”，提示词编写只处理待编写条目；已存在正式脚本时覆盖需要显式认可。[v0.31.0 Release](https://github.com/ArcReel/ArcReel/releases/tag/v0.31.0#user-content-0310-2026-09-23)

**V-R：时间线支持增删分镜和修改旁白。** Release 明确声明确认后的剧本可在时间线上增删分镜、修改旁白；仅改动的分镜重新编写提示词，未改条目和已有产物不应被整集覆盖。[v0.31.0 Release](https://github.com/ArcReel/ArcReel/releases/tag/v0.31.0)

**V-R：分集规划有独立账本。** 账本记录集号、原文范围、标题、钩子、消费状态和规划游标；物理 `episode_N.txt` 是派生物。服务端使用文本模型分批规划剧情弧完整的多集，只推进到高置信切分点，形式与范围连续性由工具机械校验。[ADR 0031](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0031-episode-ledger-single-source-of-truth.md) / [ADR 0032](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0032-episode-planning-server-side-batched.md)

**V-M：** 2026-09-24 的 `main` 新增“剧本源按下一集开头分集并展示每集首尾原文”，但这晚于 v0.31.0，属于未发布主分支变化。[提交 `88d5ba0`](https://github.com/ArcReel/ArcReel/commit/88d5ba0c56aaf4f1f0afef8cc513a931f820ae0e)

### 3.7 资产系统与一致性

**V-R：项目资产包括角色、场景、道具和商品。** 每种资产有定义、原图/资产图、版本与后续引用；项目资产只属于当前项目。全局资产库用于跨项目复用角色、场景和道具，应用到项目后成为独立副本，后续不会自动同步。[领域术语](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L322-L375)

**V-R：角色有“本体 + 衍生”模型。** 衍生用于换装、变身、易容、年龄变化等持续外观，以 `@[角色/衍生]` 在脚本中引用；衍生共享角色身份与声音，只保存相对本体的外观变化和由本体资产图编辑生成的资产图。全局资产库会让角色衍生随本体整套进出。[v0.29.0 发布记录](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CHANGELOG.md#L219-L247) / [角色衍生定义](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L340-L361)

**V-R：商品采用双层锚点。** 用户上传的商品原图是真实性验收锚点；标准化商品资产图是可选的下游生成参考。官方工作流要求检查商品外形、Logo、颜色和结构，避免让生成模型补全重要文字与结构。[ADR 0034](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0034-product-fidelity-dual-layer-anchor.md) / [工作流文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/workflows.md#L184-L191)

**V-R：引用未登记资产或缺资产图会在生成前阻断。** 原图不普遍直接替代资产图；参考图数量超过模型上限时，ArcReel 会在入队前按装配顺序裁剪并向用户和 Agent 显示提示，不静默丢图。[v0.29.0 发布记录](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CHANGELOG.md#L219-L245) / [参考图裁剪定义](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L236-L260)

**V-R：图片编辑生成新版本，不重写原图提示词。** 领域决策把“编辑”建模为从当前图片分叉出的新图片版本，编辑指令本身不回写成该资产的生成提示词。[ADR 0050](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0050-image-edit-forks-image-not-prompt.md)

### 3.8 提示词系统

**V-R：提示词是可管理的产品层，不只是后台字符串。** v0.31.0 提供只读提示词模版浏览，按流程分组，可展开片段、切换变体、标识可选块，并展示 36 种画风；生成资产图、分镜和参考视频前可查看最终渲染提示词与参考图。[v0.31.0 Release](https://github.com/ArcReel/ArcReel/releases/tag/v0.31.0)

**V-R：每个生成环节对应一份完整模版，轴差异由命名变体片段解决。** 生成环节按制作步骤、创作类型和生成模式区分；风格模版与生成提示词模版是不同概念。ArcReel 保留结构化与纯文本两种提示词形态，但最终发给模型只有一个渲染出口。[ADR 0077](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0077-whole-prompt-templates-with-named-variant-partials.md) / [领域定义](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L478-L504)

**I：** 这一设计把“用户修改的是输入意图”“模型收到的是最终渲染文本”“系统维护的是模板与变体”分开，适合做可审计的生成预览，也减少不同入口自行拼 prompt 造成的漂移。

### 3.9 模型、供应商与项目级策略

**V-R：Agent 供应商与生成供应商分离。** Agent 供应商负责理解、分析和编排；文本、图像、视频、TTS 供应商负责实际内容生成。一个项目可以用高推理 Agent、快速结构化文本模型、高质量角色图模型、低成本分镜模型、不同档位视频模型和独立 TTS 的组合。[供应商文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/providers.md#L8-L46)

**V-R：预置供应商矩阵。** v0.31.0 文档列出 Gemini、火山方舟、Grok、OpenAI、Vidu、阿里百炼、MiniMax、可灵 Kling、Agnes 以及自定义供应商。具体模型、参数、地区和价格以设置页为准；支持某供应商不等于支持它所有模型或输入形式。[供应商矩阵](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/providers.md#L48-L65)

**V-R：模型能力在模型级建模。** 上层区分文本、图像、视频、音频媒体类型，以及 t2i/i2i、i2v/r2v 任务类型；参考图、尾帧、原生音频、可选时长、分辨率等按具体模型或端点能力判断，不能靠模型名字猜。[模型能力定义](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L178-L234) / [供应商文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/providers.md#L245-L269)

**V-R：配置分层。** 支持全局默认、项目级覆盖、不同媒体类型选择不同供应商，以及预置供应商多 API Key；项目配置优先于全局。多 Key 由用户手动选择当前生效凭证，不做自动轮换或负载均衡。[供应商文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/providers.md#L67-L88) / [多 Key 说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/providers.md#L382-L402)

### 3.10 自定义供应商与调用端点

**V-R：自定义供应商不等于只填一个 OpenAI Base URL。** 每个自定义模型行绑定一个“调用端点”；端点是一整套 URL 模板、鉴权、请求字段、提交/轮询、状态映射和结果提取约定，或一份 ComfyUI workflow 与节点绑定。端点定义可以导入、导出、测试和经市场安装。[领域术语](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L29-L81)

**V-R：端点测试分三层。** “验证响应”离线检查取值路径和状态映射；“预览请求”渲染将要发送的 URL、方法、请求头和请求体；“测试连接”才真实付费生成并跟踪到终态。成功产物可播放，结果保留 24 小时；取消本地测试跟踪不保证远端任务停止，也不撤销已发生费用。[供应商文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/providers.md#L342-L355)

**V-R：外部 Agent 可协助适配声明式视频端点。** 官方 skill 的流程是“写定义 → 共享 validator → 离线验证响应 → 预览请求 → 经用户明确同意后测试连接 → 保存”。首期声明式端点面向 JSON 提交与 JSON 轮询；签名鉴权、发往供应商的 multipart、按素材切换路由不在其首期范围。[供应商文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/providers.md#L357-L380)

### 3.11 ComfyUI 集成

**V-R：一份 ComfyUI API workflow 是一个 ArcReel 端点/模型行。** ArcReel 通过 HTTP 上传素材、提交 `/prompt`、查 `/history` 并下载产物，不要求共享文件系统。用户导入 `Export (API)` JSON，而普通画布 `Export` 会被拒绝。[ComfyUI 指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/comfyui.md#L8-L48)

**V-R：节点绑定是唯一真相。** ArcReel 在导入时只推断候选，用户确认后才成为绑定；可绑定正/负提示词、首帧、尾帧、参考图、宽高、帧数、帧率、种子和产物节点。没有绑定的能力保持 workflow 字面值，不由 ArcReel 猜测。[ComfyUI 指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/comfyui.md#L50-L82)

**V-R：能力由绑定推导，不猜模型名。** 尺寸、时长和素材能力按节点绑定与约束计算；正向提示词与产物节点必填。支持请求预览、真实连接测试、远端轮询、结果入库与来源记录。[v0.31.0 Release](https://github.com/ArcReel/ArcReel/releases/tag/v0.31.0) / [ADR 0082](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0082-node-bindings-are-the-only-truth-of-comfyui-endpoint.md)

**V-R：产物格式有限制。** 视频端点接收 `.mp4`、`.mov`、`.m4v`，图像端点接收 `.png`、`.jpg`、`.jpeg`、`.webp`；文件名与真实容器均会校验，`.webm` 当前不作为成片入库。[ComfyUI 指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/comfyui.md#L140-L164)

**V-M：** 2026-09-24 `main` 新增 MiniMax H3 ComfyUI 首尾帧和参考图节点规则，晚于 v0.31.0。[提交 `ab714d9`](https://github.com/ArcReel/ArcReel/commit/ab714d9821dd4f2819466d21977ecf141f194286)

### 3.12 端点市场

**V-R：市场是“零 ArcReel 中心服务”的多源安装机制。** 市场源是 GitHub 仓库或等价 HTTPS 索引直链；官方源随版预置，用户也可添加第三方源。首期唯一条目类型是调用端点；提示词和风格模板只显示“即将推出”。[市场指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/market.md#L8-L19) / [浏览说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/market.md#L65-L78)

**V-R：安装前有显式信任检查。** 确认页展示定义校验、作者建议、API Key 将发往的提交地址、轮询地址和鉴权原文；第三方源显示未审核提示。已安装端点可以本地编辑，更新时会提示本地修改将被覆盖；禁用或删除市场源不会卸载端点。[市场指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/market.md#L80-L138)

**I：** ArcReel 把“生态扩展”定义为可检查、可本地持有、可更新的 endpoint definition，而不是把用户导向一个必须登录的云端插件商店；这与其自托管定位一致。

### 3.13 任务、批量生成、取消与恢复

**V-R：媒体任务有持久队列。** 图片、视频和音频分别有独立并发通道，支持异步执行、状态持久化、失败记录、排队任务取消、项目事件和状态刷新；文本长任务也进入持久任务体系。[架构说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md#L227-L260) / [v0.28.0 发布记录](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CHANGELOG.md#L310-L359)

**V-R：只有排队中的任务可以取消。** 一旦开始执行就继续跑到终态，结果照常保存，避免已经支付的费用落空。取消有依赖的排队任务时会提示被级联取消的下游任务。[v0.31.0 Release](https://github.com/ArcReel/ArcReel/releases/tag/v0.31.0) / [FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L220-L232)

**V-R：服务重启不盲目重提。** 只有已保存远端任务 ID 且供应商支持续查的视频任务会继续轮询；其余运行中任务标记失败，等待人工决定。官方理由是无条件重新提交可能重复计费。视频已在供应商侧成功、仅下载失败时，界面提供“重试下载”，不新建付费任务。[FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L220-L239)

**V-R：批量视频先整批准入。** 在创建任何任务前，系统对完整目标集合做一次全有或全无判定，结论为“放行、待确认、受阻”；资产缺失、混合发声、供应商约束、在途冲突或跨档费用未确认等任一问题都会导致零任务创建。准入通过后的实际执行才允许逐项成功或失败。[ADR 0061](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0061-batch-video-admission-all-or-nothing.md)

**V-R：缺失补齐不等于全部重做。** 批量任务部分失败后，系统按缺失项补齐；已有成功产物不会因为单项失败删除。默认批量生成只补 `missing`，不会自动重做仍可用但比当前内容旧的产物。[工作流文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/workflows.md#L331-L350)

### 3.14 产物、版本、来源和制作状态

**V-R：产物不是“目录里有个文件”。** 产物清单记录正式资产图、脚本、分镜图、视频、旁白等的身份、路径和生成依据摘要；读取时将依据与当前项目状态比较，得到 `current / stale / missing / blocked` 四态。[领域定义](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L546-L585) / [ADR 0062](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0062-artifact-lifecycle-and-currency.md)

**V-R：`stale` 仍然是用户拥有的可用产物。** 它可以预览、参与成片和导出，不阻断工作流，也不触发自动付费重生；只有用户显式选择才重做。`blocked` 不降级成 `missing`，避免读失败被误判为“需要重新付费生成”。[ADR 0062](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0062-artifact-lifecycle-and-currency.md)

**V-R：制作状态由服务端权威生成。** 制作状态给出当前步骤、阻断项、内容确认、各类产物时效和下一动作；制作计划在其上形成有序步骤，Web 和 Agent 共用。界面不应按文件存在性自行猜阶段。[架构说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md#L262-L324) / [领域定义](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L576-L585)

**V-R：媒体版本不会被简单覆盖。** 版本历史用于比较、回滚、保留已审核版本和降低重做风险；用户也可以手工上传替换分镜图或镜头视频。[架构说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md#L312-L324) / [v0.17.0 发布记录](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CHANGELOG.md)

### 3.15 费用与使用记录

**V-R：提交前有费用预估，调用后有实际用量记录。** 记录覆盖文本、图片、视频、TTS，不同供应商和币种分开；官方明确 ArcReel 参考费用不替代供应商账单，自定义供应商无价格或上游无 usage 时可能显示不完整或 0。[架构说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md#L326-L344) / [FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L269-L281)

**V-R：v0.30.0 把调用记录升级为可调查的运营面。** 设置页有 KPI、趋势、费用构成、异常关注、筛选、keyset 分页和单次调用深链；详情包含输入、响应、失败机器码和原始失败原因，并能关联来源和任务。[v0.30.0 发布记录](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CHANGELOG.md#L154-L176)

**V-R：任务与供应商调用不是一一对应。** 一次本地生成任务可对应零到多次供应商调用；剧本生成、Agent 对话和端点测试也可以独立产生调用。费用与用量以供应商调用为最小单位。[领域定义](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L128-L148) / [ADR 0076](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0076-usage-record-is-projection-of-provider-calls.md)

### 3.16 声音体系

**V-R：ArcReel 区分三种声音能力。**

1. 视频模型同时生成的原生音轨；
2. 角色参考音频，用于参考生视频中约束角色音色；
3. 独立 TTS 旁白素材，用于后期叠加。

三者不是同一个开关。默认角色声音靠提示词中的声音描述做软约束；使用参考音频必须是参考生视频、模型支持参考音频、每个有台词角色已有参考音频。分镜图生视频不支持角色参考音频。[FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L265-L267) / [声音领域定义](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L288-L320)

**V-R：独立 TTS 的 Web UI 只对旁白/解说开放。** 可逐段试听、生成全集旁白，并随剪映草稿导出；广告/短片的配音按官方工作流在导出后完成。[FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L265-L267) / [广告流程](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/workflows.md#L161-L181)

### 3.17 实时状态与项目事件

**V-R：** Agent 对话通过 SSE 流式返回；项目终态变化通过项目事件 SSE 触发刷新，生成任务中间状态由任务查询补充。前端切回前台会立即恢复事件流连接。[架构说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md#L75-L88) / [v0.29.0 发布记录](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CHANGELOG.md#L228-L245)

**V-M：** 2026-09-24 `main` 改为对商品、角色衍生、台词、集信息和项目设置的改动也实时推送到工作台，并重构项目状态投影；属于 v0.31.0 之后的主分支变化。[提交 `c971f5e`](https://github.com/ArcReel/ArcReel/commit/c971f5ec53bc471c8d8a8113e6a98f7cf6413449) / [ADR 0085](https://github.com/ArcReel/ArcReel/blob/10f640c391912c0cd168aabdefbc36ffac9c8512/docs/adr/0085-project-events-dual-source-registry-derived-projection.md)

### 3.18 成片、可编辑包与剪映

**V-R：ArcReel 有两条正式交付方向。** 一条是 FFmpeg 合成，处理片段拼接、转场、音频和编码；另一条是导出可继续编辑的剪映草稿，用于改片段、字幕、配音、音乐和转场。[架构说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md#L346-L370)

**V-R：成片读取模型共享版本选择。** 工作台预览、可编辑包下载和剪映草稿使用相同的已选视频版本、可选 TTS 版本和实际媒体时长；手工上传但缺少生成来源证明的视频按原始视频导出，不自动补 TTS 或字幕。[剪映指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/jianying-export.md#L76-L99)

**V-R：剪映导出支持中国大陆桌面版 5.x 和 6+。** 每集生成一个 ZIP，包含视频轨和机械字幕；旁白/解说可带独立 TTS 轨，剧情演绎字幕来自台词与画外音，广告/短片字幕来自口播。CapCut 兼容性尚未验证。[剪映指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/jianying-export.md#L8-L18) / [导出内容](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/jianying-export.md#L76-L99)

**V-R：内建成片合成的适用面有限。** 入门文档明确：分镜图生视频的剧情演绎项目可在 ArcReel 内合成；分镜图生视频的旁白/解说和广告/短片走剪映草稿；参考生视频项目下载生成片段继续后期。因此不能把“ArcReel 支持成片合成”理解为所有模式都有同等的内部编辑/渲染能力。[入门教程](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/getting-started.md#L370-L389)

### 3.19 项目导入、导出、升级与恢复

**V-R：项目 ZIP 可选择仅当前版本或包含完整版本历史。** 它用于单项目迁移，不包含全局供应商设置、登录配置、任务与费用记录、Agent 会话或 Agent 记忆，因此不等于全站备份。[FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L281-L285)

**V-R：数据库和项目目录分别迁移。** 应用启动时运行 Alembic 数据库迁移，也逐项目升级文件 schema；项目迁移按步骤幂等、单项目失败隔离，并为关键文件保留迁移前备份和迁移报告。迁移失败项目仍可只读打开，但生成入口被阻断，要求先修复。[部署说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/ops/deployment.md#L269-L301) / [领域定义](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L564-L574)

**V-M：** 主分支在 2026-09-24 新增“数据根分层：项目收进 `projects/` 子目录”的 ADR；这是架构方向，尚不能当作 v0.31.0 已发布的数据布局。[ADR 0088](https://github.com/ArcReel/ArcReel/blob/10f640c391912c0cd168aabdefbc36ffac9c8512/docs/adr/0088-data-root-layered-projects-subdirectory.md)

### 3.20 外部 Agent 与 MCP

**V-R：ArcReel 官方发布外部 Agent skills。** 用户安装 `setup-arcreel-skills`、`video-workflow`，另有 `adapt-custom-endpoint`；在 ArcReel 设置页创建一次性展示的 `arc-` API Key，连接 `/mcp`，以 `list_projects` 成功作为接线完成判据。[外部 Agent 安装指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/public/agent-installation-guide.md#L1-L31) / [skills README](https://github.com/ArcReel/ArcReel/blob/v0.31.0/skills/README.md#L1-L9)

**V-M：内嵌 Agent 与外部 Agent 的工具集在主分支进一步收敛为单源声明。** 两者的领域能力与结果一致；区别只保留项目身份来源和长任务返回方式：内嵌 Agent 在会话上下文内确定项目并可等待任务，外部 Agent 每次显式传项目并以提交回执 + 查询完成。该 ADR 于 2026-09-24 晚于 v0.31.0。[ADR 0087](https://github.com/ArcReel/ArcReel/blob/10f640c391912c0cd168aabdefbc36ffac9c8512/docs/adr/0087-agent-toolset-single-declaration.md) / [领域定义](https://github.com/ArcReel/ArcReel/blob/10f640c391912c0cd168aabdefbc36ffac9c8512/CONTEXT.md#L606-L618)

## 4. ArcReel 的产品与架构思路

本节的“官方决定”来自一手资料；“对我们意味着什么”是 I 级归纳。

### 4.1 把 AI 视频当成有状态生产，不是一次生成

**官方决定（V-R）：** 项目拥有源文件、脚本、资产、生成模式、媒体、版本和导出；状态来自服务端制作计划与产物清单，而不是前端看见某个文件就推断“完成”。[产品说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/PRODUCT.md#L18-L44) / [领域定义](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md#L546-L585)

**对我们意味着什么（I）：** 对比时必须检查状态模型、恢复与历史，不应只比较页面上有没有“脚本、分镜、生成”三个按钮。

### 4.2 让审核发生在返工便宜的地方

**官方决定（V-R）：** 内容分析、角色资产、少量分镜、少量视频、旁白试听、成片预览分别设置审核点；脚本规划未确认前不进入视觉提示词编写，批量前先做样片与费用评估。[工作流文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/workflows.md#L282-L377)

**对我们意味着什么（I）：** ArcReel 的自动化目标不是“最少点击”，而是“尽早拦住会造成大面积付费返工的错误”。

### 4.3 “旧”不等于“不可用”，也不等于“自动重做”

**官方决定（V-R）：** 产物状态和任务状态是两条独立轴；旧产物仍可导出，新一轮强制重做失败也不抹掉原来 current 的产物。[ADR 0062](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0062-artifact-lifecycle-and-currency.md)

**对我们意味着什么（I）：** 这是生成产品区别于普通 CRUD 的关键：用户付费得到的媒体是“持有物”，不应被状态变更或失败重试静默覆盖。

### 4.4 成本是工作流约束，不是事后报表

**官方决定（V-R）：** 批量视频准入在任务创建前检查资产、音频、供应商限制、在途冲突和跨档费用；费用预估不完整时不展示一个误导性的部分合计。[ADR 0061](https://github.com/ArcReel/ArcReel/blob/v0.31.0/docs/adr/0061-batch-video-admission-all-or-nothing.md)

**对我们意味着什么（I）：** “有费用页面”不等于成本控制；真正的差异是费用是否影响放行、确认、恢复和重试语义。

### 4.5 Agent 不拥有隐式真相

**官方决定（V-R）：** Agent 从服务端计划读取下一步，项目写入走工具，任务完成由状态查询确认；长文本推理交给聚焦子智能体，确定性动作不交给模型自由生成。[架构说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md#L90-L150)

**对我们意味着什么（I）：** ArcReel 的 Agent 是“受状态机约束的操作者”，不是另起一套通过自然语言猜项目状态的自动化。

### 4.6 能力适配不假装所有模型相同

**官方决定（V-R）：** 上层统一请求和任务生命周期，但时长、参考图数量、尾帧、原生音频、计费单位、失败语义仍保留在模型能力与适配器中；不支持的参数应显式拒绝，不静默忽略。[架构说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md#L181-L225) / [供应商文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/providers.md#L245-L269)

**对我们意味着什么（I）：** 供应商抽象的价值不是统一成最小公约数，而是让能力差异可查询、可解释、可在准入时验证。

### 4.7 扩展生态以“可审阅定义”为单位

**官方决定（V-R）：** 声明式调用端点、ComfyUI workflow 与市场安装均围绕 endpoint definition；用户在安装、更新和测试前能看到目的地址、鉴权方式、请求预览与能力绑定。[市场指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/market.md#L80-L127) / [ComfyUI 指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/comfyui.md#L33-L82)

**对我们意味着什么（I）：** 它将供应商适配从“发版改后端”部分转成“可验证、可安装、可本地修改的运行时资产”，但也引入新的供应链与凭证去向风险。

### 4.8 最终交付必须可继续编辑

**官方决定（V-R）：** 可编辑包和剪映草稿是一等输出；ArcReel 明确把“可继续编辑”视为区别于只输出一个视频文件的工具的重要特征。[架构说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md#L346-L376)

**对我们意味着什么（I）：** 评估 AI Video 不应以“能播放一个 MP4”结束，而应检查版本选择、字幕、音轨、轨道时序、来源证明与下游编辑器衔接。

## 5. 明确限制、缺口与不要误读之处

以下均是 ArcReel 自己的一手资料明确给出的边界。

| 边界 | 状态 | 说明与证据 |
|---|---|---|
| 没有多人协作/RBAC | V-R | 单管理员账号；结构上为未来多人保留余地，但当前不提供多人协作和角色权限。[PRODUCT](https://github.com/ArcReel/ArcReel/blob/v0.31.0/PRODUCT.md#L5-L14) |
| 没有原生移动 App | V-R | 仅 Web；手机浏览器不承诺完整编辑体验。[FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L293-L296) |
| CapCut 未验证 | V-R | 剪映草稿仅面向中国大陆桌面版剪映；不能宣称 CapCut 兼容。[剪映指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/jianying-export.md#L8-L18) |
| 内部成片合成不是全模式等价 | V-R | 内建合成主要用于分镜路线的剧情演绎；旁白/广告用剪映草稿，参考生视频下载片段后期。[入门教程](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/getting-started.md#L370-L389) |
| 独立 TTS Web UI 只覆盖旁白/解说 | V-R | 广告配音导出后完成；角色参考音频又是另一套能力。[FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L265-L267) |
| 执行中任务不可由普通取消动作中断 | V-R | 取消仅对 queued 开放，running 跑到终态。[v0.31.0 Release](https://github.com/ArcReel/ArcReel/releases/tag/v0.31.0) |
| 重启恢复有条件 | V-R | 只有有远端任务 ID 且供应商支持的部分视频任务续跑；其余失败后人工决定，防止重复计费。[FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L220-L239) |
| 扫描 PDF 没有内置 OCR | V-R | 扫描件需外部 OCR；`.doc` 需先转 `.docx`。[FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L202-L208) |
| 项目 ZIP 不是全站备份 | V-R | 不含供应商配置、账号、任务、费用、Agent 会话和记忆。[FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L281-L285) |
| 市场首期只有调用端点 | V-R | 提示词与风格模板仍标为即将推出。[市场指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/market.md#L69-L78) |
| 声明式端点覆盖面有限 | V-R | 首期适合 JSON 提交/轮询；签名鉴权、供应商 multipart、按素材换路由不在范围。[供应商文档](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/providers.md#L357-L380) |
| 角色/商品一致性不是保证 | V-R | 官方建议通过资产、参考图和样片提高一致性，同时明确生成模型仍无法保证逐帧绝对一致。[FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md#L239-L263) |
| 不能直接安全暴露公网 | V-R | 官方要求认证、HTTPS/VPN/安全隧道与反向代理，Compose 默认端口映射需额外收紧。[部署说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/ops/deployment.md#L426-L443) |
| 没有官方质量基准和客户案例研究材料 | V-R（材料缺失） | PRODUCT 明确列出当前没有客户名单、用户数、案例研究、评测数据、媒体报道、定价和付费档位文案。[PRODUCT](https://github.com/ArcReel/ArcReel/blob/v0.31.0/PRODUCT.md#L48-L55) |

## 6. 已验证的近期产品演进

这部分有助于判断 ArcReel 的投入方向，而不是只看静态功能表。

| 版本 | 日期 | 一手资料显示的产品重点 |
|---|---|---|
| v0.28.0 | 2026-08-30 | 自定义声明式视频端点、外部 Agent/MCP、最终提示词预览、长任务持久批次、参考音频、任务进度与下载续跑。[Changelog](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CHANGELOG.md#L310-L362) |
| v0.29.0 | 2026-09-05 | 两级 Agent 记忆、角色衍生、供应商失败原因可见、生成前资产完整性阻断、视频时长按能力收窄。[Changelog](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CHANGELOG.md#L216-L247) |
| v0.30.0 | 2026-09-10 | 使用记录 KPI/趋势/构成/异常关注与逐调用调查；参考图上限裁剪可见；脚本规划转正式脚本的机制继续收敛。[Changelog](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CHANGELOG.md#L154-L176) |
| v0.31.0 | 2026-09-23 | ComfyUI、端点市场、提示词模版/36 画风/最终输入预览、时间线剧本编辑、任务取消语义与安全加强。[Release](https://github.com/ArcReel/ArcReel/releases/tag/v0.31.0) |
| main（未发布） | 2026-09-24 | 剧本分集首尾原文展示、更多项目变更实时事件、视频请求事实单次求值、Agent 工具集单源声明、数据根分层、ComfyUI H3 规则与参考图裁剪修复。[v0.31.0…main](https://github.com/ArcReel/ArcReel/compare/v0.31.0...10f640c391912c0cd168aabdefbc36ffac9c8512) |

**I：演进方向判断。** 最近四个版本连续强化的不是单个模型，而是五条基础设施线：可插拔供应商、Agent 可持续工作、任务与产物可恢复、成本/失败可调查、提示词/输入可见。这说明 ArcReel 的产品重心正在从“生成流程齐全”转向“生产运行可信”。

## 7. 对比审计时必须逐项回答的问题

以下是给主比较报告的检查清单，不预设 LinglongLab 答案。

### 7.1 项目与工作流

1. 是否有服务端权威的制作状态和下一动作，还是 Agent/前端各自猜阶段？
2. 创作类型与生成模式是否正交，创建后是否有稳定迁移语义？
3. 脚本内容层和视觉提示词层是否分开，是否有低成本审核闸门？
4. 是否支持已确认脚本的增删镜头、局部重写与并发安全，而不覆盖用户精修？
5. 分集、场景、分镜/视频单元的身份和来源范围是否持久化？

### 7.2 资产与一致性

1. 角色、场景、道具、商品是否是一等领域对象，而不是上传文件标签？
2. 是否支持角色衍生、商品原图真实性锚点、全局库到项目副本？
3. 引用的资产缺失或超出模型参考图上限时，是阻断、显式降级还是静默丢弃？
4. 图片编辑是否保留版本与来源，还是覆盖原图/原提示词？

### 7.3 生成运行

1. 图片、视频、音频、长文本是否都有持久任务与批次模型？
2. 批量操作是否在任何任务创建前整体验证，还是边循环边计费？
3. “任务状态、逐项执行结果、产物时效、批量准入”是否被错误合并成一个状态？
4. 服务重启后如何区分续跑、重试、重新提交和仅重试下载？
5. 是否有任务唯一性与远端任务 ID，能够防重复点击和重复计费？

### 7.4 供应商平台

1. 是否在模型级表达参考图、尾帧、音频、时长、分辨率和任务类型能力？
2. 项目级覆盖、全局默认和单次选择的优先级是否统一？
3. 自定义供应商能否预览真实请求、离线验证响应、付费测试连接？
4. 是否支持 ComfyUI workflow 的参数绑定、能力推导、轮询、产物与错误语义？
5. 是否存在安全、可审阅、可更新的端点分发机制？

### 7.5 成本、产物与交付

1. 是否在执行前显示影响范围和预计费用，并要求跨档确认？
2. 是否能按供应商调用查看输入、响应、失败原因、来源、任务和费用？
3. 是否有正式产物清单与生成依据，能机械判断 current/stale/missing/blocked？
4. 已付费旧产物是否仍可用、可回滚、可导出？
5. 除 MP4 外，是否有字幕、音轨、版本选择、可编辑包或下游剪辑工程交付？

### 7.6 Agent 与协作

1. Agent 的项目写入是否只能通过工具，还是能任意改文件/数据库？
2. 是否有持久会话、断线续传、消息幂等、子智能体时间线和历史改写分支？
3. 用户偏好记忆、项目正式数据和 SDK transcript 是否被清晰分开？
4. 外部 Agent 是否和内嵌 Agent 使用同一状态与工具，还是旁路自动化？
5. 需要用户确认和付费的动作是否在 Agent 协议中有强制等待？

## 8. 未知项与不应做出的结论

- **U：实际视频质量、成功率、平均成本和速度。** 官方没有提供可复现的跨模型 benchmark；README 案例只能证明存在演示成片，不能证明批量生产质量或优于其他产品。[README 案例](https://github.com/ArcReel/ArcReel/blob/v0.31.0/README.md)
- **U：真实活跃用户、客户结构和商业收入。** 官方仓库的 stars/forks 是社区信号，不是活跃使用或商业规模；PRODUCT 明确没有用户数和客户材料。[PRODUCT](https://github.com/ArcReel/ArcReel/blob/v0.31.0/PRODUCT.md#L48-L55)
- **U：官方托管 SaaS。** 当前证据只验证开源自托管路径；不能据此绝对断言组织从未提供或不会提供托管服务，但官方文档没有公开的 SaaS 价格与购买流程。
- **U：CapCut 实际兼容性。** 官方明确“尚未验证”，不能自行用“剪映国际版”关系推断兼容。[剪映指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/jianying-export.md#L8-L18)
- **U：`main` 上新领域词是否都已有完整 UI。** 例如 2026-09-24 新增“剪辑时间线”术语，但正式 Release 与入门文档仍把不同模式分流到内建合成、剪映或下载片段；在出现明确 UI/发布证据前，不应宣称 ArcReel 已有覆盖所有模式的完整 NLE。[main 领域术语](https://github.com/ArcReel/ArcReel/blob/10f640c391912c0cd168aabdefbc36ffac9c8512/CONTEXT.md#L588-L604) / [已发布交付边界](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/getting-started.md#L370-L389)

## 9. 第一方来源索引

### 产品与发布

- [ArcReel README（v0.31.0）](https://github.com/ArcReel/ArcReel/blob/v0.31.0/README.md)
- [ArcReel PRODUCT（v0.31.0）](https://github.com/ArcReel/ArcReel/blob/v0.31.0/PRODUCT.md)
- [v0.31.0 Release](https://github.com/ArcReel/ArcReel/releases/tag/v0.31.0)
- [CHANGELOG（v0.31.0）](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CHANGELOG.md)
- [v0.31.0 到 2026-09-24 main 的比较](https://github.com/ArcReel/ArcReel/compare/v0.31.0...10f640c391912c0cd168aabdefbc36ffac9c8512)

### 官方用户与开发文档

- [创作流程与模式](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/workflows.md)
- [完整入门教程](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/getting-started.md)
- [供应商与模型配置](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/providers.md)
- [接入 ComfyUI workflow](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/comfyui.md)
- [市场](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/market.md)
- [剪映草稿导出](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/jianying-export.md)
- [FAQ](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/guide/faq.md)
- [架构说明](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/dev/architecture.md)
- [部署与运维](https://github.com/ArcReel/ArcReel/blob/v0.31.0/website/docs/ops/deployment.md)

### 官方领域与 Agent 资料

- [领域术语 CONTEXT](https://github.com/ArcReel/ArcReel/blob/v0.31.0/CONTEXT.md)
- [ADR 目录](https://github.com/ArcReel/ArcReel/tree/v0.31.0/docs/adr)
- [外部 Agent 安装指南](https://github.com/ArcReel/ArcReel/blob/v0.31.0/public/agent-installation-guide.md)
- [公开 Agent skills](https://github.com/ArcReel/ArcReel/tree/v0.31.0/skills)

## 10. 一句话供主报告引用

ArcReel 的本质不是“多模型 AI 视频生成器”，而是一套面向单人创作者的开源自托管生产操作系统：它用服务端权威计划、审核闸门、资产与产物来源、持久队列、费用前置、模型能力适配和可编辑交付，把小说/剧本/商品素材逐步变成可恢复、可追踪、可继续后期的视频项目；其主要短板是单管理员、内部成片能力并非全模式覆盖、独立 TTS 仅覆盖旁白路线、移动与 CapCut 未验证，以及部署和供应商配置对非技术用户仍有明显门槛。
