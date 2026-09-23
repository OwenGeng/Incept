# Gemini AI 视频生产白皮书：实现对照与测试方案

更新时间：2026-07-29

## 目标

让用户可以在一个项目内完成：上传/生成视觉素材 → 选择分镜首尾图 → 生成多个 Veo 镜头备选 → 截取可用桥接帧 → 非破坏式粗剪 → 叠加真实品牌素材并导出。

这里的原则是：**图像模型决定构图，Veo 只让已确认的静态画面运动起来；任何高成本生成都保留历史版本，不被静默覆盖。**

## 白皮书对照

| 白皮书能力 | 当前实现 | 交付状态 | 用户可见入口 |
| --- | --- | --- | --- |
| 结构化镜头（时长、画面、动作、镜头、声音、连续性） | `VideoProductionShot` + Director Prompt | 已有 | Storyboard / Videos |
| I2V 首帧生成 | Scene image 作为 `keyframe_asset_id` | 已有 | Storyboard → Videos |
| 首尾帧生成与风险拦截 | Director 评估首尾图；不合理时阻止生成 | 已有 | Storyboard / Videos |
| 4/6/8 秒模块化时长 | 每镜可单独设置 | 已有 | Videos |
| 多变体采样 | 每镜默认 2 个，可降为 1 个 | 本次补齐 | Videos → Variants |
| Take 选择、旧版本保留、过期标记 | 输出不会被覆盖；源图/Prompt 改动后标为 outdated | 已有 | Videos / Edit |
| Bridge Frame | 从已生成 Take 的用户指定时间提取 PNG，写为下一镜 Start Scene，并保留谱系 | 本次补齐 | Videos → “Extract bridge frame” |
| Extend Video | 可选择同镜已生成 Take 作为 Veo 续写输入 | 本次补齐 | Videos → Generation mode |
| 非破坏式剪辑 | Include/skip、Trim in/out、cut/fade/match cut | 已有 | Edit |
| 真正品牌 Logo、商店徽章与字幕叠加 | FFmpeg 覆盖层，避免让模型生成错误文字 | 已有 | Edit |
| Edit Reviewer + 可编辑 Timeline JSON | 评分、坏镜头提示、建议裁切；不自动替换用户选择 | 已有 | Edit |
| 交付 QC | 时长、缺失 Take、审核警告、缺失覆盖层检查 | 已有 | Edit → Render |

## 本次实现的关键规则

### 1. 视频生成前硬校验

- 必须有非空的 Director Veo Prompt。
- `image_to_video` 必须有 Start Scene。
- `first_last_frame` 必须同时有 Start/End Scene，且 Director 已评为可行。
- `extend` 必须选择本镜已经生成的一个 Take 作为源。
- 首尾图被判定需要桥接时，系统不会把不可能的插值请求发给 Veo。

### 2. 多变体不是重试

默认生成 2 个独立 Take。用户在 Edit 中选其中一个，另一个保持可预览、可回退。这样能降低“单次生成赌运气”造成的重跑成本。

### 3. Bridge Frame 是显式的人类决策

用户在上一镜 Take 中指定最后一个干净时刻（如 5.5 秒），系统：

1. 用 FFmpeg 提取 PNG；
2. 保存为 Library 资产，父级为该 Take；
3. 把它设置为下一镜 Start Scene；
4. 标记下一镜旧 Take 过期，但不删除；
5. 要求刷新下一镜 Director Prompt，再生成。

这比直接把两张差异很大的图片交给模型做“强插值”稳定得多。

### 4. Extend 的边界

Extend 用于同一镜内已经很好、但需要继续动作或延长内容的 Take；它不是用来替代镜头间剪辑。跨场景关系仍优先用 Cut、Match Cut 或用户确认后的 Bridge Frame。

## 尚不自动化的能力与原因

以下不应伪装为已完成：

| 能力 | 当前处理 | 下一阶段建议 |
| --- | --- | --- |
| Master Storyboard 一张大网格图自动生成、CV 分格、批量高清化 | 可用现有 Scene Builder 逐镜生成和用户选择 | 单独增加“Storyboard sheet → crop → upscale”后台 Job；需要对网格布局、文字禁用、失败回退做专项测试 |
| 180° 轴线/空间坐标自动判定 | Director 的首尾图可行性检查与连续性字段 | 加入可视化空间标注（人物区位、视线方向），只做建议卡，不自动改镜头 |
| 浏览器即时无缝时间线预览 | 当前用服务端 FFmpeg 可靠导出；浏览器可逐 Take 预览 | 在不改变编辑状态模型的前提下添加 WebCodecs/FFmpeg.wasm 预览层 |
| 自动口型、TTS、音画节拍 | Veo 音频按模型能力生成；字幕/品牌资产由后期覆盖 | 单独接入用户确认的 TTS/Lip-sync 提供方；不要把未验证的模型能力写死进流程 |
| 自动生成 4 个以上变体 | 当前上游接口固定支持 1/2 | 只有在用户确认供应商限制与预算后再扩大，不通过循环伪造变体 |

## 端到端验收清单

### 新项目

- [ ] 上传参考图、视频、Logo、游戏截图；确认 IP 绑定内容作为真实覆盖/参考，而不是要求 AI 重绘文字。
- [ ] 创建/选择每个 Storyboard Scene image；每镜只有一个核心动作。
- [ ] 对需要连续运动的镜头添加 End Scene；刷新 Director Prompt；若系统提示 bridge，先不要生成。

### 视频

- [ ] 每镜选择 4/6/8 秒及 1/2 个 variants；困难镜头默认 2 个。
- [ ] 在 Videos 预览两版 Take，选择最稳的一版。
- [ ] 如前后镜头连续，选上一镜最后干净帧，执行 Extract bridge frame，再刷新下一镜 Prompt。
- [ ] 只有在同一镜动作需要延续时使用 Extend；不要用 Extend 跨越不同场景。

### Edit 与交付

- [ ] 对每个 Take 使用/跳过；为尾帧衰减设置 Trim out。
- [ ] 对硬切选择 Cut / Match Cut / Fade；不要把所有镜头强行做淡入淡出。
- [ ] 将真实 Logo、商店徽章、字幕作为覆盖层；避免 AI 生成文字。
- [ ] 运行 Edit Reviewer，处理 reject/regenerate 和 unreadable text 警告。
- [ ] Render 前确认 QC：无缺 Take、时长符合目标、覆盖素材存在。

## 回归测试范围

1. Pydantic：旧 Production JSON 没有新字段时可正常加载，默认 variants=2。
2. API：1/2 variants 传入并持久化；不允许 0 或 3。
3. API：首尾图不完整、Prompt 为空、Extend 无源 Take 时均返回可读 400。
4. API：Bridge Frame 只能来自当前镜的 Take，且只写入后续镜；旧 Take 保留并标记 outdated。
5. UI：Variants、Generation mode、Take source、Bridge timestamp 都可编辑；生成一镜不禁用其他镜的操作。
6. Edit：跳过某镜不阻止导出；Trim/transition/overlay/QC 状态在刷新后仍保留。
