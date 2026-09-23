# Intelligence 项目总览 — 给新对话线程的背景文档

> 这份文档是为了把 Linglong Lab 下 **Intelligence**（供给侧分析与cross-sell prospecting模块）这条业务线单独摘出来，作为一个独立对话线程的起点，和 Studio（图片/视频生成工具）那条线区分开，避免两个不相关的业务混在一条历史记录里讨论。
>
> 新线程可以直接说"读一下 `docs/iaa_supply/` 里的文档"来接上全部背景。这份文档是对已有历史文档的整理和串联，不是重新发明——原始细节仍以各个源文档为准，本文档结尾有索引。

---

## 1. 项目背景与目标

**业务由来**：领导希望团队去开拓中小规模的IAA（In-App Advertising，广告变现）客户，服务于Moloco的 **IAA飞轮项目**。

**IAA飞轮的运转逻辑**：一个IAA客户要真正给Moloco带来价值，需要两步都发生——
1. **供给侧（Supply）**：客户接入 Moloco 的发布者 SDK（publisher SDK），把自己的广告库存开放给 Moloco 的需求方（DSP）变现。
2. **需求侧（Demand）**：客户作为广告主，用 Moloco DSP 买量（UA，用户获取）。

两边任何一边缺失，飞轮就转不起来——只接SDK不买量，或者只买量不接SDK，都不是完整的飞轮闭环。所以团队要找的目标客户，精确定义是：**明显有买量预算/media cost很高，但目前既没接Moloco SDK、也没在Moloco上买量的产品和公司**——这些客户已经证明了自己有商业化能力和UA预算（在其他平台上花钱买量了），只是还没有被Moloco覆盖，是最容易转化的一批潜客。

**团队的角色**：不是直接做销售转化，而是用数据机制**识别**出这批高价值、目前未覆盖的客户和产品，把结果**交给agency**，由agency去做实际的触达和推进（因为中小客户体量分散、数量多，直接靠NBS/GM人力覆盖不经济，agency是主要的规模化触达渠道）。

---

## 2. 目标客户定义

### 2.1 硬性筛选条件（Discover 阶段，全部满足才入选）

| 条件 | 定义 | 目的 |
|---|---|---|
| 无 Moloco SDK | app级和公司级都没有SDK关系 | 供给侧缺口 |
| 无 Moloco UA | app级和公司级近90天都没有Moloco广告主消耗 | 需求侧缺口 |
| 出海为主 | 主力下载市场不是 CN/HK/TW/MO | 排除纯内地app（微信生态等） |
| 公司HQ在中国 | `final_hq_country` 为 CN/HK/TW/SG，或经GTM人工核实 | 聚焦中国出海开发者 |
| 有规模 | 近一个完整自然月下载量 ≥ 20,000 | 排除体量太小、不值得跟进的app |
| 有变现模式 | 有广告变现（IAA）或内购（IAP）或两者兼有（Hybrid） | 排除完全免费、无商业模式的app |

### 2.2 按变现类型分三份名单（List 4/5/6）

| 名单 | 类型 | 变现信号 | 对应销售动作 |
|---|---|---|---|
| **List 4** | IAA Cold | `has_ads=true, has_iap=false` | 先推 Moloco SDK 接入，再谈UA |
| **List 5** | IAP Cold | `has_ads=false, has_iap=true` | 直接推 Moloco UA，走ROAS话术 |
| **List 6** | Hybrid Cold | 广告+内购都有 | SDK+UA双机会，AM按情况判断；游戏类进一步按题材细分Hybrid-IAA/Hybrid-IAP |

**优先跟进顺序：IAA → Hybrid → IAP**——IAA/Hybrid客户一旦接入SDK就直接产生Moloco publisher侧收入，转化路径更短、更直接。

### 2.3 优先级打分（P1/P2/P3…）

IAA/Hybrid一侧（List 4/6）用的是"供给可见度"框架：
- **P1 供给可见（Supply Visible）**：Moloco DSP已经能通过open exchange看到这个app的广告库存——摩擦最小，话术是"我们其实已经在合作了"
- **P2 已接其他交易所SDK**：证明有接SDK的意愿，只是还没加Moloco
- **P3 多网络买量**：同时在3个以上竞品网络买量，预算和意愿都强
- P4-P7：依次是有限买量、大体量纯自然量、只用Google/Meta保守型、早期阶段

IAP一侧（List 5）用的是独立的一套优先级（因为纯IAP app不投广告，永远不会产生"供给信号"，如果沿用P1-P4会全部落入P4，埋没掉真正有UA预算的优质客户）：
- **P1 UA Ready**：月下载≥10万 + 已经在竞品网络买量（证明有UA预算）+ 有T1市场下载量（ROI空间大）
- **P2 T1 Scale**：月下载≥5万 + 有T1市场量
- **P3 Growing**：月下载≥2万
- **P4 Cold**：其余

