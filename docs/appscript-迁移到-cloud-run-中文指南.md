# Apps Script 迁移到 Cloud Run 操作手册

本文是一份供同事、开发者及 AI 协作使用的 Apps Script 迁移操作手册。

本手册建议将现有 Google Apps Script 应用逐步迁移为：

- 前端：TypeScript + React + Tailwind CSS
- 后端：Python + FastAPI
- 部署：Google Cloud Run
- Google 服务：通过 Google 官方 API 调用

建议按照章节顺序推进，并优先完成“盘点”“权限”和“验收”三个部分。迁移过程中，建议先确保原有业务功能、数据和权限保持正确，再逐步优化页面体验。

---

## 1. 先理解最终会变成什么

迁移后的结构如下：

```text
用户浏览器
    │
    ▼
React + TypeScript + Tailwind CSS 前端
    │  HTTP/JSON
    ▼
FastAPI 后端
    │
    ├── Google Sheets API
    ├── Google Drive API
    ├── Gmail / Calendar / BigQuery API
    └── 外部 API
    │
    ▼
Cloud Run
```

Apps Script 中的 `doGet()`、`doPost()`、HTML 页面、Google 服务调用和定时触发器，需要按 Cloud Run 的运行方式分别改造，通常包括：

1. 页面：从 Apps Script HTML 改成 React 页面。
2. 样式：从原来的 HTML/CSS 改成 Tailwind CSS。
3. 接口：从 `doGet()` / `doPost()` 改成 FastAPI 路由。
4. Google 服务：从 `SpreadsheetApp`、`DriveApp` 等改成 Google API Client Library。
5. 配置：从 `PropertiesService` 改成环境变量和 Secret Manager。
6. 定时任务：从 Apps Script Trigger 改成 Cloud Scheduler、Pub/Sub 或 Cloud Run Job。

