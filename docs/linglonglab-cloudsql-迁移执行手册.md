# LinglongLab：SQLite 迁移到 Cloud SQL 执行手册

这份手册用于把 LinglongLab 的业务数据从 SQLite 迁移到既有的 Cloud SQL PostgreSQL。请按顺序执行；每一步完成后再进行下一步。迁移期间请保留原 SQLite 文件和 GCS 备份，**不要删除、覆盖或格式化它们**。

## 本次迁移的范围

| 项目 | 已确定的值 |
| --- | --- |
| GCP 项目 | `ads-bpd-guard-sandbox` |
| Cloud SQL 实例 | `linglonglab-tokyo-prod-main-1` |
| 数据库引擎 | PostgreSQL 17 |
| 区域 | `asia-northeast1` |
| 数据库 | `linglonglab` |
| Cloud SQL 连接名 | `ads-bpd-guard-sandbox:asia-northeast1:linglonglab-tokyo-prod-main-1` |
| Cloud Run 运行账号 | `incept@ads-bpd-guard-sandbox.iam.gserviceaccount.com` |
| 现有数据库连接密钥 | `linglonglab-tokyo-prod-main-1-db-connection`（JSON 格式） |

数据库实例已经存在，且备份和时间点恢复（PITR）已开启。迁移不需要新建实例，也不要修改区域、实例名、模型配置或现有数据库密钥的内容。

## 当前已完成的准备

- API 已增加 PostgreSQL 驱动、连接池、健康检查和 SQLite SQL 兼容层。
- API 会通过 Cloud Run 的 Cloud SQL 私有套接字连接数据库；密码不会进入代码或部署命令。
- 已加入一次性导入工具：`apps/api/scripts/migrate_sqlite_to_postgres.py`。
- 导入工具先校验 SQLite 完整性；正式导入只允许目标 LinglongLab 表为空；导入后可逐表核对行数和主键校验和。
- 工作流输出写入已改为数据库唯一约束，避免多实例或重试时产生重复记录。
- 本地 API 测试已通过。尚未创建表、导入数据、切换 Cloud Run 流量或改动云端业务数据。

## 建议管理员完成的配置

以下两项不是 Cloud SQL 导入的技术前提：数据库导入只需要现有的数据库连接 Secret，且该 Secret 已存在。不过它们关系到恢复能力和密钥安全，建议在正式切换前完成。**不要在聊天、文档或终端中发送任何密钥值**。

### 1. 打开 GCS 对象版本控制

在 Google Cloud Console 中：

1. 打开 **Cloud Storage → Buckets → `incept-assets`**。
2. 打开 **Protection（保护）**。
3. 启用 **Object Versioning（对象版本控制）**。
4. 保存后，确认 `incept@ads-bpd-guard-sandbox.iam.gserviceaccount.com` 对该 Bucket 至少具有对象读取、列出和创建权限；删除资产时还需要删除权限。

这一步的意义是：即使误覆盖了迁移快照或素材，也可以恢复旧版本。不开启时，迁移仍可以进行，但上传最终快照时必须使用从未使用过的新文件名，且覆盖后无法恢复旧对象版本。

### 2. 把运行时密钥移到 Secret Manager，并授予读取权限

运行账号已经可以读取现有数据库连接密钥。以下 3 个 Secret 用于将现有的普通 Cloud Run 环境变量移出服务配置；它们不是数据导入的必要条件，但应尽快创建并轮换对应值。管理员创建后，将各 Secret 的 `Secret Manager Secret Accessor` 角色授予 `incept@ads-bpd-guard-sandbox.iam.gserviceaccount.com`：

| Secret 名称 | 存放内容 | 说明 |
| --- | --- | --- |
| `incept-internal-api-key` | 新生成的内部 API Key | 请新生成并替换旧值；旧值曾作为普通环境变量出现，应视为需要轮换。 |
| `incept-google-client-secret` | Google OAuth Client Secret | 从现有受管配置安全迁入。 |
| `incept-auth-secret` | NextAuth/Auth Secret | 从现有受管配置安全迁入；如无法确认来源，请新生成并同步更新登录配置。 |

管理员可在 **Security → Secret Manager → Create Secret** 中创建。迁移执行人需要的只是 Secret 名称和启用的版本号，例如 `1`，不需要也不应看到 Secret 的值。