排序依据：竞品UA网络活跃数 > 当月下载规模 > 月环比下载增长率。

---

## 3. 端到端工作流

```
DISCOVER → QUALIFY → ASSIGN → ONBOARD → TRACK GROWTH
```

1. **Discover（发现）**：每周/每月自动跑一遍BQ+SensorTower的筛选逻辑，产出按公司分组、带优先级标签的排名列表。
2. **Qualify（核实）**：Owen和相关团队复核P1-P3账号——是否已被现有Moloco account team覆盖、是否需要确认主体/地区、是否适合进入季度 co-win list。
3. **Assign（分配）**：季度名单进入 `demand & supply co-win list` 后，由 Moloco Sales 判断是否认识客户并完成认领/牵线；未认领的中小客户释放给 GatherOne，由 GatherOne 负责规模化拓展和日常跟进。头部/战略账号仍可由 Moloco Sales 保留主导。
4. **Onboard（上线）**：GatherOne负责客户日常推进，Michael负责合作与跨团队协调，Supply Team提供SDK培训、资料审核和疑难技术支持；IAA/Hybrid优先推进SDK，UA机会可并行推进。
5. **Track Growth（跟踪增长）**：以Bundle为最小追踪单位，结合表格更新和真实Moloco消耗数据观察首次上线、起量和后续增长，并在季度复盘中评估名单和分工是否有效。

---

## 4. 系统架构与已上线能力

- **前端**：Next.js，路由在 `apps/web/app/(supply)/`
- **后端**：FastAPI，`apps/api/app/routers/supply_smb.py`（前缀 `/api/v1/supply-smb`），业务逻辑在 `apps/api/app/services/supply_smb_live.py`
- **Cold Prospect Pipeline（独立脚本，每月跑一次）**：`apps/api/app/incept/save_cold_prospect_table.py` — BigQuery筛选 + SensorTower API补充信息 + Gemini做公司背景/中国主体识别 + P1-P3打分，写入 `ads-bpd-guard-sandbox.supply_smb.*`
- **Prospect Tracker / "Signal Desk"（独立的Google Apps Script小工具）**：`apps/prospect-tracker/`，是给销售在Pipeline产出的Google Sheet上做标注、跟踪outreach进度用的，不需要销售直接碰BigQuery/原始表

### 已上线功能一览

| 功能 | 状态 | 说明 |
|---|---|---|
| SDK/UA重叠三象限Top List | 已上线 | `sdk-no-ua` / `ua-no-sdk` / `no-sdk-no-ua` 三个视角，公司级+app级明细，带分页和筛选 |
| 详细分析页 | 已上线 | 三个象限各自的深度分析页 |
| Weekly Brief（AI周报） | 已上线，目前只覆盖`no-sdk-no-ua` | Gemini生成的摘要+漏斗步骤+优先级卡片+图表，单独请求不阻塞主页面 |
| Ask AI | 已上线 | 自然语言查询供给数据集 |
| AI Insights | 已上线 | 全局+分scope的AI洞察 |
| Bundle Compare | 已上线 | 上传外部CSV（广大大/SensorTower导出），自动比对Moloco BQ数据，打上诊断标签（见下） |
| Leads Tracking | 已上线 | 追踪cold-prospect线索的来源、团队路由、激活、转化，能回溯到真实Moloco消耗 |
| Xiaomi专属看板 | 已上线 | 单独账号的Intelligence页面 |
| Cold Prospect Pipeline | 已上线，每月跑 | 完整方法论见站内文档 `/docs/intelligence/cold-prospect-pipeline` |
| 中国主体/公司背景AI补充 | 已上线 | Gemini + Google搜索grounding，有缓存 |
| Moloco历史广告主匹配 | 已上线 | 24个月回溯，标记出"曾经是Moloco DSP广告主"的潜客 |
| Prospect Tracker独立小工具 | 已上线 | 标注表单、BQ新公司同步、每周上线状态检测、Agency名单导出 |
| 每周上线状态检测 | 已上线 | 每周一06:00自动检测`fact_dsp_core`近7天消耗，标记 Launched/Not Onboard |
| **Agency名单导出** | **已暂停** | 原因见第6节 |
| 供给团队Top-2000 BD排除/标记 | SQL已写，未合并 | 排除供给团队已经分配了BD的账号，标记出"未分配但在Top2000"的账号 |

### Bundle Compare 的诊断标签体系

给外部上传的每个bundle打标签：
- ✅ PROSPECT — IAA/Hybrid，无SDK无UA，应该出现在no-sdk-no-ua名单里
- ① HAS_SDK — 已是Moloco SDK发布者
- ② HAS_UA — 已是Moloco广告主
- ③ PURE_IAP — 纯内购，属于List 5目标
- ④ NOT_IN_ST — SensorTower无收录/bundle_id有误
- ⑤ FREE — 完全免费，无变现路径