Cloud Run 会运行应用服务容器。它可以从源代码自动构建，也可以使用 Dockerfile；团队成员无需预先成为 Docker 专家即可开展迁移。[Cloud Run 官方说明](https://cloud.google.com/run/docs/overview/what-is-cloud-run)

---

## 2. 迁移前：建议先备份并稳定旧应用

### 2.1 建议先完成备份

建议由项目负责人或指定同事协助完成以下准备：

- 复制 Apps Script 项目，命名为“项目名-迁移备份-日期”。
- 记录当前 Apps Script 部署版本号。
- 记录旧应用网址。
- 记录所有触发器。
- 记录所有外部库及版本。
- 导出或抄下 Script Properties 的键名和值。
- 记录应用使用的 Spreadsheet、Drive 文件夹、Gmail、Calendar、BigQuery 等资源。
- 保存 5～10 个真实但不敏感的输入和正确输出。

迁移期间，建议尽量只对旧应用进行紧急修复，避免同时进行大范围功能调整，以便后续出现差异时能够更快定位原因。

### 2.2 请勿将以下内容发给 AI 或提交到代码仓库

- API Key
- OAuth Client Secret
- 服务账号 JSON 私钥
- 用户密码
- 数据库密码
- Webhook Secret
- 真实客户隐私数据

可以将配置名、字段名和脱敏样例提供给 AI；真实密钥请仅保存在 Secret Manager 或公司批准的密码管理系统中。

---

## 3. 第一步：建立迁移清单

建议复制并填写以下表格。对于暂未确认的项目，请标记为“待确认”，后续与业务或项目管理员核实后再补充。

### 3.1 应用信息

| 项目 | 内容 |
|---|---|
| 应用名称 |  |
| 业务负责人 |  |
| 技术负责人 |  |
| Apps Script 项目链接 |  |
| 旧应用网址 |  |
| 用户范围 | 公司内部 / 外部用户 / 两者 |
| 是否需要登录 | 是 / 否 |
| 测试项目 ID |  |
| 生产项目 ID |  |
| Cloud Run 区域 | 由管理员确认 |

### 3.2 功能清单

建议逐项记录“用户做什么、系统应产生什么结果”：

| 编号 | 用户操作 | 旧脚本函数 | 输入 | 输出 | 是否写数据 |
|---|---|---|---|---|---|
| F001 | 例如：查询客户 | `searchCustomer()` | 客户名 | 客户列表 | 否 |
| F002 | 例如：提交表单 | `submitForm()` | 表单字段 | 成功提示 | 是 |

建议在 Apps Script 中检索并登记以下内容：

```text
doGet
doPost
onOpen
onEdit
onFormSubmit
ScriptApp.newTrigger
SpreadsheetApp
DriveApp
GmailApp
CalendarApp
UrlFetchApp
PropertiesService
CacheService
Session.getActiveUser
Session.getEffectiveUser
Utilities.sleep
```

### 3.3 Google 资源清单

| 资源 | ID 或名称 | 读/写 | 原来由谁访问 | 迁移后由谁访问 |
|---|---|---|---|---|
| Spreadsheet |  | 读/写 | 当前用户/脚本账号 | 服务账号/用户授权 |
| Drive 文件夹 |  | 读/写 |  |  |
| BigQuery 数据集 |  | 读/写 |  |  |

请特别留意：旧 Apps Script 能访问某个表格，并不代表 Cloud Run 会自动获得访问权限。请为 Cloud Run 使用的服务账号单独授予相应资源权限。

---

## 4. 第二步：先确定身份和权限方案

在开始编写代码前，建议先明确以下问题：

> 这个操作是代表当前登录用户执行，还是代表应用自己的服务账号执行？

### 4.1 内部工具，所有人访问同一批业务数据

推荐：

- Cloud Run 服务保持私有。
- 通过公司 Google 账号登录。
- 后端验证用户身份。
- Google Sheets、Drive 等后端资源由服务账号访问。
- 后端自己检查当前用户是否有业务权限。

这是大多数内部工具的推荐起点。

### 4.2 每个用户访问自己的 Google 数据

需要做 Google OAuth/OIDC：

- 用户登录 Google。
- 用户同意授权范围。
- 后端验证登录凭证。
- 后端使用用户授权的 Token 访问用户资源。

请勿将个人账号 Token 写入环境变量，也不建议让前端直接保存长期 Token。

### 4.3 定时任务或后台同步

推荐：

- Cloud Scheduler 调用 Cloud Run。
- Cloud Run 服务只接受带身份令牌的调用。
- 定时任务使用服务账号访问 Google API。
- 每次任务生成唯一任务 ID，避免重试造成重复写入。

Cloud Run 的服务间认证方式见[官方文档](https://cloud.google.com/run/docs/authenticating/service-to-service)。

### 4.4 权限最小化原则

建议仅向服务账号授予完成工作所需的最小权限：

- 只读功能宜仅授予读取权限。
- 建议仅访问指定 Sheet，不默认扩大到整个组织。
- 建议仅访问指定 Drive 文件夹。
- 请避免仅为方便而授予服务账号项目 Owner 权限。
- 请勿将服务账号私钥下载到个人电脑或提交到 Git。

---

## 5. 第三步：建立项目骨架

推荐使用前后端分离的目录：

```text
app/
├── frontend/                 # React + TypeScript + Tailwind CSS
│   ├── src/
│   │   ├── api/              # 调用 FastAPI 的函数
│   │   ├── components/       # 可复用组件
│   │   ├── pages/            # 页面
│   │   ├── types/            # TypeScript 类型
│   │   └── App.tsx
│   ├── package.json
│   └── .env.example
├── backend/                  # FastAPI
│   ├── app/
│   │   ├── main.py           # FastAPI 入口
│   │   ├── api/              # 路由
│   │   ├── schemas/          # 请求和响应模型
│   │   ├── services/         # 业务逻辑和 Google API 调用
│   │   ├── core/             # 配置、认证、日志
│   │   └── tests/
│   ├── requirements.txt
│   └── .env.example
├── Dockerfile
├── .gitignore
└── README.md
```

### 5.1 推荐的后端分层

建议将路由、业务逻辑和外部服务调用分层处理，而不是将所有代码放在路由函数中：

```text
HTTP 请求
  → FastAPI Router：参数校验、权限校验
  → Service：业务规则
  → Google Client：调用 Sheets/Drive/API
  → 统一返回结果和错误
```

### 5.2 推荐的接口格式

接口统一使用 JSON，并统一返回结构：

成功：

```json
{
  "success": true,
  "data": {},
  "request_id": "abc123"
}
```

失败：

```json
{
  "success": false,
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "你没有权限执行此操作"
  },
  "request_id": "abc123"
}
```

建议前端向用户展示清晰友好的错误提示，将详细错误写入后端日志，并避免将堆栈信息直接返回给用户。

---

## 6. 第四步：把 Apps Script 功能逐个改成 FastAPI 接口

建议不要一次性重写整份代码；可按“一个旧函数对应一个新接口”的方式逐项迁移和验证。

### 6.1 Apps Script 入口对应关系

| Apps Script | FastAPI |
|---|---|
| `doGet(e)` | `@app.get()` 或 `@router.get()` |
| `doPost(e)` | `@app.post()` 或 `@router.post()` |
| `e.parameter` | Query 参数或 Path 参数 |
| `e.postData.contents` | Pydantic 请求模型 |
| `HtmlService` | React 页面 |
| `ContentService` | FastAPI JSON 响应 |
| `Session.getActiveUser()` | 登录凭证解析和后端身份认证 |

示例：

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Migrated App")


class SubmitRequest(BaseModel):
    name: str
    email: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/forms")
def submit_form(request: SubmitRequest):
    # 建议在这里调用 service，并将业务逻辑保留在 service 层
    return {"success": True, "data": {"name": request.name}}
```

### 6.2 Google Sheets 对应关系

| Apps Script | FastAPI 后端改造方向 |
|---|---|
| `SpreadsheetApp.openById(id)` | Google Sheets API `spreadsheets.get` |
| `getRange().getValues()` | `spreadsheets.values.get` |
| `setValues()` | `spreadsheets.values.update` |
| `appendRow()` | `spreadsheets.values.append` |
| `getSheetByName()` | 根据工作表名称定位 `range` |
| `getLastRow()` | 读取数据后计算，或使用表格元数据 |

迁移每个 Sheet 功能时，建议确认：

- 表格 ID 来自环境变量，避免写死在业务代码中。
- 工作表名称和列顺序已记录。
- 服务账号已经被共享为正确角色。
- 读写范围足够小，避免每次读取整张大表。
- 写入操作支持重复调用而不产生重复数据。
- 日期、时区、数字和空值的格式与旧系统一致。

### 6.3 Google Drive 对应关系

把 `DriveApp` 改成 Google Drive API，明确传入：

- 文件 ID
- 文件夹 ID
- 文件名
- MIME 类型
- 是否覆盖同名文件

建议不要依赖“脚本绑定的文件”“当前用户的 Drive”或模糊搜索结果；Cloud Run 不具备 Apps Script 的绑定上下文。

### 6.4 `UrlFetchApp` 对应普通 HTTP 调用

后端调用外部 API 时，建议至少设置：

- 连接超时和读取超时；
- 4xx 响应通常不宜盲目重试；
- 429、暂时性 5xx 可以有限重试；
- 重试要有间隔和最大次数；
- 校验响应 JSON 结构；
- 日志中隐藏 API Key 和 Token。

### 6.5 `PropertiesService` 对应配置

| 原来的内容 | 迁移后的存放位置 |
|---|---|
| API Key、密码、Token | Secret Manager |
| Spreadsheet ID、Drive Folder ID | Cloud Run 环境变量 |
| 测试/生产开关 | Cloud Run 环境变量 |
| 业务记录 | Sheet、数据库或 Cloud Storage |
| 临时缓存 | 可丢失的缓存，不宜存放唯一业务数据 |

Secret Manager 的创建方式见[官方文档](https://cloud.google.com/secret-manager/docs/create-secret-quickstart)。真实 Secret 请勿写入 `.env.example`、Dockerfile、前端代码或 Git。

---

## 7. 第五步：把 Apps Script 页面改成 React + Tailwind CSS

### 7.1 建议先还原功能，再优化视觉

建议按以下顺序迁移页面：

1. 列出旧页面的所有输入、按钮、列表、提示和跳转。
2. 用 React 搭出同样的操作流程。
3. 接通 FastAPI 接口。
4. 验证结果和旧应用一致。
5. 最后使用 Tailwind CSS 优化布局、间距、颜色和响应式。

在业务逻辑尚未验证前，建议避免同时大幅调整页面、接口和数据结构，以降低排查难度。

### 7.2 前端实现建议

- 所有接口调用集中放在 `src/api/`。
- 请求和响应使用 TypeScript 类型。
- 表单提交时禁用按钮，防止重复提交。
- 请求中显示加载状态。
- 失败时显示用户看得懂的错误。
- 请勿将 Secret、服务账号信息或内部 API Key 放到前端。
- 前端可负责展示和收集输入；权限判断请在后端再次执行。
- 除非已经完成隐私和安全评估，否则不建议将业务数据长期保存在浏览器本地存储中。

### 7.3 React 页面验收

建议每个页面至少检查：

- 空数据状态；
- 加载状态；
- 成功状态；
- 失败状态；
- 无权限状态；
- 网络中断状态；
- 长文本和窄屏显示；
- 键盘操作和基本可访问性。

---

## 8. 第六步：本地运行和接口验收

### 8.1 后端本地运行

开发者在 `backend/` 目录执行：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Windows 需要使用对应的虚拟环境激活命令。后端启动后检查：

```text
http://localhost:8000/health
http://localhost:8000/docs
```

### 8.2 前端本地运行

开发者在 `frontend/` 目录执行：

```bash
npm install
npm run dev
```

前端需要配置后端地址，例如：

```text
VITE_API_BASE_URL=http://localhost:8000
```

建议通过部署配置注入生产环境地址，避免将测试地址写死在代码中。

### 8.3 本地验收顺序

1. 先访问 `/health`。
2. 打开 FastAPI `/docs`，逐个调用接口。
3. 用脱敏测试数据验证只读接口。
4. 验证写入接口，确认没有重复写入。
5. 打开 React 页面，完成完整业务流程。
6. 模拟接口失败，确认页面有明确提示。
7. 运行测试和构建命令。

建议 `README.md` 写清楚以下命令：

```bash
# 后端测试
pytest

# 前端检查和构建
npm run lint
npm run build
```

---

## 9. 第七步：准备 Cloud Run 部署

### 9.1 先准备 Google Cloud 项目

建议由项目管理员协助确认：

- Google Cloud 项目 ID；
- 测试和生产项目是否分开；
- Cloud Run 区域；
- Cloud Run、Cloud Build、Artifact Registry API 是否启用；
- 服务账号名称；
- 服务账号需要访问哪些 Google 资源；
- 哪些用户或群组可以访问 Cloud Run。

请勿自行猜测项目 ID、区域、模型名或 API 地址。若遇到 400、403、404，建议先记录完整错误信息，再请项目管理员确认配置。

### 9.2 推荐部署方式

第一次迁移可以使用 Cloud Run 源代码部署：

```bash
gcloud run deploy APP_NAME-staging --source .
```

如果前端和后端分开部署，通常是两个 Cloud Run 服务：

```text
APP_NAME-frontend-staging
APP_NAME-backend-staging
```

如果使用一个容器，也可以由 FastAPI 提供构建后的 React 静态文件；建议先与团队确认采用单服务还是前后端分离。请避免让 AI 在未确认的情况下自行改变部署拓扑。

Cloud Run 的源代码部署会自动构建并部署服务；具体支持的语言、权限和限制以[官方文档](https://cloud.google.com/run/docs/deploying-source-code)为准。

### 9.3 FastAPI 容器建议满足的条件

- 监听 Cloud Run 提供的 `PORT` 环境变量。
- 监听 `0.0.0.0`，而不是仅监听 `127.0.0.1`。
- 启动命令可以在干净环境中运行。
- 依赖全部写入 `requirements.txt`。
- 不依赖本地永久文件。
- `/health` 在服务启动后返回 200。
- 日志输出到标准输出，不依赖本地日志文件。

典型启动命令：

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### 9.4 前端部署要求

React 生产构建应生成静态文件。需要明确：

- 前端生产构建命令；
- API 的生产地址；
- 是否需要自定义域名；
- 是否需要配置 CORS；
- 刷新 React 路由时服务器是否能返回入口页面。

请勿在前端 `.env` 中放置任何 Secret。`VITE_`、`NEXT_PUBLIC_` 等会暴露给浏览器的变量均不应视为秘密。

---

## 10. 第八步：配置环境变量、Secret 和 Google 资源权限

### 10.1 普通环境变量

可以配置：

```text
APP_ENV=staging
GOOGLE_CLOUD_PROJECT=项目ID
TARGET_SPREADSHEET_ID=表格ID
TARGET_DRIVE_FOLDER_ID=文件夹ID
ALLOWED_ORIGINS=https://前端地址
EXTERNAL_API_BASE_URL=https://外部服务地址
```

### 10.2 Secret

放入 Secret Manager：

- 外部 API Key；
- OAuth Client Secret；
- Webhook Secret；
- 数据库密码；
- 第三方 Token。

建议 Cloud Run 服务仅读取自身需要的 Secret。请勿让 AI 生成或修改真实 Secret 值。

### 10.3 共享 Google 资源

如果后端通过服务账号访问 Sheet 或 Drive，建议按以下步骤配置：

1. 找到 Cloud Run 实际使用的服务账号邮箱。
2. 把目标 Sheet 或 Drive 文件夹共享给该服务账号。
3. 赋予最小必要权限。
4. 用 Cloud Run 身份做一次读操作测试。
5. 再做一次写操作测试。

“我本人能打开表格”不能证明“Cloud Run 能打开表格”。

---

## 11. 第九步：测试环境部署和验收

### 11.1 先部署 staging

服务名建议使用：

```text
项目名-frontend-staging
项目名-backend-staging
```

建议不要将生产服务作为首次试验的目标。

### 11.2 功能验收

建议为每一项旧功能保留一条新系统验收记录：

| 功能 | 旧系统结果 | 新系统结果 | 通过/失败 | 备注 |
|---|---|---|---|---|
| 查询 |  |  |  |  |
| 新增 |  |  |  |  |
| 修改 |  |  |  |  |
| 删除/撤销 |  |  |  |  |
| 导出 |  |  |  |  |
| 定时同步 |  |  |  |  |

### 11.3 建议覆盖的异常场景

- 空输入；
- 错误格式；
- 无权限用户；
- 重复点击；
- 两人同时提交；
- Google API 返回 403；
- 外部 API 超时；
- 外部 API 返回 429；
- 后端重启；
- 网络中断；
- 大量数据；
- 中文、表情和特殊字符。

### 11.4 建议的验收标准

上线前建议确认以下事项均已满足：

- 所有 P0/P1 功能通过；
- 生产配置和测试配置没有混用；
- 没有硬编码 Secret；
- 没有已知的数据重复写入问题；
- 没有未解释的 401/403；
- 负责人知道查看日志和回滚方法；
- 旧触发器不会与新触发器重复执行。

---

## 12. 第十步：定时任务和长任务迁移

### 12.1 Apps Script 时间触发器

建议不要将 `ScriptApp.newTrigger()` 直接迁移到 FastAPI，可改为：

```text
Cloud Scheduler → 带身份认证的 Cloud Run API → 执行任务
```

后端接口示例：

```text
POST /internal/jobs/daily-sync
```

建议该接口具备以下能力：

- 建议仅允许 Scheduler 或指定服务账号调用；
- 校验请求身份；
- 记录任务开始、结束和结果；
- 有唯一任务 ID；
- 支持安全重试；
- 不把详细错误直接暴露给公网。

### 12.2 长时间任务

如果任务执行时间较长，建议不要让浏览器持续等待，可采用以下异步模式：

```text
用户提交 → 后端创建任务 → 立即返回任务 ID
                     ↓
                 后台处理
                     ↓
用户查询任务状态和结果
```

可根据任务量选择 Cloud Tasks、Pub/Sub 或 Cloud Run Job。请确保任务状态能够持久化保存，而不只是放在 Python 内存中。

### 12.3 幂等要求

以下操作建议具备防重复执行的能力：

- 发邮件；
- 写入 Sheet；
- 创建 Drive 文件；
- 扣费或调用有副作用的外部接口；
- 生成报告并发送通知。

建议为每次业务操作生成唯一 ID；对于重复请求，可返回已生成的结果，避免再次执行。

---

## 13. 第十一步：正式上线和切换

建议按以下顺序进行上线切换：

1. staging 全部验收通过。
2. 复制配置到生产，但重新检查每一个项目 ID、Sheet ID、Drive ID 和 Secret。
3. 部署生产 Cloud Run 服务。
4. 先由负责人完成一轮低风险真实操作。
5. 确认日志、权限和数据结果正常。
6. 更新内部文档、书签、菜单或入口链接。
7. 小范围用户试用。
8. 观察一段时间后再扩大用户范围。
9. 暂时保留旧 Apps Script 作为回退方案。
10. 确认新系统稳定后，再停用旧触发器和旧入口。

建议不要在新服务首次部署成功后立即删除旧 Apps Script。部署成功只表示容器能够启动，并不等同于业务迁移已经完成。

---

## 14. 回滚方法

### 14.1 新 Cloud Run 版本有问题

Cloud Run 每次部署都会产生一个 revision。出现问题时：

1. 打开 Cloud Run 服务的版本列表。
2. 找到上一个已验证正常的 revision。
3. 将流量切回该 revision。
4. 保留异常版本和日志，建议不要立即删除。
5. 记录错误时间、用户操作和 `request_id`。
6. 修复后重新部署 staging，再重新验收。

### 14.2 新应用业务结果错误

如果页面能打开，但写入结果错误：

- 请尽快暂停新入口的写操作；
- 请暂停新的定时任务；
- 必要时可恢复旧 Apps Script 入口；
- 建议不要直接删除新数据；
- 请先导出异常记录，确认受影响的数据范围；
- 建议由业务负责人确认数据修复方式。

### 14.3 回滚前建议保留的信息

- 旧 Apps Script 部署版本；
- 旧应用网址；
- 旧触发器状态；
- 新 Cloud Run revision；
- 失败请求的 `request_id`；
- 受影响的数据范围；
- 负责人和通知记录。

---

## 15. 常见问题

### 页面打开显示 403

Cloud Run 服务可能设置为私有，当前用户尚未获得调用权限。确认访问范围后，可请管理员配置 Cloud Run Invoker 或公司身份认证。为保障安全，建议不要仅为方便而长期开放生产服务。

### FastAPI 启动失败

建议优先检查：

- 启动命令是否正确；
- 是否监听 `0.0.0.0`；
- 是否使用了 `$PORT`；
- `requirements.txt` 是否完整；
- 导入路径是否正确；
- 启动时是否读取了不存在的环境变量。

### 调用 Sheet 或 Drive 返回 403

请确认 Cloud Run 的服务账号是否已被共享到对应资源，并核实 API 权限和读写角色。建议不要只检查个人 Google 账号的访问权限。

### 调用 Google API 返回 401

请检查认证方式、Token 是否过期、服务账号是否正确，以及后端是否已将凭证正确传给 Google API。建议不要将个人 Token 长期复制到服务器中使用。

### 迁移后数据重复

这通常由重复点击、Scheduler 重试、旧触发器未停用或缺少幂等设计造成。建议检查任务 ID、请求 ID、旧触发器和写入逻辑。

### Cloud Run 重启后数据丢失

本地文件和内存并非永久存储。建议将重要数据写入 Sheet、数据库、Cloud Storage 或其他持久化服务。

### 页面请求后端被 CORS 拒绝

请确认 FastAPI 的 `ALLOWED_ORIGINS` 配置包含正确的前端生产地址，并且未将任意来源开放到生产环境。

### 费用异常

建议检查异常循环、无限重试、过高的最小实例数、过多日志、大文件处理和外部 API 调用；同时可设置预算提醒，并定期查看 Cloud Run、Cloud Build、Artifact Registry 及相关 API 费用。

---

## 16. 给 AI 的迁移执行协议

如需请 AI 协助迁移，可将本手册与 Apps Script 源代码一并提供，并请 AI 参考以下协作方式开展工作。

### 16.1 建议 AI 遵循的协作规则

1. 请先阅读并完成盘点，再开始编写迁移代码。
2. 请先输出功能清单、接口清单、Google 资源清单和权限清单。
3. 如遇业务规则、项目 ID、区域、模型名、API 地址或权限不明确，请先提出问题并等待确认，避免猜测。
4. 请勿读取、输出或提交真实 Secret。
5. 每迁移一个功能，建议先实现后端接口，再实现前端页面。
6. 每一步请运行测试；如无法运行，请说明明确原因。
7. 请保留旧 Apps Script 代码，避免删除。
8. 未经用户明确确认，请勿修改生产配置。
9. 每次修改后，请说明修改文件、验证方式和剩余风险。
10. 建议在所有验收项通过后，再安排上线。

### 16.2 推荐直接复制给 AI 的提示词

```text
你现在负责把这个 Apps Script 应用迁移到 Cloud Run。

固定技术栈：
- 前端：TypeScript + React + Tailwind CSS
- 后端：Python + FastAPI
- 部署：Google Cloud Run
- Google 服务：使用官方 API 和服务账号/用户授权，请避免猜测权限

请按以下流程协助迁移：
1. 请先盘点 Apps Script 的所有入口、功能、触发器、外部库、PropertiesService、Google 资源和用户权限。
2. 请输出迁移清单和所有待确认问题；在此阶段请勿修改代码。
3. 请将每个旧功能映射为一个 FastAPI 接口，并列出请求/响应结构。
4. 请建立 frontend/ 和 backend/ 项目骨架。
5. 请先迁移一个低风险只读功能并完成测试。
6. 然后逐项迁移写入、导出、定时任务和长任务。
7. 前端请使用 React + TypeScript + Tailwind CSS，并将接口调用集中放在 src/api/。
8. 后端请使用 FastAPI、Pydantic 和分层 service，并提供 /health。
9. API Key、Token、密码请仅通过 Secret Manager 管理，避免写入代码、前端或日志。
10. 如遇项目 ID、区域、权限、模型名、API 地址或业务规则不明确，请暂停并提出问题，避免猜测。
11. 每完成一个功能，请报告修改文件、测试命令、测试结果和未解决风险。
12. 请保留旧 Apps Script；未经明确授权，请勿直接操作生产环境。

现在请先完成第 1 步：读取代码并输出盘点结果，暂不编写迁移代码。
```

### 16.3 AI 每轮工作后的报告格式

可请 AI 按以下格式汇报：

```text
本轮完成：
-

修改文件：
-

已验证：
- 命令：
- 结果：

待确认问题：
-

风险：
-

下一步：
-
```

这种分阶段汇报方式有助于控制每次修改的范围，也便于后续定位问题和回退。

---

## 17. 最终交付清单

迁移完成后，建议交付以下内容：

- [ ] 前端源码和启动说明；
- [ ] 后端源码和启动说明；
- [ ] `README.md`；
- [ ] `requirements.txt` 和前端依赖文件；
- [ ] 测试环境 Cloud Run 地址；
- [ ] 生产环境 Cloud Run 地址；
- [ ] API 接口清单；
- [ ] 环境变量名称清单，不包含 Secret 值；
- [ ] Google 资源清单；
- [ ] 服务账号及权限说明；
- [ ] 测试用例和测试结果；
- [ ] 日志查看方法；
- [ ] 回滚方法；
- [ ] 定时任务说明；
- [ ] 旧 Apps Script 停用计划；
- [ ] 业务负责人和技术负责人。

### 上线前建议最后确认

- [ ] 所有 P0/P1 功能通过；
- [ ] 测试和生产配置没有混用；
- [ ] 没有硬编码 Secret；
- [ ] 没有未解释的 401/403；
- [ ] 无权限用户无法绕过前端直接调用接口；
- [ ] 重试不会造成重复写入或重复发信；
- [ ] 旧触发器不会与新任务重复执行；
- [ ] 已验证 Cloud Run revision 回滚；
- [ ] 已安排上线后的观察和负责人。

---

## 18. 一句话执行顺序

建议按以下顺序推进：**先备份旧 Apps Script → 盘点功能和权限 → 建立 React/FastAPI 骨架 → 先迁移只读功能 → 再迁移写入和任务 → staging 验收 → 生产部署 → 小范围切换 → 保留回滚 → 稳定后停用旧应用。**

参考资料：

- [Cloud Run 概览](https://cloud.google.com/run/docs/overview/what-is-cloud-run)
- [从源代码部署 Cloud Run](https://cloud.google.com/run/docs/deploying-source-code)
- [Cloud Run 服务间认证](https://cloud.google.com/run/docs/authenticating/service-to-service)
- [Secret Manager 创建和访问](https://cloud.google.com/secret-manager/docs/create-secret-quickstart)
- [Apps Script Web Apps](https://developers.google.com/apps-script/guides/web)
- [Apps Script 服务](https://developers.google.com/apps-script/guides/services)

> Google Cloud 控制台、权限名称、可用区域和 API 参数可能会更新。涉及生产项目 ID、区域、权限、模型名或 API 地址时，建议以项目管理员和当前官方文档为准；如遇 400、403、404，请先核实配置，避免凭猜测修改。
