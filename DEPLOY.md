# Incept 部署文档

> 适用项目：`E:\project\NBSpark`  
> 部署平台：Google Cloud Run（区域：asia-northeast1，东京）  
> 最后更新：2026-06-08

---

## 目录

1. [架构概览](#1-架构概览)
2. [前置条件](#2-前置条件)
3. [配置文件说明](#3-配置文件说明)
4. [首次部署](#4-首次部署)
5. [日常更新部署](#5-日常更新部署)
6. [部署后必做的手动步骤](#6-部署后必做的手动步骤)
7. [常见报错与解决方法](#7-常见报错与解决方法)
8. [需要-admin-协助的事项](#8-需要-admin-协助的事项)
9. [各服务-url-汇总](#9-各服务-url-汇总)

---

## 1. 架构概览

### 是什么？

Incept 由两个独立服务组成，分别跑在 Google Cloud Run 上：

```
用户浏览器
    │
    ▼
┌─────────────────────────────┐
│  incept-web（Next.js）      │  前端 + 登录认证
│  incept-web-xxx.run.app     │  负责页面渲染、用户会话
└────────────┬────────────────┘
             │ 内部 API 调用（带 key）
             ▼
┌─────────────────────────────┐
│  incept-api（FastAPI）      │  后端数据服务
│  incept-api-xxx.run.app     │  负责查询 BigQuery、调用 AI
└────────────┬────────────────┘
             │
     ┌───────┴────────┐
     ▼                ▼
  BigQuery          Vertex AI
 (数据查询)        (AI 功能)
```

### 为什么用 Cloud Run？

- **无服务器**：不用管服务器，没有请求时自动缩容到 0，不产生费用
- **Docker 容器**：本地 build 镜像，推送到 GCP，Cloud Run 直接运行，环境完全一致
- **按量计费**：只为实际使用的计算资源付费

### 关键概念

| 概念 | 解释 |
|------|------|
| **Artifact Registry** | GCP 的私有 Docker 镜像仓库，存放 build 好的镜像 |
| **Service Account（服务账号）** | 服务在 GCP 上的"身份证"，控制它能访问哪些资源 |
| **环境变量** | 密钥、配置等敏感信息通过环境变量注入，不写死在代码里 |
| **Revision（版本）** | 每次部署都会生成一个新版本，Cloud Run 自动切换流量 |

---

## 2. 前置条件

部署前确认以下工具已安装并配置好：

### 本地工具

```bash
# 检查是否安装
gcloud --version      # Google Cloud CLI
docker --version      # Docker Desktop（需要在运行）
git --version
```

- **Docker Desktop**：必须开着，build 镜像需要它
- **gcloud CLI**：已登录公司账号（`gcloud auth list` 确认）
- **Git Bash**（Windows 用户）：用于执行 `.sh` 脚本

### GCP 权限

你的账号（`owen.geng@moloco.com`）需要具备以下权限（已通过 ticket 申请）：

- `roles/artifactregistry.editor` — 推送 Docker 镜像
- `roles/run.developer` — 部署 Cloud Run 服务
- `roles/iam.serviceAccountUser` on `incept` SA — 以服务账号身份部署

---

## 3. 配置文件说明

### `.env.deploy`（**不提交 git，本地保存**）

项目根目录下的 `.env.deploy` 存放所有部署所需的密钥和配置：

```bash
# GCP 配置
GCP_PROJECT_DEPLOY=ads-bpd-guard-sandbox
REGION=asia-northeast1
DEPLOY_SA_EMAIL=incept@ads-bpd-guard-sandbox.iam.gserviceaccount.com

# BigQuery 项目
BQ_WRITE_PROJECT=ads-bpd-guard-sandbox
BQ_READ_PROJECT=ads-bpd-guard-china
GCP_PROJECT_DATA=ads-bpd-guard-china

# 应用密钥
INCEPT_INTERNAL_API_KEY=你的内部API密钥
GOOGLE_CLIENT_ID=你的GoogleOAuth客户端ID
GOOGLE_CLIENT_SECRET=你的GoogleOAuth客户端密钥
AUTH_SECRET=随机生成的session加密密钥

# 部署后自动填入（首次留空即可）
NEXTAUTH_URL=
```

> ⚠️ 这个文件包含密钥，**绝对不能提交到 git**。`.gitignore` 已经排除它了。

### `deploy.sh`

部署脚本，封装了所有 gcloud/docker 命令，支持三种模式：

```bash
bash deploy.sh        # 完整部署：先 API 后 Web
bash deploy.sh api    # 只部署 API
bash deploy.sh web    # 只部署 Web
```

---

## 4. 首次部署

### 步骤 1：确认 Docker Desktop 在运行

打开 Docker Desktop，确认左下角显示绿色"Engine running"。

### 步骤 2：确认 gcloud 已登录

```bash
gcloud auth list
# 应该看到 owen.geng@moloco.com 带 * 号（当前激活账号）
```

如果没登录：
```bash
gcloud auth login
```

### 步骤 3：配置 `.env.deploy`

把 `.env.deploy` 里的所有空项填好（参考上方说明）。

### 步骤 4：运行完整部署

打开 Git Bash，`cd` 到项目根目录，然后：

```bash
bash deploy.sh
```

脚本会依次完成：

1. 检查/创建 Artifact Registry 仓库
2. Build API Docker 镜像（约 3–5 分钟）
3. 推送 API 镜像到 GCP
4. 部署 API 到 Cloud Run
5. Build Web Docker 镜像（约 2–3 分钟）
6. 推送 Web 镜像到 GCP
7. 部署 Web 到 Cloud Run
8. 自动用真实 URL 更新 `NEXTAUTH_URL` 环境变量
9. 自动更新 API 的 CORS 白名单

成功后会打印：

```
╔══════════════════════════════════════════════════════════════════╗
║  🎉 Incept is live!                                              ║
╠══════════════════════════════════════════════════════════════════╣
║  API  https://incept-api-xxx.asia-northeast1.run.app             ║
║  Web  https://incept-web-xxx.asia-northeast1.run.app             ║
╚══════════════════════════════════════════════════════════════════╝
```

### 步骤 5：完成手动收尾（见第 6 节）

---

## 5. 日常更新部署

修改了代码之后，按需重新部署对应服务即可。

### 只改了前端（`apps/web/` 下的文件）

```bash
bash deploy.sh web
```

### 只改了后端（`apps/api/` 下的文件）

```bash
bash deploy.sh api
```

### 前后端都改了

```bash
bash deploy.sh
```

> 💡 **Docker 缓存加速**：如果依赖没变（`package.json` / `requirements.txt` 未改动），大部分 build 层走缓存，几秒内完成。只有代码层会重新编译，整体比首次快很多。

### 更新的原理

每次 `bash deploy.sh web` 背后发生了什么：

```
本地代码改动
    │
    ▼
docker build（生成新镜像）
    │
    ▼
docker push（上传到 Artifact Registry，覆盖 :latest tag）
    │
    ▼
gcloud run deploy（Cloud Run 拉取新镜像，创建新 Revision）
    │
    ▼
流量自动 100% 切换到新 Revision
（旧版本保留，可以回滚）
```

整个过程**零停机**——Cloud Run 确保新版本通过健康检查后才切换流量。

### 如何回滚到上一个版本

如果新版本有问题：

1. 打开 [Cloud Run 控制台](https://console.cloud.google.com/run?project=ads-bpd-guard-sandbox)
2. 点击出问题的服务（`incept-web` 或 `incept-api`）
3. 点击顶部 **Revisions** 标签页
4. 找到上一个正常的版本，点击 **Manage Traffic**
5. 把 100% 流量分配给那个旧版本，保存

---

## 6. 部署后必做的手动步骤

**这两步脚本没有权限自动完成，需要人工操作。首次部署后做一次即可，日常代码更新不需要重复。**

### ① 让 Admin 开放公网访问

默认部署出来的服务只有有 GCP 权限的人才能访问（公司 org policy 限制了 `allUsers` 授权）。需要让有权限的 Admin 运行以下命令：

```bash
# 开放 Web 服务（用户访问入口）
gcloud run services add-iam-policy-binding incept-web \
  --project=ads-bpd-guard-sandbox \
  --region=asia-northeast1 \
  --member="allUsers" \
  --role="roles/run.invoker"

# 开放 API 服务
gcloud run services add-iam-policy-binding incept-api \
  --project=ads-bpd-guard-sandbox \
  --region=asia-northeast1 \
  --member="allUsers" \
  --role="roles/run.invoker"
```

**没做这步的现象**：用浏览器打开 Web URL，返回 `403 Forbidden`。

### ② 添加 Google OAuth 回调地址

用户用 Google 账号登录时，Google 需要知道"验证完成后跳转回哪里"。这个地址必须提前在 GCP 控制台白名单里注册好。

**操作步骤：**

1. 打开 [GCP Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials)
2. 找到 Incept 的 **OAuth 2.0 Client ID**，点击编辑（铅笔图标）
3. 在 **Authorized redirect URIs** 部分，点击 **Add URI**，填入：
   ```
   https://incept-web-263521371395.asia-northeast1.run.app/api/auth/callback/google
   ```
4. 点击 **Save**

**没做这步的现象**：用户点"用 Google 登录"后，出现 `Error 400: redirect_uri_mismatch`，无法登录。

---

## 7. 常见报错与解决方法

### ❌ `Permission 'iam.serviceaccounts.actAs' denied`

**原因**：部署命令没指定 `--service-account`，gcloud 默认用了 Compute Engine 默认服务账号，你没有使用它的权限。

**解决**：确认 `deploy.sh` 里的每个 `gcloud run deploy` 命令都带了：
```bash
--service-account="${DEPLOY_SA_EMAIL}"
```
同时确认 `.env.deploy` 里 `DEPLOY_SA_EMAIL=incept@ads-bpd-guard-sandbox.iam.gserviceaccount.com` 填写正确。

---

### ❌ `--update-env-vars: Bad syntax for dict arg`

**原因**：gcloud 用逗号分隔多个环境变量（`KEY1=val1,KEY2=val2`），如果某个值本身包含逗号或冒号（比如 URL 列表），就会解析出错。

**解决**：在值前加 `^|^` 前缀，告诉 gcloud 改用 `|` 作为分隔符：
```bash
# 错误写法
--update-env-vars="CORS_ALLOW_ORIGINS=https://a.com,http://localhost:3000"

# 正确写法（单引号很重要，防止 bash 解析 |）
--update-env-vars='^|^CORS_ALLOW_ORIGINS=https://a.com,http://localhost:3000'
```

---

### ❌ `--allow-unauthenticated` 部署时报 `PERMISSION_DENIED`

**原因**：公司 GCP org policy 禁止普通开发者直接设置公网访问权限。

**解决**：脚本已改为 `--no-allow-unauthenticated`，公网访问权限单独找 Admin 授权（见第 6 节第①步）。

---

### ❌ Docker build 时报找不到 `sql/` 目录

**原因**：API 的 `Dockerfile.api` 需要同时复制 `apps/api/` 和 `sql/` 两个目录，build context 必须是项目根目录，不能是 `apps/api/` 子目录。

**解决**：`deploy.sh` 已正确配置：
```bash
docker build \
  -f "${SCRIPT_DIR}/Dockerfile.api" \   # Dockerfile 在根目录
  -t "..." \
  "${SCRIPT_DIR}"                        # context = 项目根目录 ✅
```

---

### ❌ 登录页面 Logo 图片不显示

**原因**：Next.js middleware 对未登录用户拦截了 `/logo.png` 的请求，重定向到 `/sign-in`，造成死循环（sign-in 页面本身又需要加载 logo）。

**解决**：`middleware.ts` 的 matcher 已加入 `.*\\.` 规则，所有带文件扩展名的路径（`.png`、`.svg`、`.ico` 等）自动跳过认证拦截：
```ts
"/((?!api|_next/static|_next/image|sign-in|unauthorized|.*\\.).*)"
//                                                              ^^^^
//                                         匹配到扩展名就跳过 middleware
```

---

### ❌ 登录时报 `Error 400: redirect_uri_mismatch`

**原因**：Google OAuth 配置里没有注册当前部署的回调地址。

**解决**：参考第 6 节第②步，在 Google Cloud Console 添加回调 URI。

---

## 8. 需要 Admin 协助的事项

以下操作你没有权限自己执行，需要通过 ticket 找 Admin（Bruce Li 团队）处理：

| 事项 | 影响 | 状态 |
|------|------|------|
| `incept` SA 获得 `bigquery.jobUser` + `bigquery.dataViewer`（china 项目） | API 无法查询 Supply SMB 数据 | ✅ Ticket 已发 |
| `incept` SA 获得 `bigquery.jobUser`（sandbox 项目） | API 无法在 sandbox 跑 BQ 查询 | ✅ Ticket 已发 |
| `incept` SA 获得 `aiplatform.user`（sandbox 项目） | AI Insights 功能无法调用 Gemini | ✅ Ticket 已发 |
| `allUsers` invoker on `incept-web` 和 `incept-api` | 外网用户无法访问（403） | ✅ Ticket 已发 |

---

## 9. 各服务 URL 汇总

| 服务 | URL |
|------|-----|
| **Web 前端**（用户入口） | `https://incept-web-263521371395.asia-northeast1.run.app` |
| **API 后端** | `https://incept-api-263521371395.asia-northeast1.run.app` |
| **GCP Cloud Run 控制台** | https://console.cloud.google.com/run?project=ads-bpd-guard-sandbox |
| **Artifact Registry** | `asia-northeast1-docker.pkg.dev/ads-bpd-guard-sandbox/incept/` |

### 查看线上日志

出问题时，用以下命令看实时日志（在 Git Bash 里）：

```bash
# Web 服务日志（最近 50 条）
gcloud run services logs read incept-web \
  --project=ads-bpd-guard-sandbox \
  --region=asia-northeast1 \
  --limit=50

# API 服务日志（最近 50 条）
gcloud run services logs read incept-api \
  --project=ads-bpd-guard-sandbox \
  --region=asia-northeast1 \
  --limit=50
```

也可以在 [GCP Cloud Run 控制台](https://console.cloud.google.com/run?project=ads-bpd-guard-sandbox) 里点击服务 → **Logs** 标签页，在线查看和搜索日志。
