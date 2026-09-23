# GamingPlayable 产品设计文档（v1）

> 状态：产品设计冻结前草案。本文只定义产品结构与用户体验；暂不改动现有代码或云端配置。

## 1. 产品定位

GamingPlayable 是一个为轻度游戏广告制作 3–10 分钟可重复试玩循环的工作台。它不是 Studio 的一个“生成按钮”，也不是一个只有预览画布的单页工具；它需要管理项目、参考素材、玩法配置、测试和可交付 HTML。

首期目标用户是没有专职 playable 团队的游戏客户和创意人员。他们可以从游戏截图、录屏、Logo、UI 和一句需求开始，完成一个可编辑、可反复试玩、可验证的 HTML5 playable。

首期不做公开社区、不把客户素材自动共享、不承诺把 Unity/Cocos 原工程直接转换为 playable。

## 2. 视觉方向

首页工具卡的模块识别色必须互不重叠：Studio 保持紫色、OpenVideo 保持蓝色、GamingPlayable 使用**浅橙色**。GamingPlayable 的内部 UI 延续橙色系统，不再使用紫色或绿色作为主品牌色。

### Reference Palette Record

参考图采样文件：[gaming-playable-home-reference-palette.json](page-masters/gaming-playable-home-reference-palette.json)。以下为已观察到的颜色，而非对其紫色品牌的复用：

| 观察色 | 参考图中的角色 | 画面占比 |
| --- | --- | --- |
| `#F7F8FB` | 主页面浅灰画布 | 约 37.75% |
| `#FFFFFF` | 卡片与顶部栏表面 | 大面积（采样近白色合并） |
| `#0F1827` | 主文字与深色 icon 容器 | 约 0.76% |
| `#7C3AED` / `#ECE4FF` | Studio / 原 GamingPlayable 的紫色强调与卡片顶部 | 不复用 |
| `#DFECFF` | OpenVideo 的浅蓝色卡片顶部 | 仅 OpenVideo 使用 |

用户已指定 GamingPlayable 采用橙色，故以下为针对该产品的适配 token，而不是从参考图臆测出的品牌色。

| 用途 | 色彩 |
| --- | --- |
| 首页 GamingPlayable 卡片背景 | **Light orange** `#FFEDD5` |
| 主品牌 / 关键行动 | **Orange** `#F97316` |
| Hover / 深层强调 | `#EA580C` |
| 页面背景 | 参考浅灰 `#F7F8FB` |
| 卡片 | `#FFFFFF` |
| 边框 / 弱背景 | `#FED7AA` / `#FFF7ED` |
| 成功与合规通过 | Green `#15803D` |
| 警告 / 未交付 | Amber `#B45309` |
| 文字 | Slate `#1F2937` |

原则：首页 GamingPlayable 卡片使用浅橙色背景、橙色 icon 与文字；内部页面保持参考图的浅灰画布和白色卡片，橙色只用于品牌、激活导航与关键行动。避免大面积纯黑、紫色渐变、绿色品牌按钮或游戏化霓虹背景。试玩内容本身可以保留客户的视觉风格，不受产品外壳配色限制。

### Phase A UI Plan（供页面母版确认）

**视觉主张：** 像专业创作软件的清爽项目首页，而不是游戏启动器；通过克制的浅橙识别色提示“互动玩法”。

**颜色预算：** `#F7F8FB` 作为 65% 以上画布；白色卡片约 25%；`#FFEDD5` 仅用于 GamingPlayable 的卡片头部、空状态插图区和次级选中背景，不超过 8%；`#F97316` 仅用于主按钮、active nav、icon 容器和关键文字，不超过 3%。不使用 `#7C3AED`、`#8338EC`、`#356FEC` 作为 GamingPlayable UI 色。

**固定组件：** 左侧 240px Sidebar、顶部 72px 项目栏、16px 圆角白色卡片、轻灰边框、低高度阴影、深色文字。所有页面保持同一 Shell；只改变主内容区和 Sidebar 的 active 项。

**首页（Hub）构图：**

1. 顶栏：`GamingPlayable`、工作区、帮助、用户菜单。
2. Sidebar：我的 Playables（选中）、橙色新建按钮、模板库、素材库、交付与 QA。
3. 主区标题：`My Playables` 与 `New playable` 主按钮。
4. 状态概览：Draft / Needs assets / Ready to playtest / Ready to deliver 四个低密度统计卡。
5. 最近项目：三张可继续的项目卡；没有真实项目时展示一个明确的空状态，而不是虚构数据。
6. 热门模板：三张紧凑模板卡，显示玩法、收藏与 Fork；无客户图时使用抽象棋盘占位图。

**排除项：** 不复制参考图中的 Linglong Logo、用户头像、具体文字内容、紫色图标容器；不出现第二条全局导航；不以“下载 HTML”作为首页主行动。

## 3. 信息架构：一个 Shell，五个主页面

进入 `/gaming-playable` 时不直接打开一个空试玩编辑器，而是先进入 **Playable Hub**。所有页面共享同一个左侧 Sidebar、顶部项目上下文和用户菜单。

