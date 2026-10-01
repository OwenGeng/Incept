# LinglongLab AI Video — 广告视频核心对齐范围

> 决策日期：2026-09-24；P1 集成层更新：2026-09-25  
> 产品目标：先完成一个可交付的广告视频生产系统，而不是复刻 ArcReel 的全部生态。

## 核心用户结果

用户应能在 `/ai-video` 中完成：

```text
广告 Brief
→ 商品/品牌/参考资产
→ 已批准脚本与 Shot Plan
→ 已批准 Keyframe
→ 镜头 Takes 与显式选片
→ EditRevision
→ 确定性品牌后期
→ 广告 QA
→ Final MP4 + SRT + Manifest
```

任何阶段都不能因为“页面有按钮”而算完成；必须能保存、刷新恢复、失败重试，并保留版本与来源。

## P0 验收清单

### A. Brief 与广告约束

- [x] 商品/服务、受众、市场、平台、转化目标、卖点、CTA 和 Legal 可持久化。
- [x] 项目级目标时长、画幅、语言、默认模型和预算可持久化。
- [x] 研究来源、findings、creative direction 和批准门。
- [x] creative direction、脚本、镜头和交付通过 revision lineage、fingerprint 和 manifest 可追溯。

### B. 商品与品牌资产

- [x] 一等 Product，区分不可修改的商品原图锚点与标准化生成素材。
- [x] Logo、字体、品牌色、安全区、禁用表达和 claim evidence。
- [x] 人物、场景、道具、服装和镜头关联。
- [-] 上传、生成、采用、恢复和人工替换已闭环；侧-by-侧视觉比较仍可继续增强。

### C. 脚本、分镜与 Keyframe

- [x] ScriptRevision、ShotPlanRevision、批准人与批准时间。
- [x] 广告脚本编辑器支持 hook、proof、payoff、CTA、对白/旁白和时间码。
- [-] Shot Card 与 Shot Plan 快照包含目的、时长、摄影、动作、对白/音频 cue、帧提示；连续性专用字段仍可增强。
- [x] 首帧、关键帧、尾帧及组合参考模式。
- [x] Keyframe 生成只新增候选；明确选用时更新正式帧并创建已批准不可变 revision，旧版可恢复且上游变化传播 stale。

### D. Video Take 与任务可靠性

- [x] 生成只新增候选 take，不自动覆盖正式选择。
- [x] 显式采用 take，切换时保留旧版本。
- [x] 批量全有或全无准入、费用确认和在途冲突。
- [x] Idempotency-Key、Provider checkpoint、重启恢复和下载阶段重试。
- [-] 批次逐项持久化状态、错误码与错误消息已具备；聚合的 succeeded/failed/blocked/skipped 视图仍可增强。
- [-] 产品、脚本、批准门和刷新恢复已完成浏览器 smoke；真实 provider 的付费批量提交仍需在可用凭证环境验收。

### E. 广告剪辑与确定性品牌后期

- [x] 中立 EditDocument/EDL、EditRevision 和输入 manifest 后端合同。
- [x] 后端 FFmpeg 裁切、排序、转场、音轨、字幕和文字 overlay 渲染能力。
- [x] 活跃编辑器 UI：顺序、裁切、转场、音轨、字幕、CTA、Legal、End Card。
- [x] Logo 图片 overlay、音量 ducking 和视频原生音轨选择。
- [x] FFmpeg 真实素材渲染 smoke test。
- [-] 主画幅与安全区会从 Brief 自动进入编辑器；同一母版批量派生多个画幅留在 P1。

### F. QA、费用与交付

- [x] Production WorkflowPlan、Artifact currency、QAReport、DeliveryManifest 基础合同。
- [x] 项目用量账本和显式模型定价估算。
- [x] 项目预算、预计/实际费用和剩余额度。
- [x] ffprobe 检查时长、画幅、帧率、黑帧/静帧、音量峰值和轨道存在性。
- [x] CTA、Legal、Logo、字幕安全区和必需素材规则检查。
- [x] 阻断 QA 不得创建 Final；通过后可下载 MP4、SRT 字幕和 manifest。

## P1 广告增强

- [ ] Reference Video 结构分析与原创 keep/change 规则。
- [ ] 2×2 / 3×3 Keyframe Grid。
- [ ] TTS、角色声音、音乐/SFX 生成与版本选择。
- [ ] 商品 claim evidence 自动进入脚本、镜头和 QA。
- [ ] 平台派生版本批量渲染。
- [x] 自定义声明式 endpoint：显式请求/轮询合同、类型保真的输入模板、状态/结果映射、离线响应验证、请求预览和需确认的真实连接测试。
- [x] ComfyUI API workflow：JSON 导入、显式节点绑定、能力推导、同步或 job polling 执行，以及需确认的素材/候选 ProductionArtifact 入库。
- [x] 可审阅的 endpoint market：来源、信任级别、版本、凭证去向、无密钥模板、本地安装副本和安装后独立修改。
- [x] MCP 与外部 Agent：带 scope 的一次性 API Key、现代 stateless MCP discovery/tool calls、可公开复制的 Web 代理地址，以及 WorkflowPlan/Revision/Artifact/Memory/Integration 共用合同；MCP Bearer 与 Cloud Run 服务身份可并存。
- [x] 用户/项目两级复杂记忆：类型、标签、来源、置信度、置顶、搜索、归档和 Agent 上下文注入；记忆只作为不可信建议，不覆盖正式项目数据。

## 明确不做

- 企业组织、RBAC、客户 review、多人审批和多租户治理。
- EPUB/长视频分集。
- Jianying/Premiere/Final Cut Pro 等 NLE 工程文件 adapter；产品只交付标准 MP4、字幕和 manifest。
- 跨产品/跨部署的完整历史 ZIP 导入迁移平台和高级运维控制台。

## 仍必须保留的基础工程能力

- 数据库 schema migration：应用升级时安全增加字段、表和索引，不是用户可见的“迁移平台”。
- 当前项目的备份和失败回滚：避免版本升级或渲染失败损坏广告项目。
- 标准成片导出：MP4、可选字幕文件和生产 manifest。

## 当前核心闭环状态

```text
Brief/Research 批准
→ 结构化广告脚本批准
→ 持久化 Shots 快照为 ShotPlanRevision 并批准
→ Keyframe 候选显式选用/批准
→ Takes 批量预检与显式选片
→ 编辑器保存/批准 EditRevision
→ FFmpeg 确定性渲染
→ ffprobe/品牌规则 QA
→ Final MP4 + SRT + Manifest
```

该 P0 垂直链与上述 P1 集成层已完成自动化回归。自定义 endpoint 和 ComfyUI 不内置猜测路径或模型 ID；真实第三方调用仍需用户提供 endpoint 合同、服务端环境变量凭证和可用额度，并在调用时明确确认。
