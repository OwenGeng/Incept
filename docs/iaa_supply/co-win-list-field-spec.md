# Demand & Supply Co-win List 字段规范

> 目的：让表格负责记录客户级事实和进展，让运行规范负责记录流程，让 SDK 手册负责提供可复用知识。

## 1. 字段分组

### A. 识别字段

| 字段 | 规则 |
|---|---|
| Quarter | 固定格式，如 `2026 Q3` |
| Snapshot date | 季度名单生成日期 |
| Company name | 公司归组名称 |
| China entity | 中国主体；未知时写 `Unknown`，不要留空后无法区分 |
| Publisher name | 数据源中的发行方名称 |
| Bundle | 主要去重键，必须尽量完整 |
| Base | 城市/地区；未知时标记待核实 |
| Gaming / Non-Gaming | 固定下拉选项 |

### B. 来源与优先级

| 字段 | 规则 |
|---|---|
| Lead source | `SensorTower` / `GatherOne self-sourced` / `Moloco referral` / `Other` |
| Priority | 使用项目统一的优先级，如 `P1`、`P2`、`P3`；同时保留推荐理由 |
| UA signal | 记录数据来源或判断依据 |
| IAA / SDK signal | 记录广告变现或 SDK 潜力依据 |
| Moloco history | `No` / `Existing` / `Historical` / `Unknown` |

### C. 归属与推进

| 字段 | 规则 |
|---|---|
| Moloco sales owner | 只有实际认领或需要引荐时填写 |
| GatherOne sales owner | GatherOne 分配销售后填写 |
| Claim status | `Pending` / `Claimed` / `Released to GatherOne` / `Reserved` |
| Stage | 使用固定状态值，见下表 |
| Last update | 最近一次有效动作或结论 |
| Next action | 下一步具体动作，不能只写“跟进” |
| Next action due | 下一步日期 |
| Last updated date | 最近更新时间 |

### D. 支持与闭环

| 字段 | 规则 |
|---|---|
| Support needed | `None` / `Sales intro` / `Business` / `SDK technical` / `Data` / `Other` |
| Blocker category | `No contact` / `No response` / `Technical` / `Commercial` / `Ownership` / `Other` |
| Support owner | Michael、Supply 或其他明确负责人 |
| SDK status | `Not assessed` / `Evaluating` / `In progress` / `Live` / `Not applicable` |
| UA status | `Not assessed` / `Evaluating` / `In progress` / `Live` / `Not applicable` |
| Launch / spend evidence | 链接、日期或数据口径；如有真实消耗，以数据为准 |
| Update | 用短句记录本次变化，不写长篇聊天记录 |

## 2. 状态定义

| 状态 | 进入条件 | 离开条件 |
|---|---|---|
| Candidate | 仅完成数据筛选 | 通过校验进入季度名单，或被排除 |
| Pending Claim | 已进入名单，等待 Sales 判断 | Claimed / Released to GatherOne |
| Assigned | 已明确执行 owner | 有实际触达 |
| Contacted | 已完成有效触达 | 客户有反馈或进入 No Response |
| Opportunity Confirmed | 客户确认有明确机会 | 进入 SDK/UA 推进或关闭 |
| SDK/UA In Progress | 已进入评估、开发、测试或商业推进 | Launched / Blocked / Closed |
| Launched | 有上线或真实消耗证据 | 进入持续增长追踪 |
| Blocked | 明确存在阻塞且已填写支持请求 | 解除阻塞、转交或关闭 |
| No Response | 按项目规则完成多次触达仍无响应 | 新反馈后回到 Contacted |
| Not a Fit | 明确不符合项目目标 | 一般不重新打开，除非条件变化 |
| Closed | 已完成、放弃或转入其他流程 | 仅在出现新机会时建立新记录 |

## 3. 认领规则

1. Sales 认领的是“关系和引荐责任”，不是自动认领 GatherOne 的全部日常推进。
2. GatherOne 认领的是“规模化拓展和更新责任”，不是替 Moloco 承诺技术或商业条件。
3. 同一 Bundle 只能有一个当前执行 owner；Moloco 关系人可以作为协作 owner 同时保留。
4. 认领窗口结束且无明确保留理由，默认释放给 GatherOne。
5. 任何转交必须在表格写明转交日期、原 owner、新 owner 和下一步。

## 4. 更新质量检查

每次双周会前检查：

- 是否有 owner；
- 是否有最近更新时间；
- 是否有下一步和日期；
- `Blocked` 是否有阻塞类别和支持负责人；
- SDK/UA 状态是否与实际进展一致；
- 是否存在重复 Bundle；
- 是否有超过 14 天未更新的 Stale 记录。
