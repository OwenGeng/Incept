# Agent Reach 与 Scrapling：Incept Video 搜索/调研系统适配评估

研究日期：2026-09-28（Asia/Shanghai）
评估对象：[Scrapling](https://github.com/D4Vinci/Scrapling) v0.4.15
证据范围：Scrapling 官方 GitHub 仓库、v0.4.15 标签下的源码/文档、官方 Release/PyPI 元数据，Agent Reach 官方仓库，Google Cloud Run 官方文档，以及 Incept 当前仓库源码。未使用第三方测评、博客或营销转载。本文不是法律意见。

> 更正说明：上一份将 Agent Reach 与 Anthropic Financial Services 对比的报告基于误输的 URL；本文以用户更正后的 [D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling) 为正确评估对象，替代之前的 Financial Services 比较。

## 结论

**选择：可选稍后（optional later）。现在不安装进 Incept 的 FastAPI 生产运行时，也不接 Scrapling MCP/官方 Agent Skill。**

Scrapling 能补上 Incept 现有 `web_fetch` 的一个真缺口：对 JavaScript 动态页面进行可等待 DOM、交互、截图和 XHR 捕获的真浏览器取证。但它不是搜索引擎，也不是 YouTube/B站字幕、视频帧理解或社媒平台适配器，不能单独取代 Incept 现有搜索发现层或 Agent Reach 的专项渠道层。

当前不安装的直接理由是：

1. Incept 的当前生产 API 已同时承载 Chromium/FFmpeg/视频导出，Cloud Run 配置为 2 vCPU、4 GiB、单实例、并发 20；在同一进程内再允许并发启动 Playwright/Patchright 浏览器，资源和故障半径过大。[`deploy.sh`](../../deploy.sh) / [`Dockerfile.api`](../../Dockerfile.api)
2. Incept 现有 `web_fetch` 在首次请求和每次跳转前做公网 DNS/IP 校验，拒绝私网、metadata host、非标准端口，并限制响应为 2 MiB。Scrapling 静态 fetcher 有 `follow_redirects="safe"`，但浏览器 fetch/MCP 的入参是任意 URL；其官方 MCP 源码自己也警告，可达服务的人能“从本机抓取任意 URL”。直接替换会降低现有 SSRF 安全边界。[`research_tools.py`](../../apps/api/app/video_studio/research_tools.py) / [Scrapling MCP 源码](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/scrapling/core/ai.py#L1126-L1173)
3. Scrapling `ai` extra 需要 `mcp>=2.0.0`，Incept 当前是 `mcp>=1.30,<2`，存在明确依赖冲突。[`pyproject.toml`](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/pyproject.toml#L69-L97) / [`apps/api/requirements.txt`](../../apps/api/requirements.txt)
4. 反爬绕过不是 Incept 视频调研的必需能力。官方把 Cloudflare Turnstile/Interstitial 自动解题、浏览器指纹伪装和代理轮换当作主要功能，而 robots.txt 遵守在 Spider 中默认关闭。这需要站点条款、数据使用和账号风险的单独治理，不应由模型自动决定。[StealthyFetcher 官方文档](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/fetching/stealthy.md) / [Spider 官方文档](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/spiders/getting-started.md#L140-L162)

如果以后数据证明动态页失败率已经成为调研主要瓶颈，建议只在**独立、低并发、可限流的 Cloud Run 动态抓取 worker/service** 中试验 `scrapling[fetchers]==0.4.15`；对 Agent 只暴露 Incept 自己的窄契约 `dynamic_web_fetch(url)`，不暴露 Scrapling MCP、通用 Playwright callback、代理、Cookie、CDP URL 或 `solve_cloudflare`。

## Incept 当前基线

Incept 已经不是“没有网页研究能力”：

- `web_search` 通过 DuckDuckGo HTML 结果做候选发现，返回 URL、title 和 snippet；`web_fetch` 用 HTTPX 取静态文本。[`research_tools.py`](../../apps/api/app/video_studio/research_tools.py)
- URL 边界拒绝非 HTTP(S)、用户信息、非 80/443 端口、私网/本地/metadata 地址，每次 redirect 重新解析并检查所有 IP。响应限制为 2 MiB，只接受文本/JSON/XML 类型。[`research_tools.py`](../../apps/api/app/video_studio/research_tools.py)
- Agent 最多 6 轮、12 次 tool call，单次 tool result 最多 20,000 字符；prompt 明确要求把网页当作不可信证据，不得把搜索摘要当成“已观看视频”。[`agent.py`](../../apps/api/app/video_studio/agent.py)
- 可写调研产物限定在五个路径，替换时需先读取并提交 `sha256`，生成节点还有 approved brief 门槛。[`research_tools.py`](../../apps/api/app/video_studio/research_tools.py) / [`agent.py`](../../apps/api/app/video_studio/agent.py)
- API 镜像已包含 Chromium、FFmpeg 和 Node/pnpm，主要用于可玩广告视频抓取/导出；这不等于已经具备了受控的任意公网浏览器取证边界。[`Dockerfile.api`](../../Dockerfile.api)

现有真正缺口是：`web_fetch` 不执行 JavaScript，不能等待异步 DOM、操作页面、捕获 XHR 或截图；它也没有 YouTube/B站字幕和视频帧分析能力。Scrapling 只能补前一类缺口。

## Scrapling 是什么

截至研究日期，最新官方 Release 是 2026-08-23 发布的 **v0.4.15**；该版本对 MCP 服务带来 breaking changes，包括默认本机绑定、HTTP 传输认证和 session tool 改造。包元数据仍把项目标为 **Beta**。[官方 v0.4.15 Release](https://github.com/D4Vinci/Scrapling/releases/tag/v0.4.15) / [`pyproject.toml`](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/pyproject.toml#L33-L59)

Scrapling 当前是四层结构：

| 层 | 主要职责 | 对 Incept 的意义 |
|---|---|---|
| Parser / `Selector` / `Response` | CSS、XPath、文本、正则查找；将 HTML 转为可提取结构；可选 adaptive selector | 能替换现有简单 `HTMLParser`，但 Incept 已有 Trafilatura 依赖，仅为此引入价值不大 |
| Fetchers | `Fetcher`/`FetcherSession` 用 `curl_cffi`；`DynamicFetcher` 用 Playwright Chromium/Chrome；`StealthyFetcher` 使用 Patchright 和指纹伪装 | 真正有价值的是动态浏览器 fallback，而不是静态 HTTP 替换 |
| Spider framework | async crawler engine、priority scheduler、URL dedupe、多 session、并发/每域限制、blocked retry、可选 robots、checkpoint/pause-resume | 适合长时批量 crawl；Incept 当前“每次研究少量来源”不需要这一层 |
| AI 适配 | MCP server、官方 Agent Skill、Markdown/RAG 转换和截图 tool | 与 Incept 已有 typed tool loop 重复，而且 MCP 主版本冲突；不应引入 |

这个分层由官方 [fetcher 选型文档](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/fetching/choosing.md)、[Spider 架构](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/spiders/architecture.md) 和 [MCP 指南](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/ai/mcp-server.md) 可直接验证。

### 安装与依赖面

基础 `pip install scrapling` 只安装 parser，直接依赖为 `lxml`、`cssselect`、`orjson`、`tld`、`w3lib` 和 `typing_extensions`。要用 fetchers/spiders 必须安装 `scrapling[fetchers]`，再运行 `scrapling install`；该命令会下载浏览器、系统依赖和指纹相关依赖。[官方安装说明](https://github.com/D4Vinci/Scrapling/tree/v0.4.15#installation) / [`pyproject.toml`](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/pyproject.toml#L61-L97)

`fetchers` extra 增加 `curl_cffi`、`playwright`、`patchright`、`browserforge`、`apify-fingerprint-datapoints`、`msgspec`、`anyio`、`protego` 等。`rag` 增加 `markdownify`；`ai` 增加 `mcp>=2.0.0`并包含 fetchers；`all` 还包含 IPython shell。Scrapling 的官方 Dockerfile 以 Python 3.12 slim 为基础，安装 all extras、Playwright Chromium 及其 apt 系统依赖。[`Dockerfile`](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/Dockerfile)

对 Incept 的实际含义：

- 不安装 `scrapling[ai]`、`[all]` 或官方整体镜像。
- 即使未来试验，也只 pin `scrapling[fetchers]==0.4.15` 和相容的浏览器产物；不在容器启动时运行下载/安装命令。
- 官方支持 `executable_path`指向自定义 Chromium，因此可在 PoC 中验证复用 Incept 现有 `/usr/bin/chromium`；不应在未测试 Playwright/Patchright 兼容性时就假设可以复用。[DynamicFetcher 参数](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/fetching/dynamic.md#L53-L90)

## 浏览器、动态抓取与反爬能力

### 能做什么

- **静态 HTTP**：`Fetcher`/`AsyncFetcher` 可模仿浏览器 TLS 指纹和 headers，支持 HTTP/3、session、cookies、代理和重试；`follow_redirects="safe"` 拒绝跳转到内网/私有 IP。[官方静态 fetcher 文档](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/fetching/static.md)
- **JavaScript/浏览器**：`DynamicFetcher`/session 使用 Chromium 或 Google Chrome，可等待 DOM/network idle/selector，在导航前后执行 `page_setup`/`page_action`，阻断资源或域名，复用 browser/tab，捕获 XHR/fetch 响应，也可连接远程 CDP 浏览器。[DynamicFetcher 文档](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/fetching/dynamic.md)
- **反爬绕过**：`StealthyFetcher` 在动态 fetcher 上增加 Patchright 隔离执行、CDP/WebRTC leak 处理、canvas noise、headless 指纹 patch，并声称能自动解 Cloudflare Turnstile/Interstitial。官方建议解 Cloudflare 时至少给 60 秒 timeout。[StealthyFetcher 文档](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/fetching/stealthy.md#L21-L29) / [Cloudflare 选项](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/fetching/stealthy.md#L83-L110)
- **长时爬取**：Spider 支持全局/每域并发、download delay、AutoThrottle、阻断检测/重试、多 session、代理轮换、pause/resume 和实时流式结果。robots.txt 可遵守 `Disallow`、`Crawl-delay`、`Request-rate`，但必须显式设置 `robots_txt_obey=True`。[Spider 入门](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/spiders/getting-started.md) / [Spider 架构](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/spiders/architecture.md)
- **自适应选择器**：第一次保存元素的 tag/text/attributes/父子和路径特征，网页结构变化后以相似度重新定位；功能默认关闭，默认使用 SQLite 持久化。[自适应抓取文档](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/parsing/adaptive.md)
- **AI 输出整理**：`Response.markdown()` 和 MCP 会移除 script/style、隐藏内容、零宽字符等常见 prompt-injection 载体，可用 CSS selector 缩小传给模型的内容。这是减噪和部分防护，不是对可见正文中语义 prompt injection 的完整安全边界。[fetcher 基础文档](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/fetching/choosing.md#L55-L76) / [MCP 指南](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/ai/mcp-server.md#L30-L44)

### 不能做什么

- 没有全网搜索 provider；`google_search=True` 只是设置 Google referer，不是调用 Google 搜索 API。[DynamicFetcher 参数](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/docs/fetching/dynamic.md#L71-L94)
- 没有 YouTube/B站视频搜索、字幕提取、媒体下载、转录或视频帧语义理解契约。它只能抓页面 DOM、截图或捕获页面请求。
- 不自带 Incept 需要的 source policy、claim-level evidence schema、项目/租户授权、引用与抓取时间/hash 持久化、人工审核门槛。
- “能绕过”不等于“被允许抓取”；库的 BSD 许可不会为目标网站内容版权、服务条款、个人数据或账号自动化授权。

## 与 Agent Reach 的概念关系

Scrapling 和 Agent Reach 不是互相替代的同类产品。

| 维度 | Scrapling | Agent Reach | 对 Incept 的含义 |
|---|---|---|---|
| 定位 | 可嵌入 Python 的 parser/fetcher/browser/spider 框架，外加 MCP 和 Skill | “能力层”/安装器/doctor/路由表；实际读取交给上游 CLI/MCP | Scrapling 可以是一个底层 provider；Agent Reach 是 provider 选型和运维层 |
| 渠道广度 | 任意公网页的 HTTP/DOM/浏览器抓取 | Web、YouTube、B站、X、Reddit、小红书、GitHub、RSS 等多渠道 | Agent Reach 对 Video 的补充点是字幕/平台搜索；Scrapling 的补充点是 JS 页面 |
| 搜索 | 无内建通用搜索 provider | 路由到 Exa、YouTube/B站搜索等 | 都不应替换 Incept 服务端稳定 `web_search` 契约 |
| 集成方式 | Python API，也可 CLI/MCP | 要求 Agent 可执行 shell，直接运行 `yt-dlp`、`gh`、OpenCLI、mcporter 等 | Incept 生产 Agent 不应获得通用 shell；若试 Scrapling，只用库 API 后置于 typed adapter |
| 反爬 | 直接实现指纹伪装、代理、Cloudflare 解题 | 按渠道选择外部工具或浏览器登录态 | 两者都需要单独的 ToS/账号/凭据治理 |
| 持久化 | adaptive SQLite、Spider 本地 checkpoint/cache，browser session 在进程内 | 用户级 config/credentials，provider 状态与 doctor | 都不能直接当作 Cloud Run 的耐久任务系统 |

Agent Reach 官方自定义为“能力层，不是又一个工具”，负责选型、安装、体检和路由，实际读取由 Agent 直接调用上游工具。[官方 README](https://github.com/Panniantong/Agent-Reach/blob/main/README.md#L177-L203)
因此，理想的 Incept 内部分层是：

```text
web_search / video_search / video_transcript_fetch   稳定产品契约
                    |
          server-owned provider router
              /                 \
   HTTPX static fetch      Scrapling dynamic fetch  (可选稍后)
   平台官方/API适配器   字幕/媒体专项 adapter (独立评估)
```

不应在模型 prompt 中同时暴露 Scrapling MCP 和 Agent Reach shell Skill，让模型自行选择命令、登录态、代理或反爬参数。provider 选择和授权必须由 Incept 服务端决定。

## Cloud Run 运维与安全风险

| 风险 | 当前证据 | 对 Incept 的处置 |
|---|---|---|
| CPU/内存争抢 | Scrapling browser fetcher 会启动/复用 Chromium tab；Incept 当前 API 只有 2 vCPU/4 GiB、单实例但并发 20，还执行视频抓取/导出 | 不放进主 API；独立 worker，初始 concurrency 1，设置每租户/每 host 队列和内存门槛 |
| 非耐久状态 | Cloud Run 容器文件系统是内存且实例停止后不持久；Scrapling adaptive 默认 SQLite，Spider checkpoint/cache 写本地磁盘，session 在进程内 | PoC 先禁用 adaptive/Spider/session 跨请求依赖；若有耐久 crawl 需求，用外部任务/证据存储重新设计，不依赖实例本地状态。[Cloud Run 容器契约](https://cloud.google.com/run/docs/container-contract) |
| 超时与中断 | Cloudflare solver 建议至少 60 秒；Incept Cloud Run request timeout 为 900 秒。Cloud Run 超时后客户连接终止，容器代码可能仍在运行 | 动态 fetch 设置更短的应用级 deadline/取消；长任务转队列/作业，任务幂等且可恢复。[Cloud Run 超时文档](https://cloud.google.com/run/docs/configuring/request-timeout) |
| SSRF/内网探测 | Scrapling 静态 safe redirect 只解决 redirect 私网问题；MCP/browser tool 可从服务主机 fetch 任意 URL，`cdp_url`、proxy、cookies 也是入参 | 不直接用 MCP；在启动浏览器前和每次顶层 redirect 重用 Incept URL policy，还要在 browser route 层拦截所有私网/metadata/非 allowlist 子资源 |
| 登录态/代理风险 | 官方 API 支持 cookies、persistent user data dir、proxy、CDP remote browser | 第一阶段全部不暴露；不使用员工主账号和浏览器 profile；若以后确有需求，单独租户隔离、Secret Manager、日志脱敏和审核 |
| prompt injection | Markdown/MCP sanitizer 删除隐藏 DOM 和常见不可见字符，但正文仍是不可信内容 | 保留 Incept 现有“evidence, never instructions”规则，严格限字符并先转 evidence schema，不让 retriever 直接获得 canvas/写入权限 |
| robots/ToS/封禁 | robots.txt 遵守默认关闭；项目以绕过 Cloudflare/指纹检测为卖点 | 默认不启用 stealth/solver，站点维度 allowlist + robots + 服务条款复核；403/429/CAPTCHA 立即停止，不自动升级为绕过 |
| 依赖/版本风险 | v0.4.15 仍为 Beta 且 MCP 有 breaking changes；官方 extras 多为下限约束 | pin 准确 Scrapling/browser 版本，lock/hash/SBOM 和回归测试；不跟 `latest` 镜像，不与 API 主依赖共享升级周期 |

Cloud Run 官方还说明，文件写入会占用实例内存，超出总内存限制会终止实例；并发请求不互相隔离。官方建议对每请求消耗大部分 CPU/内存或共享全局状态的服务降低 concurrency。[Cloud Run 容器契约](https://cloud.google.com/run/docs/container-contract) / [Cloud Run 并发说明](https://cloud.google.com/run/docs/about-concurrency)

## 许可证与合规边界

Scrapling 本体使用 **BSD 3-Clause**：允许源码/二进制使用、修改和分发；分发时需保留版权、许可条款与免责声明，不得未经允许使用版权人/贡献者名称背书。软件按现状提供。[官方 LICENSE](https://github.com/D4Vinci/Scrapling/blob/v0.4.15/LICENSE)

本体许可友好，但不会自动解决：

- Playwright、Patchright、Chromium、curl_cffi 等直接/传递依赖的许可声明与安全更新；
- 被抓内容的版权、隐私和保留要求；
- 目标平台的 ToS、robots.txt、登录态自动化、代理使用、反爬绕过和账号封禁风险。

## 建议的分阶段方案

### 现在：不安装

1. 保留现有 `web_search` + 受控 `web_fetch`；先把 evidence schema、抓取时间/hash、provider health/fallback 做完，因为 Scrapling 不会替代这些产品契约。
2. 统计调研中 `web_fetch` 的失败原因：JS 空页、403/429、内容类型、页面过大、超时、视频/字幕需求分开记录。不要把“需字幕”误归为动态 HTML 抓取失败。
3. 不安装 Scrapling MCP、Agent Skill、`ai`/`all` extras，不向生产 Agent 开放通用浏览器、代理、cookies、CDP 或 Playwright callback。

### 触发条件：数据证明 JS 页是主要瓶颈时

只在以下条件同时成立时开始 PoC：

- 连续真实调研中，一批业务重要的允许站点因 JS 渲染而不可取证，且占比/频率已足以支撑一个 browser worker；
- 目标域名已通过产品/法务/安全复核，不需要登录、付费墙、CAPTCHA 或反爬绕过；
- 有独立 Cloud Run service/worker 预算和可观测性，不与视频导出共享主 API 资源。

### PoC 形式

1. 只测 `DynamicFetcher`/`AsyncDynamicSession`，暂不测 `StealthyFetcher`、Spider、adaptive、MCP 或官方 Agent Skill。
2. 固定 2–3 个 allowlisted 域名和 20–50 个真实样本；阻断私网/metadata/跨域第三方资源，不传 cookies/proxy/CDP/user-data-dir。
3. 比较现有 HTTPX 与 Scrapling：成功取得可引用正文的比率、冷启动、p50/p95 耗时、单请求峰值内存/CPU、输出稳定性、超时/崩溃、页面更改后维护成本。
4. 产物只能是受控 evidence document：original/final URL、retrieved_at、HTTP status、content hash、限长文本/截图、extractor/version、policy decision。
5. 验收前做内网地址、DNS 重绑、redirect、子资源请求、超大 DOM、无限 network idle、browser crash、取消和并发压力测试。

### 只有 PoC 证明净收益后才集成

将它作为 Incept 后端的一个内部 provider，而不是 Agent 可直接控制的新工具族：

```text
Agent: dynamic_web_fetch(url)
        |
Incept policy: URL allowlist + DNS/IP + redirect + robots/ToS + quota
        |
queue / isolated low-concurrency worker
        |
Scrapling DynamicFetcher (pinned version, no stealth/cookie/proxy/CDP)
        |
bounded EvidenceDocument -> existing research artifact flow
```

对外契约保持为 Incept 自己的 `dynamic_web_fetch`，这样可以随时把 Scrapling 换成 Playwright/Crawl4AI 或其他 provider，不把库的大量参数、breaking changes 和反爬能力固化到 Agent 协议中。

## 最终决策

**可选稍后，不是现在安装，也不是永久排除。**

- **现在**：不改 `requirements.txt`、Dockerfile、Agent tool registry 或 Cloud Run 配置。
- **未来评估形式**：独立 worker 中的 allowlisted `DynamicFetcher` PoC，只验证 JS 页面取证。
- **明确不做**：Scrapling MCP、Agent Skill、`ai`/`all` extra、主 API 内嵌 browser pool、模型可控的 cookies/proxy/CDP/Playwright callback、默认 Cloudflare 绕过。
- **与 Agent Reach 的结论不变**：Agent Reach 是多渠道能力路由/诊断概念，Scrapling 是一个抓取引擎/provider；两者都不应以通用 shell/MCP 形态进入 Incept 生产 Agent。
