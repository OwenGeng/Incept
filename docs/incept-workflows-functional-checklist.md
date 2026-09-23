# Comfy Workflow — 功能 Checklist 与验收标准

**目标：** 用户不需要理解节点图，也能在与 Studio、Intelligence 并列的 **Comfy Workflow** 产品中完成剧本、图片、视频和商业片制作；高级用户可以查看、调整并运行有类型约束的工作流。Comfy Workflow 与 Studio 共享 workspace、资产和 Production 数据，但不共享页面层级或导航状态。

**状态图例：**

- `[x]` 已实现并通过本地构建
- `[-]` 已有界面或数据模型，尚未完成真实执行/持久化
- `[ ]` 未实现
- `[*]` 需要真实 provider / 本地运行环境验收

本文件是实施唯一 checklist。新功能必须先在这里增加验收项；实现完成后更新状态和测试证据，不能以“页面能打开”代替可用验收。

## A. 入口、信息架构与安全迁移

| 状态 | 功能 | 用户体验与验收 |
| --- | --- | --- |
| [x] | 独立产品入口 | 根入口显示暖橙色 **Comfy Workflow** 卡片，路由为 `/comfy-workflow`；不再是 Studio 内部视图。 |
| [x] | 单一工作流侧栏 | 复用 `AppSidebar` 的品牌 Logo、返回首页、折叠和账户区；不显示 Workflow / Studio / Intelligence 导航，主内容插槽承载 New workflow、模板、Node Library、approved outputs 与最近工作流。 |
| [x] | Studio 内部 Workflows 入口清理 | Studio 的 `AppView` 不再包含 `ComfyUI`，也不再渲染 Workflows 画布；旧 video thread 会打开 Video Production。 |
| [ ] | Workflows 导航 badge | 有排队/运行任务时显示数量；完成/失败后 badge 立即更新。 |
| [x] | 用户可理解的产品命名 | 产品文案统一使用 `Comfy Workflow`；页面说明为“Node-based AI production canvas”。 |
| [-] | Studio ↔ Comfy Workflow 交接 | Comfy Workflow 的 approved Script / Commercial output 提供 `Open production`，会带着 production ID 跳转并定位到现有 Studio Video Production 页面。仍需 Image、Library、Video Production → Comfy Workflow 的反向入口及 asset/shot 深链接。 |
| [ ] | 深链接 | 每个 workflow 有稳定 URL / 可分享 ID；刷新、后退、复制链接仍打开相同 workflow。 |
| [ ] | 权限边界 | 用户只能看见当前 workspace 有权访问的 workflow、资产、run 和模板；服务端验证，前端隐藏不是权限控制。 |

## B. 工作流文档与多标签体验

| 状态 | 功能 | 用户体验与验收 |
| --- | --- | --- |
| [-] | 四个新建模板 | 可选 `Write a script`、`Create an image`、`Create a video shot`、`Create a commercial`；每项有一句非技术说明。 |
| [ ] | 新建空白高级工作流 | 高级用户可从空白图开始；普通用户默认看到模板而不是空白画布。 |
| [-] | 工作流列表 | 已可加载最近 workflow、创建、打开和保存；仍需完整列表、最后运行状态、缩略图/输出数量及搜索/排序。 |
| [x] | 重命名 | Workflows header 提供应用内 rename Dialog；标题经 revision 保存，失败在 Run drawer 显示可读错误。 |
| [-] | 多标签 | 可同时打开、切换、关闭 workflow，窄屏时横向滚动；切换会载入最后保存版本。仍需关闭未保存草稿前的确认与每个 tab 独立的临时草稿。 |
| [-] | 自动保存 | 节点坐标、连线和 Inspector 参数在 900ms 停止编辑后自动按 revision 保存；节点选择不会产生无意义 revision。仍需离线草稿恢复。 |
| [-] | 修订历史 | 每次保存生成不可变 revision，侧栏可列出并将旧 revision 恢复为当前草稿后另存为新 revision。仍需作者/变更摘要和“另存为新 workflow”。 |
| [ ] | 并发编辑 | revision 冲突返回友好提示：比较、重新加载、另存副本；不能静默覆盖他人修改。 |
| [x] | 删除 | 应用内 destructive Dialog 明确“删除 workflow/run history、不删除生成素材”；删除后切换到最近 workflow 或空画布。 |

## C. 画布、节点库与可访问性