---

## 5. 当前进展亮点（可用于汇报）

- Pipeline每月自动跑通，端到端覆盖"筛选→补充信息→打分→写库"，不需要人工从零拉数据。
- 24个月历史广告主回溯上线，能识别"曾经合作过、后来流失"的客户，这类客户比纯冷启动客户转化门槛更低。
- IAP独立打分框架解决了"纯内购app全部被埋没在P4"的问题，让List 5也能产出有效的优先级排序。
- Bundle Compare让运营人员可以直接拿外部数据源（广大大等）比对，不用等团队排期。
- Prospect Tracker把"标注/跟踪"这个日常操作从BigQuery/原始Sheet中解耦出来，销售不需要懂SQL也能用。

---

## 6. 已知问题 / 待决策事项

- **Agency名单导出功能已暂停**：线上Google Sheet的"Agency List" tab被人工加了新列（Onboarding Bonus、GatherOne销售、是否有增加Bundle、备注拓展情况等），和导出函数原本写的列对不上；为避免导出时覆盖掉人工填的数据，已把导出功能禁用（点了会报错而不是真的跑）。字段和状态的建议基线见 `docs/iaa_supply/co-win-list-field-spec.md`，后续需要再把这套规范落回 Apps Script/表格实现。
- **供给团队Top-2000 BD排除逻辑**：SQL已经写好，但按要求暂缓合并进主pipeline，不是技术卡点。
- **公司名匹配**：和供给团队BD目标名单的匹配是精确字符串匹配（`LOWER(TRIM(...))`），没有模糊匹配兜底，匹配率还没验证过。
- **Weekly Brief覆盖范围**：目前只给`no-sdk-no-ua`这一个象限做了周报，另外两个象限要不要做还没定。
- **广大大数据的定位问题**：实测244条bundle里64%落在"纯IAP"标签，说明广大大的选品本身偏工具/效率类订阅app，跟List 4的IAA导向天然不太匹配——未来可以考虑把广大大数据直接当List 5（IAP）候选池用，而不是拿去跟List 4比对。

---

## 7. 参考文档索引（原始细节以这些文件为准）

| 文档 | 内容 |
|---|---|
| `docs/linglong-progress/intelligence.md` | Intelligence模块的完整进度追踪表（功能状态、关键文件、已知问题、按日期的更新日志）——**这是最权威、更新最频繁的单一状态来源** |
| `docs/supply-smb-crosssell-project.md` | 项目最初的立项文档：目标客群定义、P1-P7优先级框架、五阶段工作流、各团队职责与价值、收入追踪框架、成功指标 |
| `docs/list4_5_6_logic.md` | List 4/5/6筛选与排除逻辑的技术细节，含全部数据源表名 |
| `docs/supply-smb-iap-and-external-data.md` | IAP独立优先级框架的设计理由；Bundle Compare外部数据接入架构的完整数据流 |
| `docs/bq-tables-reference.md` | 用到的BigQuery表结构参考 |
| `docs/prospect-engine-queries.md` | Prospect Engine相关SQL查询 |
| `docs/sensortower-api-reference.md` / `docs/sensortower-bq-reference.md` | SensorTower API和BQ数据接入参考 |
| `docs/AGENT_GUIDE_team_progress.md` | 团队间共享进度用的Google Drive同步机制说明（跨项目的通用工具，不是Intelligence专属） |

---

## 8. 给汇报准备的建议（供下一步讨论）

汇报给领导时，建议按这个顺序组织（具体怎么写、篇幅多长可以在新线程里细化）：
1. **一句话立项理由**：为什么要做（IAA飞轮需要双边打通，中小客户体量分散只能靠agency规模化触达）。
2. **怎么找到这些客户**：筛选逻辑一句话概括（有买量能力但没被Moloco覆盖），不用展开技术细节。
3. **系统能力**：pipeline每月自动跑、AI补充公司信息、优先级打分——重点强调"从人工拉数据变成自动化流水线"这个效率提升。
4. **已经交付了什么**：目前有多少条P1-P3的合格线索、有多少交给了agency、agency那边转化了多少（如果有数据的话，这是最有说服力的部分，需要从Leads Tracking或Prospect Tracker里拉实际数字）。
5. **卡点/需要领导支持的地方**：Agency名单导出待定列结构、Top-2000排除逻辑要不要合并——这些可以包装成"需要领导拍板的事项"。

**下一步**：如果要写正式汇报，建议先去Leads Tracking/Prospect Tracker里拉一版实际数字（多少条线索、多少个agency在跟、目前转化了几个），这是本文档目前缺的部分——历史文档里都是方法论和系统状态，没有"到目前为止实际产出了多少结果"的数字。
