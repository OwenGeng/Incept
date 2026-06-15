# NBSpark — 本地开发指南（macOS）

本项目包含两个服务，本地开发时需要同时运行：

| 服务 | 目录 | 端口 |
|------|------|------|
| nbs-api（后端：InterSight + Incept） | `apps/api` | 8000 |
| nbs-portal（前端：Next.js） | `apps/web` | 3000 |

---

## 一、首次环境配置

### 1. 确认工具已安装

打开终端，逐行运行以下命令，确认每个工具都有输出版本号：

```bash
node --version      # 需要 20+
pnpm --version      # 需要 10+
python3 --version   # 需要 3.12+
gcloud --version    # 需要已安装 Google Cloud SDK
docker --version    # 需要已安装 Docker Desktop（部署时用）
```

如果 `pnpm` 未安装：
```bash
npm install -g pnpm
```

如果 `gcloud` 未安装，前往 [cloud.google.com/sdk](https://cloud.google.com/sdk/docs/install) 下载安装。

如果 `docker` 未安装，前往 [docker.com](https://www.docker.com/products/docker-desktop/) 下载 Mac 版本（仅部署生产环境时需要）。

#### gcloud PATH 配置（换新 Mac 必做）

新 Mac 上 gcloud 安装后，`docker-credential-gcloud` 等工具可能不在 PATH 里，需要手动加：

```bash
# 查找 gcloud 安装位置
gcloud info --format='value(installation.sdk_root)'
# 通常输出 /Users/你的用户名/google-cloud-sdk

# 把 gcloud bin 加到 PATH（永久生效）
echo 'export PATH="$PATH:$HOME/google-cloud-sdk/bin"' >> ~/.zshrc
source ~/.zshrc

# 验证
which docker-credential-gcloud  # 应该有输出路径
```

---

### 2. 配置 GCP 登录（ADC）

InterSight（BigQuery）和 Incept（Vertex AI / Gemini）都通过 Google 账号授权访问，运行：

```bash
gcloud auth application-default login
```

浏览器会弹出 Google 登录页面，用公司账号授权即可。

验证是否成功：
```bash
gcloud auth application-default print-access-token
# 输出一长串 ya29.xxx 表示成功
```

> Token 有效期约 1 小时，过期后重新运行 login 命令即可，无需重启服务。

---

### 3. 安装 Node 依赖

在**项目根目录**运行（安装所有前端 workspace 依赖）：

```bash
pnpm install
```

---

### 4. 配置 Python 虚拟环境（venv）

> **为什么要用 venv？**
> macOS 上可能同时安装了多个 Python 版本（3.9、3.12 等），venv 会为本项目创建一个独立的 Python 环境，避免版本混乱。

```bash
# 进入后端目录
cd apps/api

# 创建虚拟环境（只需运行一次）
python3 -m venv venv

# 激活虚拟环境（每次打开新终端都需要运行）
source venv/bin/activate
```

激活成功后，终端提示符前面会出现 `(venv)` 字样：
```
(venv) owen.geng@ogeng-mba-lr6 api %
```

然后安装 Python 依赖：
```bash
pip install -r requirements.txt
```

> 第一次安装时 `rembg` 会下载约 170 MB 的模型文件，耐心等待即可，后续启动不会重复下载。

---

### 5. 配置环境变量（.env 文件）

#### nbs-api 配置：`apps/api/.env`

如果 `apps/api/.env` 不存在，从模板复制一份：
```bash
cp apps/api/.env.example apps/api/.env
```

打开 `apps/api/.env`，需要填写的关键字段：

```dotenv
# 内部 API 密钥（前后端必须一致，随意填一个字符串即可，如 local-dev-key）
# 方法1：openssl（推荐，任何Mac都有）
# openssl rand -base64 32
INCEPT_INTERNAL_API_KEY=your-internal-key-here

# GCP 项目配置（向 Owen 确认具体值）
GCP_PROJECT_DEPLOY=ads-bpd-guard-sandbox
GCP_PROJECT_DATA=ads-bpd-guard-china
BQ_WRITE_PROJECT=ads-bpd-guard-sandbox
BQ_READ_PROJECT=ads-bpd-guard-china

# 数据模式：mock = 静态假数据，live = 真实 BigQuery 数据
INTERSIGHT_API_MODE=mock
```

#### nbs-portal 配置：`apps/web/.env.local`

如果 `apps/web/.env.local` 不存在，从模板复制：
```bash
cp apps/web/.env.example apps/web/.env.local
```

打开 `apps/web/.env.local`，需要填写：

```dotenv
# 必须与 apps/api/.env 中的 INCEPT_INTERNAL_API_KEY 完全一致
INCEPT_INTERNAL_API_KEY=your-internal-key-here

# 本地跳过 Google 登录（开发时方便，生产环境不可用）
AUTH_DEV_SKIP_SIGN_IN=true

# Google OAuth（如需真实登录，向 Owen 获取）
GOOGLE_CLIENT_ID=replace-with-google-oauth-client-id
GOOGLE_CLIENT_SECRET=replace-with-google-oauth-client-secret
# 生成方法：方法1：NextAuth 官方推荐
# npx auth secret
NEXTAUTH_SECRET=any-random-string-for-local-dev

NEXTAUTH_URL=http://localhost:3000
API_BASE_URL=http://localhost:8000
```

> **关键规则**：`INCEPT_INTERNAL_API_KEY` 在前后端两个文件中必须完全一致，否则 API 请求会被拒绝（401 错误）。

---

## 二、日常启动服务

每次开发都需要开两个终端窗口：

### 终端 1 — 启动后端（nbs-api）

```bash
cd apps/api

# 激活虚拟环境（每次打开新终端都要运行）
source venv/bin/activate

# 启动服务
uvicorn app.main:app --reload --port 8000
```

看到以下输出表示启动成功：
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 终端 2 — 启动前端（nbs-portal）

```bash
cd apps/web
pnpm dev
```

看到以下输出表示启动成功：
```
▲ Next.js 15.x.x
- Local:  http://localhost:3000
✓ Ready in x.xs
```

---

## 三、验证服务是否正常

两个服务都启动后，打开浏览器访问：

| 页面 | 地址 |
|------|------|
| 主页 | http://localhost:3000 |
| InterSight 分析 | http://localhost:3000/supply-smb/no-sdk-no-ua/weekly-brief |
| Incept 工作台 | http://localhost:3000/incept |
| API 接口文档 | http://localhost:8000/docs |

后端健康检查（终端运行）：
```bash
curl http://localhost:8000/health
# 返回 {"status":"ok",...} 表示正常
```

---

## 四、InterSight 数据模式切换

修改 `apps/api/.env` 中的 `INTERSIGHT_API_MODE`，然后重启后端：

| 值 | 说明 | 适用场景 |
|----|------|----------|
| `mock` | 返回静态假数据，不查 BigQuery | 开发 UI、快速调试 |
| `live` | 查询真实 BigQuery 数据 | 功能验证、数据验证 |

> 切换到 `live` 模式前，确保已完成第 2 步的 GCP 登录。

---

## 五、常见问题（本地开发）

### uvicorn: command not found

虚拟环境没有激活，运行：
```bash
source apps/api/venv/bin/activate
```

### API 返回 401 / 请求被拒绝

`INCEPT_INTERNAL_API_KEY` 前后端不一致，检查两个文件的值是否完全相同：
- `apps/api/.env`
- `apps/web/.env.local`

### InterSight 无数据 / BigQuery 报错

GCP 登录过期，重新运行：
```bash
gcloud auth application-default login
```
然后重启后端。

### Incept 图片生成失败（Vertex AI 报错）

按顺序检查：
1. 重新登录 GCP：`gcloud auth application-default login`
2. 检查 `apps/api/.env` 中的 `GCP_PROJECT_DEPLOY` 是否正确
3. 在 GCP Console 确认已开启 `aiplatform.googleapis.com`

### nbs-api 启动后立刻崩溃（SQLite 报错）

删除损坏的数据库文件，重启后会自动重建：
```bash
rm -f apps/api/data/incept.db
```

### `pnpm dev` 报错 `Cannot find module '@incept/shared'`

回到项目根目录重新安装依赖：
```bash
pnpm install
```

### 不想每次都登录 Google，想直接跳过

在 `apps/web/.env.local` 中设置：
```dotenv
AUTH_DEV_SKIP_SIGN_IN=true
```
重启前端即可。**仅限本地开发，生产环境严禁使用。**

---

## 六、部署到生产环境（Cloud Run）

> 本地开发不需要这一节。只有需要把改动发布到线上时才用。

### 部署前提

1. **Docker Desktop** 已安装并运行（左下角绿色"Engine running"）
2. **gcloud PATH** 已配置（见第一节）
3. **gcloud 已登录**：`gcloud auth list` 看到 `owen.geng@moloco.com` 带 `*`
4. **`.env.deploy` 文件存在**（见下方）

### `.env.deploy` 文件

这个文件包含部署密钥，**不提交 git**，换电脑后需要重新创建。在项目根目录创建 `.env.deploy`：

```dotenv
DEPLOY_SA_EMAIL=incept@ads-bpd-guard-sandbox.iam.gserviceaccount.com
GCP_PROJECT_DEPLOY=ads-bpd-guard-sandbox
GCP_PROJECT_DATA=ads-bpd-guard-china
BQ_WRITE_PROJECT=ads-bpd-guard-sandbox
BQ_READ_PROJECT=ads-bpd-guard-china

INCEPT_INTERNAL_API_KEY=（问 Owen 获取）
GOOGLE_CLIENT_ID=（问 Owen 获取）
GOOGLE_CLIENT_SECRET=（问 Owen 获取）
AUTH_SECRET=（问 Owen 获取）

NEXTAUTH_URL=https://incept-web-263521371395.asia-northeast1.run.app
```

> 如果丢失了这些值，可以从现有 Cloud Run 服务里读取：
> ```bash
> gcloud run services describe incept-web --region=asia-northeast1 \
>   --project=ads-bpd-guard-sandbox \
>   --format="value(spec.template.spec.containers[0].env)" | tr ';' '\n'
> ```

### 配置 Docker 对 GCP 的认证

**换新 Mac 后只需做一次：**

```bash
# 1. 安装 docker-credential-gcr（如果 which docker-credential-gcloud 没输出）
gcloud components install docker-credential-gcr

# 2. 配置 Docker 使用 gcloud 认证推送镜像
gcloud auth configure-docker asia-northeast1-docker.pkg.dev --quiet
```

### 日常部署命令

```bash
cd ~/Documents/Projects/Incept

# 部署前在当前终端确认 PATH（每次新开终端要运行一次）
export PATH="$PATH:$HOME/google-cloud-sdk/bin"

# 完整部署（前后端都更新）
bash deploy.sh

# 只更新前端
bash deploy.sh web

# 只更新后端
bash deploy.sh api
```

### Docker Hub 在国内无法访问时（TLS 超时）

`deploy.sh` 用本地 Docker 构建镜像，需要从 Docker Hub 拉取基础镜像（`node:20-alpine`、`python:3.12-slim`）。国内直连 Docker Hub 不稳定，会报 `TLS handshake timeout`。

**方案 1：开 VPN 再跑 `deploy.sh`**（最简单）

**方案 2：用 Cloud Build 在 GCP 云端构建**（不需要 VPN，推荐）

```bash
cd ~/Documents/Projects/Incept

# 云端构建 web 镜像（3-5 分钟，在 GCP 日本节点跑，不走本地网络）
gcloud builds submit . \
  --config cloudbuild.web.yaml \
  --project ads-bpd-guard-sandbox

# 部署
gcloud run deploy incept-web \
  --image asia-northeast1-docker.pkg.dev/ads-bpd-guard-sandbox/incept/incept-web:latest \
  --region asia-northeast1 \
  --project ads-bpd-guard-sandbox \
  --quiet
```

> 项目根目录有 `cloudbuild.web.yaml`，已经配置好了。

---

## 七、常见问题（部署相关）

### `docker-credential-gcloud`: executable file not found in $PATH

gcloud 的 Docker 凭证工具没在 PATH 里，两步修复：

```bash
# 方法 1：安装
gcloud components install docker-credential-gcr

# 方法 2：确保 PATH 包含 gcloud bin（每次新终端都要，或写入 ~/.zshrc）
export PATH="$PATH:$HOME/google-cloud-sdk/bin"
```

### 部署报错 `Container manifest type must support amd64/linux`

Mac M 系列芯片默认 build 出 ARM 镜像，Cloud Run 只接受 `linux/amd64`。build 时必须加 `--platform`：

```bash
docker build \
  --platform linux/amd64 \
  -f Dockerfile.web \
  -t asia-northeast1-docker.pkg.dev/ads-bpd-guard-sandbox/incept/incept-web:latest \
  .
```

### Docker build 报 `TLS handshake timeout` / `net/http: TLS handshake timeout`

Docker Hub 在国内直连不稳定。解决方案：
- **开 VPN** 再重新 build
- 或用 **Cloud Build**（见第六节"方案 2"），完全不走本地网络

> 不要配置中国 Docker 镜像源（如 `mirror.baidubce.com`），这些镜像目前大多已无法解析。

### `.env.deploy not found`

换电脑后 `.env.deploy` 不会自动同步（它被 gitignore 了）。参考第六节重新创建，或从现有 Cloud Run 环境变量中读取已有值。

### 登录时报 `Error 400: redirect_uri_mismatch`

Google OAuth 没有注册当前生产 URL 的回调地址。进入 [GCP Console → Credentials](https://console.cloud.google.com/apis/credentials)，在 OAuth Client ID 的 **Authorized redirect URIs** 里添加：
```
https://incept-web-263521371395.asia-northeast1.run.app/api/auth/callback/google
```

同时确认 Cloud Run 上的 `NEXTAUTH_URL` 与访问 URL 一致：
```bash
gcloud run services update incept-web \
  --region=asia-northeast1 \
  --project=ads-bpd-guard-sandbox \
  --update-env-vars="NEXTAUTH_URL=https://incept-web-263521371395.asia-northeast1.run.app"
```

### 线上页面数据全部加载失败（Supply / Settings / AI Insights 显示错误）

查看 Cloud Run 日志确认根因：
```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="incept-api"' \
  --project=ads-bpd-guard-sandbox --limit=20 \
  --format="value(timestamp,textPayload,httpRequest.status,httpRequest.requestUrl)"
```

如果看到 `The request was not authenticated. Empty Authorization header value.`，说明 incept-web 没有成功获取 GCP identity token 来调用 incept-api。这是一个已知问题，已在代码里修复（`lib/api.ts` 改用 Node.js 原生 `http` 模块）——确保最新代码已部署。

## 八、开发工作流

### 新增后端 API 接口

1. 在 `apps/api/app/routers/` 下创建或编辑路由文件
2. 如果是新文件，在 `apps/api/app/main.py` 中注册
3. 开启 `--reload` 后，保存文件会自动热重载

### 新增 Python 依赖

```bash
# 1. 编辑 requirements.txt，添加包名
# 2. 激活 venv 后安装
source apps/api/venv/bin/activate
pip install -r apps/api/requirements.txt
```

### 新增前端页面

```
apps/web/app/
├── incept/          → Incept 工作台 (/incept)
├── supply-smb/      → InterSight 分析 (/supply-smb/...)
└── <new-tool>/      → 新工具入口
    ├── layout.tsx   → 鉴权 + Provider 包裹
    └── page.tsx     → 主组件
```

在 `apps/web/app/page.tsx` 的首页卡片列表中添加新工具入口。
