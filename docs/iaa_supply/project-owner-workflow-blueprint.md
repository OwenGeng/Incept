# IAA × GatherOne 项目 Workflow Blueprint

> 项目负责人工作底稿｜版本：v1.0｜适用：2026 Q3
>
> 本文档先定义项目如何运行，再决定表格怎么长。表格、知识库、培训和汇报都必须服务于这些 workflow。

## 1. 先确定项目是什么

这个项目不是“把一批客户交给 GatherOne”，也不是“维护一张客户表”。它是一个多方协作的客户激活系统：

```text
发现机会 → 判断机会 → 分配责任 → 客户触达 → SDK / UA 推进 → 上线验证 → 数据闭环 → 复盘迭代
```

项目的最小工作单位是：

> 一个 Company 下的一个 Bundle，对应一个明确的商业动作、一个当前执行负责人、一个下一步动作和一个验证结果。

同一个公司可以有多个 Bundle，但不能把公司级关系、Bundle 级推进和整个项目的统计混在一条记录里。

## 2. Workflow-first 的五条原则

### 原则一：每个 workflow 都必须有“完成定义”

没有完成定义的流程，最后一定会变成“大家都以为别人会做”。例如：

- “交给 GatherOne”不算完成；GatherOne 接受、分配销售、写入下一步，才算完成交接。
- “客户上线”不以手填状态为准；必须有 SDK live、首次收入或 UA spend 等证据。
- “需要 Supply 支持”不算工单；必须有问题描述、Bundle、平台、版本和期望回复时间。

### 原则二：一个动作只能有一个执行 owner

可以有多个协作人，但每个当前阶段只有一个 `execution owner`。否则所有人都参与，最后没有人真正负责。

### 原则三：所有 handoff 都必须被接收

交出方不能把名单放进表格后就视为交付；接收方必须明确 `Accepted / Needs Info / Rejected / Re-routed`。

### 原则四：流程解决问题，表格记录问题

表格不应该承担“临时想流程”的功能。遇到重复问题，先更新 workflow、FAQ 或字段规范，再更新表格。

### 原则五：先用小范围 pilot 验证，不要先清理全部历史数据

当前大表混合了多个用途。不要一开始就试图清理所有 2,000+ 行；先选一小批真实账户跑通全流程，再把验证过的字段和状态推广到全量。

## 3. Workflow 总目录

| 编号 | Workflow | 解决的问题 | 主要 owner | 核心输出 |
|---|---|---|---|---|
| W0 | 项目治理与节奏 | 谁召集、谁决策、如何升级 | Owen | 规则、会议、决策记录 |
| W1 | 月度数据发现 | 如何从 SensorTower 和 Moloco 数据找机会 | Owen / Intelligence | 候选机会池 |
| W2 | 资格判断与优先级 | 哪些值得进入本季度工作池 | Owen | Qualified / Hold / Exclude |
| W3 | 季度规划与名单冻结 | 本季度到底推进哪些客户 | Owen + Michael | 季度 snapshot |
| W4 | 关系认领与责任分配 | Moloco Sales、GatherOne 谁负责什么 | Michael | Accepted owner map |
| W5 | GatherOne 数据匹配与销售分配 | GatherOne 如何接收、去重、分配 | GatherOne | Agency action queue |
| W6 | Moloco Sales 牵线 | 如何低成本利用 Sales 关系 | Michael + Sales | Introduction / Release |
| W7 | 客户资格确认与 pitch | 如何判断客户真实需求和第一动作 | GatherOne | Opportunity brief |
| W8 | IAA / SDK onboarding | 如何从客户兴趣推进到 SDK 上线 | GatherOne + Supply | SDK plan / live evidence |
| W9 | UA opportunity onboarding | 如何推进 Moloco UA 机会 | GatherOne + Sales/UA | UA plan / spend evidence |
| W10 | 技术支持与升级 | SDK 问题如何进入 Supply 支持 | Michael | Resolved ticket / escalation |
| W11 | 状态追踪与数据闭环 | 如何避免表格变成静态名单 | Owen + GatherOne | Weekly status / launch evidence |
| W12 | 关闭、回收与重分配 | 无响应、冲突、低质量线索如何退出 | Owen + Michael | Closed / Recycled / Reassigned |
| W13 | 复盘与下一周期迭代 | 哪些筛选和动作真正有效 | Owen | Quarterly review / next changes |
| W14 | 知识库维护 | 如何让问题不重复发生 | Owen + Supply + Michael | FAQ / training updates |