| 状态 | 功能 | 用户体验与验收 |
| --- | --- | --- |
| [x] | xyflow 无限画布 | 支持平移、缩放、MiniMap、Controls 和自定义节点；不复制 ComfyUI GPL 前端代码。 |
| [x] | 模板节点与连线 | 四种模板展示输入、Agent、生成、输出节点及默认有向连线。 |
| [x] | 节点选择与检查器 | 点击节点后右侧显示名称、说明、状态及输入/状态说明；运行中的画布节点同步显示成功绿、失败浅红、stale/queued 黄、running 蓝状态。 |
| [x] | 节点库 | 左侧加载服务端 NodeDefinition catalog，支持搜索、类别/收费/approval 标识和安全的 Add 操作；加入节点自动放置并可 Undo。 |
| [x] | 节点添加 | 从节点库点击加入、自动放置、可撤销；重复节点使用新 ID，保留可编辑参数。 |
| [x] | 类型端口 | 节点显示橙色 input / 蓝色 output 的端口名与 value type；前端在连线时拒绝不兼容、重复单输入连线并显示可读原因，服务端在保存/运行前再次严格验证。 |
| [x] | 服务端验证 | 校验空图、未知节点、重复 ID、端口存在性/类型、必填输入、单输入限制、自环和循环，并在 run 前阻止。 |
| [x] | 节点分组 | 可多选节点后创建视觉 Group，也可删除 Group；Group 不参与执行、成员关系随图持久化。 |
| [x] | 节点移动与布局 | 拖动只影响 UI 坐标，不改变执行语义；有 `Auto-layout`，拖动前状态可 Undo。 |
| [-] | 剪切/复制/粘贴/删除 | 有可见复制/删除按钮、Delete/Backspace、Undo/Redo、连线删除的 history；仍需跨 workflow clipboard 与删除上游节点的确认说明。 |
| [ ] | 键盘与无障碍 | 节点、端口和 inspector 可获得焦点；支持 Escape、Delete、Enter、搜索；屏幕阅读器可读状态与错误。 |
| [ ] | 性能 | 60 秒 commercial 图可平滑平移/缩放；不因为 Run drawer 更新使全画布重渲染。 |

## D. Inspector、资产与输出选择

| 状态 | 功能 | 用户体验与验收 |
| --- | --- | --- |
| [-] | Inspector 基础骨架 | 显示所选节点和运行状态；Reference 可编辑 brief 并选择 workspace 参考/品牌资产，Image Prompt 可编辑 prompt 并选择图片参考，Video 可选择 keyframe。仍需 schema 驱动的完整参数/资产表单。 |
| [ ] | 参数表单 | 文本、数值、分辨率、比例、时长、下拉框、资产选择器全部由服务端 NodeDefinition schema 驱动。 |
| [ ] | Prompt 编辑 | 长 prompt 在 inspector 编辑，有字数、变量/资产引用提示、恢复默认和版本快照。 |
| [ ] | 资产选择器 | 显示可用图片/视频/音频/品牌资产；过滤 workspace、类型和角色；可预览且能移除。 |
| [ ] | 资产 provenance | 可查看来源文件、生成 prompt、父资产、provider run、使用过它的 workflow 节点。 |
| [x] | 输出预览 | Run drawer 可显示图片候选与 muted video take preview、展开 script / Creative Contract；点击候选进入大图/视频播放的审阅 Dialog，侧边栏列出 server-side approved outputs。 |
| [x] | Candidate 选择 | Candidate review 支持 A/B/C/D 标记、网格比较、图片大图 / 视频 controls 和显式 `Use candidate`；选择写入 approval node，须再次 Save & Run 才会批准，重跑不会重复请求已选择的 image/video provider job。 |
| [-] | Approval gate | image/video 未选择 candidate 时会以可读原因阻止，选择后需显式 Save & Run 批准；Script 输出亦需用户点击批准，批准后重跑会复用已审核 production 而非再次调用 Strategist/Screenwriter。仍需跨节点类型、依赖失效和独立批准 API。 |
| [-] | Stale 提示 | 修改任一节点参数会遍历实际连线并将下游标记为 stale；image/video approval 会清除旧 asset selection，script approval 会清除旧 production/revision，同时提示用户重跑。仍需展示依赖范围、处理比例/角色专用字段和 server-side stale provenance。 |
| [ ] | 失败处理 | 失败节点显示普通语言原因、技术详情折叠区、可执行下一步（修正、重试、取消或联系管理员）。 |

## E. Durable queue、实时事件与成本控制

