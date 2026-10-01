# AI Video 与 ArcReel 对比：哪里好，哪里不好

- **对比对象**：LinglongLab AI Video（`apps/api/app/ai_video/` 约 3.6 万行 Python，`apps/web/components/ai-video/` 约 4.3 万行 TS）；ArcReel `10f640c3`（参考本目录 01–07 章）。
- **代码版本**：LinglongLab HEAD `5b1fa03`，加上 2026-09-25 上午的工作区。审查期间工作区一直有人在改，部分结论可能已经被修掉，见各处注明。
- **方法**：对 `docs/ai-video-arcreel-parity-plan.md` 和 `docs/ai-video-ad-core-scope.md` 里的每一个 `[x]`，都逐项核实四件事：代码里是否有真实逻辑、是否持久化、活跃的 `/ai-video` 界面是否能用到、是否有测试。计划里的勾选状态不直接采信。
- **实测**：后端测试 343 过、1 失败；`tsc` 通过；另外用 FFmpeg 做了真实渲染，复现了两个音频 / QA 缺陷（见 §4.3）。

> 本文遵循 docs/linglong-arcreel-parity-method.md：不含从 ArcReel 复制的代码、提示词或 schema。

## 1. 一页结论

**产品方向上，AI Video 在广告场景比 ArcReel 更对路。** 结构化的广告 Brief、商品 lineage、多候选 take 显式采用，以及服务端的"剪辑 → 确定性渲染 → QA → Final"闭环，这些 ArcReel 要么没有，要么做得更弱。

**工程可信度上，AI Video 明显不如 ArcReel。** ArcReel 最有价值的是"不变量"：不会重复扣费、重启后能安全恢复、过期状态按内容计算、每个付费动作都要先确认。计划把这些标成了 `[x]`，但多数只做到"表结构和接口都有"，还没做到"行为上确实成立"。

另外有三个跨领域的问题，比单项功能的差距更要紧：

1. **广告核心 P0 的大部分代码还没进 git。** `production_control`、`production_execution`、`editing`、`media_qa`、`products`、`project_research`、`integration_hub`、`automation`，前端的 `ProductionTab`、`ProductsTab`、`ResearchTab`，以及这两份计划文档本身，全部是未跟踪文件（`??`）。HEAD 里并没有 Plan / QA / Delivery 控制面。代码有丢失风险，所有 `[x]` 也没有可复现的证据。
2. **存在一个高危安全问题，已人工核实，目前仍未修复。** 自定义 endpoint 的 `credential_env` 可以填任意环境变量名，代码用 `os.getenv` 读出来，拼进请求头，发往用户填写的公网地址（`services/studio/integration_hub.py:248-254`，schema 只校验名字格式，见 `schemas/studio/integration_hub.py:19`）。任何登录用户都能借此把 `INCEPT_INTERNAL_API_KEY`、`OPENAI_API_KEY` 这类密钥发到自己的服务器上。SSRF 已经在修：私网和元数据地址拦截、重定向关闭都做了，但 DNS rebinding 和"没有供应商白名单"这两个口子还在。
3. **广告核心还没提交、也没上生产，就已经做了 P1 集成层**，包括 MCP 加 API Key、外部 Agent、可以接任意供应商的自定义 endpoint、ComfyUI 和 endpoint market。这和 `linglong-arcreel-parity-method.md` 原来的范围锁、本目录研究的结论（04 §2.7、07 §16）都相冲突，也会显著扩大 AI Gov 和 Security 的审查范围：MCP 属于新增 Connector，会触发重新分级；可以接任意供应商，就绕开了 Zip 采购流程。

## 2. 各领域评分

