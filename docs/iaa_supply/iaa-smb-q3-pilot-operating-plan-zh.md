# Moloco IAA SMB 中小客户拓展方案 — Q3 试点工作方案

> Q3 Pilot｜项目统筹：Owen｜版本：v1.0｜2026-08-18

## 1. 目标

通过识别有价值的中小 IAA 开发者，推动 Moloco SDK 接入与 UA 拓展，形成可验证的 Demand–Supply 增长闭环；同时扩大 Moloco 的优质 Publisher 流量覆盖。

Q3 的目标是跑通一套可复制的联合拓展机制，而非单纯扩大名单或账户数量：

1. 建立从客户发现、内部筛选、Agency 推进到数据验证的标准流程；
2. 推动高潜客户完成 SDK / UA 机会确认与实际推进；
3. 完成至少一个可验证的 Demand + Supply 双边案例；
4. 验证 GatherOne 的执行能力，并据此决定后续优化或扩展。

## 2. 团队分工

| Workstream | DRI | 主要职责 |
|---|---|---|
| 项目统筹与数据闭环 | Owen | 项目推进、客户优先级、名单质量、跨团队协调、风险升级、复盘与 leadership update |
| Non-Gaming 机会识别 | Daniel | 识别非游戏 SDK / IAA 高潜机会，提供业务判断和关系支持 |
| Gaming 机会识别 | Clara | 识别游戏类高潜机会，提供业务判断和关系支持 |
| Agency 协作 | Michael / Anita | 对接 GatherOne、推动 Moloco 引荐、收集并路由商务支持需求 |
| Supply Enablement | Owen / Daniel / Morden / Jim / 指定 SME | Supply 客户信息输入、SDK 培训、材料审核、技术答疑与升级 |
| Agency 执行 | GatherOne（佳佳 + 销售 owner） | 客户匹配、销售分配、客户 pitch、进展更新、自有线索提交 |

原则：Moloco Sales 主要负责关系判断和牵线；GatherOne 负责中小客户的日常拓展与推进。每个执行中的 Bundle 必须有唯一的 GatherOne owner 和明确的下一步。

## 3. 工作流程

| 步骤 | Owner | 核心动作 | 输出 / 完成标准 |
|---|---|---|---|
| 1. 发现与筛选 | Owen；Daniel / Clara 协作 | 月度更新 Intelligence 数据，结合 SensorTower、Moloco SDK/UA、Supply 信息筛选客户；GatherOne 也可提交自有线索 | 每个候选 Bundle 有数据日期、优先级和 Publisher 信息 |
| 2. 内部校验与优先级 | Owen | 判断客户是否已有 Moloco 关系、适合的商业路径和是否进入 Q3 队列；必要时请 Growth / Supply 判断 | `Qualified / Hold / Exclude`，并明确 `SDK-first / UA-first / Co-win` 路径 |
| 3. 关系判断与交接 | Michael；Growth / Sales 协作 | Moloco 关系人选择引荐、保留或释放给 GatherOne；Michael / Anita 完成交接 | 每个入池 Bundle 有 team route、Moloco owner（如有）和跟进状态 |
| 4. GatherOne 拓展 | GatherOne 销售 owner | 数据库匹配、销售分配、客户触达和 pitch；持续更新客户反馈 | 有 owner、stage、last update、next action |
| 5. 支持、上线与闭环 | GatherOne + Michael/Anita + Supply + Owen | 推进 SDK / UA；技术和商务问题；验证上线、覆盖率、消耗及SDK Media cost | 记录支持账户和产品数据、奖励资格和后续状态；已结束客户有明确结论 |
| 6. 现场 pitch 复盘 | Michael/Anita + GatherOne；Owen 统筹 | 共同选取重要机会 shadow SDK / IAA pitch，记录客户问题、话术有效性和支持卡点 | 形成 pitch 复盘与改进行动，回写 Playbook / FAQ |

### GatherOne 执行规则