| 状态 | 功能 | 用户体验与验收 |
| --- | --- | --- |
| [x] | 持久化 workflow runs | 已持久化 `workflow_run`、revision、events、`workflow_run_node` 和不可变 `workflow_outputs`；lineage API 返回当前 graph、runs、每个 run node 和 outputs，侧栏可按 run 查看节点状态。 |
| [-] | 队列 worker | 已有 lifecycle 启动的 SQLite durable worker，原子领取 queued run、执行拓扑、写入 node/run 状态并支持取消/retry；已用隔离 SQLite 执行过缺 prompt run，验证 worker 会领取后以可读 blocked 状态结束。仍需独立 worker process、多实例协调和真实 provider 端到端验收。 |
| [x] | 执行计划 | 用户点击 Run 后，服务端只执行所请求输出及其拓扑上游；双击非生成节点可局部重跑该节点和上游。Image/Video 首次只生成，选候选后只跑 approval；已选择 candidate 会复用而不重复消费 provider。 |
| [x] | 队列优先级 | Run 可选择 Normal / High / Urgent；SQLite claim 以 priority DESC、created_at ASC 排队，retry 保留优先级。 |
| [x] | 安全节点缓存 | 输入节点使用持久化 hash cache，命中会在 run node 明示 `Reused a cached deterministic node result`；有成本或副作用的 Agent/Image/Video 永不通过该 cache 静默复用。 |
| [-] | Run drawer | 已在画布底部轮询并显示当前 run 的每节点状态、消息和失败原因，并可取消 queued/running run；仍需队列位置、输出预览、retry 和点击定位。 |
| [-] | 实时事件 | 已持久化 node/run events、SSE stream 和前端 EventSource 订阅，且保留 polling 兜底；仍需 after-event cursor 的前端恢复、SSE 断线提示与多实例 event broker。 |
| [-] | 取消 | Run drawer 可取消 queued/running workflow；worker 在下一个节点前读取 durable cancellation 状态。仍需 provider-in-flight cancellation、cancelling 状态和保留未自动选择结果的说明。 |
| [-] | 重试 | Run drawer 对 failed/cancelled run 提供 Retry；服务端会创建新的持久化 run，保留旧 run/结果，不覆盖历史。仍需 stale-only node retry、明确 lineage 视图和 provider-level retry 策略。 |
| [-] | 成本确认 | Image/Video 首次 provider generation 前显示应用内确认；已选 candidate 的无费用 approval 不会再次打扰用户，视频运行仍经过 server-side budget guard。仍需准确价格估算、商业片/批量成本汇总与 image budget 展示。 |
| [ ] | workspace 公平性 | 有图片/视频并发上限；一个大批次不会饿死其他用户。 |
| [ ] | 审计 | 保存谁创建、选择、批准、运行、取消和删除；管理员可追踪而不泄露 provider secret。 |

## F. `Write a script` 模板

| 状态 | 功能 | 用户体验与验收 |
| --- | --- | --- |
| [-] | 模板画布 | Reference → Creative Strategist → Senior Screenwriter → Script output。 |
| [-] | 输入 | Reference Inspector 可附 creative reference 与 brand assets（独立角色），输入 brief、15/30/60s、9:16/16:9、720p/1080p；这些会写入新建 Video Production 的 asset links 与 production settings。仍需目标受众、产品字段与显式输出语言选择。 |
| [-] | Creative Strategist 节点 | 已由 Worker 调用现有 Creative Strategist 并创建关联 Video Production；仍需 reference/brand 资产选择、最新输入语言显示与 contract UI。 |
| [-] | Contract 可读视图 | Creative Strategist run 会把 reference insight、商业类型、输出语言、可借鉴点、叙事结构、人物/场景、所需资产与 risks 写为结构化结果；Run drawer 以可展开的 Creative Contract 呈现，不显示 Python list / 原始 JSON。仍需独立全页 contract、参考素材缩略图和 approval 状态。 |
| [-] | Screenwriter 节点 | 已由 Worker 调用现有 Senior Screenwriter 并保存关联 production/script revision；Run drawer 可展开全文，用户可点击批准。仍需 Workflows 内编辑 structured script。 |
| [ ] | Script 编辑 | 用户可编辑 structured beat 和全文；保存后下游节点 stale；编辑不损坏 schema。 |
| [-] | 交接 | 已将批准 script 的 production ID 与 script revision 写入 workflow node；仍需一键打开/同步关联 Video Production。 |

