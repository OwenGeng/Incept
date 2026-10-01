# GamingPlayable 引擎选型：Unity / Cocos / Phaser / LittleJS

> 调研日期：2026-09-02。本文只引用各项目的官方文档或官方 GitHub 仓库。本文的 `单 HTML、<5 MB、无外部请求 / XHR / mraid.js、离线可运行` 是 Moloco standalone playable 的**产品交付约束**，不是任一引擎自动保证的能力。

## 结论

客户的正式游戏由 Unity 或 Cocos 制作，并不意味着试玩广告也应继续用 Unity/Cocos。对 LinglongLab 而言，试玩不是把完整游戏移植到浏览器，而是把一个可控的「核心动作 → 爽点/失败 → CTA」做成确定性的轻量 HTML。

**建议：先建设与引擎无关的 GamingPlayable 生产/导出层；首个复杂模板以 Phaser 实验，随后用 LittleJS 做同玩法的体积/性能对照。**

- **Phaser 是默认的复杂模板候选。** 适合 Match-3、Merge、Parking/Tile Puzzle、Runner、Idle Battle：有 Scene、Tilemap、动画、相机、粒子、Tween、Arcade/Matter 物理及完整输入系统，但单文件体积和运行时开销较高。
- **LittleJS 是极限体积与定制 2D 的候选。** 适合单核心交互的拖拽、点击、合成、排序、路径解谜、简单跑酷；引擎小、无依赖、可 Canvas-only，但团队要自己承担更多关卡、UI、状态机和工具化工作。
- **Unity / Cocos 不是首选 standalone 运行时。** 它们能构建 Web，但默认产物是多文件/多资源的 Web 项目，且常规资源机制面向 HTTP 或资源服务器；要变成一个无网络依赖的 5 MB HTML，需要额外的深度重打包，通常不划算。
- **CR Agent 不重复。** 无论选 Phaser 还是 LittleJS，CR Agent 仍负责广告壳、Safe Area、CTA、预览、构建/校验与发布；GamingPlayable 负责玩法、关卡、数值、IP 素材装配与试玩创意。

## 先固定的产品架构（不绑定引擎）

```text
客户游戏截图 / 录屏 / Logo / UI / brief
  → Copilot：识别真实玩法与卖点，推荐试玩创意
  → GamingPlayable Schema：玩法、关卡、数值、素材槽、教程、失败/奖励、CTA 时机
  → Phaser 或 LittleJS Runtime：只执行游戏逻辑与渲染
  → Standalone packer：内联代码/素材，生成单 HTML
  → CR Agent：广告壳、预览、CTA、安全区、构建/交付
  → Validator：5 MB、断网、无外链/XHR/mraid、CTA 可调用、真机操作
```

`schema` 是长期资产：例如 `boardWidth`、`moves`、`goal`、`dropWeights`、`obstacles`、`tutorialSteps`、`rewardTiming`、`assetSlots`。不要把这些参数写死在某次客户创意里；如此才能让一个玩法模板服务不同 Unity/Cocos 客户。

## 引擎对比

| 维度 | Unity WebGL | Cocos Creator Web Mobile | Phaser | LittleJS |
|---|---|---|---|---|
| 面向对象 | 完整 Unity 项目的浏览器发布 | 编辑器驱动的跨端游戏发布 | JavaScript/TypeScript 2D Web 游戏框架 | 极小的 JavaScript 2D 引擎 |
| 标准 Web 产物 | `loader.js`、`framework.js`、`.wasm`、`.data` 等多个文件 | 发布目录及 `assets/import/native` 等资源目录 | 开发期通常有外部 Loader；可控制打包 | 可直接 script tag；正常素材仍可为外部文件 |
| 单 HTML / 无网络难度 | 很高 | 很高 | 中等：官方已支持 Data URI Loader | 低到中等：引擎很小；素材仍需内联 |
| 引擎体积线索 | 未以 single-file ad 为目标 | 未以 single-file ad 为目标 | 全功能 min 约 1.29 MB raw；Arcade 约 1.18 MB raw | 官方 FAQ：`release/min` 远低于 100 KB |
| 复杂玩法能力 | 最强，但对广告体积不友好 | 强，有编辑器工作流 | 强：Scene、Tilemap、物理、粒子、Tween、输入 | 中：2D 渲染、arcade physics、碰撞、粒子；重系统需自建/插件 |
| 移动操作 | 可做，但 WebGL 资源/内存需谨慎 | Web Mobile、触摸与自适应成熟 | Pointer/drag/多点触控与 Scale Manager | Touch 自动映射为 mouse，可选虚拟手柄 |
| 适合 LinglongLab 的位置 | 读取客户原项目/素材的参考来源，非运行时 | 同左；必要时接入客户已有 Cocos 工程 | 复杂可复用试玩模板的 Runtime | 微型试玩、5 MB 高风险创意、快速定制 Runtime |

