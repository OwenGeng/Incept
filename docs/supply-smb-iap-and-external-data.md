# Supply SMB: IAP 优先级逻辑 & 外部数据接入架构

> 更新：2026-06-15

---

## 一、背景：为什么要给 IAP 单独一套优先级

原有 P1–P4 框架基于 `is_supply_partner`（Moloco DSP 能否通过 open exchange 看到该 app 的广告库存）。纯 IAP app（`has_ads = false`）不投广告，永远不会产生供给信号，导致所有 IAP app 统一落入 P4，但其中很多有百万级下载、已在竞品网络投 UA，是优质的 Moloco UA 潜客。

**两条销售路径的本质差异：**

| 路径 | 目标 App 类型 | 第一步 | 对代理的话术 |
|------|--------------|--------|-------------|
| List 4 / 6（IAA / Hybrid） | 已有广告变现 | 接 Moloco SDK | "接 SDK 提升 eCPM，之后一起做 UA" |
| List 5（IAP） | 纯订阅 / 内购 | 直接投 Moloco UA | "你有用户基础，我们帮你用 UA 提升安装量" |

---

## 二、IAP 优先级框架（List 5）

### 数据来源

| 字段 | 来源表 | 说明 |
|------|--------|------|
| `downloads_latest_month` | `sensortower.download_revenue_v3` | 最近完整月下载量 |
| `competitor_network_count` | `sensortower.network_analysis` | 近 90 天竞品 UA 网络数（排除 Moloco） |
| `t1_downloads_total` | `sensortower.download_revenue_v3` | T1 市场 30 天下载量（US/CA/DE/FR/GB/AU/JP/KR/TW） |

### P 标签定义

```
P1 — UA Ready
  条件：月下载量 ≥ 100K
        AND competitor_network_count > 0（已在竞品投 UA，说明有 UA 预算）
        AND t1_downloads_total > 0（有 T1 市场量，ROI 空间大）
  含义：最优先，已验证 UA 意愿 + 出海规模，直接推 Moloco UA

P2 — T1 Scale
  条件：月下载量 ≥ 50K
        AND t1_downloads_total > 0（T1 有量但未必在投 UA）
  含义：规模可观，有 T1 意图，优先跟进

P3 — Growing
  条件：月下载量 ≥ 20K
  含义：体量尚小或纯国内，持续观察

P4 — Cold
  条件：其余
  含义：暂不优先
```

### SQL 位置

文件：[`sql/list4_5_6_cold_prospects.sql`](../sql/list4_5_6_cold_prospects.sql)

`app_level` CTE 中的 `prospect_label` 和 `priority_score` CASE 语句，以 `WHEN m.monetization_type = 'IAP' THEN ...` 分支触发。

IAA / Hybrid 的 P1–P4 逻辑（基于 `is_supply_partner` + `sdl_media_cost_usd_30d`）**完全不变**，两路并存。

### 前端兼容性

后端 `_priority_code()` 检测标签中是否包含 "P1"/"P2"/"P3"/"P4" 字符串，新标签（`P1 — UA Ready`、`P2 — T1 Scale` 等）自动命中，前端筛选 / 排序 / 汇总逻辑无需修改。

---

## 三、外部数据接入架构（广大大 / SensorTower CSV 比对）

### 设计目标

运营人员定期导出广大大（或其他外部来源）的 app 列表，上传后自动与 Moloco BQ 数据比对，每条 bundle_id 打上诊断标签，输出可直接给领导看的 enriched CSV。

### 数据流

