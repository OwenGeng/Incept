# Phaser 用于 LinglongLab GamingPlayable 的调研

> 调研日期：2026-09-02。本文只引用 Phaser 官方 GitHub 仓库及官方文档；涉及 Moloco 的单文件、5 MB、禁止外网 / XHR / `mraid.js` 约束，均视为 LinglongLab 的交付约束，而非 Phaser 的承诺。

## 结论

**建议采用 Phaser 作为 GamingPlayable 的游戏运行时，但不把它当成广告交付框架。** 它适合承载 Match-3、Merge、拖拽解谜、Runner、Idle Battle、轻量塔防等有状态、有关卡和触控操作的试玩；它不解决客户的玩法创意、素材改造、试玩节奏或 Moloco CTA/安全区/发布。

当前官方仓库主线为 Phaser 4.2.1。官方定位是可在桌面和移动 Web 上运行、同时支持 WebGL 和 Canvas 的 HTML5 游戏框架；README 也明确列出 Scene、物理、动画、输入、相机、Tilemap、粒子及 Tween 等能力。 [官方 README](https://github.com/phaserjs/phaser#phaser---html5-game-framework)

产品分层应是：

```text
客户图片 / 视频 / brief
  → LinglongLab：识别玩法、生成资产需求与试玩脚本
  → GamingPlayable：配置 Phaser 模板、关卡、数值、引导和 CTA 时机
  → Phaser：渲染、输入、物理、动画和游戏状态
  → CR Agent：广告壳、预览、规范校验、打包和发布
```

这不是与 CR Agent 的重复：Phaser/GamingPlayable 负责「能玩且好玩」，CR Agent 负责「能交付」。

## Phaser 能提供什么

### 渲染与游戏能力

- `Phaser.AUTO` 会优先使用 WebGL、在浏览器/设备不支持时回退 Canvas；也可以明确选择 `CANVAS` 或 `WEBGL`。游戏配置同时决定 Canvas 的尺寸与挂载容器。 [Game 配置入门](https://docs.phaser.io/phaser/getting-started/making-your-first-phaser-game)
- 当前 Phaser 4 的渲染管线已改为 node-based WebGL 架构，官方特别说明了 WebGL context 恢复和移动端 multi-texture batching 的改进。它适合需要大量精灵、粒子、相机推进和动画反馈的复杂试玩；但仍必须把低端机 WebGL 和帧率纳入真实设备验收。 [Phaser 4 渲染器说明](https://github.com/phaserjs/phaser#whats-new-in-phaser-4)
- Scene 是基础组织单元：每个 Scene 有自己的 display list、update loop、camera、input 和 loader；多个 Scene 可以同时运行，例如 `Play` 场景上叠 `HUD/CTA` 场景。 [Scene API](https://docs.phaser.io/api-documentation/class/scene)

建议将每个玩法模板固定拆为 `Boot → Play → End/CTA` 三个 Scene，并把以下内容放进可编辑 schema，而不是生成到业务代码里：棋盘尺寸、目标、步数/时限、掉落概率、障碍、敌人波次、奖励、失败阈值、教程步骤、素材槽位、CTA 出现时间。

### 移动端输入与适配

- Phaser 把鼠标和触摸收敛为同一套 Pointer API。对对象调用 `setInteractive()` 后，桌面点击和手机手指都可由同一个 `pointerdown` 等事件处理；官方还提供拖拽和多点触控能力。 [Input 概念文档](https://docs.phaser.io/phaser/concepts/input)
- Scale Manager 提供 `FIT`、`EXPAND`、`RESIZE` 等缩放模式，并可设置居中和监听 resize。竖屏试玩应以固定设计分辨率加 `FIT` 为默认，随后在实际广告容器内验证安全区、刘海区和 CTA 覆盖关系。 [Scale Manager](https://docs.phaser.io/phaser/concepts/scale-manager)

这意味着客户没有 playable 团队时，LinglongLab 可以给他们交付一套一致的「拖、点、滑」操作体验，而无需为每一款广告重新兼容鼠标和触控。

## 单文件 Moloco 导出的关键边界

### 默认 Loader 不可直接使用

Phaser 的常规 Loader 面向外部资源：图片 API 默认经 XHR 以 Blob 载入，Loader 也公开 `baseURL`、`path`、XHR 设置和并行下载能力。直接使用 `this.load.image('hero', 'assets/hero.png')` 或 CDN `<script>` 都与「无外网、无实际 XHR」的 standalone 模式冲突。 [Loader API](https://docs.phaser.io/api-documentation/class/loader-loaderplugin)

导出器必须执行以下转换，而不是把开发期的资源路径原样带进 HTML：

1. Phaser 运行时和游戏代码内联入一个 HTML，绝不引用 CDN。
2. 图片、音频、配置 JSON 转为 `data:` URI 或 JS 内嵌数据。
3. 不输出 `fetch`、`XMLHttpRequest`、WebSocket、动态 `<script src>`、外部 URL 或 `mraid.js`；CTA 由 CR Agent/Moloco 适配层统一注入。
4. 对最终 HTML 做静态扫描和在断网浏览器中的运行测试；不能只看源码是否「没有业务请求」。

Phaser 3.80 的官方发布说明专门加入了 Base64/Data URI Loader，并明确把「单一 HTML、无 XHR 请求的 Playable Ads」列为使用场景：当输入是 Data URI 时，图片走 `Image` 元素，XHR Loader 返回解码结果而不创建真实 `XMLHttpRequest`。 [Phaser 3.80 官方发布说明](https://github.com/phaserjs/phaser/discussions/6744)

对于图片，还可绕开常规 Loader：`TextureManager.addBase64(key, data)` 使用 `Image.src` 加载 Base64 纹理；其结果是异步的，模板启动必须等候纹理加载完成事件。 [TextureManager API](https://docs.phaser.io/api-documentation/3.88.2/class/textures-texturemanager#addbase64)

**版本注意：** 上述「Playable Ads + 无真实 XHR」的直接表述来自 Phaser 3.80 官方发布说明，而当前仓库主线是 Phaser 4.2.1。因此首个工程 Spike 必须锁定一个精确版本、断网实测 data URI 的图片/音频/JSON 载入，并把检查结果写进 exporter 回归测试；不可因为开发环境可访问本地资源就视为合规。

### 5 MB 体积预算

官方 README 给出的 Phaser 4.2.1 数据是：完整 `phaser.min.js` 原始大小约 **1.29 MB**，`phaser-arcade.min.js` 约 **1.18 MB**；345 KB 是 Web 服务器 gzip 后的体积，不能用来判断单文件 playable 是否低于 5 MB。官方同时说明可以排除不需要的特性以进一步缩小构建。 [官方体积说明](https://github.com/phaserjs/phaser#how-big-is-phaser)

因此，在 5 MB **未压缩最终 HTML** 上限下，完整引擎先占约 1.29 MB；Base64 会使原始二进制素材约增加三分之一。以 1.4 MB（引擎加压缩后玩法代码/HTML）作保守起点，剩余约 3.6 MB 文本空间只相当于约 2.7 MB 原始二进制素材，且尚未计入 Data URI 前缀和配置。这个数字是由 Base64 编码规则推导出的预算，不是 Phaser 的官方限制。

由此导出产品规则：

- 默认以压缩后的静态图、Sprite Sheet/Atlas、矢量形状和程序化粒子完成试玩；不要把客户整段视频默认内嵌。
- 视频仅作为「可选且先测体积」的素材槽。官方 Video Loader 的常规示例仍是外部 URL，不能据此承诺其 Data URI 视频在目标广告 WebView 中稳定可用。 [Video Loader API](https://docs.phaser.io/api-documentation/class/loader-loaderplugin#video)
- 模板按需选择最小构建：没有物理就不引入 Matter；需要轻量碰撞时评估 Arcade 构建；不需要音频时排除相应功能。每次导出以实际字节数作为通过条件。

## 对 LinglongLab 的实施建议

先做一个严格的 `phaser-standalone` exporter POC，而不是马上扩展多个玩法：

1. 用一个竖屏「拖拽合成」或「三消一步爽点」模板，实施 `Boot / Play / End` 三 Scene 和 schema 化参数。
2. 从用户上传的 3–8 张图片生成一个精灵图/纹理槽位；视频只抽关键帧或作为非默认增强项。
3. 产出一个单 HTML，内联 Phaser、素材和配置；由 CR Agent 接管 Safe Area、CTA、校验和最终 AdForge 发布。
4. 自动测试：最终字节数 `< 5 MB`、离线启动、无外部 URL、无真实网络请求、无 `mraid.js`、WebGL/Canvas 与常用竖屏尺寸下的首帧和操作可用。

通过该 POC 后，模板优先级应是：Merge、Match-3、Tile/Parking Puzzle、Runner、Idle Battle。客户真正购买的不是 Phaser 本身，而是「给定少量图片/视频也能在一天内产出一个可调、可验收、可发布的游戏试玩」。

## 官方来源

- [Phaser 官方 GitHub 仓库 README](https://github.com/phaserjs/phaser)
- [Phaser 官方 API：Scene](https://docs.phaser.io/api-documentation/class/scene)
- [Phaser 官方概念文档：Input](https://docs.phaser.io/phaser/concepts/input)
- [Phaser 官方概念文档：Scale Manager](https://docs.phaser.io/phaser/concepts/scale-manager)
- [Phaser 官方 API：LoaderPlugin](https://docs.phaser.io/api-documentation/class/loader-loaderplugin)
- [Phaser 官方 API：TextureManager `addBase64`](https://docs.phaser.io/api-documentation/3.88.2/class/textures-texturemanager#addbase64)
- [Phaser 官方发布说明：v3.80 Base64 Loader](https://github.com/phaserjs/phaser/discussions/6744)