### Unity：客户来源强，广告 Runtime 弱

Unity WebGL 标准构建明确产生 loader、framework、WebAssembly、asset data 等多个文件；服务器还需要正确的压缩响应头。官方的 `UnityWebRequest` 在 WebGL 里通过 JavaScript `XMLHttpRequest` 实现。两者与「单 HTML、禁止 XHR、无外网」直接相冲突。 [Unity WebGL 构建文件](https://docs.unity3d.com/2020.2/Documentation/Manual/webgl-building.html) [Unity WebGL 网络](https://docs.unity3d.com/2018.3/Documentation/Manual/webgl-networking.html)

Unity 仍能生成面向移动浏览器的构建，并提供 Size 优化和移动纹理压缩选项；但官方说明 Size 模式的目的就是缩小下载量、帮助较大 WebAssembly 构建在移动浏览器加载。这证实它在常规 Web 产品中可用，**不等于**适合 5 MB 的无网络单文件广告。 [Unity WebGL 构建与 Size 优化](https://docs.unity3d.com/2022.1/Documentation/Manual/webgl-building.html)

**LinglongLab 策略：** 用 Unity 客户的截图、Sprite、UI、录屏和玩法说明来建立试玩，而不把 Unity WebGL build 直接作为输出。只有客户已拥有一个极小、可合法重打包的 Unity WebGL 试玩时，才把它作为“导入并验证”的例外路径。

### Cocos：客户来源强，standalone 同样需重构

Cocos Creator 提供 Web Mobile，默认全屏填充浏览器，并有方向和 Retina 等移动 Web 配置；它的输入系统覆盖 touch、mouse、keyboard、device motion 等。 [Cocos Web 发布](https://docs.cocos.com/creator/3.4/en/editor/publish/publish-web.html) [Cocos Input](https://docs.cocos.com/creator/3.4/manual/en/engine/event/event-input.html)

但 Cocos 的资源管理以 Asset Bundle 为中心：构建后的代码、依赖资源和 `config.json` 放在 bundle 目录；可配置为 remote bundle，并通过 URL 加载。这对普通 Web 游戏很合理，却和禁止动态资源/请求的 standalone 合同相反。 [Cocos Asset Bundle](https://docs.cocos.com/creator/3.8/manual/en/asset/bundle.html)

**LinglongLab 策略：** 将 Cocos 客户理解为“已有游戏资产和玩法来源”。若未来客户提供 Cocos 工程，可做专门的 asset extractor；不要把 Cocos 标准 Web build 当作默认 playable exporter。

### Phaser：复杂玩法优先，但必须严控输出

Phaser 是面向桌面与移动浏览器的 2D HTML5 框架，支持 WebGL/Canvas、Scene、动画、输入、相机、Tilemap、粒子、Tween 和 Arcade/Matter 物理；官方 README 也列出 YouTube Playables 作为目标之一。 [Phaser README](https://github.com/phaserjs/phaser)

它的默认 Loader 为外部资源加载，直接输出会违反 standalone 约束。但 Phaser 3.80 官方加入了 Data URI/Base64 Loader，并特别说明它适用于需要单一 HTML、内嵌素材且没有 XHR 的 Playable Ads。这是 Phaser 可作为广告 runtime 的重要依据；正式接入时要锁定具体版本，并用断网测试证实实际产物没有网络调用。 [Phaser Base64 Loader 发布说明](https://github.com/phaserjs/phaser/discussions/6744)

体积是取舍：官方 README 的全功能 `phaser.min.js` 为约 1.29 MB raw（345 KB gzip），而广告上传应按最终未压缩 HTML 判断，不可把 gzip 数字当 5 MB 预算。完整 Phaser 适合复杂的可复用游戏系统，不适合把原始视频或大量 2K 图片塞进广告。 [Phaser 体积说明](https://github.com/phaserjs/phaser#how-big-is-phaser)

### LittleJS：5 MB 场景的有力补充，而非“简化 Phaser”

LittleJS 官方定位是无依赖、轻量的 HTML5 引擎；支持 WebGL2 + Canvas2D 混合渲染、2D 物理/碰撞、粒子、声音以及 mouse/keyboard/gamepad/touch。官方 FAQ 表示生产用的 `littlejs.release.js` / `littlejs.min.js` 均远低于 100 KB，专用 js13k 分支可约 7 KB zipped。 [LittleJS README](https://github.com/KilledByAPixel/LittleJS) [LittleJS FAQ](https://github.com/KilledByAPixel/LittleJS/blob/main/FAQ.md)

触控会自动路由到 mouse API，因此很多点击/拖拽玩法不必分别维护手机输入；也可启用内置触摸虚拟手柄。引擎允许关闭 WebGL，只用 Canvas2D，以降低兼容性和输出复杂度。 [LittleJS FAQ：输入与设置](https://github.com/KilledByAPixel/LittleJS/blob/main/FAQ.md)

它不是“零打包工作”：通常 `engineInit(..., ['tiles.png'])` 仍会引用外部资源。并且 Box2D 插件需要 JS loader 和独立 WASM，严格单文件时应默认不用；只有我们的 exporter 证明可以安全内联后再开放。 [LittleJS FAQ：插件与素材加载](https://github.com/KilledByAPixel/LittleJS/blob/main/FAQ.md)

**LinglongLab 策略：** LittleJS 适合“一个动作做到极好”的轻量定制：拖拽拼图、串珠、整理、合成、路径引导、点击战斗。不要一开始把它用于完整 Match-3 生态或重 UI 编辑器；否则会把 Phaser 现成的结构能力重新造一遍。

## 商用与再分发：可用，但把许可证做成导出器的硬规则

**两个核心引擎都是 MIT。** Phaser 官方 `package.json` 标识其 license 为 MIT；LittleJS 的官方 `LICENSE` 明确允许使用、复制、修改、发布、分发、再许可及销售。两者在“为客户制作并交付收费 playable”的场景中都可以使用。 [Phaser 官方 package metadata](https://github.com/phaserjs/phaser/blob/master/package.json) [LittleJS 官方 LICENSE](https://github.com/KilledByAPixel/LittleJS/blob/main/LICENSE)

MIT 的条件也不可省略：交付副本或实质性部分时，必须保留原版权声明与许可文本。对 LinglongLab 而言，最终单 HTML 应由 exporter 自动在注释中写入 `Third-party notices`，并在交付目录额外输出一份 `THIRD_PARTY_NOTICES.txt`；不要指望客户或创意人员手工维护。

还要分清“引擎代码”和“其它内容”：Phaser 官方仓库明确说明其 logo/characters 属于 Phaser Studio；LittleJS/Phaser 的示例素材、客户提供的游戏截图、字体、音频、第三方插件/物理库都不应因引擎是 MIT 就默认获得商业再分发权。每个模板需要一份**第三方依赖与资产清单（BOM）**，并在导出前阻止无来源/无授权素材。 [Phaser 官方 README 的品牌权属说明](https://github.com/phaserjs/phaser)

建议的最小合规策略：

1. 锁定引擎版本与构建 hash，记录到 playable manifest。
2. 每次导出自动收集 runtime、插件、字体、音频、素材的 license / owner / source；缺一项即标红。
3. 默认不带 Phaser 品牌素材或示例素材；客户 IP 的授权状态由项目级字段确认。
4. 对可选插件单独复核：例如 LittleJS 的 Box2D 插件和 Phaser 的第三方扩展，不把“核心引擎 MIT”扩展解释成“所有依赖都已授权”。

## 是否适合 3–10 分钟沉浸式手机试玩？

**技术上两者都可以；产品上必须用“可重复的短循环”实现，而不是把完整客户端塞进 5 MB。** 3–10 分钟应理解为用户在同一个 playable 内可以连续玩多局/多层，而非首屏就下载 3–10 分钟的关卡、视频或语音资产。

### Phaser：更适合多阶段、可沉浸的 3–10 分钟试玩

Phaser 的 Scene 可拆分 Loading、Menu、Level、Boss、Shop、HUD 等逻辑区，并支持暂停、恢复和多 Scene 同时运行；Scene 还自带独立的 input、tween、game object、camera 等系统。它很适合把试玩组织成“教学 → 关卡 1 → 难度/奖励升级 → 失败/胜利 → CTA → 再玩”的多阶段状态机。 [Phaser Scenes](https://docs.phaser.io/phaser/concepts/scenes)

适用前提是：

- 关卡由 `schema + seed` 生成或复用少量 board/obstacle 模板；不能每过一关再下载资源。
- 从开始就内联所有必要纹理/音频；当 5 MB 预算紧张，优先 Sprite Sheet、程序化粒子和文字/形状渲染。
- 每次换关清理不再使用的对象、事件和缓存引用。Phaser 场景的 Cache 是游戏级共享缓存；长时间试玩时，这一点是我们的实现责任，而不是引擎自动保证。 [Phaser Scenes：全局 Cache](https://docs.phaser.io/phaser/concepts/scenes)

结论：**若客户需要 3–10 分钟内仍能体验多层目标、数值成长、连锁反馈或轻叙事，Phaser 是更稳妥的主选。**

### LittleJS：适合“一个循环反复变好玩”的 3–10 分钟试玩

LittleJS 官方提供循环更新、对象系统、2D physics/collision、tile collision、particle、声音及 A* 等能力，另外将 UI、tween、pathfinding、Box2D 等做成按需插件。其触控自动映射为 mouse，并可启用移动端虚拟手柄。对 Merge、Tile/Parking Puzzle、Drag Sort、简单生存/跑酷等“少素材、强操作、重复循环”的玩法，3–10 分钟完全可行。 [LittleJS README](https://github.com/KilledByAPixel/LittleJS) [LittleJS FAQ：插件和触控](https://github.com/KilledByAPixel/LittleJS/blob/main/FAQ.md)

但它不应被误判为“更长内容的免费答案”：复杂的关卡编排、任务系统、存档/经济、富 UI 和内容工具需要我们自己实现或挑选插件；若引入 Box2D，又会带来独立 WASM 资源，和严格单 HTML 输出产生额外打包风险。 [LittleJS FAQ：Box2D 插件](https://github.com/KilledByAPixel/LittleJS/blob/main/FAQ.md)

结论：**若目标是让用户在同一核心手势里不断获得更强反馈，LittleJS 可以做 3–10 分钟，并会留下更多体积给客户素材；若目标是多系统、多场景、持续内容感，优先 Phaser。**

### 真实产品建议

- 不把“可玩 10 分钟”设为每个广告的 KPI；先确保前 3–10 秒立刻可玩、30–90 秒有完整爽点与 CTA。
- 以“可继续玩至 3–10 分钟”为加分能力：使用随机种子、关卡池、递增目标和重复挑战，而非大体积内容。
- 首个 POC 应同时记录 `firstInputToPlay`、首帧时间、30/60/180 秒内存与帧率、最终 HTML 字节数、一次完整 CTA 成功率；用真机数据决定 Phaser/LittleJS 的模板边界。

## 统一合规与质量门（两种 Runtime 都必须通过）

引擎不等于可交付。每个 exporter 的必经门：

1. **单文件：** runtime、业务代码、图片、音频、配置均内联；无 CDN、无外部 URL、无动态 script。
2. **静态扫描：** 拒绝 `XMLHttpRequest`、`fetch(`、`WebSocket`、`mraid.js`、跳转脚本；CTA 只通过 `FbPlayableAd.onCTAClick()`。
3. **离线验收：** 在禁网 browser/WebView 中打开，首帧、教程、一次失败/胜利、CTA 都成功。
4. **体积验收：** 对最终 `.html` 的字节数判定 `< 5 MB`；Base64 会放大二进制素材，视频默认不进包。
5. **真机验收：** 至少覆盖 iOS Safari、Android Chrome 和目标广告预览环境，检查竖/横屏、安全区、首帧时间、触控和帧率。

## 选择矩阵与实施顺序

| 需求 | 推荐 | 原因 |
|---|---|---|
| 复杂棋盘、多个场景、关卡/数值配置要长期复用 | Phaser | 结构与现成系统最完整，适合做产品化模板 |
| 单核心动作，需最大化留给客户图片/UI的体积 | LittleJS | 引擎开销极低、无依赖、Canvas-only 可选 |
| 客户只有 Unity/Cocos 截图/视频 | Phaser 或 LittleJS | 用真实资产重建广告核心循环，不移植完整客户端 |
| 客户已有可运行的旧 HTML playable | 先走导入/校验路径 | 先由 CR Agent + Validator 评估，不强行换引擎 |
| 3D、完整关卡、重物理或大量视频 | 不承诺 standalone | 先评估 IEC/托管 Web 方案；5 MB 单 HTML 不应强做 |

**推荐的 POC 顺序：**

1. 抽象 `PlayableSchema` 与同一套 exporter/validator；先不锁引擎。
2. Phaser 做一个竖屏 Merge 或“一步爽点” Match-3，证明复杂状态、内联素材与离线 CTA。
3. LittleJS 用同一份 `PlayableSchema` 做 Drag Puzzle 或 Merge，比较最终 HTML 字节数、首帧时间、低端 Android 帧率和迭代效率。
4. 以真实客户素材完成 3 个创意变体后，再决定“Phaser 默认、LittleJS 轻量模式”是否成立。

最终不是二选一：**Phaser 是复杂模板的主力，LittleJS 是体积/性能优先模板的武器；两者共用 Copilot、Schema、packer、validator 和 CR Agent 交付层。**