| 领域 | 相对 ArcReel | 一句话 |
| --- | --- | --- |
| 广告 Brief、研究、创意方向 | **更好** | 字段完整：CTA、Legal、禁用表达、品牌色和字体、安全区、预算都有；研究结论是结构化的。 |
| 商品与资产 | 模型更好，注入逻辑更差 | 商品有数据库 lineage；但生成时原图不一定进入参考图，而且会把项目里所有商品注入每一个镜头。 |
| 剧本、Shot Plan、Revision | **更差** | Revision 只是一份记录，不是生产依据。生成读的是随时可以改的镜头卡。 |
| 产物过期状态（currency） | **更差** | stale 是存在库里的字段，只在"批准新版本"时改一次；指纹从来没有被拿来比对过；没有测试。 |
| Keyframe 与 Take 选择 | **更好或持平** | 候选、已采用、已废弃三态显式区分，比 ArcReel 的"只有一个当前版本"更适合广告选片。 |
| 任务可靠性与恢复 | **明显更差** | 有重复扣费风险，没有重启恢复，单镜头路径绕过了所有关卡。 |
| 费用与用量 | 部分更好，整体更差 | 价目带来源和核实日期，报价指纹会和确认绑定；但账本按任务记而不是按调用记，报价用到的参数也不是实际发给模型的参数。 |
| 剪辑、渲染、QA、交付 | 闭环更好，质量更差 | ArcReel 没有服务端成片。AI Video 的闭环是有的，但音频有实测 bug，QA 里有两项是假检查。 |
| Agent | 能力更弱，风险面更小 | 项目 Agent 没有工具，只能给建议；确认靠客户端传一个布尔值。 |
| MCP、Key、自定义 endpoint、market | 结构更好，安全更差 | Key 有 scope、只存哈希、可撤销；但存在高危的凭证外泄漏洞，market 也不是真正的远程来源。 |
| 身份与审计 | **更差** | 后端从不读取已登录用户的身份，批准人和确认人都由客户端填，界面里写死成 `studio-user`。 |
| 前端架构与 UX | **更差** | SPA 套 SPA，三套 API 客户端，没有 SSE，界面直接暴露原始 enum 和 JSON，还要手填 file ID。 |
| 工程护栏 | **明显更差** | 没有 CI，前端测试为 0，构建时忽略类型错误，没有 Alembic，也没有 ADR。 |
| 部署与身份 | **更好** | 接入 Moloco SSO / NextAuth，有 Cloud Run identity token，能水平扩展。ArcReel 只能单进程、单管理员。 |

## 3. AI Video 做得更好的地方

1. **广告 Brief 和品牌约束**：商品 / 服务、受众、市场、渠道、CTA、Legal、禁用表达、必须出现的叠加层、品牌色、字体、安全区、预算都有字段，QA 会把 CTA、Legal 和 Brief 逐字比对，还会检查禁用词（`production_control.py:1015-1048`）。ArcReel 的 ad 模式只有一段 brief 文本加卖点。
2. **研究和证据**：来源、发现和创意方向是结构化对象，创意方向可以关联到支撑它的发现（`routes/studio/project_research.py`）。ArcReel 没有对应的能力。
3. **商品 lineage**：`truth_anchor → standardized` 之间有外键和审计，claims 和禁止修改的地方都是结构化字段（`models/studio_products.py`），比 ArcReel 按名称做身份识别更稳。
4. **显式选 take**：生成只会新增候选，不会覆盖已有的选择；采用 take 时在行锁里保证同一镜头只有一个 accepted，并且可以切回去，有测试（`test_generated_video_service.py:277,356`）。这比 ArcReel 更贴近 P-09。
5. **服务端成片闭环**：EditRevision（不可变，批准后才能渲染）→ FFmpeg 渲染 → ffprobe 和品牌规则 QA → QA 不通过就不能出 Final → 交付 MP4、SRT 和 manifest。ArcReel 没有服务端成片，也没有 QA，这里是真正的超越。
6. **确定性叠加层**：Logo、CTA、Legal、End Card 的文字通过 ASS 字幕文件渲染，不拼进滤镜图，所以没有滤镜注入的风险（`editing.py:62-103,277-312`）。另外还有 ducking 和可调时长的转场。
7. **首帧 / 关键帧 / 尾帧的控制模型**更细，定义了 6 种组合，不过在 Veo 执行时有损（见 §4.2）。
8. **企业化部署**：复用 SSO，模型凭证不会下发到浏览器，用 Postgres 加 Cloud Tasks 可以水平扩展。ArcReel 在 ADR 0083 里明确只支持单进程。
9. **Key 的设计**：分 scope，只存 sha256 哈希，Token 只显示一次，可以撤销。ArcReel 是"有 Key 就是全权"（ADR 0065）。
10. **定价声明**带 `source_url` 和 `verified_on`，并区分"本地估算"和"provider 实报"；批量生成时报价指纹会和确认绑定。

