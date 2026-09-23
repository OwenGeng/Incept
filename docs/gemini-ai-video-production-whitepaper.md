# AI 短视频生产 WebApp 架构设计与标准 SOP 流程白皮书

> 来源：基于 `gemini-storyboard-workflow-transcript.md` 对话记录（含《谁送的花》全流程实战调试），由 Gemini 总结整理，本版本已合并空间轴线、元数据解耦、桥接帧与浏览器剪辑等新发现的架构升级。

---

## 目录
1. [执行摘要与核心设计理念](#1-执行摘要与核心设计理念)
2. [SOP 全流程标准工序 (End-to-End Workflow)](#2-sop-全流程标准工序-end-to-end-workflow)
3. [变量解耦与资产架构 (Variable Decoupling & Asset Model)](#3-变量解耦与资产架构-variable-decoupling--asset-model)
4. [核心技术坑点与工业级解决方案](#4-核心技术坑点与工业级解决方案)
5. [空间轴线与视线连续性 (Spatial & Eyeline Continuity)](#5-空间轴线与视线连续性-spatial--eyeline-continuity)
6. [Veo 生成模式与动态时长控制](#6-veo-生成模式与动态时长控制)
7. [WebApp 系统 Agent 架构蓝图](#7-webapp-系统-agent-架构蓝图)
8. [元数据叠加架构 (Metadata Overlay Architecture)](#8-元数据叠加架构-metadata-overlay-architecture)
9. [帧桥接机制与多变体生成 (Bridge Frame & Variants)](#9-帧桥接机制与多变体生成-bridge-frame--variants)
10. [浏览器端轻量时间轴剪辑器 (Browser Timeline Editor)](#10-浏览器端轻量时间轴剪辑器-browser-timeline-editor)
11. [批量化自动化处理管道 (Batch Pipelines)](#11-批量化自动化处理管道-batch-pipelines)
12. [Prompt 动态编译与增量重跑 (Prompt Compiler & Incremental Re-run)](#12-prompt-动态编译与增量重跑-prompt-compiler--incremental-re-run)
13. [Human-in-the-Loop 模块化微调与追溯机制](#13-human-in-the-loop-模块化微调与追溯机制)

---

## 1. 执行摘要与核心设计理念

本白皮书旨在为 AI 短视频（如买量广告、短剧、品牌宣传片）自动化生成 SaaS 产品（WebApp）提供可工程化落地的底层逻辑与架构指南。全部结论来自一次完整的实战案例复盘——一支名为《谁送的花》(The Cozy Florist) 的 7 镜头游戏买量广告，从创意提案、脚本设计、分镜生成，到 Veo 视频调试、空间轴线报错排查、最终架构提案的全过程。

### 核心设计原则：
1. **模型分工解耦 (Task Decoupling)**：
   * **图像 AI**（如 FLUX, Nano Banana 2, Midjourney）：负责 100% 的静态构图、角色一致性、场景道具融合及画质提升。
   * **视频 AI**（如 Veo, Runway, Kling）：**仅负责**"首帧动效化（Image-to-Video）"，严禁用纯文本直接生成复杂角色视频。
2. **文本与图像解耦 (Text-Image Separation)**：
   * 图像模型严禁直接渲染复杂的中文/英文排版标签。
   * 所有导出的分镜表文字、镜头编号、运镜参数均由后端代码（Python/Node.js）结合 JSON 数据进行组件化渲染，AI 只产出纯净画面。
3. **空间先于美观 (Spatial Logic Before Aesthetics)**：
   * 分镜图像模型没有 3D 空间坐标系和影视 180° 轴线概念，只会生成"单张好看、互相矛盾"的孤立画面。**"垃圾入，垃圾出"**——分镜图阶段的空间/视线错误，会原样传导到 Veo 视频，无法在后期修正。空间与视线约束必须在生成分镜图的 Prompt 阶段就显式注入。
4. **物理素材与 AIGC 素材双轨制 (Dual-Track Asset Workflow)**：
   * 与广告的 IP/游戏画面绑定的素材（游戏 Logo、真实 UI、实际玩法画面）**必须使用真实截图/录屏**，或以参考图强锚定生成，严禁 AI 自由发挥；只有非 IP 绑定的场景/人物/道具才允许纯 AIGC（T2V/I2V）自由生成。
5. **全链路可追溯微调 (Granular Overrides)**：
   * 系统在"剧本 → 资产 → 全景分镜 → 单镜高清 → Veo 视频 → 后期剪辑"的每个环节均提供可随时修改和重跑的干预节点（Human-in-the-Loop），且修改需增量重跑而非全盘重算。

---

## 2. SOP 全流程标准工序 (End-to-End Workflow)

```
[阶段一：结构化剧本拆解 + 变量解耦]
↓
[阶段二：基础资产生成 (三视图/场景/道具/IP，区分 AIGC-free 与 IP-bound)]
↓
[阶段三：空间坐标锚定 (Spatial Agent) + 2x4 全景分镜网格图生成 (Master Storyboard)]
   ──> [导演/用户 全局逻辑、空间轴线与转场审核]
↓
[阶段四：自动化 CV 切块 + 批量 2K 9:16 高清化 (Upscale)]
↓
[阶段五：Veo 生成模式标注 (单图 I2V / 首尾图 / Extend) + 动态时长 + 音频生成 + 多变体采样]
↓
[阶段六：Bridge Frame 截帧衔接 + 浏览器端粗剪 (In/Out 裁剪)]
↓
[阶段七：AI 后期对口型 + 代码化元数据叠加 + PDF/Web 分镜手册导出]
```

### 详细步骤说明：

#### 阶段一：结构化剧本拆解
* 输入非结构化文本（创意提案/口播稿），生成格式化的 `script_data.json`，将剧本拆解为连续镜头（Shots），定义景别、角色动作、道具、运镜、时长和音频描述。
* 采用**变量解耦（Variable Decoupling）**：脚本中所有实体统一替换为 `[CHAR_A]` `[CHAR_B]` `[SCENE_X]` `[PRODUCT]` `[STYLE_TAGS]` 等占位符，脚本本身只负责叙事节奏、运镜与转场逻辑，具体是谁、什么风格由用户/美术 Agent 在下一阶段绑定。这样同一套"剧本骨架"可复用于不同角色、不同游戏 IP、不同美术风格的广告变体，无需重写整个脚本。

#### 阶段二：基础资产生成 (Asset Genesis)
* 生成或上传三视图资产（男主、女主）、场景全景图、现实道具（鲜花/手机）、游戏/IP 宣传图，作为后续所有生成步骤的固定 Prompt 垫图（Image Reference）。
* **双轨素材原则**：
  * AIGC-free 轨道（人物、场景、通用道具）：可用 T2V/I2V 自由生成，只需保证跨镜头一致性。
  * IP-bound 轨道（游戏 Logo、实际游戏内 UI、真实玩法录屏）：**必须是真实素材**（截图/录屏）或以参考图像强约束生成，AI 不得自由创作，避免失真代言游戏本身画面。

#### 阶段三：全景分镜网格图合成 (Master Storyboard)
* 在生成 Prompt 前，先由**空间与视线检查 Agent**（详见第 5 节）锚定场景坐标与镜头朝向，避免"背对空间发火"这类致命错误。
* 使用 **2x4 网格布局**，将 7~8 个 9:16 竖屏镜头组合在一张 16:9 画幅大图中生成。
* **作用**：提供给导演/客户做全局视觉逻辑、转场节奏、空间轴线与角色一致性审核。

#### 阶段四：自动化 CV 裁剪与批量高清化
* 代码根据分割线算法精准裁切出独立的 9:16 镜头图像。
* 自动调用 Img2Img 精细化模型，将低分辨率网格切块提升为 2K 高清首帧（Keyframe）。

#### 阶段五：Veo 视频与音频合成
* 每个 Shot 在 JSON 中显式标注**生成模式**（单图 I2V / 首尾图 / Extend Video，详见第 6 节）与**镜头时长**（4s/6s/8s 等模块化时长，总时长可动态拼装，不限定固定秒数）。
* 结合"动态五要素 Prompt"（运镜 + 主体动作 + 光影特效 + 台词 + 音效）生成带有运动光影、镜头运动和声音/音效的视频片段，默认并发生成 2 个 Variant 供挑选。

#### 阶段六：帧桥接与粗剪
* 通过交互式截帧器从上一镜头的可用帧中提取 Bridge Frame，作为下一镜头首帧输入，解决 Veo 视频末尾衰减/虚影问题。
* 在浏览器端完成粗剪（In/Out 点裁剪、去除坏帧、顺序拼接），无需导出到 CapCut/PR。

#### 阶段七：后期与交付导出
* 系统自动合成对口型（Lip-sync）、拼接视频；元数据（镜头号/场景描述/运镜参数）由代码在裁切后叠加，不占用生成模型算力；最终生成带排版参数的专业 PDF/HTML 分镜手册。

---

## 3. 变量解耦与资产架构 (Variable Decoupling & Asset Model)

### 三层职责划分
| 层级 | 角色 | 职责 |
| :--- | :--- | :--- |
| 剧本层 | Screenwriter Agent | 只负责镜头时长、运镜、转场节奏——不绑定具体角色/风格 |
| 视觉层 | Director / Art Agent | 负责视觉身份与 Prompt 组装——将占位符替换为具体角色描述、场景描述、风格标签 |
| 用户层 | User | 选择市场（哪款游戏/哪个风格），触发变量绑定 |

### 占位符体系
`[CHAR_A]` / `[CHAR_B]`（角色）、`[SCENE_X]`（场景）、`[PROP_X]`（道具）、`[PRODUCT]` / `[IP_ASSETS]`（游戏 IP 素材）、`[STYLE_TAGS]`（美术风格标签）。

### `image-asset-generate` 通用 Skill
一个可复用于任意脚本的资产生成 Skill：
1. 从任意剧本文本中提取 `[CHAR_X]` `[SCENE_X]` `[PROP_X]` `[IP_ASSETS]` 占位符列表。
2. 当信息不足以生成明确资产时，**交互式澄清**（最多 3 个追问，如角色年龄/发色/场景风格）。
3. 每个资产遵循**双输出标准**：
   * 三视图转身表（正面/侧面/背面，用于保持跨镜头一致性）；
   * 2×2 表情/角度网格（用于捕捉不同情绪和视角，供分镜阶段挑选）。
4. 统一 2K 分辨率输出。

### 动态时长支持
不再假设视频固定为某一秒数（如 30s），而是由 N 个模块化的 4s/6s/8s 镜头自由拼装出任意总时长，由脚本 Agent 根据叙事节奏动态决定每个镜头的时长。

---

## 4. 核心技术坑点与工业级解决方案

| 遇到的工业坑点 | 现象 / 崩溃原因 | 工业级最佳解决方案 (Best Practices) |
| :--- | :--- | :--- |
| **坑点 1：Direct T2V 多人崩脸** | 直接把多张资产图和文本发给视频模型，生成出的视频角色脸部扭曲、男女熔合。 | **"静态首帧锁定"原则**：强制先在图像模型中合成 100% 完美的单镜首帧图，再传给 Veo 进行 Image-to-Video 驱动。 |
| **坑点 2：横屏转竖屏构图缺失** | 16:9 比例生成的画面在裁切为 9:16 时，切掉了手部动作、道具或人物头部。 | **"原生竖屏网格"原则**：在 Prompt 中强制定义 `each inner panel strictly rendered in vertical 9:16 portrait composition`。 |
| **坑点 3：代码切图对不准** | AI 生成的网格线不均匀或标签文本跨越网格，导致 OpenCV/PIL 错位。 | **"无文纯净网格"原则**：Prompt 加入 `no text, clean solid black/white borders`；代码采用"网格轮廓检测"或"标准比例容错切块"。 |
| **坑点 4：一图多场景混淆** | 单格里放了"手机"和"花束"两张拼图，Veo 生成视频时产生融合怪。 | **"一镜头一事件"拆分原则**：将逻辑拆解为独立镜头（如手机点击 vs 现实花束特写），保持画面单一聚焦。 |
| **坑点 5：Prompt 冗长导致 Img2Img 变脸** | 图生图精细化时写了大段描述，AI 重构了原本满意的画面。 | **"极简高精 Prompt"**：图生图只需传递 `Upscale and refine to 2K, preserve exact composition, pose and lighting.` |
| **坑点 6：动作幅度过大导致尾帧虚影** | 角色同时做多个大幅度动作（走位+侧身+推镜），4~6s 视频在第 3~4 秒后算力预测跟不上，出现肢体撕裂重影。 | **控幅+剪辑双保险**：Prompt 中加入 `smooth slight movement, stable body posture, no motion blur, no visual distortion`；剪辑端在动作最完美的时间点直接截断，不强求用满整个时长。 |
| **坑点 7：素材跨镜头不一致（花束/道具位置漂移）** | 同一束花在 Panel 1 与 Panel 5 长得不一样，道具摆放位置（茶几/沙发）前后矛盾。 | **显式锚定描述**：Prompt 中反复用完全相同的文字描述同一资产（如 "the exact same fresh kraft paper bouquet of pink tulips"），并统一声明道具的物理位置（如 "on the wooden coffee table in front of the couch"）。 |
| **坑点 8：Veo 用错运镜词导致意外硬切** | Prompt 写 `Pan`（普通摇镜），Veo 实际生成了一个隐含的硬切/空间跳变，而非连续摇镜。 | **精确运镜术语**：需要连续镜头衔接时使用 `Whip Pan`（快速甩镜）而非普通 `Pan`，甩镜在视觉上强制观众注意力锁定主体，避免 AI 插入不连续的中间空间。 |

---

## 5. 空间轴线与视线连续性 (Spatial & Eyeline Continuity)

这是本轮实战调试中发现的**最根本问题**：分镜图生成模型完全没有 3D 空间坐标系和影视 180° 轴线（Eyeline）的概念，只会孤立地生成"单张好看但互相矛盾"的画面。案例中男主本应对着沙发上的女主发火，但生成结果是男主正对镜头怒吼、背后紧贴着沙发——等于对着空气发火，女主反而在他身后。**根因发生在分镜网格图生成的那一步，而非下游的 Veo 阶段**，因此必须在生成 Prompt 阶段就注入空间约束，无法靠后期修补。

### 5.1 空间与视线检查 Agent (Agent 1.5)
在剧本 Agent 和 Master Storyboard Agent 之间插入一个新 Agent：
```
[Agent 1.5: 空间轴线与视线检查 Agent (Spatial & Eyeline Agent)]
 ┌───────────────────────────────────────────────────────┐
 │ 1. 锚定场景空间：定义 Door_Pos, Sofa_Pos, Camera_Pos    │
 │ 2. 锁定角色视角：Shot N (Door -> Sofa), Shot N+1 (Sofa) │
 │ 3. 校验 Prompt：禁止角色背靠场景元素的同时 Point at Camera│
 └───────────────────────────────────────────────────────┘
```

### 5.2 空间几何校验规则
1. **视线向量匹配（Eyeline Matching）**：若 Shot N 是角色 A 对角色 B 说话，摄像机应放在 Zone_B 位置拍摄 A，则该镜头背景强制排他 Zone_B 的元素。
2. **反打互斥原则（Reverse Shot Isolation）**：拍摄入口处角色时，Prompt 显式加入 `Background MUST BE Zone_Door, NO Zone_Sofa in background`。
3. **POV / 过肩强制锚定**：优先使用主观视角（POV）或过肩镜头（OTS）来锚定两个角色的空间关系，而非各自独立生成正面镜头。
4. **180° 轴线强制声明**：Prompt 末尾统一加入 `Strict spatial continuity and 180-degree eyeline matching between Panel N and Panel N+1`。
5. **对象物理位置锚定（Object Permanence）**：跨镜头出现的同一道具（花束、手机）必须在每个 Panel 的描述中重复完全相同的措辞，并显式声明其物理摆放位置（如统一放在"客厅茶几"），避免位置或外观漂移。

### 5.3 通用 Skill：空间感知分镜生成器 (Spatial Storyboard Skill)
用于让分镜生成模型（如 Nano Banana 2）根据散件资产 + 剧本，自动生成严格遵循 180° 轴线的分镜 Prompt：

```
[输入: 散件资产 + 剧本] ➔ [1. 3D 空间坐标锚定] ➔ [2. 视线与镜头向量对齐] ➔ [3. 画面互斥校验] ➔ [输出: 2x4 纯净 Prompt]
```

**输入数据映射**：
* 角色资产：`Ref_Char_A`（男主）、`Ref_Char_B`（女主）
* 空间锚点：`Zone_Door`（入口）、`Zone_Sofa`（沙发区）、`Zone_Table`（茶几区）
* 道具与 IP：`Ref_Prop_Flower`、`Ref_UI_Game`

**Prompt 编译模板**：
```
[System Role: Cinematic Storyboard Architect]

TASK: Generate a 2x4 master storyboard prompt from loose character, environment, and prop asset images.

INPUT ASSETS:
- Character A: [Name/Ref] -> Position: [Zone A]
- Character B: [Name/Ref] -> Position: [Zone B]
- Scene Zones: Zone A = [Entrance/Door], Zone B = [Sofa/Living Room]

SPATIAL & CAMERA CONSTRAINTS:
1. Enforce 180-degree rule and strict eyeline matching between consecutive shots.
2. Shot (Zone A -> Zone B): Camera at Zone B. Background MUST only show Zone A. Exclude Zone B from background.
3. Shot (Zone B -> Zone A): Camera at Zone A. Background MUST only show Zone B.

OUTPUT GRID FORMAT:
- Layout: 2x4 grid (8 panels), clean borders, no text/labels, 2k resolution --ar 16:9.
- Cell Ratio: Each inner panel strictly 9:16 vertical composition.
- Panel Prompts: Detailed description for Panels 1-8 following the spatial rules above.
```

---

## 6. Veo 生成模式与动态时长控制

每个镜头必须在分镜脚本 JSON 中明确标注采用哪种生成模式，因为这决定了 API 调用方式、前端需要准备一张还是两张首帧图，以及算力成本。

| 生成模式 | 工作原理 | 最适用的镜头类型 |
| :--- | :--- | :--- |
| 单图 + 文本提示词 (Single Frame I2V) | 给 1 张首帧图 + 动态 Prompt，AI 自由驱动接下来 3~8 秒的动作和运镜。 | 动作起点明确、运动幅度可预测的常规剧情镜头。 |
| 首尾图控制 / 帧图插值 (First & Last Frame) | 同时上传起始帧和结束帧，AI 负责填充中间的过渡动画。 | 高难度转场、状态剧变、或有极强前置/后置构图要求的镜头（如从手机屏幕推入游戏画面）。 |
| 视频续写 / 延长 (Extend Video) | 在已生成的优质片段末尾，基于最后一帧继续往后延伸。 | 连续对话、长镜头、或动作太复杂需要分段生成的镜头。 |

### JSON 数据结构
```json
[
  {
    "shot_id": 3,
    "title": "推入游戏画面",
    "generation_mode": "FIRST_LAST_FRAME",
    "duration_sec": 4,
    "frame_assets": {
      "first_frame": "shot_03_start.png",
      "last_frame": "shot_03_end.png"
    },
    "veo_prompt": "Rapid zoom-in into smartphone screen transitioning into 3D game...",
    "audio_prompt": "Upbeat 3D casual game background music, cheerful water spraying sound..."
  },
  {
    "shot_id": 6,
    "title": "男主震惊求教",
    "generation_mode": "I2V_WITH_EXTEND",
    "duration_sec": 6,
    "extend_duration_sec": 2,
    "frame_assets": { "first_frame": "shot_06_start.png" },
    "veo_prompt": "Man leans closer with wide shocked eyes pointing at phone...",
    "audio_prompt": "Shocked gasp, enthusiastic male voice..."
  }
]
```

明确标注生成模式后，WebApp 才能：
1. 在前端自动提示用户"该镜头推荐提供首尾图以获得最佳转场效果"；
2. 调 API 时精准匹配参数（`first_frame_image` / `last_frame_image`），避免盲目全用单图生成导致的转场失控。

时长不再假设固定总秒数，而是由每个镜头的 `duration_sec`（4s/6s/8s 等模块化时长）自由累加，支持任意总长度的成片。

---

## 7. WebApp 系统 Agent 架构蓝图

```
                          [用户交互 UI / WebApp 控制台]
                                       │
┌─────────────────────────────────────────┼─────────────────────────────────────────┐
│                                          ▼                                          │
│                       [Agent 1: 剧本与编导 Agent]                                   │
│              (结构化 JSON 拆解 + 变量解耦占位符 + 景别/运镜/音频/时长规划)            │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                           │
┌─────────────────────────────────────────┴─────────────────────────────────────────┐
│                                          ▼                                          │
│                 [Agent 1.5: 空间轴线与视线检查 Agent]                               │
│           (锚定场景坐标 Door_Pos/Sofa_Pos + 锁定视角规则 + 校验背景互斥)              │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                           │
┌─────────────────────────────────────────┴─────────────────────────────────────────┐
│                                          ▼                                          │
│                      [Agent 2: 资产管理与 Prompt Agent]                             │
│        (image-asset-generate Skill：三视图+表情网格资产，区分 AIGC-free/IP-bound)     │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                           │
┌─────────────────────────────────────────┴─────────────────────────────────────────┐
│                                          ▼                                          │
│                    [Agent 3: Master Storyboard 合成 Agent]                          │
│      (多图参考合成 2xN 纯净 9:16 网格全景分镜图，严格遵循空间/视线约束)                │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                           │
┌─────────────────────────────────────────┴─────────────────────────────────────────┐
│                                          ▼                                          │
│                     [Agent 4: CV 自动化切块与超分 Agent]                            │
│              (OpenCV 自动分割 + 批量 Img2Img 2K 高清提升 + Metadata Overlay)          │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                           │
┌─────────────────────────────────────────┴─────────────────────────────────────────┐
│                                          ▼                                          │
│                    [Agent 5: Veo 视频与音频驱动 Agent]                              │
│     (Prompt 动态编译 + 生成模式标注 + I2V/首尾图/Extend + 多 Variant + 音轨对齐)      │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                           │
┌─────────────────────────────────────────┴─────────────────────────────────────────┐
│                                          ▼                                          │
│                     [Agent 6: Bridge Frame 与粗剪 Agent]                            │
│         (交互式截帧器提取最佳残帧 + 浏览器端 In/Out 剪辑 + 时间轴自动插拔)             │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                           │
┌─────────────────────────────────────────┴─────────────────────────────────────────┐
│                                          ▼                                          │
│                   [Agent 7: 后期合成与分镜手册导出 Agent]                           │
│                (LivePortrait 口型合成 + HTML/PDF 导出 + 版本追溯)                    │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. 元数据叠加架构 (Metadata Overlay Architecture)

**底层逻辑：视觉归视觉，数据归数据。** AI 只应生成 100% 纯净画质的分镜图（无文字标签），镜头编号、场景描述、运镜参数等元数据一律由后端代码叠加，实现零成本修改。

* **自动裁切引擎 (Auto-Cropping)**：根据网格固定坐标比例，后端自动切出每个独立的 9:16 高清单格图。
* **代码渲染 UI 覆膜 (Canvas/Pillow Overlay)**：在裁切后的图片上叠加矢量文字层：
  * Shot 编号（如 `Shot 01`）
  * 场景描述（如 `Living Room Entrance`）
  * 镜头参数（如 `Framing: Medium | Motion: Whip Pan | Duration: 2s`）
* **修改零成本**：导演修改时长或文字描述时，无需重新生成图片，只需重新渲染文本叠加层——彻底避免"改个字幕就要重跑整张分镜图"的算力浪费。

---

## 9. 帧桥接机制与多变体生成 (Bridge Frame & Variants)

**问题**：Veo 生成的视频常在末尾出现衰减（Motion Decay）——例如 6 秒的片段可能只有前 4~5 秒可用，且下一镜头的场景衔接经常对不上。

**解决方案**：利用上一镜头生成视频中的"最佳残帧"作为锚点，链式衔接到下一镜头的首帧，而非让每个镜头各自独立生成关键帧。

* **多变体采样 (Variants Generation)**：每个 Shot 默认并发生成 **2 个 Variant**（可选 1~4 个），供用户快速对比挑选最自然的一版，而非全靠单次生成赌运气。
* **交互式截帧器 (Bridge Frame Grabber)**：
  1. 提供按帧微调的 Video Scrubber（视频滑块），用户可逐帧查看生成结果。
  2. 当用户发现某片段在第 X 秒出现虚影/衰减时，拖拽到最后一个可用帧（如 4.2s），点击"设为下镜头首帧 (Extract Bridge Frame)"。
  3. 后端抓取该时间点的高分辨率 PNG，自动写入下一个 Shot 的 `first_frame_image` API 参数中，实现镜头间的无缝链式衔接。

---

## 10. 浏览器端轻量时间轴剪辑器 (Browser Timeline Editor)

**底层逻辑**：无需导出到 CapCut/Premiere 才能完成"去除坏帧 + 顺序拼接"这类基础粗剪操作，在浏览器端原生完成。

* **无损 In/Out 点设置**：每个生成好的视频片段下方带可拖动的波形/卡尺，直接设定入点（In-Point）和出点（Out-Point），剪掉末尾的坏帧或多余秒数。
* **WebCodecs / FFmpeg.wasm 实时预览**：在浏览器端实时无缝拼接播放，确认无误后一键渲染导出最终完整广告片，全程无需服务器往返。

### 优化后的全流程图
```
[剧本/资产输入]
     ↓
[空间控制 Agent] ──> 编译带有空间排他词的 Prompt
     ↓
[生成纯净分镜图] ──> [代码切割单格 + 动态 overlay 文字层]
     ↓
[生成 Veo 视频 (2x Variants)]
     ↓
[用户筛选 & 在第 N 秒点击 "Extract Bridge Frame"]
     ↓
[提取帧作为下一个 Shot 的 First Frame 续写]
     ↓
[Web Timeline 划定 In/Out 点裁掉末尾坏帧] ──> [导出成品视频]
```

---

## 11. 批量化自动化处理管道 (Batch Pipelines)

在 WebApp 的后端架构中，需要通过 Celery/Redis 或 Temporal 任务队列实现以下自动化批量管道：

### 1. 批量资产生成管道 (Batch Asset Pipeline)
* 自动提取剧本中的 Entity（角色/场景/道具），并发调用图像 API 生成角色三视图与场景基准图，区分 AIGC-free 与 IP-bound 两条资产轨道。

### 2. 自动化图像分割管道 (CV Grid Splitting Pipeline)
* 使用 Python OpenCV 对 Master Storyboard 输出的网格大图进行预处理：

```python
import cv2
import numpy as np

def split_storyboard_grid(image_path, rows=2, cols=4):
    img = cv2.imread(image_path)
    h, w, _ = img.shape
    cell_h = h // rows
    cell_w = w // cols
    cropped_shots = []

    for r in range(rows):
        for c in range(cols):
            # 边缘容错裁剪（缩减 2px 避开分割线）
            ymin, ymax = r * cell_h + 2, (r + 1) * cell_h - 2
            xmin, xmax = c * cell_w + 2, (c + 1) * cell_w - 2
            crop = img[ymin:ymax, xmin:xmax]
            cropped_shots.append(crop)

    return cropped_shots  # 返回每个独立的镜头图片矩阵
```

### 3. 批量 Img2Img 高清超分管道 (Batch Upscale Pipeline)
* 异步并发调用 Nano Banana 2 / FLUX API，传入裁剪出的单格图，利用简短高精 Prompt 批量放大至 2K (9:16) 分辨率。

### 4. 批量 I2V 视频生成管道 (Batch Veo Render Pipeline)
* 将 2K 高清首帧并发提交至 Veo API，带上 JSON 中预设的生成模式、镜头动态、运镜及 Audio 提示词，每镜头默认生成 2 个 Variant，批量获取 `.mp4` 片段。

---

## 12. Prompt 动态编译与增量重跑 (Prompt Compiler & Incremental Re-run)

分镜图与 Veo Prompt 的频繁修改是影视工业化 AI 工作流中的**必然常态**（改一个道具、一句台词，往往牵连整个镜头的 Prompt）。核心解法：**解耦与数据驱动（Data-Driven Dynamic Compilation）**——绝不把 Veo Prompt 当作死板的文本存死，而是当成由分镜元数据自动编译出的动态模板。

### 自动化同步流程（三步法）
```
[用户修改分镜图 / 导演意图]
        ↓
[更新 Shot Metadata JSON (单点变更)]
        ↓
[Prompt 编译器 (Agent 5) 自动重绘 Prompt] ──> [仅触发受影响镜头的局部增量重跑]
```

### 动态 Prompt 编译机制
后端定义编译公式：`Veo Prompt = [Camera Motion] + [Subject Action] + [Lighting/VFX] + [Audio/Dialogue]`，前端只需修改基础字段，后端自动拼装出最新 Prompt：

```json
{
  "shot_id": 2,
  "camera_motion": "Fast camera whip pan from the man to the woman on couch",
  "subject_action": "Woman looks up from smartphone, smiling playfully, speaking naturally",
  "dialogue_text": "Dear, don't be mad. Come take a look at this!",
  "audio_sfx": "relaxed living room ambience, subtle smartphone screen tap sound",
  "compiled_veo_prompt": "Fast camera whip pan from the man to the woman on couch... Audio: Dear, don't be mad..."
}
```

### 增量渲染与版本控制
为防止"改一个镜头，全盘重新排队算力崩溃"，WebApp 必须实现局部擦除与重新编译：
1. **变动标记（Diff Detection）**：系统检测到只有某个 Shot 的分镜图或导演参数变了，自动将该 Shot 标记为 Stale（待更新），其他镜头锁定为 Frozen（已冻结）。
2. **局部刷新（Single Shot Overwrite）**：重新编译该 Shot 的 Veo Prompt，单独调用 Veo API 渲染该片段。
3. **时间轴自动插拔（Timeline Auto-Stitch）**：视频生成后，剪辑引擎自动将新片段替换掉时间轴上的旧片段，保持前后音轨与转场不乱。
4. **版本追溯**：为每个 Shot 保存历史 Prompt 与生成的视频版本（v1, v2, v3…），随时可回滚。

---

## 13. Human-in-the-Loop 模块化微调与追溯机制

为保证 SaaS 软件的可用性，用户不能被迫"不满意就全盘重跑"，必须在前端提供针对特定节点的重写与擦除（Inpainting）覆盖能力：

```
[节点 1: 剧本编辑] ──> 用户可修改单个 Shot 的文字、景别、时长或台词，同步更新 JSON。
        │
[节点 2: 资产重跑] ──> 允许用户仅重新生成"男主服装"或更换"游戏海报"，其他资产锁定。
        │
[节点 3: 网格局部修正] ──> 允许用户对分镜图的单个 Cell 进行图生图替换 (Inpainting)，无需重跑整张大图。
        │
[节点 4: 单镜首帧微调] ──> 用户可在 2K 高清切块阶段上传自己的参考图、手动修图，或从上一镜头截取 Bridge Frame 覆盖。
        │
[节点 5: 动态 Prompt 调整] ──> 可微调单镜给 Veo 的运镜强度 (Motion Scale)、生成模式或音效描述，重新生成单段视频（含多 Variant 重选）。
        │
[节点 6: 时间轴粗剪] ──> 在浏览器端 Timeline Editor 中调整 In/Out 点、替换坏帧片段，无需离开 WebApp。
```

白皮书终