## G. `Create an image` 模板

| 状态 | 功能 | 用户体验与验收 |
| --- | --- | --- |
| [-] | 模板画布 | Prompt & references → Generate image → Select candidate。 |
| [ ] | 输入体验 | 选择纵横比、分辨率、候选数、参考资产、品牌角色；说明每项会如何影响结果。 |
| [-] | 图像生成节点 | Worker 调用已有 image adapter，默认读取现有 `VERTEX_GEMINI_IMAGE_MODEL`（当前配置为 `gemini-3.1-flash-image`），不改变 endpoint/location；Run drawer 已显示候选预览并允许选择后再次运行批准。仍需 contact sheet 标注和独立 approval API。 |
| [ ] | 实时进度 | 等待、生成、完成、失败都在节点和 Run drawer 同步。 |
| [x] | Contact sheet | 多候选可点击网格展示；面板 A/B/C/D 有清楚标记，图片大图与视频播放预览，明确选择后才写入 approval node。 |
| [ ] | 图像编辑链 | 支持选中图像 → remove background / edit / outpaint / text/logo composition → 输出。 |
| [ ] | 导出 | 可下载，或标为 design state/keyframe/品牌资产；资产库立即可见。 |

## H. `Create a video shot` 模板

| 状态 | 功能 | 用户体验与验收 |
| --- | --- | --- |
| [-] | 模板画布 | Approved keyframe → Generate video shot → Select take。 |
| [ ] | 关键帧 gate | 只接受 approved keyframe；未选择/未批准时 explainable blocked state。 |
| [-] | 视频参数 | 已可选择 approved keyframe、prompt、4/6/8 秒和比例；仍需 resolution、镜头运动、首尾帧、音频与配置允许项。 |
| [-] | Video generation 节点 | Worker 已调用既有视频 planning confirmation、预算检查和 video adapter（不修改模型、endpoint/location）；Run drawer 可选择 take。仍需视频播放预览、显式费用确认 Dialog 与 take 独立批准 API。 |
| [ ] | 视频候选 | 可播放、看时长/比例/生成时间，选择 approved take 或再次生成。 |
| [ ] | 连续性 | 节点显示人物、环境、prop、UI 和上一/下一镜状态；冲突时不能运行且说明原因。 |
| [ ] | 导出 | 批准 take 可发送至 Video Production shot 或交付 timeline。 |

## I. `Create a commercial` 模板

| 状态 | 功能 | 用户体验与验收 |
| --- | --- | --- |
| [-] | 模板画布 | Reference/Brand → Strategist → Screenwriter + Designer → Director → Delivery。 |
| [-] | Creative Contract gate | Workflow 会把标记的 reference / brand assets 以对应 Production asset-link roles 传给 Strategist；reference 与 brand 不再混为纯 text brief。仍需 server-side contract assertion，确保人物文化/地区/风格字段可回溯到 source asset。 |
| [-] | Designer assets | Commercial Worker 已调用现有 Production Designer，产出关联 design bible/asset-pack plan；Delivery 节点会在 Director 完成后输出关联 production，供后续 review。仍需 Workflows 内 2x2 生成、选择、批准和唯一性 UI。 |
| [ ] | Asset pack review | 每个 2x2 sheet 可选面板、批准或重生；ready 为绿底绿字、failed 为浅红，失败显示原因与下一步。 |
| [ ] | Storyboard | 每个 shot 有一个目标、一个 approved keyframe、简短用户可读描述；不把所有 technical prompt 堆在主界面。 |
| [ ] | Shot execution | 只可生成所选 shot；修改 keyframe 后只影响下游 shot/timeline。 |
| [ ] | Audio/delivery | 可建立 audio plan、生成音轨、渲染 first cut；最终交付前检查 required selected states 与 stale node。 |
| [ ] | 与旧 Production 互通 | 导入旧 production 后能追溯所有已有资产与来源；不丢失 conversation、script、design sheet、shot 或 final asset。 |

## J. API、数据与测试