## 4. AI Video 做得不如 ArcReel 的地方

### 4.1 Revision 和过期状态没有成为"生产依据"

- 视频生成读的是当前镜头卡和当前帧，不读已批准的 `ShotPlanRevision` 或 keyframe revision（`services/film/generated_video.py:178-200`）。单镜头接口完全不检查审批状态（`routes/film/generated_video.py:55-72`），只有批量接口会检查。
- `current / stale / missing / blocked` 是数据库里的一个字段，调用方可以随意写入（`schemas/studio/production_control.py:68`）。唯一会把它改成 stale 的地方是"批准新版本"时（`production_control.py:229-232`）。镜头卡、Brief、商品、资产图有变化，都不会触发 stale；missing 也从来不会被自动计算出来。
- 输入指纹里混入了"项目当前所有已批准的版本"，帧产物的指纹直接填的是任务 ID（`image_task_runner.py:240-243`）。全仓库没有任何地方比对过指纹，测试目录里也搜不到 stale。
- 广告脚本只是前端表单里的一份孤立 JSON，后端不校验结构（测试里批准的就是 `{"script":"approved"}`，见 `test_production_control.py:273`），镜头、提示词、QA 都不读它。
- ArcReel 的做法是：只存依据摘要，读的时候现算四种状态，入队时冻结输入，提交时再复核一次（ADR 0062）。

### 4.2 任务可靠性：有重复扣费风险

- **状态迁移没有守卫**（`stores.py:569-580`），执行入口也不检查任务是否已经在跑或已经结束。Cloud Tasks 是"至少投递一次"：重复投递、实例被杀后重试，甚至任务已经成功之后又来一次投递，都可能把同一个 Veo 视频再提交一次，重复扣费。视频执行器的超时是 3600 秒，而 Cloud Tasks 默认的派发截止时间是 900 秒（`config.py:97`），超时触发重试的窗口是真实存在的。
- **"服务重启后有条件续跑"标了 `[x]`，但代码里没有实现。** 启动时不扫描卡在 running 的任务；Veo 的 LRO operation name 在开始轮询之前没有存库（`vertex/video.py:87-94`）；Celery 没开 `acks_late`，worker 崩溃后任务会永远卡在 running。
- **"只重试下载、不重复计费"在 Veo 上基本不成立。** 暂存对象在 `finally` 里就被删掉了（`vertex/video.py:108-112`），GCS 读取失败也会删，等于把已经付费的产物直接丢掉。
- **执行中的任务也能取消**（`task_status.py:186-211`），结果是"任务显示已取消，但 take 里有文件，账本停在 estimated"。ArcReel 只允许取消排队中的任务（ADR 0006）。
- **单镜头路径绕过了所有关卡。** 没有审批、在途冲突、费用确认、预算检查，活跃界面也不带 `Idempotency-Key`（`ChapterStudio.tsx:3102`）。批量路径和单镜头路径的口径不一致，这正是 ArcReel ADR 0061 想要避免的情况。
- **账本是一个任务一行**，不是 ArcReel 那样一次真实调用一行，也没有 cancelled 状态。报价用到的 `resolution` 和 `audio` 参数从来没有传给 Veo，报价和实际执行不是基于同一份请求事实（违反 ADR 0056/0086 的原则）。
- **商品锚点**：选了标准图之后，原图就不再进入参考图；项目里所有商品都会被注入每一个镜头，并且排在参考列表的最后（`services/studio/products.py:189-205`）。另外，Veo 适配器把 key 帧当成首帧使用，`first_last_key` 模式下 key 帧会被悄悄丢掉（`vertex/video.py:78-85`）。

### 4.3 渲染和 QA：两个实测 bug，两项假检查