## 4. 所有 Workflow 共用的标准格式

以后设计或检查任何 workflow，都按下面八个问题写：

1. **Trigger：** 什么事件触发它？
2. **Input：** 开始时需要哪些信息？
3. **Decision：** 需要做什么判断？
4. **Action：** 谁做哪些动作？
5. **Output：** 完成后产生什么结果？
6. **Owner：** 当前执行负责人是谁？
7. **SLA：** 多久完成或多久更新？
8. **Exception：** 卡住、信息不全或发生冲突时怎么办？

如果一个流程无法回答这八个问题，就还没有设计完成。

## 5. 核心工作流详表

## W0：项目治理与节奏

### 目标

让所有参与方知道什么时候同步、谁能做决定、问题应该去哪儿解决。

### 运行方式

- Owen 是项目 owner，负责项目目标、方法、名单质量和最终推进。
- Michael 是 GatherOne 的单一协调入口，负责合作、Sales 牵线和支持路由。
- GatherOne 有一个固定项目联系人，不能让不同销售分别向 Moloco 多个团队提需求。
- Supply 指定一个 primary SME 和一个 backup SME。

### 固定节奏

| 节奏 | 会议/动作 | 参加人 | 输出 |
|---|---|---|---|
| 每月 | 数据刷新与候选池检查 | Owen，必要时 Michael | 新候选池、异常列表 |
| 每季度 | 名单冻结与责任分配 | Owen、Michael、Sales、GatherOne | 季度 snapshot、owner map |
| 每两周 | 机会推进会 | Owen、Michael、GatherOne，必要时 Supply | Blocker list、next actions |
| 按需 | 技术升级 | Michael、Supply、GatherOne | 技术结论或预计处理时间 |
| 季度末 | 结果复盘 | 全部核心角色 | 转化、价值、问题和改进项 |

### 完成定义

- 有明确的项目 owner、agency owner、Supply SME；
- 有当前周期、目标和会议节奏；
- 重大决策和未解决问题有记录。

## W1：月度数据发现

### Trigger

进入新的自然月，或需要补充某个细分市场机会。

### Input

- SensorTower 下载、变现、UA 和 SDK 信号；
- Moloco SDK / UA / historical relationship 数据；
- 上一周期的排除名单和已关闭名单；
- Supply Top-2000 或其他内部覆盖信息。

### Action

1. Intelligence 按统一口径运行筛选。
2. 按 Company 和 Bundle 归组。
3. 补充中国主体、base、Gaming / Non-Gaming 和公司背景。
4. 标记 IAA、UA、Hybrid 或不确定。
5. 标记数据置信度和需要人工核实的字段。

### Output

`Candidate Pool`，不等于可直接给 GatherOne 的执行名单。

### Exception

- Bundle 无法确认：进入 `Data Exception`；
- 公司重复：合并到同一 Company view，但保留 Bundle 级记录；
- 已有 Moloco owner：进入 ownership review；
- 明显不符合条件：记录 exclude reason，不要直接删除。

## W2：资格判断与优先级

### 目标

把“有数据兴趣”变成“值得投入销售和 agency 资源的机会”。

### 每条机会必须回答

1. 为什么认为它有 IAA / SDK 潜力？
2. 为什么认为它有 UA 潜力？
3. 第一商业动作是什么：`IAA-first / UA-first / Co-win / Observe`？
4. 是否已有 Moloco 或其他团队覆盖？
5. 是否有可触达的公司或技术联系人线索？
6. 是否存在法律、产品、流量或合规排除项？

### 输出分类

| 分类 | 含义 | 下一步 |
|---|---|---|
| Qualified | 数据和商业动作足够清晰 | 进入季度规划 |
| Needs Review | 机会可能成立，但关键信息不足 | 指定核实人和截止日期 |
| Hold | 暂时不投入，但保留观察 | 下周期重新评估 |
| Exclude | 明确不适合或存在排除原因 | 记录原因，避免重复进入 |

## W3：季度规划与名单冻结

### Trigger