| 状态 | 功能 | 用户体验与验收 |
| --- | --- | --- |
| [x] | Workflow API | 已实现 create/list/get/update/delete/validate/run/cancel/retry/events/revisions/outputs/lineage，并由画布实际调用。 |
| [x] | 数据库 | 已实现 `workflows`、`workflow_revisions`、`workflow_runs`、`workflow_run_nodes`、`workflow_events`、`workflow_outputs`、`workflow_node_cache` 与 queue/cache 索引。 |
| [x] | Schema contract | 后端提供受控 `NodeDefinition` / `PortDefinition` catalog；前端用其渲染节点库、真实端口和连接限制。 |
| [-] | 单元测试 | 已完成隔离 SQLite 冒烟：strict port、Group、cache、create → revision → queued run → run nodes → cancel/retry/lineage。pytest 用例已扩展；当前 API virtualenv 未安装 pytest，需 CI 或安装后正式执行。 |
| [-] | API 集成测试 | 已新增 `apps/api/tests/test_workflows_api.py` 覆盖 create → save/revision → validate → run → node query → cancel → retry → catalog；当前 API virtualenv 未安装 pytest，文件已通过 Python compile，待 CI / 安装 pytest 后正式执行。仍需事件、选择/批准与下游 run 覆盖。 |
| [ ] | UI 测试 | 模板创建、连线限制、保存状态、失败提示、键盘操作、Dialog、移动端降级。 |
| [ ] | 手动冒烟 | 本地从 Studio 打开 Workflows，分别跑 Script、Image、Video、Commercial；检查真实 asset/run 在刷新后仍存在。 |

## 当前实施顺序

1. 让 Comfy Workflow 成为与 Studio、Intelligence 并列的独立产品；保留 Studio Video Production 的引导式入口。`[x]`
2. 建立 workflow schema、SQLite 持久化、API、worker/event contract。
3. 将 Workflows 画布从临时模板提升为可保存的多文档工作区。
4. 接入 Script、Image、Video、Commercial 的真实 adapters 和 approval/stale 规则。
5. 完成测试、真实 provider 冒烟和 Studio ↔ Workflows 双向交接。

## 手工验收剧本（本地 / 真实 provider）

> 每次 API 或 Web 代码更新后，都应重启本地开发服务再执行。本段记录的是验收步骤，不以截图或“页面能打开”替代最终状态检查。

### 1. Image workflow

1. 进入 **Comfy Workflow**，选择 **Create an image**。
2. 在 `Prompt & references` 输入一个清楚的英文 prompt；可从 Inspector 选择一张 workspace 图片作为参考。
3. 等待自动保存显示为 Saved，点击 **Validate & run**。
4. 验收：只运行 `prompt → image`；Run drawer 显示真实 image job 的候选，不应因为 `Select candidate` 尚未选择而失败。
5. 选择一张候选，验收：候选卡显示 `Selected`；点击 Run 后只运行 approval，不能再创建 image provider job。
6. 刷新页面并重新打开 workflow，验收：选中资产、节点位置、连线和 revision 均保留。

### 2. Video workflow

1. 准备一张已在 Library / Studio 中可见的图片，选择 **Create a video shot**。
2. 在 `Approved keyframe` 选择该图片；输入动作、镜头运动和场景的 English shot prompt，选择 4/6/8s 与比例。
3. 点击 Run。
4. 验收：运行沿用既有 video plan confirmation 和预算检查；失败时在节点和 Run drawer 显示普通语言原因，不泄露配置；成功后以 video preview 显示 take。
5. 选择一个 take 并再次 Run，验收：仅审批已选 take，不再重新生成视频。
6. 对 queued/running run 点击 **Cancel run**；对 failed/cancelled run 点击 **Retry**，验收：新增 run ID，旧 run 仍可审计。

### 3. Script workflow

1. 选择 **Write a script**，在 `Creative reference` 输入 English brief，或选择 reference video / brand assets。
2. 点击 Run。
3. 验收：依次运行 Reference → Creative Strategist → Senior Screenwriter；Run drawer 可展开 screenplay，内容应保持最新输入语言。
4. 点击 **Approve this script**，等待自动保存后再运行。
5. 验收：只复用已审核 production 并运行 script approval；不重复调用 Strategist/Screenwriter。

### 4. Commercial workflow

1. 选择 **Create a commercial**，附参考视频及品牌资产，并写明 product、audience、时长、比例与语言。
2. 点击 Run。
3. 验收：依拓扑运行 Creative Strategist → Screenwriter + Production Designer → Storyboard Director → Delivery，交付节点返回关联 production ID。
4. 验收 Creative Contract 中人物文化、地区、风格来自所附 reference/brand assets，不可退化为泛化人物描述。
5. 从关联 Video Production 审核 design sheet、keyframe 与 shots；该互通入口仍是待完成项，暂以 production ID 和现有 Video Production 页面交叉核验。