若管理员希望授予执行人权限，由于需要创建 Secret，应临时授予项目级 `roles/secretmanager.admin`，完成后再回收；仅有读取权限不足以创建 Secret。迁移部署脚本使用非破坏性更新：Secret 尚未创建时，会保留当前服务的普通环境变量；创建后才会改用 Secret Manager 引用。

## 迁移前冻结与快照

请在约定的低峰时段执行，建议预留 30 分钟。最终导入必须使用最新数据，不能使用仓库中的旧 `apps/api/data/incept.db` 作为生产最终来源。

1. 暂停 LinglongLab 的写入操作：请同事不要生成素材、编辑工作流或新建视频制作。API 保持单实例（当前就是 `max-instances=1`）。
2. 在当前承载真实数据的环境中，创建一个新的 SQLite 一致性副本，文件名使用日期时间，例如 `incept-pre-cloudsql-20260820-153000.db`。
3. 用 SQLite 执行完整性检查，并记录各表行数。至少记录 `jobs`、`threads`、`assets`、`video_productions`、`workflows`、`workflow_runs`。
4. 将该副本上传到版本控制已开启的 Bucket 路径，例如：

   ```text
   gs://incept-assets/data/migrations/incept-pre-cloudsql-20260820-153000.db
   ```

   上传人需要该路径的对象创建权限。上传完成后记录完整的 `gs://` 路径；不要覆盖同名文件。

5. 保留原 SQLite 文件及本地/GCS 历史备份。它们是回滚依据。

## 部署支持 PostgreSQL 的 API 版本

在仓库根目录创建或更新未提交的 `.env.deploy`。迁移所必需的是现有数据库连接 Secret：

```dotenv
CLOUD_SQL_INSTANCE_CONNECTION_NAME=ads-bpd-guard-sandbox:asia-northeast1:linglonglab-tokyo-prod-main-1
DATABASE_CONFIG_SECRET=linglonglab-tokyo-prod-main-1-db-connection
DATABASE_CONFIG_SECRET_VERSION=2
```

如三个安全 Secret 已创建，再追加以下可选配置；未创建时不要填写这些字段：

```dotenv
INCEPT_INTERNAL_API_KEY_SECRET=incept-internal-api-key
INCEPT_INTERNAL_API_KEY_SECRET_VERSION=1
GOOGLE_CLIENT_SECRET_SECRET=incept-google-client-secret
GOOGLE_CLIENT_SECRET_SECRET_VERSION=1
AUTH_SECRET_SECRET=incept-auth-secret
AUTH_SECRET_SECRET_VERSION=1
```

`DATABASE_CONFIG_SECRET_VERSION` 必须填写当前启用版本号；上面的 `2` 是当前已确认可用的版本。其他三个版本号以管理员实际创建的启用版本为准。

代码已经让 `deploy.sh api` 自动完成两件关键事：把 API 附加到正确的 Cloud SQL 实例，以及以 `DATABASE_CONFIG_JSON` 的方式挂载数据库密钥。部署仍保持 API 单实例，避免尚未完全去除的内存缓存被多个实例同时持有。

不要在此时直接运行正式 API 部署来初始化生产数据。先执行下一节的迁移 Job，确认导入校验通过后，再将 API 切换到 PostgreSQL。

## 创建并执行 Cloud Run 迁移 Job

迁移 Job 使用与 API 相同的镜像，但只运行导入脚本，不对外提供 HTTP 服务。下面的 `API_IMAGE` 必须是包含本次代码的已推送镜像；请由有 Cloud Run 和 Artifact Registry 发布权限的执行人完成。

在仓库根目录，用一次性、带日期的镜像标签构建并推送迁移镜像。这个动作只写入 Artifact Registry，不会更新 Cloud Run 服务：

```bash
set -a
source .env.deploy
set +a

MIGRATION_TAG=incept-cloudsql-migration-20260820-1
API_IMAGE=asia-northeast1-docker.pkg.dev/ads-bpd-guard-sandbox/incept/api:${MIGRATION_TAG}
gcloud auth configure-docker asia-northeast1-docker.pkg.dev --quiet
docker build \
  --platform linux/amd64 \
  --build-context creative-core="${CREATIVE_CORE_BUILD_CONTEXT}" \
  -f Dockerfile.api \
  -t "${API_IMAGE}" \
  .
docker push "${API_IMAGE}"
```

