# LinglongLab 项目 Context

## 产品
Linglong Lab 是 Moloco 内部创意工具，含 Image、Library、Usage、Comfy UI、Video Production。用户默认只看自己的内容，管理员可看全部。当前最高优先级是 **Video Production**：做成可控、可交付的广告视频工作台。旧 Video 已从 Sidebar 隐藏，不再新增功能。

## 技术与约束
- Web：Next.js 15/TypeScript，`apps/web`，端口 3000；API：FastAPI/Python，`apps/api`，端口 8000。
- 视频核心：`apps/api/app/incept/video_production_store.py`；前端：`apps/web/components/incept/VideoProductionView.tsx`。
- 数据为 SQLite+GCS 备份，计划迁移 Cloud SQL；资产用 `INCEPT_ASSET_BUCKET`；部署 Cloud Run。
- 图像：`gemini-3.1-flash-image`，Vertex `global`。分析/Agent：`gemini-3.8-flash`。视频：`veo-3.1-fast-generate-001`，单段仅 4/6/8 秒，长视频必须逐镜生成后拼接；image input 与 reference images 不能同时传。音乐：`lyria-3-clip-preview`，在后期处理。
- 报告、回答、fallback 必须跟随用户输入语言。禁止猜测或修改 GCP 模型、端点、区域、项目配置；4xx 先要求官方文档或用户确认，遵守 `AGENTS.md`。

## Video Production 流程
每个 production 是一支广告的制作档案，不以旧 Thread 为核心。
1. **Direction / Creative Strategist**：分析参考视频可迁移的结构、节奏、镜头语言和商业机制；输出策略、素材缺口、故事结构、原创边界。不得复制竞品品牌、人物、Logo、文案。
2. **Script / Screenwriter**：输出可编辑、版本化剧本。每个 Beat/Shot 不超过 5 秒，包含画面、台词/字幕、音效、CTA、品牌规则。
3. **Design / Production Designer**：先建 Design Bible 与受控 Asset Packs，再进入 Storyboard。底部 Composer 用来修订视觉规则、Pack 范围、提示词和连续性；Pack 的 Generate 才执行生图。
4. **Storyboard**：每镜头绑定角色状态、场景、产品/UI、灯光、运动、单张关键帧、Veo prompt、连续性和声音提示。
5. **Generate/Edit/Deliver**：逐镜 Veo、必要时首尾帧，再确定性剪辑音乐、字幕、CTA、免责声明，最后 QA 和导出。

## 一致性与 Pack
2x2/contact sheet 仅锁定视觉状态，整张不能交给 Veo；Veo 只接收当前镜头的单张 9:16/16:9 关键帧，连续运动才用首尾帧。
- Character：正面、3/4 侧面、背面，锁脸、发型、服装、体型。
- Environment：全景、正反打、关键物件位置，防空间断层。
- Prop：独立产品/道具，不能出现人物、手或参考视频；优先 Product 静态图，历史数据可回退静态 Brand 图。
- UI：Logo、手机屏幕、CTA、游戏 UI；Lighting：色温/光向/焦段；Motion：起势/动作/微动；Transition：跨镜头视觉锚点。

Designer 按剧本实际需求创建 Pack，不能将同一历史素材误拆成多个。支持 `Generate missing packs` 与 `Regenerate all packs`。没有静态产品图时，Prop Pack 必须明确失败，不能借用人物或视频。

## 目标与工程纪律
完成稳定的 Pack、Storyboard、逐镜 Veo、后期音频/字幕/CTA、QA 与下载链路。QA 关注黑帧、重复镜头、人物/产品/灯光一致、时长、品牌清晰、失败可诊断。UI 保持白底工作区、结构化结果卡片、阶段导航、底部固定 Composer，避免冗长聊天历史。

工作区常有用户未提交修改，禁止重置或覆盖。手动编辑用 `apply_patch`。大改前后运行 `code-review-graph`，并运行 Python 编译、`git diff --check` 和 Web build。不要提交密钥、环境变量、数据库、临时素材或 `tmp`。