新季度开始前，或当季新增名单达到需要重新规划的程度。

### Action

1. Owen 从 Qualified pool 中选择本季度工作范围。
2. 每个 Bundle 标记主要商业动作和优先级。
3. 区分战略账户和规模化账户。
4. 生成季度 snapshot；snapshot 不能被后续月度刷新无痕覆盖。
5. 说明本季度的来源月、筛选口径、排除规则和目标。

### Output

`Q3 2026 Co-win Snapshot`，它回答“本季度我们决定推进什么”。

### 关键规则

- 不是所有候选都必须进入季度工作池；
- 进入工作池后必须有计划的 route；
- 一个 Bundle 只能有一个当前执行 owner；
- Company 级 relationship owner 可以与 Bundle 级 execution owner 不同。

## W4：关系认领与责任分配

### Trigger

季度 snapshot 发布。

### Action

1. Michael 组织 Moloco Sales 在限定时间内判断：`Claim / Introduce / Reserve / Release`。
2. Sales 只需要提供关系判断和引荐，不需要先写完整拓展计划。
3. Michael 处理冲突和战略账户保留。
4. 未被认领的规模化账户释放给 GatherOne。
5. 责任分配必须由接收方确认。

### Output

每个 Bundle 有：

- relationship owner；
- execution owner；
- route；
- claim date；
- accepted date；
- next action。

### Exception

- 两个 Sales 同时认领：Michael 在 2 个工作日内裁决；
- Sales 想保留但没有下一步：标记 `Reserved - Action Required`，不能无限期占用；
- GatherOne 不接受：必须写明原因，返回 W2 或重新分配。

## W5：GatherOne 数据匹配与销售分配

### Trigger

GatherOne 接收到已释放或已转交的季度名单。

### Action

1. GatherOne 用自己的数据库匹配公司、联系人和现有关系。
2. 以 Bundle 去重，以 Company 做归组。
3. 判断是否已有 GatherOne 销售关系。
4. 分配一个 GatherOne execution owner。
5. 标记客户的第一商业动作。
6. 在执行队列中写入首次动作和下次动作。

### Output

`Accepted Agency Action Queue`。

### 完成定义

不能只写“已收到名单”。必须同时具备：

- GatherOne owner；
- 匹配结果；
- 当前阶段；
- 下一步动作；
- 下一步日期。

## W6：Moloco Sales 牵线

### 目标

把 Sales 的价值压缩为高杠杆动作：识别关系、完成引荐、在关键节点参与。

### Action

1. Michael 发送最小化的 intro request。
2. Sales 判断是否认识客户或是否适合自己跟进。
3. 如适合，Sales 完成引荐并把 GatherOne 放入沟通链路。
4. 引荐后，GatherOne 负责日常 follow-up；Sales 保留战略节点参与权。
5. 若不适合，Sales 明确释放，不让客户停在 Pending Claim。

### 结束条件

- 已完成有效引荐；
- 或明确释放给 GatherOne；
- 或记录保留理由和下一次动作。

## W7：客户资格确认与 pitch

### 目标

避免 GatherOne 只完成触达数量，却没有确认真实商业机会。

### 第一次有效沟通需要确认

- 客户的业务和海外市场；
- 当前 mediation 和广告变现情况；
- 当前 UA 投放情况；
- Android / iOS / Unity 等平台；
- 技术接入决策人和商业决策人；
- 客户当前最关心收入增量、技术成本、竞价还是 UA 效果；
- 第一动作是 SDK、UA 还是双线推进。

### Output

一页 `Opportunity Brief`，至少包含：

- 客户现状；
- 机会类型；
- 关键联系人；
- 第一动作；
- 预计阻塞；
- 下一步会议或材料。

## W8：IAA / SDK onboarding

### Workflow

```text
SDK opportunity confirmed
→ confirm platform and mediation
→ select integration path
→ provide approved materials
→ customer technical evaluation
→ test / troubleshoot
→ go-live confirmation
→ verify first publisher revenue
```

### 分工

- GatherOne：客户推进、信息收集、会议安排、进度更新；
- Michael：路由、协调和升级；
- Supply：技术培训、文档审核、案例和疑难问题；
- Owen：流程和结果追踪。

### 完成定义

“SDK live”必须有客户确认、平台证据或数据证据中的至少一种；最好进一步记录首次 publisher revenue 日期。