```
1. 用户在 Supply SMB 面板 → "Bundle Compare" tab 上传 CSV
         ↓
2. 浏览器 POST FormData → /api/incept/api/v1/supply-smb/enrich-bundles
   （经由 Next.js catch-all proxy /api/incept/[...path] 转发，携带用户身份头）
         ↓
3. FastAPI 端点接收文件 → 调用 SupplySmbLiveService.enrich_bundles()
         ↓
4. Python 解析 CSV，归一化 iOS bundle_id（"1234567.0" → "1234567"）
         ↓
5. 构造 BQ 诊断查询，JOIN 三张表：
   - fact_supply_with_tracking_publisher  → SDK 信号
   - athena.fact_dsp_core                 → UA 消耗信号
   - athena.dim1_app_v3                   → ST 元数据（变现类型 / 国家）
         ↓
6. 结果 merge 回原始 CSV，追加 7 列 Moloco 标签
         ↓
7. JSON 返回前端，展示表格 + 支持下载 enriched CSV
```

### 诊断标签（moloco_diagnosis）

| 标签 | 条件 | 含义 |
|------|------|------|
| `✅ PROSPECT` | IAA/Hybrid，无 SDK，无 UA | 应该在 no-SDK-no-UA 名单里 |
| `① HAS_SDK` | `fact_supply` 有 `MOLOCO_SDK%` 记录 | 已是 Moloco SDK publisher |
| `② HAS_UA` | `fact_dsp_core` 近 90 天有消耗 | 已是 Moloco advertiser |
| `③ PURE_IAP` | `has_ads=false AND has_iap=true` | 纯内购，List 5 目标 |
| `④ NOT_IN_ST` | `dim1_app_v3` 找不到 | ST 无收录 / bundle_id 有误 |
| `⑤ FREE` | `has_ads=false AND has_iap=false` | 完全免费 app，无变现路径 |

### 追加列清单

原始 CSV 所有列保留，右侧追加：

| 列名 | 说明 |
|------|------|
| `moloco_diagnosis` | 上表标签 |
| `moloco_has_sdk` | true / false |
| `moloco_ua_spend_90d` | 近 90 天 UA 消耗（USD） |
| `st_app_name` | ST app 名（用于核对） |
| `st_company` | ST 公司名 |
| `st_hq_country` | ST HQ 国家 |
| `st_monetization` | IAA / IAP / Hybrid / Free |

### iOS bundle_id 格式处理

广大大导出的 iOS App Store ID 存为浮点数（如 `1612792132.0`），BQ 中为整数字符串（`1612792132`）。后端在构造 BQ 查询前自动归一化：

```python
if bid.endswith(".0") and bid[:-2].isdigit():
    bid = bid[:-2]
```

### 关键文件

| 文件 | 作用 |
|------|------|
| `apps/api/app/routers/supply_smb.py` | `POST /enrich-bundles` 端点 |
| `apps/api/app/services/supply_smb_live.py` | `enrich_bundles()` 方法，BQ 查询逻辑 |
| `apps/web/components/supply-smb/bundle-compare-view.tsx` | 上传 UI + 结果表格 + CSV 下载 |
| `apps/web/app/(supply)/supply-smb/no-sdk-no-ua/bundle-compare/page.tsx` | 页面入口 |
| `apps/web/lib/supply-navigation.ts` | 导航 tab 注册（"Bundle Compare"） |

---

## 四、广大大数据接入的已知问题

**Issue 1：广大大列表以 IAP 为主**

本次比对 244 条 bundle_id 结果：156 条（64%）为 `③ PURE_IAP`。这不是数据缺失问题，是广大大选品偏向工具类 / 效率类 app（多为订阅模式），与我们 no-SDK-no-UA 名单的 IAA 导向天然错配。

→ 未来可将广大大数据直接作为 **List 5 IAP 候选**使用，而不是与 List 4 比对。

**Issue 2：`✅ PROSPECT` 的 62 条未必都出现在面板里**

`dim1_app_v3` 有记录、无 SDK 无 UA，但最终可能被以下过滤条件踢掉：
- 主下载市场为国内（top country = CN/HK/TW）
- 公司名命中 `moloco_known_companies` 排除表（如百度、阿里巴巴旗下产品）

**Issue 3：广大大即将与 SensorTower 数据合并**

两个来源都会有同一 app 的 bundle_id，合并时注意去重（以 bundle_id 为主键）。Bundle Compare 上传功能支持任意来源的 CSV，列名可由用户指定。
