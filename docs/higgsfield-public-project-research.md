# Higgsfield 公开项目研究：Zephyr Special 与 100 项样本边界

研究日期：2026-09-15
范围：只核对 Higgsfield 第一方页面；不下载素材、不登录、不调用未公开接口。

## 结论

可以把公开项目当作**人工研究的案例库**，而不能当作可抓取的 prompt/素材数据集。给定的 [ZEPHYR: Special 项目页](https://higgsfield.ai/@higgsfield.studio/projects/zephyr-special) 对未登录访客公开了成片、项目 brief、素材文件夹、`Download assets` 与 `Open project` 入口；页面显示 `All assets 4,848`、`regenerations 90`。

点击公开素材卡片会打开 `Asset showcase`。实测其中一张图公开了：两张输入参考图、完整文本 prompt、模型（Nano Banana Pro）、质量（2k）、尺寸（2752×1536）和创建时间。项目 brief 还明确表示“all prompts are open-sourced”。所以答案是：**这个 Zephyr 项目可以看到单个素材对应的 prompt/输入/部分参数；但不能据此假设所有公开项目都以相同粒度或许可开放。**

## 可提炼的 Zephyr 制作方法

项目 brief 可归纳出一套可复用的创作方法，而不是照搬其角色、素材或 prompt：

1. **把难物理预先编码进输入。** 倒置机甲镜头没有靠不断加长 prompt 解决，而是先倒置角色设定图，让模型从输入阶段接受重力关系。
2. **先编排动作，再生成。** 对跨角色、跨机甲的跳跃镜头，团队先用 layout/reference image 固定空间位置、方向和动作，参考图是位置导向而非直接镜头输入。
3. **区分“严格控制”和“锚点控制”。** 连续性要求高的镜头依靠角色/布局约束；救援镜头只规定危险感、体量、人物姿态等关键锚点，保留模型对镜头运动和角度的探索空间。
4. **以多次生成换取可剪辑性。** 项目同时公开失败尝试与最终镜头；先保证同一地点和物体位置连续，再从变化的机位中挑选并剪辑。
5. **按叙事序列设计而非逐镜头堆料。** 把同一场景的三种复杂镜头分散到剧情中，用一次“高光场景”支撑递进的张力。

这些方法可以转写为我们自己的 workflow：`剧情/动作分镜 → 身份与空间参考包 → 先做连续性验证 → 受控变体 → 选片与剪辑`。它们适合学习，但 Zephyr 的具体提示词、人物设定和图像不能直接作为 LinglongLab 或其他外部生成器的输入。

## 100 个公开项目：可以做什么，不能做什么

| 目标 | 结论 | 依据/做法 |
|---|---|---|
| 人工逐个浏览约 100 个项目并写“方法论卡片” | 可以，建议按公开页面正常浏览、限量人工记录 | OWL-NC-1.0 允许 access/view/download/inspect/analyse/study，并允许学习、教学和研究用途。每一项先核对其页面的具体许可。|
| 自动枚举、爬取 100 项、批量抓 prompt/素材 | 不应做 | Higgsfield Terms §5.2(vi) 明确禁止 spider、robot、crawler、avatar、data-mining 等抓取或下载网页数据；没有书面授权或官方支持的访问方式前，不启动。|
| 将 100 项的原始 prompts/assets 整理为内部 dataset/prompt pack | 不应做 | OWL-NC-1.0 禁止将 Materials 作为 standalone/repackaged asset pack、prompt pack、dataset、model、preset 或 library 发布/提供。|
| 用素材或 prompt 去训练、微调或“蒸馏”外部模型 | 不应做 | Terms §5.2(iv) 禁止把 Service、Outputs 或衍生数据用于训练/微调/知识迁移到 AI 系统；OWL-NC-1.0 也要求含 Materials 的生成在 Higgsfield 平台内进行。|
| 写去标识化的创作洞察，如“先布局后镜头”“锚点约束” | 可以，谨慎记录 | 这是对方法的独立总结；尽量不存原始 prompt、大量素材或可复用的角色/风格包，且保留项目链接、作者和许可证。|

## 推荐的合规执行单元

建议把 100 项拆成每批 10–20 项的人工研究，不做批量采集：

1. 只从 Community/推荐列表中人工打开项目页，并记录 URL、作者、日期、项目页可见的许可证和是否有 brief。
2. 每项只写 1 张方法论卡：叙事目标、输入策略、连续性策略、镜头/剪辑策略、失败模式、可迁移原则；不复制完整 prompt 或保存素材。
3. 明确区分“页面证明的事实”和“我们的推断”。无明确 `OWL-NC-1.0` 或等效许可的项目，只做观看与高层笔记，不下载/复用。
4. 最终交付为聚合的原创研究报告，而非项目清单、素材包或 prompt 库；在报告中链接回来源并归属作者。
5. 如确实需要程序化样本或可复现的元数据导出，先向 Higgsfield 取得书面许可，或使用其官方为账户开放、且明确允许该用途的 API/MCP/CLI，并遵守账户的限额。

## 第一方来源

- [ZEPHYR: Special — Higgsfield Community](https://higgsfield.ai/@higgsfield.studio/projects/zephyr-special)：公开成片、brief、素材卡、下载/项目入口、许可证标识及逐素材展示的实际界面。
- [Open Works License 1.0 — Non-Commercial Universe (OWL-NC-1.0)](https://higgsfield.ai/licences/owl-nc-1.0)：§2.1–2.2（研究/学习/检查许可）、§2.7 与 §3.2（限 Higgsfield 平台生成）、§3.8（禁止 prompt pack/dataset 等再打包）。
- [Higgsfield Terms of Use](https://higgsfield.ai/terms-of-use-agreement)：§1.5（官方程序化访问仍受限额约束）、§5.2(iv)（禁止用数据训练/蒸馏 AI）、§5.2(vi)（禁止爬虫/抓取）。

> 本文是产品与许可的操作性解读，不构成法律意见；许可证和项目页内容可能变化，开始每批研究前应复核当时页面与条款。