- **视频原生音轨错位（已实测）。** 原生音轨只做了 `atrim`，没有做 `adelay`，每一段的原声都从第 0 秒开始播（`editing.py:435-443`）。实测两段各 2 秒的视频，第 2 段的声音出现在 0–2 秒，2–4 秒是静音。
- **峰值检查不起作用（已实测）。** `volumedetect` 最高只会报到 0.0 dB，而判定条件是 `<=0` 就算通过（`production_control.py:954`）。实测一个峰值 +11.55 dBFS 的文件被判为通过。代码里也没有 LUFS 或 true-peak 检查。
- **字幕安全区检查写死成通过**（`production_control.py:1004-1014`）。字幕和 Legal / CTA 都放在画面底部、边距相同，大概率会重叠（待确认）。
- 片段的出点用的是**计划时长**，不是实际生成出来的时长（`editing.py:59,125`）；音频可以超出视频长度，实测 4 秒的视频输出了 10 秒的文件。转场时音频也不做交叉淡化，求和之后没有限幅。
- QA 报告没有绑定到具体的某一次渲染：QA 之后再重新渲染，Final 可能拿到一个没有经过 QA 的文件。QA 不通过时阻断 Final 的这条路径也没有测试。manifest 里没有费用、每个片段实际用的是哪个 take、FFmpeg 版本和字体。
- 渲染在唯一的 API 实例上同步执行，FFmpeg 子进程没有超时（`editing.py:552-557`），输入输出文件都整个读进内存。本机的 Homebrew FFmpeg 不带 `ass` 滤镜，只要有字幕就必定渲染失败；smoke test 只用了纯色视频，没覆盖音频、ASS 和 Logo。
- ArcReel 的 compose skill 在音频同步、补静音、转场做 acrossfade 这几点上反而做对了。字幕、TTS 和时长也是从同一份 utterances 派生的（ADR 0040）；AI Video 的字幕全靠手填。

### 4.4 身份、确认和审计不可信

- Web 代理已经转发了 `x-user-email`，但后端从来不读（`app/api/ai-video/[...path]/route.ts:60`）。批准人、确认人都是请求体里的字符串，界面里写死成 `studio-user`（`ProductionTab.tsx:301`）；MCP 以外的路径，批准人都是空的。
- "确认"只是客户端传上来的 `confirm=true` 或 `confirm_cost=true` 布尔值（`automation.py:168-169`），没有服务端签发、并绑定操作人、价格和目标的一次性令牌。ArcReel 至少有一个会回传的 `overwrite_revision`。
- 任何登录用户都能创建带写权限的 Key，也能撤销别人的 Key。Key 不绑定用户和项目，也没有过期时间和限流。记忆的 `owner_key` 全部是 `local-user`，所谓"用户记忆"实际上是全员共享的。
- 普通的保存接口允许客户端直接提交"已批准"状态，绕过审批接口（`project_research.py:61-83`）。Brief 在批准之后修改，也不会让批准失效。

### 4.5 前端和工程护栏

- **架构**：Next 的 catch-all 路由加 `ssr:false`，里面再包一个 react-router 的 `BrowserRouter`，等于 SPA 套 SPA；同时存在三套 API 客户端（生成的客户端、axios、手写 fetch），还有 81 处 `as any`。
- **数据层**：没有 SSE，全局固定每 4 秒轮询一次；轮询失败时会清空任务列表；全仓库没有一处 `AbortController`。`ChapterStudio.tsx` 一个组件 6481 行，里面有 107 个 `useState`。
- **UX**：生产面板直接显示原始的 `next_action.type`，阻断原因用 `JSON.stringify` 直接输出；剪辑和交付都要手填 file ID，没有预览；页面上有 13 个 Tab，还沿用"章节 / 演员 / 服装"这套短剧语义。
- **视觉**：antd 5 和 Tailwind 混用，存在三个互相冲突的主色和 69 处 `!important`，不符合 P-14 规定的白 / 浅灰 / 炭黑。
- **i18n**：`copy(en, zh)` 这个 helper 在 28 个文件里各定义了一遍，另外还有一个 MutationObserver 在运行时改写 DOM 里的中文。
- **护栏**：没有 `.github/` CI，前端测试为 0，`next.config.ts` 里开了 `ignoreBuildErrors: true`；数据库迁移靠 `create_all` 加手写 `ALTER TABLE`，没有 Alembic；决策记录只有 2 条。对比 ArcReel：Alembic 56 个版本，88 篇 ADR，约 800 个测试文件，ruff、basedpyright 和 CodeQL 都有。