1. **接收与分配：** GatherOne 在收到 Bundle 后 5 个工作日内标记 `Accepted / Needs Info / Duplicate / Rejected`。每条 Accepted Bundle 必须有唯一 sales owner、stage、首个动作和日期。
2. **客户 pitch：** 根据客户情况选择 `SDK / IAA-first`、`UA-first`、`Co-win` 或 `Not a fit`。客户已存在 Moloco owner 时，先协同关系人，不重复触达。
3. **推进记录：** `Contacted` 必须写明触达日期、方式、客户反馈和下一步；SDK / UA 推进必须记录 blocker、support owner 和 target date。
4. **上线与关闭：** SDK live、覆盖率、测试、Supply 消耗或 UA 进展必须有可追溯事实；不再推进的客户必须写明原因。
5. **Shadow pitch：** Michael / Anita 与 GatherOne 在双周 review 中选取少量重要客户共同旁听 SDK / IAA pitch。GatherOne 销售主导客户沟通；会后 1 个工作日内记录客户异议、有效话术、未解决 blocker、所需支持和下一步，并更新 FAQ 或 pitch material。

### Bundle Lookup 与 Growth Review

Daniel / Clara 使用 Prospect Tracker 的 **Bundle Intelligence Lookup** 协助判断机会，不承担 SMB 客户的日常销售跟进。

- 一次输入 1–20 个 Bundle。工具先检查 prospect 历史和当前 Moloco 历史；两者均无时才补充按需 Intelligence 数据。结果只写入 `tempory_query`，不自动进入正式队列。
- Review 时依次检查：身份与现有 owner、下载规模与趋势、paid share / 活跃 UA 网络、变现模式、Supply BD、Moloco 历史和当前季度状态。
- Daniel / Clara 对需 review 的 Bundle 回传五项内容：`Recommendation`（SDK / IAA-first、UA-first、Co-win、Observe 或 Not a fit）、一句话 `Rationale`、`Relationship support`、建议 owner 与 `Next action`。
- Lookup 显示 `Already in this quarter` 或 `Existing Moloco relationship` 时，优先协同现有 owner；`Qualified internal prospect` 交由 Owen 决定入池；`Needs review` 必须说明缺失信息、核实人和回看日期。

### 支持升级路径

- 客户关系、引荐、商务协同：Michael,Owen
- 客户优先级、数据判断、名单问题：Owen,Daniel,Clara
- SDK 集成、mediation、技术疑难：Supply team
- 需要跨团队决策、影响客户上线或超过 SLA：Owen 发起升级
- Supply team对接：Daniel,Owen

## 4. Tracker 与文档使用规则

- 本文档：项目级目标、角色、流程、节奏和决策规则。
- External Tracker：每个 Bundle 的 owner、进展、下一步和支持请求；每次有效客户动作后更新。每个 active Bundle 至少维护 sales owner、stage、最新客户反馈、next action、due date，以及 blocker / support needed（如有）。
- Internal Tracker：数据依据、优先级、内部关系、Supply 信息与激励判断。
- SDK Playbook / FAQ：客户 pitch、接入路径、常见问题和技术升级说明。

同一季度按 `quarter + bundle` 去重。后续月度数据只更新已有 Bundle 的 Intelligence 字段；不覆盖人工填写的 owner、客户进展、下一步或支持记录。所有 active Bundle 至少在双周 review 前更新一次；未分配、无下一步或超过 14 天未更新的 Bundle 进入 review。

## 5. Supply 支持与 Enablement

Supply 不承担 SMB 客户的日常销售拓展；其职责是指导协助 GatherOne 能独立完成标准 SDK pitch 和接入推进，并对重要或复杂问题提供明确支持。

