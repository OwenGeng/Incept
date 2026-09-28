# Agent Reach 与 Anthropic Financial Services：Incept 搜索与调研适配评估

研究日期：2026-09-28  
评估对象：

- [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach)
- [anthropics/financial-services](https://github.com/anthropics/financial-services)

评估范围只采用两个项目自己的官方 GitHub 仓库 README、LICENSE、源码和仓库内官方文档；未采用第三方文章、测评或二手解读。本文不是法律意见。

## 结论

**两个项目都不需要安装到 Incept 的 FastAPI 运行时、生产镜像或项目 Python 环境。**

| 项目 | 实际定位 | 与 Incept 的直接重合 | 建议 |
|---|---|---|---|
| Agent Reach | 面向本机 Agent 的 CLI/安装器/doctor/Skill；实际搜索和读取由 Exa、Jina Reader、`gh`、`yt-dlp`、OpenCLI、各平台 CLI/MCP 完成 | Incept 已有服务端 `web_search`、`web_fetch`、research artifacts 和受限 tool loop；通用网页搜索与抓取高度重复 | **不安装进 Incept。** 可在隔离开发机用 `pipx` 做小范围只读 PoC；只验证 YouTube/B站字幕和少数社媒信号，验证后将单项能力重写为受控 adapter/worker |
| Anthropic Financial Services | Claude Cowork 插件、Markdown Skill、金融 Agent prompt、MCP 配置和 Claude Managed Agents 示例 | 金融分析内容与视频制作不匹配；Managed Agents/Claude 模型与当前 Gemini/FastAPI 技术栈不兼容 | **不安装。只借鉴架构。** 重点吸收不可信材料隔离、结构化交接、唯一写入者、人工审核门槛、typed handoff；不引入金融 Skill、数据连接器或 Anthropic API |

对搜索与调研确实有补充，但补充点不是“把两个仓库装上”：

1. Agent Reach 补的是 **YouTube/B站字幕、社媒讨论、渠道健康检查和 provider fallback**。
2. Financial Services 补的是 **研究流程的安全分层、证据结构、写权限隔离与人工签核**。
3. 现阶段优先级应是把这些模式融入 Incept 自己的 typed tools 和 artifact contract，而不是在 FastAPI 进程中开放 shell、浏览器 Cookie、通用 MCP 或第二套模型供应商。

## Incept 当前基线与真正缺口

当前实现已经具备以下基础：

- `apps/api/app/video_studio/research_tools.py` 内建服务端 `web_search` 与 `web_fetch`，包含 HTTP(S) 限制、非标准端口拒绝、DNS/IP 公网检查、重定向逐跳复核、响应类型/大小/字符数限制。
- 同一模块把可写 research artifact 限制在固定路径，并通过 `sha256` 实现 read-before-replace 和并发覆盖保护。
- `apps/api/app/video_studio/agent.py` 已有最多 6 轮、12 次调用、每轮最多 3 个工具和单次结果 20,000 字符的 tool loop；prompt 也明确把网页内容视为不可信证据。
- 已有 `production/approved-brief.md` 的生成门槛，研究阶段可以阻止生成节点。

因此，现阶段不是缺一个“通用上网包”，而是有四个更具体的缺口：

1. 静态网页工具不能可靠提取需要 JavaScript、登录态或媒体解析的视频/社媒内容。
2. 研究结果虽然要求 URL 引用，但没有强制的 claim-level evidence schema、抓取时间、内容 hash、来源类型和“未证实”状态。
3. 同一个模型同时接触不可信网页内容、写 research artifact、生成最终回答，并在允许时编辑 canvas；prompt 隔离已经有了，权限隔离还没有。
4. 搜索/抓取 provider 没有显式 health 状态、故障分类、fallback 顺序和可观测性。

这四点正好分别可以从两个项目中择优借鉴。

## 项目一：Agent Reach

### 定位：CLI/工具与 Skill，不是应用运行时搜索 SDK

Agent Reach 官方源码把自己定义为“installer, doctor, and configuration tool”；`AgentReach` Python 类只提供渠道健康检查，实际读取和搜索要直接调用上游工具。[`core.py`](https://github.com/Panniantong/Agent-Reach/blob/main/agent_reach/core.py) 和 [MCP server](https://github.com/Panniantong/Agent-Reach/blob/main/agent_reach/integrations/mcp_server.py) 都明确说明 MCP 仅暴露状态，真实内容访问仍由 `twitter-cli`、`yt-dlp`、`mcporter` 等完成。

项目随包附带的 [Agent Skill](https://github.com/Panniantong/Agent-Reach/blob/main/agent_reach/skill/SKILL_en.md) 本质是命令路由手册：先运行 doctor，再让 Agent 直接执行 `mcporter`、`curl`、`gh`、`yt-dlp`、OpenCLI 或各平台 CLI。它适合可执行本机命令的 Claude Code/OpenClaw/Cursor 类环境，不是可直接挂到 FastAPI tool registry 的受控 API。

分类结论：

- 不是 Incept 的运行时依赖。
- 是本机 CLI/安装器/诊断工具。
- 同时提供一个 Agent Skill/命令示例集。
- 其 channel/provider 设计可以作为架构参考。

### 安装会引入什么

官方 [`pyproject.toml`](https://github.com/Panniantong/Agent-Reach/blob/main/pyproject.toml) 要求 Python 3.10+，直接 Python 依赖为：

- `requests>=2.28`
- `feedparser>=6.0`
- `python-dotenv>=1.0`
- `loguru>=0.7`
- `pyyaml>=6.0`
- `rich>=13.0`
- `yt-dlp[default]>=2026.07.04`

可选 extras 还包括 Playwright、`mcp[cli]` 和 `browser-cookie3`。但 Python 包只是入口；完整安装的实际范围大得多。

官方 [安装指南](https://github.com/Panniantong/Agent-Reach/blob/main/docs/install.md) 推荐通过 GitHub `main.zip` 安装。默认 `agent-reach install` 是只读检查；传入 `--system` 后，[安装器源码](https://github.com/Panniantong/Agent-Reach/blob/main/agent_reach/cli.py) 可进一步：

- 通过 apt 或 Homebrew 安装 `gh`、Node.js/npm；
- 通过全局 npm 安装 `undici`、`mcporter`、OpenCLI；
- 通过 pipx/uv 安装 Twitter、Reddit、Bilibili、Boss 等平台 CLI；
- 写用户级 mcporter/Exa 配置、yt-dlp 配置和 Agent Skill；
- 某些频道需要 Chrome 扩展、本地浏览器或额外 MCP 服务；
- 小宇宙转录需要 `ffmpeg` 和 Groq；其他转录路径可能使用 OpenAI。

这与“向 FastAPI 加一个 Python 库”完全不同。它会扩大操作系统、Node、浏览器、全局命令和用户配置的供应链面，因此不应在生产镜像构建或 API 服务启动时执行。

### 密钥、外部服务和登录态

仓库的 [`.env.example`](https://github.com/Panniantong/Agent-Reach/blob/main/.env.example) 和安装文档列出或涉及：

- Exa、Jina Reader 等远端搜索/读取服务；
- GitHub token；
- Groq API key、可选 OpenAI API key；
- HTTP/HTTPS 或平台代理；
- Twitter/X、Reddit、小红书、Facebook、Instagram、雪球等平台的 Cookie 或浏览器登录态；
- Chrome 扩展和 OpenCLI 对现有浏览器会话的访问；
- 本地 xiaohongshu MCP、mcporter 以及其他第三方 CLI。

配置代码有值得肯定的安全实现：[`config.py`](https://github.com/Panniantong/Agent-Reach/blob/main/agent_reach/config.py) 使用 `~/.agent-reach/config.yaml`、原子替换、Unix `0600`，并拒绝符号链接路径；输出会遮蔽常见敏感字段。但这只能保护本地配置文件，不能消除 Cookie 等同完整登录权限、上游 CLI 读取凭据、第三方远端服务接收查询/内容、平台封号或服务条款等风险。

### 主要风险

1. **供应链不可直接纳入生产。** 官方安装命令引用可变的 `main.zip`；多数 Python 依赖只有下限，没有 lock。系统安装还会拉取多个 npm/pipx/uv 包和 GitHub 工具。若未来做 PoC，应固定 commit、固定每个上游版本、保存 hash 并扫描 SBOM。
2. **凭据爆炸半径大。** Cookie 往往等同账户会话；浏览器扩展或 CLI 也可能访问登录态。生产服务账号与员工日常账号不能混用，不能把用户 Cookie 存进 FastAPI 普通配置或日志。
3. **平台稳定性与 ToS 风险。** 很多能力依赖非正式接口、浏览器会话或反自动化敏感平台。项目自己的 [安全政策](https://github.com/Panniantong/Agent-Reach/blob/main/SECURITY.md) 也把依赖漏洞排除在项目漏洞范围之外，因此依赖治理必须由 Incept 自己承担。
4. **过宽的 Agent 行为。** 内置 Skill 把大量互联网任务声明为 MUST USE，并指导 Agent 执行 shell。这个策略不能原样注册到生产 Agent；Incept 应继续只暴露后端实现的 typed tools。
5. **运行形态错位。** OpenCLI、浏览器 Cookie 和桌面扩展适合个人开发机，不适合多租户、无界面的 FastAPI 服务。

### 对 Incept 的具体补强

#### 值得试验的能力

- **YouTube 字幕与元数据**：对 CTV/电商视频案例调研最直接。静态 `web_fetch` 无法证明“看过视频”，字幕/章节/时长能显著提高证据质量。
- **B站字幕、搜索和视频元数据**：补足中文视频创意样本。
- **少量社媒讨论信号**：Reddit、X、小红书、B站可用于受众痛点、评论语言和竞品口碑，但不能作为权威事实来源。

#### 值得借鉴的架构

- [Channel 基类](https://github.com/Panniantong/Agent-Reach/blob/main/agent_reach/channels/base.py) 的“有序候选 backend + 显式 `active_backend` + 用户 override”。
- [probe](https://github.com/Panniantong/Agent-Reach/blob/main/agent_reach/probe.py) 与 [doctor](https://github.com/Panniantong/Agent-Reach/blob/main/agent_reach/doctor.py) 的真实轻量探测，而不是只用 `which` 判断存在；区分 missing、broken、timeout 和远端错误。
- 每个平台独立 adapter，失败后按已配置顺序降级，而不是让模型临时猜命令。

#### 不应照搬

- 不替换现有 `web_search`/`web_fetch`；Incept 当前的 SSRF、响应大小和 artifact 写入边界更符合服务端产品。
- 不给模型通用 shell、`curl`、mcporter 或浏览器控制权。
- 不在 API 容器里全量安装 Agent Reach，也不启用自动系统修改。
- 不把社媒 Cookie 作为多租户服务的常规认证方式。

### 明确建议

**生产：不安装。开发评估：可选、隔离、只做最小 PoC。**

如果确实要验证增益，建议流程是：

1. 在非生产开发机用 `pipx` 隔离安装固定 commit；先运行只读检查或 `--dry-run`，不使用 `--system`。
2. 只启用 YouTube/B站，不启用 `all`，不导入主账号 Cookie。
3. 记录成功率、平均耗时、转录覆盖、来源可引用性、失败分类和维护成本。
4. 只有指标证明有价值，才在 Incept 中实现独立 `video_transcript_fetch` adapter/worker：固定允许的平台与命令、无 shell 字符串拼接、URL allowlist、文件/时长/超时/并发限制、隔离临时目录、结构化输出和审计。

## 项目二：Anthropic Financial Services

### 定位：金融 Skill/Agent 示例与 Claude 部署模板

官方 [README](https://github.com/anthropics/financial-services/blob/main/README.md) 把仓库定义为金融服务工作流的 reference agents、skills 和 data connectors，并提供两种运行方式：Claude Cowork 插件或 Claude Managed Agents API。仓库主要内容是 Markdown、JSON 和 YAML，没有面向 FastAPI/Gemini 的通用运行时包或 SDK。

它包含：

- 自包含的金融 Agent prompt 与 Skill；
- 投行、股票研究、私募、基金运营、KYC 等 vertical plugins；
- `/comps`、`/dcf`、`/earnings` 等 Claude 命令；
- 金融数据商与文档系统的 MCP 配置；
- `agent.yaml`、leaf worker 和 steering 示例；
- 把 Skill 上传到 Anthropic、创建 subagent/orchestrator 的参考脚本。

分类结论：

- 不是 Incept 的运行时依赖。
- 是 Claude/Cowork 的 Skill 和插件集合。
- Managed Agent 部分是 reference cookbook/示例部署。
- 对 Incept 最有价值的是安全和编排架构，不是金融内容。

### 安装与运行会引入什么

只在 Claude Code/Cowork 中安装插件时，仓库主体是文件式 prompt/Skill，并无统一 build step。若部署 Managed Agents，[部署脚本](https://github.com/anthropics/financial-services/blob/main/scripts/deploy-managed-agent.sh) 要求：

- `ANTHROPIC_API_KEY` 和 Anthropic API；
- `curl`、`jq`、`zip`、Python 3 与 PyYAML；
- 上传 Skill 到 `/v1/skills`，创建多个 agent，并使用 Managed Agents beta API；
- 参考 orchestrator 还导入 `anthropic` Python SDK 与 `jsonschema`。[`orchestrate.py`](https://github.com/anthropics/financial-services/blob/main/scripts/orchestrate.py)

部分 DCF Skill 脚本还声明 `openpyxl>=3.0.0` 和 `requests>=2.28.0`。Microsoft 365 示例另有 FastAPI、Uvicorn、PyJWT 等依赖，但与 Incept 视频研究无关。

[Market Researcher manifest](https://github.com/anthropics/financial-services/blob/main/managed-agent-cookbooks/market-researcher/agent.yaml) 直接指定 Claude 模型和 CapIQ/FactSet MCP，要求 `CAPIQ_MCP_URL`、`FACTSET_MCP_URL`。这不是 Incept 当前的 Vertex Gemini 配置；也没有理由为视频研究引入第二套模型供应商、API key 和 agent 生命周期。

### 外部服务、数据和安全风险

官方 README 列出 Daloopa、Morningstar、S&P Global、FactSet、Moody's、MT Newswires、Aiera、LSEG、PitchBook、Chronograph、Egnyte、Box 等远端 MCP，并明确说明访问可能需要订阅或 API key。[金融 MCP 配置](https://github.com/anthropics/financial-services/blob/main/plugins/vertical-plugins/financial-analysis/.mcp.json)

风险包括：

1. **数据出境与第三方处理。** 报告、客户材料或内部文档若发往 Anthropic 或外部 MCP，必须单独完成供应商、地区、保留策略、权限和合同审查。
2. **prompt injection 与跨 Agent 注入。** 仓库自己的 [`orchestrate.py`](https://github.com/anthropics/financial-services/blob/main/scripts/orchestrate.py) 明确警告：不可信文档可以伪造 `handoff_request` 文本。参考脚本通过目标 allowlist 与 JSON Schema 降低风险，并建议生产中使用模型无法通过引用文本伪造的专用 tool call 或 typed SSE event。
3. **Preview 能力。** README 把 `callable_agents` 标记为 Research Preview，不应当作 Incept 生产稳定接口。
4. **当前主分支不宜直接投产。** 本次对官方主分支快照运行静态检查时，`plugins/vertical-plugins/financial-analysis/.mcp.json` 不能通过 JSON 解析（`box` 项目前缺逗号且闭合结构不完整）；运行仓库自己的 [`scripts/check.py`](https://github.com/anthropics/financial-services/blob/main/scripts/check.py) 也报告 meeting-prep-agent 的三个 bundled skills 找不到对应 vertical source。其定位确实应按“可定制参考模板”理解，而不是可无审查部署的产品依赖。
5. **领域错配。** 金融 Agent 的来源、术语、合规门槛、Excel/PowerPoint 产物均不是视频创意调研需求；照搬会增加 prompt 体积和错误路由。

### 值得借鉴的研究架构

最值得参考的是 [Market Researcher](https://github.com/anthropics/financial-services/blob/main/plugins/agent-plugins/market-researcher/agents/market-researcher.md) 与其 [managed-agent cookbook](https://github.com/anthropics/financial-services/blob/main/managed-agent-cookbooks/market-researcher/README.md)：

1. **不可信文档读取者与写入者分离。** `sector-reader` 只拥有 Read/Grep，不拥有 Write 或外部 connector；`note-writer` 是唯一拥有 Write 的 worker，且不直接打开第三方报告。
2. **结构化、限长交接。** reader 返回有 `maxItems`、`maxLength`、禁止额外字段的 schema-validated JSON，而不是把原始网页任意文本直接交给可写 Agent。[`sector-reader.yaml`](https://github.com/anthropics/financial-services/blob/main/managed-agent-cookbooks/market-researcher/subagents/sector-reader.yaml)
3. **最小权限。** comps worker 只读金融 MCP，writer 无外部 connector；每个 worker 只持有完成角色所需的工具。
4. **人工审批。** Agent prompt 要求 peer comps 和最终 note 后停止，等待分析师审核；README 总则也要求所有输出由合格人员签核，Agent 不负责发布或执行交易。
5. **来源纪律。** 每个数字必须有来源，找不到时显式标记 `[UNSOURCED]`，而不是估计。
6. **typed handoff。** 跨 Agent 目标硬 allowlist、payload schema、长度和字符集约束；不把模型文本本身当作可信控制面。

### 对 Incept 的具体补强

这些模式可以直接转译到视频调研，而不需要 Claude Managed Agents：

#### 1. 把 research tool loop 分成三个信任区

```text
Retriever（联网、只读）
  -> Evidence Extractor（无写权限，schema JSON）
  -> Research Writer（无联网权限，只写允许的 artifact）
  -> Human approval
  -> Canvas / generation
```

当前 Incept 已在 prompt 中声明外部内容不可信，但同一个模型仍然读取 tool result、写 artifact，并可能编辑 canvas。至少在逻辑契约上，应把“外部文本”先收敛成结构化 evidence，再允许写入 artifact；writer 不应直接看到完整 HTML 或网页中的指令性文本。

#### 2. 建 claim-level evidence schema

建议每条事实保存：

- `claim`
- `source_url` 与最终重定向 URL
- `publisher/domain`
- `retrieved_at`
- `content_sha256`
- `evidence_excerpt`（限长）
- `source_type`（official、publisher、social、transcript 等）
- `support_status`（supported、conflicting、unsourced）
- `artifact_id` 或 evidence id

这比只要求自然语言附 URL 更容易审计、去重、重新抓取和显示“证据已过期”。所有数值、效果宣称和市场规模信息必须有 evidence id；否则标记未证实，不允许静默估计。

#### 3. 强化审批门槛与写权限

现有 `approved-brief.md` 是正确方向，可进一步规定：

- retrieval/extraction 工具永远不能写 canvas；
- 只有 artifact writer 可以写允许路径；
- research evidence table 和 creative synthesis 分别需要显式状态；
- 无论 Skill 是否通过 `/skill:` 显式选择，只要请求进入研究型流程，未批准 brief 都不能生成媒体节点；
- 发布、外发、账户操作不属于研究 Agent 工具范围。

#### 4. 给 provider 加 doctor 与 fallback

为 DuckDuckGo HTML、后续 transcript provider 或其他搜索源维护：

- `provider_id`
- `enabled`
- `health_status`
- `last_probe_at`
- `failure_kind`
- `capabilities`
- `priority`
- `credential_scope`

tool 执行由后端按固定策略选择 provider；模型只调用 `web_search`、`web_fetch`、`video_transcript_fetch` 等稳定契约，不看也不拼接底层 CLI 命令。

#### 5. 若以后引入多 Agent，只使用 typed event

不要解析自由文本中的 `handoff_request`。FastAPI/Pydantic 应校验目标 allowlist、payload schema、租户/项目范围、最大长度和权限；事件写审计日志，并由服务端创建下一阶段任务。

### 明确建议

**不安装，不部署 Managed Agents，不接金融 MCP。只借鉴部分架构与少量通用 prompt 规则。**

如果团队另外有真实的金融研究产品，并且已经采用 Claude Cowork/Managed Agents，可以在那个独立场景评估对应插件；它不应成为 Incept 视频研究的依赖。

## 许可证与商业内部使用

| 项目 | 许可证 | 内部商业使用 | 复制/分发时的主要注意点 | 许可证未覆盖的事项 |
|---|---|---|---|---|
| Agent Reach | [MIT](https://github.com/Panniantong/Agent-Reach/blob/main/LICENSE) | 允许使用、修改、合并和商业使用 | 分发软件或 substantial portions 时保留版权与许可声明；软件无担保 | 上游 CLI/MCP/扩展各自许可证；网站内容版权；平台服务条款、Cookie 自动化和账号封禁；远端 API 的合同与费用 |
| Financial Services | [Apache-2.0](https://github.com/anthropics/financial-services/blob/main/LICENSE) | 允许使用、修改和商业内部使用，并含有条件的专利许可 | 分发时附许可证；修改文件需显著说明；保留适用版权/专利/商标/归属声明；若有 NOTICE 则按许可证处理；不得据此获得 Anthropic 或数据商商标权；发起特定专利诉讼会触发专利许可终止条款 | Anthropic API/Cowork/Managed Agents 服务条款；第三方 MCP 与金融数据订阅/再分发权；输入文档和生成产物的合规责任；金融、法律、税务和会计专业责任 |

两个许可证本身都不阻止内部商业使用，但“代码许可证允许”不等于“外部数据、网站内容、平台账户和 SaaS API 可以任意用于商业产品”。若把任何 Skill、prompt 或源码复制到 Incept，应在第三方 notices/依赖台账中记录来源、版本或 commit、许可证和修改说明。

Financial Services README 还明确表示其产物仅供合格专业人员审核，不构成投资、法律、税务或会计意见，也不执行交易、记账或 onboarding 审批。这个“Agent 起草、人工负责”的边界值得保留为一般产品治理原则。

## 建议的落地优先级

### P0：现在

- 不向 Incept requirements、Dockerfile、启动脚本或模型配置加入任何一个仓库。
- 清理旧 Video Production 测试引用时，不以这两个项目作为替代运行时依赖。
- 把本评估作为依赖决策记录。

### P1：优先吸收，不需要新外部服务

1. 为 research evidence 定义 Pydantic/JSON Schema，并把 artifact 中的 claim 与 evidence id 关联。
2. 把不可信 retrieval result 与 artifact writer/canvas editor 分成不同权限阶段。
3. 把人工批准从 prompt 约定提升为后端状态门槛。
4. 为现有 search/fetch provider 增加 health、failure taxonomy、fallback 和审计指标。
5. 对未来 handoff 使用服务端 typed event，不解析自由文本控制指令。

### P2：有需求再做

- 用隔离开发 PoC 验证 YouTube/B站字幕与元数据；只在证明确实提高参考样本质量后，做 Incept 自有的只读 transcript adapter。
- 社媒信号采用单独来源等级与低置信度标签；只做研究，不做登录、点赞、评论或发布。

### 不建议做

- 全量安装 Agent Reach `--channels=all`。
- 在 FastAPI 服务进程中执行平台 CLI、浏览器自动化或读取员工 Cookie。
- 安装 Financial Services 的 Claude 插件作为 Incept 功能依赖。
- 为了使用示例而更改 Incept 现有 Vertex AI/Gemini 模型名、endpoint 或 location。
- 未经供应商与法务审核接入金融 MCP 或把内部资料发送到外部服务。

## 最终决策

- **Agent Reach：不安装到 Incept；只借鉴 provider/doctor/fallback，字幕能力仅做隔离 PoC 后按单项重写。**
- **Anthropic Financial Services：不安装；只借鉴研究编排、安全分层、结构化证据、唯一写入者和人工审批。**
- **对搜索与调研的净补充：有，但应成为 Incept 自己的受控能力，而不是新增两个生产依赖。**
