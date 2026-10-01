# 受控网页抓取与搜索来源层：开源方案评估

研究日期：2026-09-24  
目标：给 AI Video Research Agent 提供**可审计、可限流、不能任意联网**的检索与取证能力，而不是部署一个无边界的爬虫。

## 结论

首期建议在现有 FastAPI 内实现一个很小的 policy layer，使用 **HTTPX + Trafilatura 处理静态正文，Crawl4AI 作为少量 JS 页面 fallback**；搜索发现如确有需要，再部署隔离的 **SearXNG**。这不是从零造爬虫：这些组件都是可直接集成的开源项目；真正需要自己拥有和测试的是许可/安全策略、任务配额和证据记录。

不要把 Firecrawl self-hosted 作为第一期依赖。它功能完整，但当前官方 Compose 基线包含 API/workers、Playwright、Redis、RabbitMQ、NuQ PostgreSQL 和可选 FoundationDB，且主体为 AGPL-3.0，部署、升级和许可证评估的成本明显超过本产品“每次研究抓取少量可引用来源”的需求。[官方自托管说明](https://github.com/firecrawl/firecrawl/blob/main/SELF_HOST.md)

`robots.txt` 是访问约定而不是许可；必须同时遵守站点条款、付费墙/登录限制和适用法律。下述技术控制不能替代这些审核。

## 方案对比

| 方案 | 许可证/自托管 | 受控访问能力 | 产物与引用 | 对 FastAPI 的适配判断 |
|---|---|---|---|---|
| **Crawl4AI** | Apache-2.0；可作为 Python 库或 Docker 服务运行。[仓库许可](https://github.com/unclecode/crawl4ai/blob/main/LICENSE) / [自托管文档](https://docs.crawl4ai.com/core/self-hosting/) | 原生支持 `check_robots_txt=True`、随机延迟、429/503 退避、并发 dispatcher；`url_matcher` 支持 glob/函数规则，另有排除外链/域名配置。[参数](https://docs.crawl4ai.com/api/parameters/) | 可得 Markdown、HTML、结构化 CSS/JSON 抽取；Markdown 链接可渲染为编号引用，便于保存证据链。[SDK 文档](https://docs.crawl4ai.com/complete-sdk-reference/) | **JS fallback 首选**。把它置于 policy layer 后：只接收已验证的 URL 和小批量任务，避免让模型直接配置 crawler。 |
| **Trafilatura** | Apache-2.0、纯 Python 库。[官方文档](https://trafilatura.readthedocs.io/en/stable/index.html) | 支持 sitemap/feed/link discovery、URL filter、blacklist、每站点等待时间；但不会替应用完成 robots、SSRF 或全局限流政策。[CLI 文档](https://trafilatura.readthedocs.io/en/latest/usage-cli.html) | `extract()` 可输出 JSON/XML/Markdown，并含标题、作者、发布日期、URL 等元数据。[核心 API](https://trafilatura.readthedocs.io/en/latest/corefunctions.html) | **静态页面正文首选**：轻、易部署、无浏览器服务；抓取请求与安全策略由 HTTPX/FastAPI 统一执行。 |
| **HTTPX + Trafilatura**（最佳轻量替代） | HTTPX 为 BSD-3-Clause；与 FastAPI 同为 async Python 生态。[许可证](https://github.com/encode/httpx/blob/master/LICENSE) / [async 文档](https://www.python-httpx.org/async/) | HTTPX 有 timeout、连接池、重定向上限与流式读取；allow/block host、DNS/IP 校验、每 host token bucket 均由本项目显式实现。 | 原始响应 metadata + Trafilatura 的正文/metadata；引用格式完全由 LinglongLab 定义。 | **第一期基础**：最小依赖、可针对我们的审计模型设计；不能渲染 JS，交给 Crawl4AI。 |
| **Playwright** | Apache-2.0。[仓库许可](https://github.com/microsoft/playwright/blob/main/LICENSE) | `browserContext.route()` / `page.route()` 可按 glob、正则或 predicate continue/abort 请求，适合阻断第三方资源或强制 host allowlist；它不负责 robots 或站点级限流。[网络控制文档](https://playwright.dev/docs/network) | 可取 DOM、HTML、截图和网络响应，但正文清洗、元数据与引用 schema 需自行实现。 | 只作为 Crawl4AI 不能覆盖时的最后 fallback；单独维护浏览器进程的性价比不高。 |
| **SearXNG** | AGPL-3.0-or-later；官方提供 Docker/Compose 部署。[许可证](https://github.com/searxng/searxng/blob/master/LICENSE) / [容器安装](https://docs.searxng.org/admin/installation-docker) | 可 keep/remove 特定搜索引擎、设置其 timeout/连接池；自身 limiter 用 Valkey 做 bot detection/rate limiting。[engines 设置](https://docs.searxng.org/admin/settings/settings_engines.html) / [limiter](https://docs.searxng.org/admin/searx.limiter) | 返回检索候选（标题、摘要、URL），不是页面证据；每个候选仍须交由 fetch 工具按 policy 重新验证。 | 可选的**发现层**，内网部署且仅由后端调用；需评估 AGPL 和上游搜索引擎条款/封禁风险。 |
| **Firecrawl self-hosted** | 主体 AGPL-3.0；官方开源且提供 Compose/Kubernetes 路径。[README](https://github.com/firecrawl/firecrawl) / [SELF_HOST](https://github.com/firecrawl/firecrawl/blob/main/SELF_HOST.md) | 有 scrape/crawl/map/extract API 与并发变量；但默认 API 无认证，官方明确要求生产环境自行补鉴权、TLS、网络策略、持久化和备份。 | 可输出 clean Markdown/HTML/结构化数据，适合更大规模 crawler 服务。 | **暂不推荐首期**：更重的运行栈和 AGPL 义务，应等需求出现批量站点抓取/团队通用服务时再评估。 |

## 建议的受控契约

Agent 不应获得浏览器、HTTP 或任意 URL 工具，只能调用后端定义的两个 typed tools：

```text
search(query, approved_domains?, max_results<=5) -> SearchResult[]
fetch(url, purpose, max_chars<=12000) -> EvidenceDocument | PolicyRejection
```

`fetch` 在任何具体抓取器之前执行以下强制规则：

1. 只接受 `http` / `https`；每次 DNS 解析和每次 redirect 后，拒绝 loopback、private、link-local、metadata IP 与非标准端口，防止 SSRF。
2. 先用站点条款/域名 allowlist，再读取 `robots.txt`；默认拒绝，只有明确允许才继续，并尊重 `Crawl-delay`。
3. 默认上限：每 host 并发 `1`、`0.2–0.5 req/s` token bucket、每次研究至多 `5` 页、单页 `2 MB`、`20 s` 超时、最多 `3` 次 redirect。收到 429/403 或反爬页面即停，不尝试绕过。
4. 不登录、不提交表单、不绕过付费墙/CAPTCHA，不抓取社媒无限流或下载文件；对产品官网、官方文档、可信媒体采用项目或管理员维护的 allowlist。
5. 每个可供模型使用的 document 持久化：原始 URL、最终 URL、title、publisher/domain、抓取时间、HTTP 状态、content hash、截取文本、抽取器版本与 policy decision。模型的每一条 research finding 必须保存其 `evidence_id` 列表，前端显示链接和抓取时间。

## 首期落地轮廓

1. 建 `web_research` FastAPI 模块：`URLPolicy`、`RobotsCache`、per-host limiter、`EvidenceStore` 和上述两个 tool endpoint；配置采取显式 allow/block list，而非让模型传 crawler 参数。
2. `fetch` 先由 HTTPX 下载受控大小的 HTML，再用 Trafilatura 抽正文与 metadata；对正文过短、明确要求渲染、或运营方列入 allowlist 的页面才排队进 Crawl4AI。
3. 研究会话先只允许“用户提供的 URL + 已批准产品/官方文档域名”；SearXNG 可后加为 search provider，但搜索结果不会绕过 `fetch` policy。
4. 为 `URLPolicy` 写单元测试：私网 IP、DNS rebinding、redirect、robots 拒绝、429、超页/超大小和跨域跳转；为 evidence persistence 做集成测试，确认 UI 引用能回到精确来源。

这套 MVP 是中等偏小的工程量：静态抓取与证据 schema 可以先做，动态页与搜索作为独立的可插拔 provider。它把合规与安全风险集中在一个可测试的模块内，同时不会阻碍 Research Agent 用 Gemini 对已取证材料进行多轮分析。

> 本说明不是法律意见。上线前应由负责方核查各目标网站条款、robots 规则、部署地区的法规，以及 AGPL 组件在实际部署方式下的义务。