| 支持事项 | 当前原则 | 需确认的责任 / 产出 |
|---|---|---|
| Onboarding bonus | 拟以 SDK live 且用户覆盖率 >80% 作为奖励资格；奖励可与 Demand 侧 IAA MDF 并行；每个 Bundle 的工作测算记录在 Internal Tracker | Yoni 书面确认金额逻辑、支付时间、审批与例外；工作测算不是对客户的承诺，GatherOne 只传递已确认政策 |
| 技术支持人力 | GatherOne 负责日常客户推进；Supply 负责培训、标准技术问题、疑难问题升级和重要客户的必要支持 | 指定 primary / backup SME、支持边界、响应 SLA，以及何种情况由 Supply 参加客户会议 |
| SDK 培训与知识库 | 面向 GatherOne 销售和运营，覆盖标准 pitch 与接入路径 | 完成培训、材料 / 录屏、FAQ、中文接入文档和升级入口 |
| 账户管理 | 需支持 Agency 管理开发者账户的实际操作 | Morden / Xiaowen 确认 admin 权限、单一或多 publisher account 结构及操作流程 |

培训内容至少包括：

1. Moloco SDK 整体介绍；
2. IAA SDK 接入效果与案例；
3. IAA SDK 常见问题与排查路径；
4. 指定答疑 owner，以及特殊问题的升级机制。

现有中文资源：

- [Moloco Publisher Help Center](https://help.publisher.moloco.com/hc/zh-cn)
- [MAX 聚合接入指南](https://help.publisher.moloco.com/hc/zh-cn/articles/26777419191063-%E4%BD%BF%E7%94%A8-AppLovin-MAX-%E5%BC%80%E5%A7%8B-App-%E5%86%85%E7%AB%9E%E4%BB%B7)
- [Unity LevelPlay 聚合接入指南](https://help.publisher.moloco.com/hc/zh-cn/articles/26777434783255-%E4%BD%BF%E7%94%A8-Unity-LevelPlay-%E5%BC%80%E5%A7%8B-App-%E5%86%85%E7%AB%9E%E4%BB%B7)

## 6. Q3 关键控制项与衡量标准

### 近期需明确的事项

| 事项 | Owner | 完成标准 |
|---|---|---|
| Onboarding incentive | Yoni | 明确奖励资格、金额逻辑、支付流程、支付时间和例外情况 |
| 账户管理方式 | Morden / Xiaowen | 明确 Agency admin 权限及账户管理流程 |
| Supply 支持模式 | Morden / Jim | 明确 SME 人选、支持边界、SLA，以及重要客户是否参加客户会议 |
| SDK 培训与知识库 | Supply + Michael | 完成培训，发布材料，并指定技术答疑 owner |
| Pipeline 完整性 | Owen + GatherOne | 每个 active Bundle 都有 owner、进展、下一步和支持需求 |
| Shadow pitch 复盘 | Michael + GatherOne + Owen | 选取重要客户共同旁听 SDK / IAA pitch，沉淀客户异议和改进动作 |

### Q3 成功指标

- 高质量 pipeline：P1/P2 客户接入率；
- Supply 结果：SDK live、覆盖率满足奖励要求的 Bundle、上线后的实际消耗；
- Demand–Supply 结果：同一开发者具备可验证的 Supply 与 Moloco UA 证据；
- 执行能力：GatherOne 更新及时性、支持请求解决效率、至少一个可复盘的双边成功案例。

## 7. 运行节奏

- 双周 Pipeline Review：Owen、Michael、GatherOne；聚焦客户进展、缺失 owner、阻塞和需决策事项。
- 月度 Leadership Update：汇报 pipeline 质量、SDK / UA 结果、关键案例、风险及所需支持。
- Technical Escalation：按需进行；技术问题必须包含 Bundle、OS、mediation、集成阶段、问题描述和客户 deadline。

## 8. 配套执行文档

以下文档服务于本方案，但不重复本方案的项目级规则：

| 文档 | Owner | 用途 |
|---|---|---|
| [Prospect Identification & Prioritization SOP](prospect-identification-and-prioritization-sop-zh.md) | Owen | 月度候选客户识别、内部校验、优先级与入池判断 |
| [GatherOne IAA SDK Playbook](gatherone-iaa-sdk-playbook.md) | Supply + Michael | SDK pitch、接入、FAQ 与技术升级 |
| [Co-win List Field Spec](co-win-list-field-spec.md) | Owen | Tracker 字段、数据边界与工具实现约定 |

> 客户级状态以 Tracker 为准；项目级规则、跨团队决策和升级以本文档为准。