```text
GamingPlayable
├── 我的 Playables（Hub）
├── 新建 Playable
├── 模板库
├── 素材库
└── 交付与 QA
```

### Sidebar 规范

顶部：GamingPlayable 标志、产品名、折叠按钮。

主导航（按顺序）：

1. **我的 Playables** — 图标：Grid。项目首页和近期项目。
2. **新建 Playable** — 图标：Plus。Orange 主按钮，不是普通列表项；每次点击创建草稿并进入引导。
3. **模板库** — 图标：LayoutTemplate。查看、收藏和 Fork 可复用玩法配方。
4. **素材库** — 图标：FolderImage。跨项目的素材浏览与复用入口。
5. **交付与 QA** — 图标：ShieldCheck。查看 Build、验证和下载历史。

底部：当前工作区、帮助/规格文档、账户菜单。首期不展示“社区”入口，以免误导客户素材会公开。

桌面端 Sidebar 宽度 240px，可折叠为 72px；窄屏使用抽屉。项目内的步骤导航不再作为第二条全局导航，而放在主内容区的项目标题下。

## 4. 页面一：我的 Playables（默认首页）

### 目的

让用户一眼知道有哪些项目可以继续、哪些需要素材、哪些已经可交付；同时给出“新建”与“从模板开始”两种路径。

### 内容

- 顶部：标题“我的 Playables”、`新建 Playable` 主按钮、`从模板开始` 次按钮。
- 概览指标：草稿、待补素材、可测试、可交付。指标只展示项目状态，不展示没有依据的质量分数。
- 最近项目卡片：封面、项目名、玩法类型、最后编辑时间、状态、素材完整度、最近 Build 结果。
- “继续创作”区：最近三个未完成项目。
- “热门模板”区：按收藏数和 Fork 数排序的 Workspace Template。
- 空状态：解释可上传截图/录屏/Logo，提供 `新建 Playable` 与 `浏览模板` 两个行动。

### 项目状态

`Draft`、`Needs assets`、`Ready to playtest`、`QA blocked`、`Ready to deliver`、`Delivered`。这些状态由真实条件计算，不允许用户手动伪造“已交付”。

## 5. 页面二：新建 Playable（引导式创建）

### 目的

把“我有一些图片/视频，想做 playable”的模糊输入转换为一个可编辑项目，而不是要求用户先理解引擎和 schema。

### 创建入口

用户点击 Sidebar 的 `新建 Playable` 后创建一个 Draft Project，并进入四步引导。右上始终可 `保存草稿` 或 `退出到项目`。

| 步骤 | 页面内容 | 必需输入 | 输出 |
| --- | --- | --- | --- |
| 1. 创作 Brief | 游戏名、平台、地区、目标画幅、试玩目标、CTA | 游戏名、画幅、试玩目标 | Project brief |
| 2. 参考与玩法 | 上传截图/录屏/旧 HTML，描述核心玩法 | 至少一个参考或文字玩法说明 | 玩法假设与可行玩法建议 |
| 3. 素材计划 | 明确需要的角色、棋盘、道具、Logo、UI、音频 | 关键 IP 素材来源确认 | Asset Kit checklist |
| 4. 选择起点 | 推荐模板、玩法循环、难度和教程方案 | 一个玩法模板 | 可打开的 Playable Project |

### Copilot 在此页的职责

Copilot 只做三件事：分析参考、提出可执行的玩法建议、把用户确认的答案写进项目状态。它不能擅自把截图中的 Logo 重绘，也不能在玩法识别不确定时假装理解；应给出 2–3 个明确选项让用户确认。

## 6. 项目工作台（项目内页，不计入五个主页面）

这是一个具体 Playable Project 的编辑页，路由建议为 `/gaming-playable/projects/:projectId`。它不是新的全局页面，因此不占 Sidebar 项。

顶部项目栏：项目名、状态、保存状态、预览、`生成 Build`。

项目内只有一条水平步骤栏：

1. **Brief**：受众、市场、画幅、CTA 和试玩目标。
2. **Assets**：项目 Asset Kit、素材授权/来源、缺失项与槽位映射。
3. **Gameplay**：玩法模板、关卡/棋盘、目标、数值、教程、失败/奖励、CTA 时机。
4. **Playtest**：真实交互预览、设备/方向切换、行为记录和问题清单。
5. **Build & QA**：生成的单 HTML、静态扫描、离线测试、体积和授权清单。

工作台两栏布局：左侧是当前步骤的编辑表单，右侧是可折叠实时预览。用户点击预览中的元素时，应在左侧定位到对应的“可编辑参数”；复杂意图（如“奖励更爽一点”）才交给 Copilot 转换为候选修改并要求确认。

## 7. 页面三：模板库

### 目的

让创意经验积累为可复用玩法起点，而不是复制某个客户项目。

### 内容