## 5. 计划中被高估的 `[x]`（汇总）

| 计划条目 | 实际状态 |
| --- | --- |
| §3.6 服务重启后有条件续跑 | 没有实现，没有启动扫描，operation name 也没有提前落库 |
| §3.6 只重试下载、不重复计费 | 对 Veo 基本不成立：暂存对象被删；落盘失败时直接结算 |
| §3.6 禁止无条件重新提交 | 被执行层破坏：没有状态守卫，at-least-once 投递会重新提交 |
| §3.6 幂等与在途冲突 | 活跃界面不带 Key；单镜头路径不做检查；并发时会返回 500 |
| §3.7 生成前费用估算与确认 | 只覆盖批量页；单镜头的视频和图片都没有；前后端的确认契约对不上（工作区正在改） |
| §3.7 Provider call 级用量账本 | 实际是一个任务一行 |
| §3.2 ScriptRevision 批准人 / 时间 | 网页端的批准人是空的 |
| §3.2 结构化广告脚本 | 只存在于前端表单，后端不校验，也没有下游使用 |
| §3.5 current/stale/missing/blocked | 字段可以随意写入，上游变化不会触发 stale，没有测试 |
| §3.5 上游变化只标 stale | 实际上基本只有渲染产物会变成 stale |
| §3.8 视频原生音轨 | 有 bug，已实测确认 |
| §3.8 实际时长使用同一个 EditRevision | 用的是计划时长，不是实际时长 |
| 范围 F 音量峰值、字幕安全区 | 峰值检查失效，安全区检查写死成通过 |
| §4.3 QA 严重级别、修复动作、豁免 | 没有实现，`waivers` 恒为空 |
| §3.9 可审阅的 endpoint market | 没有远程来源，信任级别和凭证去向都是发布者自己填的 |
| §3.10 正式批准要求显式 confirm | 只是客户端布尔值，不是服务端门禁 |
| §3.11 审批、采用、生成、交付的审计事件 | 采用 take 和生成批次都不写审计，actor 也没有绑定真实身份 |
| 广告核心范围 "已完成自动化回归" | `test_integration_hub.py` 曾导入一个还不存在的函数；现在有 1 个测试失败；前端测试为 0 |

按计划 §8 自己定的关闭规则（活跃界面能用、有持久化、有自动化测试、不会静默覆盖），上面这些都应该退回 `[-]`。

## 6. 建议路线（按影响排序）

**立即做（本周）**

1. **提交或备份未跟踪的代码**，修好失败的测试。否则既有丢失风险，也没有审计证据。
2. **关掉高危入口。** 用服务端 feature flag 默认关闭自定义 endpoint 和 ComfyUI 的执行，以及 market 的发布；MCP 只开放只读 scope。如果以后要重新打开，必须满足：`credential_env` 只能用固定前缀的变量名；供应商域名只能是 Zip 已批准的白名单；做 DNS pinning 防 rebinding；外部调用纳入账本和预算。
3. **堵住重复扣费。** 状态迁移改成 CAS（`UPDATE … WHERE status IN (…)`），执行入口只认领 pending 状态的任务；Veo 的 operation name 在轮询之前就落库；启动时扫描卡住的任务，有 operation name 的续轮询，没有的标为失败，绝不重新提交；暂存对象要等我方存储落盘之后再删；只允许取消 pending 的任务。
4. **收拢所有付费入口。** 单镜头就当作"批次大小为 1"，走同一套审批、在途冲突、报价、预算和确认流程，带上 Idempotency-Key；服务端对 (shot, 活动状态) 加唯一部分索引。
5. **服务端身份。** 后端从已认证的会话里取操作人，不再接受请求体里的 `approved_by` 和 `confirmed_by`；确认改为服务端签发的一次性 nonce，绑定操作人、目标、报价和有效期，并存成确认记录（这也是 AI Gov 需要的 Oversight 证据）。