请将 `MIGRATION_TAG` 改为实际执行日期和递增编号。构建完成后不要再修改代码；同一标签应贯穿干跑、导入和校验。

先创建 Job（将 `<API_IMAGE>` 替换为实际镜像地址）：

```bash
gcloud run jobs create incept-sqlite-to-postgres-migration \
  --project=ads-bpd-guard-sandbox \
  --region=asia-northeast1 \
  --image=<API_IMAGE> \
  --service-account=incept@ads-bpd-guard-sandbox.iam.gserviceaccount.com \
  --add-cloudsql-instances=ads-bpd-guard-sandbox:asia-northeast1:linglonglab-tokyo-prod-main-1 \
  --set-secrets=DATABASE_CONFIG_JSON=linglonglab-tokyo-prod-main-1-db-connection:2 \
  --command=python \
  --args=/app/scripts/migrate_sqlite_to_postgres.py,--source,gs://incept-assets/data/migrations/<最终快照文件名>,--dry-run \
  --max-retries=0 \
  --task-timeout=20m
```

然后逐步执行，任何一步失败都先停止，不要跳到下一步：

1. 执行干跑并查看日志。它只检查 SQLite 源文件，不创建表、不写 Cloud SQL：

   ```bash
   gcloud run jobs execute incept-sqlite-to-postgres-migration \
     --project=ads-bpd-guard-sandbox --region=asia-northeast1 --wait
   ```

2. 将 Job 参数中的 `--dry-run` 改为 `--apply`，然后再次执行。此步骤会创建 LinglongLab 表，并且只在所有 LinglongLab 表为空时导入。若日志说“目标表非空”，请停止并调查，**不要清空现有数据库来强行重试**。

3. 将 Job 参数改为 `--verify`，再次执行。日志会逐表比较行数和主键校验和。所有表均通过才可继续。

可用下面命令查看某次执行的日志；将 `<EXECUTION>` 替换为 Job 执行名称：

```bash
gcloud run jobs executions logs read <EXECUTION> \
  --project=ads-bpd-guard-sandbox --region=asia-northeast1
```

## 切换 API 并验收

确认导入校验成功后，部署 API：

```bash
./deploy.sh api
```

验收顺序如下：

1. 调用 API 的 `/readyz`。返回 `{"status":"ok","database":"postgres"}` 才说明 API 已连接 Cloud SQL。
2. 重新打开至少一个旧视频制作、一个素材线程和一个工作流，确认历史数据、图片预览和脚本内容正常。
3. 创建一个测试素材或工作流，刷新页面后确认仍存在；再重启/发布一个 API 修订版本后再次确认。
4. 确认 GCS 上传成功后，将 `INCEPT_REQUIRE_GCS_UPLOAD` 改为 `true` 并部署 API。这样 GCS 写入失败时会明确报错，不会把资产悄悄留在 Cloud Run 临时磁盘。
5. 稳定运行至少 7 天后，再决定何时停止 SQLite 备份；Cloud SQL 的自动备份与 PITR 应继续保持开启。

## 失败时怎么处理

- 干跑、导入或校验失败：保持 API 仍使用 SQLite，不部署 PostgreSQL 配置，不删除任何数据；根据日志修复后从干跑重新开始。
- API 部署后 `/readyz` 失败：将 Cloud Run API 回滚到上一修订版本，并保持 SQLite 源文件不变；不要用旧 SQLite 覆盖 Cloud SQL。
- 发现数据差异：停止写入，保留 Cloud SQL 现状和源快照，使用校验日志定位差异。是否重建一个新的空数据库，需要由数据负责人确认后再做。

## 给 AI 的执行约束

如将此手册交给 AI 执行，请要求它严格遵守：

- 先报告每项前置配置是否已满足，再执行任何写操作。
- 不得输出、复制、提交或记录任何 Secret 值。
- 不得猜测或变更 GCP 项目、区域、Cloud SQL 实例名、数据库名、模型 ID 或 API 地址。
- 不得删除 SQLite 文件、GCS 对象、Cloud SQL 表或 Cloud Run 历史修订版本。
- 导入只可使用最终冻结后生成的快照；校验不通过时必须停止。