## W9：UA opportunity onboarding

### Workflow

```text
UA opportunity confirmed
→ confirm app, market, budget, and goal
→ identify Moloco Sales / UA owner
→ define campaign readiness
→ launch or reject with reason
→ verify first spend
→ track D30 / D90 spend
```

### 关键区别

UA 机会不应被强行套入 SDK 流程。纯 IAP 客户可以走 UA-first；IAA / Hybrid 客户可以走 Co-win，但必须明确哪一边是先手。

## W10：技术支持与升级

### 支持入口

所有技术问题统一由 Michael 接收或路由；GatherOne 不要直接找多个 Supply 同事。

### 必填信息

- Company；
- Bundle；
- Platform；
- Mediation；
- SDK / mediation version；
- 当前阶段；
- 具体问题；
- 报错、截图、日志；
- 已尝试步骤；
- 客户会议或截止时间。

### 分级

| 级别 | 说明 | 处理方式 |
|---|---|---|
| L0 | 文档已有答案 | GatherOne 自助解决 |
| L1 | 业务或流程问题 | Michael 判断路由 |
| L2 | 标准技术问题 | Supply 在约定 SLA 内回复 |
| L3 | 影响上线或文档无法覆盖 | Michael 指定 Supply owner 和预计时间 |

### 完成定义

不是“Supply 回过消息”，而是：GatherOne 知道结论、客户获得下一步、必要内容已进入 FAQ。

## W11：状态追踪与数据闭环

### 每周动作

- GatherOne 更新 active opportunities；
- Owen 检查 stale、owner 缺失、重复 Bundle 和异常状态；
- 系统或数据查询验证 launch / spend；
- Michael 汇总需要跨团队决策的问题。

### 每条 active record 必须有

- current stage；
- execution owner；
- last action date；
- next action；
- next action due；
- blocker category；
- support owner；
- last update。

### 不能使用的更新方式

- 只写“跟进中”；
- 只写“客户有兴趣”；
- 只写“需要支持”；
- 用列名写 DDL 日期；
- 用手填 Launched 代替真实上线证据。

## W12：关闭、回收与重分配

### 关闭条件

- Not a fit；
- 客户明确拒绝；
- 合规或产品排除；
- 长期无响应且完成规定触达次数；
- 已转入其他 Moloco owner 或项目。

### 回收条件

- GatherOne 在规定周期内没有有效动作；
- owner 离职或无法继续；
- 支持请求长期无人处理；
- 客户需要战略 Sales 介入。

### 重启条件

- 新季度出现新的 UA / SDK 信号；
- 客户业务或联系人发生变化；
- 新的 Moloco product / support capability 解决了原阻塞。

关闭不等于删除。必须保留关闭原因和日期，避免下一周期重复消耗人力。

## W13：复盘与下一周期迭代

### 复盘不只看数量

每季度回答：

1. 哪些数据特征最能预测转化？
2. 哪些优先级实际没有价值？
3. Sales intro 是否缩短了触达周期？
4. GatherOne 哪类客户最容易推进？
5. 哪些 SDK 问题可以通过文档解决？
6. 哪些客户应该从名单中永久排除？
7. Supply 的支持投入是否产生了可复用资产？

### 推荐指标

| 层级 | 指标 |
|---|---|
| Input | qualified opportunities、source mix |
| Handoff | accepted rate、owner completeness、claim-to-intro rate |
| Activity | contacted rate、meeting rate、stale rate |
| Conversion | opportunity rate、SDK evaluation rate、SDK live rate、UA launch rate |
| Business | first publisher revenue、D30/D90 publisher revenue、first UA spend、D30/D90 UA spend |
| Efficiency | time to first action、time to live、support resolution time |

## W14：知识库维护

### 资料分层

1. **Sales one-pager：** 给 GatherOne 销售讲清楚客户价值和第一步。
2. **SDK quick guide：** 帮销售判断 MAX、LevelPlay 或其他接入路径。
3. **FAQ：** 记录高频业务和技术问题。
4. **Technical escalation template：** 让 Supply 一次拿到完整信息。
5. **Approved cases：** 只放 Supply 审核过的案例和效果数字。

### 更新规则