**接下来做**

6. **修渲染和 QA。** 原生音轨按时间轴 `adelay`；转场时音频做 acrossfade；截断到片长并加限幅；峰值改用 `ebur128` 或 true peak；安全区做真实的碰撞检测；QA 绑定到具体的 render ID；加上豁免机制；EDL 使用 ffprobe 测出来的实际时长；渲染移到独立的 Cloud Run Job 并设置超时；锁定 FFmpeg 版本和字体。
7. **让 Revision 成为生成依据。** 为 keyframe、take、render 定义各自的依据（内容字段、提示词、选定帧的摘要、商品原图的摘要、Brief 的 CTA / Legal / 时长）；入队时冻结，提交时复核，读取时计算过期状态；补上相关测试。
8. **补工程护栏。** 最小 CI 跑 pytest、tsc、eslint 和 locale audit；关掉 `ignoreBuildErrors`；引入 Alembic；开始写 ADR。
9. **UX。** 生产面板把 `next_action` 和阻断原因翻译成用户能看懂的话，stale 的产物要能直接查看或重生；剪辑和交付改成从已选 take 和渲染产物里挑选；加上 SSE，并按"有任务在途 / 空闲"切换 3 秒和 30 秒两档轮询；去掉短剧语义。

**治理**

10. P1 集成层回到原来的范围锁，先把 P0 提交并在生产环境验证；开放 MCP 之前先向 AI Gov 申请重新分级；外部供应商走 Zip 采购；把 `ArcReel/` 移出工作区，或者加进 `.gitignore`。

## 7. 技术债清理清单

| 项 | 路径 | 建议 |
| --- | --- | --- |
| 没有接入路由的页面，约 2500 行 | `pages/aiStudio/agents/AgentManagement.tsx`、`AgentEdit.tsx`、`chapter/ChapterPrep.tsx`、`chapter/prep/usePrepFlow.ts` | 删除 |
| 旧 video-production 客户端，约 1270 行，没有调用方 | `apps/web/lib/incept-api.ts:33-1302` | 删除（后端路由是否一起下线，由你决定） |
| 空目录 | `components/openvideo/`、`components/video-studio/` | 删除 |
| 会进生产构建的 mock | `public/ai-video/mockServiceWorker.js`、`src/mocks/*` | 改为只在开发环境加载 |
| 三套 API 客户端 | `services/generated`、`services/http.ts`、`services/productionControl.ts` | 合并成一套，按 OpenAPI 重新生成，并把生成脚本写进 package.json |
| film 和 studio 两套路由 | `api/v1/routes/film/*` 和 `studio/*` | 合并；单镜头改走统一的准入流程 |
| 超大组件 | `ChapterStudio.tsx`（6481 行）、`ChapterShotEditPage.tsx`（1803 行） | 拆成 hooks 和子面板 |
| 运行时改写 DOM 的翻译层 | `components/SystemTextEnglishAdapter.tsx` | 删除，改成基于 key 的 i18n |
| 两份重复的代理逻辑 | `app/api/ai-video/…/route.ts` 和 `app/api/incept/…/route.ts` | 抽到 `lib/` 里共用 |
| 后端有两个 venv | `apps/api/venv`（没有 pytest）、`apps/api/.venv` | 只保留一个 |

## 8. 待确认

- Next 的生产构建里是否仍然带着 msw chunk。
- Web 代理靠 Host 头判断是否为 localhost 并放行登录校验，经过自定义域名或负载均衡时能否被利用（`route.ts:47`）。另外，API 中间件在内部密钥为空时会直接放行，属于 fail-open（`main.py:106`）。
- Cloud Tasks 队列的重试策略，由运维配置决定。
- 生产镜像里 Debian 的 FFmpeg 是否带 libass。
- 字幕和 Legal 叠加层是否真的会重叠，需要用真实素材渲染一次确认。
- 工作区在审查期间持续变化。SSRF 的主要部分已经在修；`confirm_video_batch` 和前端的确认契约也在调整，需要以最新的代码为准重新核对。
