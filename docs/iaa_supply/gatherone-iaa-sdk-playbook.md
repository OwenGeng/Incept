# GatherOne IAA SDK 使用手册

> 面向 GatherOne 销售和客户拓展团队的简版材料。
>
> 本手册用于帮助销售判断客户、选择沟通路径和提交支持请求；不替代 Moloco 官方技术文档。任何效果数字、案例和技术承诺，以 Moloco Supply Team 审核后的版本为准。

## 1. 先判断客户是否适合

优先关注同时具备以下特征的客户：

- 有一定广告变现收入或广告库存；
- 使用 AppLovin MAX、Unity LevelPlay 或其他 mediation；
- 有海外用户或出海业务；
- 对广告收入增长、填充率、竞价或增量需求有明确诉求；
- 当前尚未接入 Moloco SDK，或有明确的增量接入空间。

如果客户同时有 UA 预算，可以将 SDK 变现和 Moloco UA 作为一个联合机会沟通；如果暂时只有 IAA 需求，先推进 SDK，不必等待 UA 机会成熟。

## 2. 销售沟通的基本边界

可以沟通：

- Moloco SDK 可以作为现有变现体系的增量需求来源；
- 可以根据客户现有 mediation 选择对应接入路径；
- Moloco 侧可以提供接入资料、培训和技术支持；
- 接入后通过实际数据评估广告收入和整体变现效果。

不要未经确认承诺：

- 固定收入、固定提升比例或固定上线时间；
- 客户一定需要更换现有 mediation；
- 任何尚未被 Supply Team 审核的案例数字；
- 具体技术行为、兼容性或排障结论。

## 3. 接入路径快速判断

| 客户当前情况 | 推荐动作 | 资料 |
|---|---|---|
| 使用 AppLovin MAX | 按 MAX 路径了解 Moloco SDK 竞价接入 | [使用 AppLovin MAX 开始 App 内竞价](https://help.publisher.moloco.com/hc/zh-cn/articles/26777419191063-%E4%BD%BF%E7%94%A8-AppLovin-MAX-%E5%BC%80%E5%A7%8B-App-%E5%86%85%E7%AB%9E%E4%BB%B7) |
| 使用 Unity LevelPlay | 按 LevelPlay 路径了解 Moloco SDK 竞价接入 | [使用 Unity LevelPlay 开始 App 内竞价](https://help.publisher.moloco.com/hc/zh-cn/articles/26777434783255-%E4%BD%BF%E7%94%A8-Unity-LevelPlay-%E5%BC%80%E5%A7%8B-App-%E5%86%85%E7%AB%9E%E4%BB%B7) |
| 使用其他 mediation 或尚未确定 | 先确认当前架构，再由技术支持判断路径 | [Moloco Publisher SDK 资源中心](https://help.publisher.moloco.com/hc/zh-cn) |

> 注：LevelPlay 链接的 URL 由项目负责人提供。发布前请由 Supply Team 点击验证，确认页面可访问且链接文字正确。

## 4. 与客户第一次沟通时需要问什么

1. 目前使用哪一种 mediation？
2. 主要平台是 Android、iOS，还是两者都有？
3. 当前是否已经接入其他竞价或广告网络？
4. 目前最关心的是收入增量、填充率、竞价竞争，还是技术接入成本？
5. 是否有近期版本发布或接入排期？
6. 是否同时有海外 UA 投放需求？
7. 谁负责技术接入，谁负责商业化决策？

销售不需要在第一次沟通中解决技术问题。先收集这些信息，再在 co-win list 中提交清晰的支持请求。

## 5. 常见问题的处理方式

### 客户问：是否必须替换现有 mediation？

不要直接承诺。先确认客户使用的 mediation 和当前版本，再参考对应的官方接入路径，由 Supply Team 确认具体兼容方案。

### 客户问：接入后能提升多少收入？

不要承诺固定数字。可以说明需要结合国家、流量结构、广告位、现有竞价网络和实际流量进行评估；具体案例和效果数字由 Moloco 侧提供经过审核的版本。

### 客户问：多久可以接入？

不要给未经确认的固定周期。可以先确认客户技术资源、平台、mediation 和版本，再由 Supply Team 给出评估。

### 客户遇到报错或接入失败

请收集 Bundle、平台、mediation、SDK 版本、报错信息、日志/截图、已尝试步骤和客户截止时间，再通过 Michael 提交给 Supply Team。不要只转发一句“客户接不进去”。

## 6. 支持请求模板

```text
【IAA SDK 支持请求】
公司：
Bundle：
客户联系人/会议时间：
平台：Android / iOS / 两者
当前 mediation：MAX / Unity LevelPlay / 其他 / 未知
当前阶段：评估 / 开发 / 测试 / 上线后
问题描述：
客户期望结果：
报错、截图或日志：
已经尝试的步骤：
期望回复时间：
GatherOne 负责人：
```

## 7. 官方资源

- [Moloco Publisher SDK 资源中心](https://help.publisher.moloco.com/hc/zh-cn)
- [使用 AppLovin MAX 开始 App 内竞价](https://help.publisher.moloco.com/hc/zh-cn/articles/26777419191063-%E4%BD%BF%E7%94%A8-AppLovin-MAX-%E5%BC%80%E5%A7%8B-App-%E5%86%85%E7%AB%9E%E4%BB%B7)
- [使用 Unity LevelPlay 开始 App 内竞价](https://help.publisher.moloco.com/hc/zh-cn/articles/26777434783255-%E4%BD%BF%E7%94%A8-Unity-LevelPlay-%E5%BC%80%E5%A7%8B-App-%E5%86%85%E7%AB%9E%E4%BB%B7)

## 8. 文档维护规则

- Owen 维护结构、版本和销售可读性；
- Supply Team 审核技术结论、案例数字和接入路径；
- Michael 负责收集 GatherOne 实际使用中遇到的问题；
- 新问题解决后，优先补进 FAQ，再在群聊中回复；
- 未经审核的草稿不得作为客户承诺材料转发。