每次出现重复问题时，不只在群里回答；要判断应该更新流程、FAQ、表格字段还是培训内容。

## 6. 当前最应该先做什么

不建议现在直接把整张共享表“整理漂亮”。建议按以下顺序启动。

### 第一步：先定 6 个项目规则

由项目负责人先确定，不需要等所有人开会：

1. 项目最小单位是 Company + Bundle；
2. 每个 Bundle 必须有一个 execution owner；
3. 每个机会必须有一个 primary motion；
4. 所有 handoff 必须有接收确认；
5. 所有 active record 必须有 next action + due date；
6. 所有 launch / spend 结果尽量用数据验证。

### 第二步：选一批 pilot accounts

不要一开始覆盖全量。建议选择 10–20 个有代表性的 Bundle：

- 一部分有 Moloco Sales 关系；
- 一部分完全交给 GatherOne；
- 一部分 IAA / SDK-first；
- 一部分 UA-first 或 Hybrid；
- 至少包含一个可能遇到技术问题的客户。

Pilot 的目的不是产生最大收入，而是验证每个 handoff 是否顺畅。

### 第三步：只建立一张窄的 Pilot Execution Queue

从当前大表复制必要字段，不把 Top-2000、SQL、Lookup 和历史数据一起复制。Pilot 表只保留：

```text
Quarter
Company
Bundle
Lead Source
Priority
Primary Motion
Moloco Relationship Owner
GatherOne Execution Owner
Claim Status
Current Stage
Last Action
Next Action
Next Action Due
Blocker
Support Needed
Last Updated
Launch / Spend Evidence
```

### 第四步：跑完整个 W4–W11

用真实账户跑一遍：

```text
认领 → GatherOne 接收 → 销售分配 → 首次触达 → 资格确认 → SDK/UA 推进 → 支持 → 上线验证
```

每遇到一个问题，先记录它属于哪个 workflow，而不是立即增加一列。

### 第五步：Pilot 复盘后再改表

Pilot 结束时再决定：

- 哪些字段真的需要；
- 哪些状态太细或太粗；
- 哪些支持问题可以 FAQ 化；
- 哪些责任边界不清；
- 哪些步骤需要自动化；
- 哪些历史数据值得迁移。

## 7. 项目负责人需要保持的控制面板

作为项目负责人，你不需要每天追每个客户，但每周必须能回答这十个问题：

1. 本周期新增了多少 Qualified opportunities？
2. 其中多少已经进入季度工作池？
3. 多少已经被 Moloco Sales 或 GatherOne 接收？
4. 还有多少没有 owner？
5. 多少已经完成首次有效触达？
6. 多少是真正的 Opportunity Confirmed？
7. 多少卡在 SDK、UA、Sales intro 或客户无响应？
8. 哪些问题需要 Michael 升级？
9. 哪些 Bundle 已经有真实上线或 spend 证据？
10. 本周哪个 workflow 最容易出问题，应该改流程还是补资源？

如果这十个问题无法在 10 分钟内回答，说明项目控制面板或 workflow 还不够清晰。

## 8. 后续文档体系

建议最终只保留以下几类正式文档：

| 文档 | 用途 | 读者 |
|---|---|---|
| 本文档 | 项目主 workflow 和推进顺序 | Owen、Michael、核心协作人 |
| GatherOne Operating Model | 对外协作规则和责任边界 | GatherOne、Michael |
| GatherOne SDK Playbook | GatherOne 销售和技术入门 | GatherOne |
| Co-win List Field Spec | 表格字段和状态规范 | Intelligence、Michael、GatherOne |
| Quarterly Snapshot | 某一季度的客户工作范围 | 全部项目成员 |
| Quarterly Review | 结果、问题和下一周期决策 | Leadership |

## 9. 当前结论

项目现在最需要的不是更多数据，也不是更多功能，而是把“谁在什么时间基于什么输入做什么动作，产出什么结果，卡住后找谁”写清楚。

建议先以 W0–W5 建立项目骨架，再用 W6–W11 跑通一个 10–20 个 Bundle 的 pilot，最后用 W12–W14 做退出、复盘和知识沉淀。

当 workflow 跑通以后，表格应该自然变窄、字段自然固定、会议自然变短，领导汇报也会自然变成结果汇报，而不是解释表格为什么这么乱。
