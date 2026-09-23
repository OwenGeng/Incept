# Prospect Identification & Prioritization SOP

> 客户识别与优先级 SOP｜Owner：Owen｜适用：Moloco IAA SMB Q3 Pilot
>
> 本文定义“哪些客户进入季度执行队列，以及为什么”。客户日常推进不在本文维护，以 External Tracker 为准。

## 1. 目标与输出

每月将数据候选转化为可执行的 Q3 pipeline，并保证每个进入队列的 Bundle 都有清晰的优先级、商业路径和交接判断。

输出只有四种：

| 结果 | 含义 | 下一步 |
|---|---|---|
| Qualified | 值得进入当季执行队列 | 进入关系判断与 Agency 交接 |
| Needs Review | 有潜力，但缺少关键事实或关系判断 | 指定核实人和截止日期 |
| Hold | 当前不投入资源，但保留观察 | 下次月度刷新时重新评估 |
| Exclude | 明确不适合或已被充分覆盖 | 记录原因，不重复进入 |

## 2. 输入与刷新节奏

每月 Intelligence 更新完成后，Owen 从以下输入开始 review：

- `cold_prospect_app`：Bundle 级的市场、下载、UA、Moloco 与 Supply 信号；
- `cold_prospect_publisher`：Publisher 聚合视图，用于识别同一主体下的产品组合；
- 当前季度 Supply target snapshot：用于识别已有 Supply 覆盖和 BD owner；
- 当前季度 External / Internal Tracker：用于避免重复入池，并保留已有客户动作；
- GatherOne self-sourced submissions：Agency 提供的候选 Bundle。

数据先进入内部候选池；未完成校验前，不直接加入 GatherOne 执行队列。

## 3. 识别与校验步骤

### Step 1：确认 Bundle 与数据完整性

- Bundle、App、Publisher、OS 和 `data_as_of` 可识别；
- 检查最近完整月下载、下载环比、付费下载占比、活跃 UA 网络和 MAU（如有）；
- 检查公司 / Publisher 是否已有中文主体、网站或可用联系路径；
- 数据缺失或 Bundle 无法确认时，标记 `Needs Review`，不凭名称猜测。

### Step 2：确认商业机会

重点判断以下问题：

1. 是否具备 IAA / SDK、UA 或双边机会？
2. 是否已经有 Moloco SDK、UA 或历史商业关系？
3. 该客户更适合 `IAA-first`、`UA-first`、`Co-win` 还是 `Observe`？
4. 是否已有 Supply BD、Moloco Sales 或 GatherOne 的有效关系？
5. 是否存在明显的地域、产品、商业或归属冲突？

### Step 3：确定优先级

系统优先级是数据排序的起点，不替代业务判断：

| 系统优先级 | 当前信号 | Owen 的处理 |
|---|---|---|
| P1 | IAA / Hybrid App，付费下载占比 ≥50%，且第一下载国不为中国、印度、孟加拉、伊拉克或巴基斯坦 | 优先完成关系判断和 Agency 路径 |
| P2 | 付费下载占比 ≥20%，且第一下载国不为中国、印度、孟加拉、伊拉克或巴基斯坦；纯 IAP App 最高为 P2 | 进入正常 Q3 review 队列 |
| P3 | 数据信号较弱、缺少关键字段或暂不适配 | 仅在有强关系或明确补充信息时推进 |

`active_ua_networks` 仅作为辅助判断信号，不再作为 P1 / P2 的硬性门槛。首要下载市场统一按 SensorTower 当前月与上月累计下载量计算；若该市场属于中国、印度、孟加拉、伊拉克或巴基斯坦，App 保留为 P3 观察，不进入 P1 / P2 执行队列。判断时同时考虑下载规模与趋势、变现模式、Publisher 产品组合、可触达性及现有 Moloco 覆盖。不要仅因下载量大或奖励金额高就进入执行队列。

### Step 4：决定入池与商业路径

对每个 Qualified Bundle 写入以下最小决策：

- `priority` 与一句话理由；
- `route`：`IAA-first / UA-first / Co-win / Observe`；
- 是否需 Moloco intro，以及建议关系 owner；
- 是否适合释放给 GatherOne；
- 下一个责任人和完成日期。

只有完成以上字段的 Bundle 才能进入当季执行队列。

## 4. 月度入池规则

- 同一季度以 `quarter + normalized_bundle` 去重；
- 新 Bundle：经内部校验后追加到当季队列；
- 已存在 Bundle：只刷新 Intelligence 事实字段和 `latest_data_as_of`，不新增重复行；
- 人工字段（owner、stage、客户反馈、next action、support）不得被数据刷新覆盖；
- 同一中文主体或 Publisher 的多个 Bundle 可归组 review，但仍按 Bundle 分别决定是否推进。

## 5. GatherOne 自有线索

GatherOne 提交的客户必须至少包含 Company、App、Bundle、OS、GatherOne owner、关系依据和 IAA / UA 潜力说明。

Owen 使用 Bundle Lookup 和内部数据完成核验后：

- 已在队列：标记 duplicate，并回到现有 owner；
- 有数据且符合标准：按正常流程进入 Qualified / Hold / Exclude；
- 暂无数据：标记 Needs Review，先补充 Bundle、OS、Publisher 或客户背景。

## 6. 例外与升级

| 情况 | 处理方式 |
|---|---|
| 已有 Moloco 或 Supply owner | 不直接外发；先由 Michael / 对应 owner 判断引荐、保留或释放 |
| Top 2000 / 战略账户 | 标记并由 Owen 与 Supply / Sales 判断路径，不自动排除或自动交给 Agency |
| 数据与实际客户信息冲突 | 以可验证信息为准，记录待复核原因 |
| 同一客户多个 Publisher 名称 | 用中文主体、网站和客户确认辅助归组；不要仅根据名称相似自动合并 |
| 无明确下一步 | 不计入 active pipeline，回到 Needs Review 或 Hold |

## 7. 月度检查清单

- [ ] 数据已刷新，`data_as_of` 清晰；
- [ ] 新增 P1 / P2 Bundle 已完成内部 review；
- [ ] 已存在 Bundle 未重复加入队列；
- [ ] 每个 Qualified Bundle 有 priority、route、owner 建议和下一步；
- [ ] GatherOne 自有线索已给出审核结论；
- [ ] 异常、冲突和战略账户已进入 action register。

> 详细客户状态、客户沟通和支持请求只在 Tracker 中维护；本 SOP 只定义 Owen 的筛选与入池动作。