- Tab：`全部 Workspace 模板`、`我的模板`、`已收藏`。
- 筛选：玩法（Merge / Match-3 / Sort / Tile / Runner 等）、画幅、运行时、可玩时长、状态。
- 模板卡：封面（无客户素材时为通用示意）、名称、玩法循环、适用场景、作者、版本、收藏数、Fork 数、需要填充的 Asset Slots。
- 操作：预览、收藏、`使用模板`、仅对所有者显示“创建新版本”。

### 核心规则

- `使用模板` 永远创建一个 **Template Fork**，不会修改源模板。
- 模板保存时只保存玩法与样式配置；客户图片、视频、Logo、账号和原始上传文件都不进入模板。
- 首期只支持 `Private` 与 `Workspace`。`Community` 仅预留领域模型，待版权审核、举报和许可清单完成后另行开放。

## 8. 页面四：素材库

### 目的

集中管理可复用且授权清楚的素材，同时让项目素材不再散落在浏览器本地状态中。

### 内容

- Scope 切换：`当前项目 Asset Kit` / `我的素材` / `工作区素材`。
- 素材类型：Game art、角色、棋盘/道具、Logo、UI、音频、参考视频、旧 playable HTML。
- 每张卡显示：预览、来源、授权状态、可被哪些项目使用、是否为 IP-locked。
- 上传入口支持图片、WebP、视频和 HTML；上传 HTML 进入“待检查”状态，而不是直接运行。
- `添加到项目` 操作只建立关联；不复制同一份原始文件。

### 素材合规规则

- `IP-locked`（Logo、真实 UI、商店按钮、游戏截图）只能从已授权素材输入或后期叠加使用；不交给模型重绘。
- Project Asset Kit 可以引用素材；模板只能保留“需要一个 Logo / 背景 / 角色”的槽位定义。

## 9. 页面五：交付与 QA

### 目的

把“浏览器里能玩”与“广告平台可交付”明确分开。

### 内容

- Build 历史：项目、版本、运行时、生成时间、创建者、状态。
- QA Gate：单一 HTML、最终大小 < 5 MB、无外部 URL、无 `XMLHttpRequest`、无 `fetch`、无 `mraid.js`、CTA 调用、离线启动、横竖屏与安全区。
- 质量数据：首帧时间、交互可用、一次完整胜负循环、CTA 成功记录；未真实测得的数据不展示为“通过”。
- 交付操作：下载 HTML、下载第三方声明、导出 QA 报告。未通过 Gate 时下载按钮禁用并说明原因。

### 与 CR Agent 的边界

GamingPlayable 负责“玩法、关卡、资产装配、试玩体验”；CR Agent 负责广告壳、规格验证和目标平台发布。交付页可以把已通过的 Build 发送到 CR Agent，但不重复实现其广告管理功能。

## 10. 关键用户路径

### A. 从零开始

`Hub → 新建 Playable → Brief → 参考与玩法 → 素材计划 → 选择模板 → 项目工作台 → Playtest → Build & QA → 交付`

### B. 从模板开始

`模板库 → 预览 → 使用模板 → 新 Project → 填充 Asset Kit → Gameplay 微调 → Playtest → Build & QA`

### C. 复用自己的成熟方案

`我的 Playables → 项目 → 保存为模板 → Private / Workspace → 模板库 → Fork`

## 11. 分阶段实现顺序

### Phase A：先建立正确的产品壳

1. 新 GamingPlayable Layout、橙色视觉 token、Desktop/移动 Sidebar。
2. Hub、模板库和新建入口的三个独立路由与空状态。
3. 将当前单页 Phaser demo 收进“项目工作台 / Gameplay + Playtest”，不再作为产品首页。

### Phase B：让项目成为真实容器

1. 项目列表、项目创建、加载、保存和最近访问。
2. Brief 与 Project Asset Kit 的持久化。
3. 现有 Template / Favorite / Fork 功能迁移到模板库页面。

### Phase C：让创作流程可用

1. 创建向导的四步状态与 Copilot 的参考分析/确认卡。
2. Asset Slot 与当前项目素材绑定。
3. 首个 Merge 模板的可编辑 Gameplay 与 Playtest；后续才扩展 Match-3、Tile、Sort。

### Phase D：交付闭环

1. 真实 no-XHR Phaser Build 或 LittleJS 对照 Build。
2. QA Gate、离线测试和体积报告。
3. 合规通过后才允许导出，并接入 CR Agent 的交付能力。

## 12. 本期验收标准

- 打开 GamingPlayable 默认看到 Hub，而非空白试玩编辑器。
- 用户无需理解 schema 即可新建、保存、继续一个项目。
- 模板、素材、项目和交付产物在导航和数据上清晰分离。
- Workspace 模板不包含客户图片、视频、Logo 或原始上传文件。
- 每个 Build 都能明确说明“仅概念预览”或“已通过交付 QA”，不能混淆。
- 首页工具卡与内部 GamingPlayable UI 使用浅橙色 / 橙色体系，不与 Studio 的紫色或 OpenVideo 的蓝色重叠。
