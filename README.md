# 个人全资产管理工具 V1.5

本项目是个人本地优先的全资产管理工具。当前完成阶段 6：复盘 + 导入导出 + 自动备份。

## 本地开发与 Linux 部署准备

`data/asset_manager.sqlite3` 是迁移源档案，保持原位，不再用作日常开发，也不会在应用启动时迁移。Mac 开发环境使用从可信 SQLite Backup API 备份恢复出的独立 `data/asset_dev.sqlite3`，已验证并建立 Alembic baseline。服务器计划使用 `runtime/data/asset_prod.sqlite3`，目前尚未创建。这些数据库及备份都不进入 Git。

若旧项目仍占用 `127.0.0.1:8000/5173`，可在不停止旧服务的情况下，于 `backend/.env` 设置 `ASSET_MANAGER_API_PORT=8002`、`ASSET_MANAGER_DATABASE_PATH=../data/asset_dev.sqlite3` 和 `ASSET_MANAGER_CORS_ORIGINS=["http://127.0.0.1:5174","http://localhost:5174"]`，于 `frontend/.env.local` 设置 `VITE_API_BASE_URL=http://127.0.0.1:8002`、`VITE_DEV_PORT=5174`。两份私有配置均被 Git 忽略。此时使用启动脚本后，新项目访问地址为 `http://127.0.0.1:5174`。首次开发前无需再对已有 `asset_dev` 执行 `upgrade`。

### Mac 开发

需要 Python 3.9+、Node 24 和 npm。安装依赖：

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm ci && cd ..
```

可参考根目录 `.env.example`，把开发变量放在不进 Git 的 `backend/.env`。创建全新开发库时显式运行：

```bash
cd backend
.venv/bin/python -m app.db.migrate upgrade --database ../data/asset_dev.sqlite3
cd ..
scripts/start_app.sh
```

`backend/.env` 中的相对路径以 `backend/` 为工作目录。前端开发模式默认访问 `http://127.0.0.1:8000`，也可在 `frontend/.env.local` 中设置 `VITE_API_BASE_URL` 和 `VITE_DEV_PORT`。生产构建默认走同源 `/api`。后端启动前会检查 Alembic 是否处于最新版本，不自动创建表或修改 schema。

Mac 开发环境示例（保存到 `backend/.env`，不进 Git）：

```dotenv
ASSET_MANAGER_DATABASE_PATH=../data/asset_dev.sqlite3
ASSET_MANAGER_BACKUP_DIR=../backups
ASSET_MANAGER_UPLOAD_DIR=../data/ocr_uploads
ASSET_MANAGER_OCR_CACHE_DIR=../data/paddleocr_home
ASSET_MANAGER_SCHEDULER_ENABLED=false
ASSET_MANAGER_CORS_ORIGINS=["http://127.0.0.1:5173","http://localhost:5173"]
```

运行隔离测试与前端构建：

```bash
cd backend && PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider
cd ../frontend && npm run build
```

测试使用 pytest 临时数据库、备份和上传目录，并关闭 scheduler。不要把 `data/asset_manager.sqlite3` 设为测试数据库。

### SQLite 备份与恢复

备份使用 SQLite Backup API，并生成同名 `.manifest.json`，记录 SHA-256、schema 版本、文件大小和核心表记录数。迁移源档案的可信备份位于被 Git 忽略的 `backups/migration-preflight/`；已通过完整性、逐表记录和临时恢复演练。后续恢复生产库仍须单独确认。

```bash
scripts/backup.sh --source /path/to/test.sqlite3 --backup-dir /path/to/test-backups
cd backend && .venv/bin/python -m app.db.backup_cli verify --backup /path/to/test-backups/backup.sqlite3
cd ..
scripts/restore.sh --backup /path/to/test-backups/backup.sqlite3 --destination /path/to/restored.sqlite3
```

默认恢复只创建并验证 `restored.sqlite3.new` 及其校验清单。确认应用已停止后，使用相同备份和目标路径加 `--promote` 原子切换；目标已存在时还需 `--replace-existing --rollback-dir /path/to/rollback-backups`，工具会先生成独立回滚备份。文件名应使用备份命令实际输出，不要照抄示例名。历史绝对路径备份记录不会被新清理逻辑删除。

### Migration

`backend/migrations/versions/schema_1_4_0.py` 固定了当前真实数据库的 1.4.0 schema。旧库首次纳入 Alembic 时，先创建并验证完整备份，再在停机窗口执行：

```bash
cd backend
.venv/bin/python -m app.db.migrate validate-baseline --database /path/to/existing.sqlite3
.venv/bin/python -m app.db.migrate baseline --database /path/to/existing.sqlite3
.venv/bin/python -m app.db.migrate status --database /path/to/existing.sqlite3
```

`baseline` 只在 schema、索引和 1.0.0～1.4.0 历史记录匹配时写入 Alembic 版本标记；仅 `asset_dev` 已执行，迁移源档案未执行。新空库使用 `upgrade`，后续发布 schema 变更时新增 Alembic revision，并采用 SQLite batch migration。发布顺序固定为备份、显式 `upgrade`、启动新版本。不能通过 Web 启动隐式迁移。

新导出文件标记 `dataVersion=1.4.0`。旧版本误标为 `1.0.0`、但含有 1.4.0 schema 历史记录的 JSON 导出仍可导入；真实旧 schema 的导出需单独转换和验证。

后续创建 revision 时在 `backend/` 执行 `.venv/bin/alembic -c alembic.ini revision -m "change description"`，在新 revision 的 `upgrade()` 中使用 `op.batch_alter_table(...)` 修改 SQLite 表。先在临时副本上验证，再安排正式 migration。

### Linux Docker Compose

目标目录为 `/opt/apps/asset-management/`。服务器先准备私有 `.env` 和 `runtime/{data,backups,uploads,ocr-cache}`，确保 bind mount 对 Compose 中配置的 UID/GID 可写。Compose 默认使用隔离的 `runtime/data/asset_test.sqlite3` 且禁用 scheduler；完成只读盘点、选定空闲回环端口后，先在测试库上构建和验证。初次迁移时应先恢复到 `runtime/data/asset_prod.sqlite3.new` 并核对，再经单独确认后提升为正式文件；对旧 schema 执行经验证的 `baseline`。服务器的首次数据库恢复和 baseline 必须单独确认。

Linux 根目录 `.env` 示例（只写服务器专用值，不进 Git）：

```dotenv
ASSET_MANAGER_FRONTEND_PORT=8088
ASSET_MANAGER_UID=1000
ASSET_MANAGER_GID=1000
ASSET_MANAGER_OCR_PROVIDER=none
ASSET_MANAGER_DOCKER_DATABASE_PATH=/srv/runtime/data/asset_test.sqlite3
ASSET_MANAGER_DOCKER_SCHEDULER_ENABLED=false
```

Compose 将数据目录挂载到容器内 `/srv/runtime`；无需设置 DB_HOST/DB_PASSWORD。OCR 可在以后通过环境变量切换到远程服务或独立容器。只有正式库经过确认并 promote 后，才可把 `ASSET_MANAGER_DOCKER_DATABASE_PATH` 改为 `/srv/runtime/data/asset_prod.sqlite3` 并显式启用 scheduler。

```bash
docker compose build
docker compose run --rm --no-deps backend python -m app.db.migrate upgrade --database /srv/runtime/data/asset_test.sqlite3
docker compose run --rm --no-deps backend python -m app.db.migrate status --database /srv/runtime/data/asset_test.sqlite3
docker compose up -d
docker compose ps
```

前端 Nginx 将 `/api` 转发到内部后端。后端只有一个实例、一个 Uvicorn worker，不对宿主机发布后端端口；前端只绑定宿主机 `127.0.0.1:8088`（可通过 `ASSET_MANAGER_FRONTEND_PORT` 调整）。当前阶段不配置公网或域名。服务器端脚本 `scripts/deploy.sh --execute` 仅适用于首次部署完成、已有 Alembic 管理的正式库；它会 pull、构建、备份、迁移、更新容器。执行前必须检查 Git 工作树和备份空间。

回滚时先停止新容器，保留故障库，用 `runtime/backups` 中迁移前备份恢复到 `.new`、验证，再原子替换；随后启动对应旧代码/镜像。不能用 Git 回滚替代数据库恢复。生产备份还需定期复制到服务器以外的位置。

### Git 边界

`.gitignore` 排除数据库、runtime、备份、上传、OCR 模型缓存、环境文件及密钥。首次提交前先运行 `git add --dry-run .` 核对清单。需求文档可提交，`投资/.obsidian/` 为个人编辑器状态，已排除。

以下阶段说明保留原有功能验收资料；出现旧启动和备份描述时，以本节为准。

## 项目结构说明

```text
.
├─ backend/          FastAPI 后端、SQLModel 模型、SQLite 初始化
├─ frontend/         React + Vite + TypeScript 前端
├─ data/             SQLite 数据库目录
├─ backups/          后续自动备份目录
├─ docs/             阶段说明
├─ scripts/          启动脚本
├─ 投资/             需求、数据字典、验收用例、设计规范
└─ README.md
```

## 关键文件清单

- `backend/app/main.py`：FastAPI 入口与 `GET /health`。
- `backend/app/core/config.py`：本地配置、数据库路径、默认 ownerId、dataVersion。
- `backend/app/models/tables.py`：V1.5 核心表模型。
- `backend/app/db/init_db.py`：供显式 Alembic baseline 使用的默认 settings、alert_rules、data_sources 初始化数据。
- `backend/app/api/`：资产、设置、提醒规则 API。
- `backend/app/schemas/`：请求 / 响应数据结构。
- `backend/app/services/`：SQLite 写入、校验、ID 生成、更新时间维护。
- `backend/app/tasks/scheduler.py`：APScheduler 本地后台任务注册。
- `backend/app/services/task_runner.py`：任务执行、日志、失败重试。
- `backend/app/services/alerts.py`：核心提醒规则生成并持久化到 `alert_records`。
- `backend/app/services/snapshots.py`：每日资产快照生成。
- `backend/app/services/reviews.py`：基于真实快照、交易、提醒、行情生成月度复盘。
- `backend/app/services/import_export.py`：完整 JSON 导出、导入校验和覆盖写入。
- `backend/app/services/backups.py`：手动 / 自动备份与 30 天保留策略。
- `frontend/src/App.tsx`：空状态首页与后端连接状态。
- `frontend/src/api/client.ts`：统一前端 API 客户端，支持 `VITE_API_BASE_URL`。
- `frontend/src/styles.css`：执行项目内 Arounda / FocusFlow 设计规范的基础样式。
- `scripts/start_backend.sh`、`scripts/start_frontend.sh`、`scripts/start_app.sh`：启动脚本。

## 阶段 2 API 路径

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/api/assets?includeInactive=false` | 查询资产列表，默认排除停用资产 |
| POST | `/api/assets` | 新增资产 |
| GET | `/api/assets/{asset_id}` | 查询资产详情 |
| PATCH | `/api/assets/{asset_id}` | 编辑资产 |
| POST | `/api/assets/{asset_id}/deactivate` | 停用资产 |
| GET | `/api/settings` | 查询设置 |
| PATCH | `/api/settings/{setting_key}` | 修改设置值 |
| GET | `/api/alert-rules` | 查询提醒规则 |
| PATCH | `/api/alert-rules/{rule_code}` | 修改提醒规则 |
| GET | `/api/dashboard/summary` | 今日页汇总 |
| GET | `/api/data-sources` | 数据源状态 |
| GET | `/api/task-logs` | 任务日志 |
| GET | `/api/alerts` | 提醒记录 |
| GET | `/api/monthly-reviews` | 月度复盘记录 |
| POST | `/api/monthly-reviews/generate` | 生成月度复盘 |
| POST | `/api/assets/{asset_id}/price/update` | 单资产 AKShare 行情更新 |
| POST | `/api/assets/{asset_id}/price/manual` | 单资产手动补录价格 |
| POST | `/api/tasks/price-update/run` | 手动触发全部权益资产行情更新 |
| GET | `/api/tasks/status` | 查询后台任务状态 |
| POST | `/api/tasks/{task_type}/run` | 手动触发指定后台任务 |
| GET | `/api/export` | 导出完整 JSON 数据包 |
| POST | `/api/import` | 校验并覆盖导入 JSON 数据包 |
| GET | `/api/backups` | 查询备份记录 |
| POST | `/api/backups/run` | 手动创建备份 |

## API 请求示例

新增现金资产：

```bash
curl -X POST http://127.0.0.1:8000/api/assets \
  -H 'Content-Type: application/json' \
  -d '{"assetType":"cash","name":"招商银行活期","platform":"招商银行","currentValue":10000,"targetTag":"应急金"}'
```

新增权益资产：

```bash
curl -X POST http://127.0.0.1:8000/api/assets \
  -H 'Content-Type: application/json' \
  -d '{"assetType":"equity","name":"纳指基金","platform":"支付宝","productCode":"000000","market":"CN_FUND","holdingShare":1000,"costAmount":2000,"latestPrice":2.1}'
```

修改设置：

```bash
curl -X PATCH http://127.0.0.1:8000/api/settings/monthly_required_expense \
  -H 'Content-Type: application/json' \
  -d '{"settingValue":"10000"}'
```

修改提醒规则：

```bash
curl -X PATCH http://127.0.0.1:8000/api/alert-rules/cash_safety \
  -H 'Content-Type: application/json' \
  -d '{"isEnabled":true,"thresholdValue":"4","alertLevel":"must","repeatIntervalDays":3}'
```

## 安装依赖

后端：

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
```

前端：

```bash
cd frontend
npm install
```

## 启动步骤

单独启动后端：

```bash
scripts/start_backend.sh
```

开发时如需热重载，可在本机权限允许的环境下手动运行：

```bash
cd backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

单独启动前端：

```bash
scripts/start_frontend.sh
```

一键启动：

```bash
scripts/start_app.sh
```

访问地址：

- 前端：`http://127.0.0.1:5173`
- 后端健康检查：`http://127.0.0.1:8000/health`

## 固定网址与自动启动

如果希望每次登录电脑后自动启动前后端，不再手动运行启动命令，可以安装 macOS 用户级自启动服务：

```bash
scripts/install_macos_autostart.sh
```

安装后固定访问：

- 前端：`http://127.0.0.1:5173/`
- 后端健康检查：`http://127.0.0.1:8000/health`

后台日志位于：

```bash
~/Library/Logs/personal-asset-manager/
```

如需取消自动启动：

```bash
scripts/uninstall_macos_autostart.sh
```

## OCR 服务配置

上传截图录入资产时，后端会先探测本地 OCR HTTP 服务；本地不可用时，再检查是否配置了远程 OCR API。任一方式都只做字段预填，保存前仍需人工确认，不会伪造识别结果。

默认本地 OCR 探测地址：

```bash
ASSET_MANAGER_OCR_LOCAL_PYTHON_PATH=/path/to/paddleocr-python
ASSET_MANAGER_OCR_LOCAL_PYTHON_HOME=/path/to/ocr-cache
ASSET_MANAGER_OCR_LOCAL_PYTHON_TIMEOUT_SECONDS=20
ASSET_MANAGER_OCR_LOCAL_ENDPOINTS='["http://127.0.0.1:8866/ocr","http://127.0.0.1:8001/ocr"]'
ASSET_MANAGER_OCR_LOCAL_TIMEOUT_SECONDS=1.5
```

远程 PaddleOCR HTTP API 兜底示例：

```bash
ASSET_MANAGER_OCR_PROVIDER=paddleocr_http
ASSET_MANAGER_OCR_ENDPOINT=https://your-paddleocr-api.example.com/ocr
ASSET_MANAGER_OCR_API_KEY=
ASSET_MANAGER_OCR_TIMEOUT_SECONDS=30
```

DeepSeek OCR / OpenAI-compatible 视觉 OCR 服务示例：

```bash
ASSET_MANAGER_OCR_PROVIDER=deepseek_ocr
ASSET_MANAGER_OCR_ENDPOINT=https://your-ocr-provider.example.com/v1/chat/completions
ASSET_MANAGER_OCR_API_KEY=your_token
ASSET_MANAGER_OCR_MODEL=deepseek-ocr
ASSET_MANAGER_OCR_TIMEOUT_SECONDS=30
```

说明：

- `paddleocr_http` 会向服务发送 JSON：`imageBase64`、`image`、`fileName`。
- `deepseek_ocr` 会按 OpenAI-compatible `chat/completions` 图片消息格式发送请求。
- 如果配置了 `ASSET_MANAGER_OCR_LOCAL_PYTHON_PATH`，后端会优先调用该 Python 环境里的 PaddleOCR；缓存目录通过 `ASSET_MANAGER_OCR_LOCAL_PYTHON_HOME` 指到项目内，避免写入系统家目录。
- 后端先尝试本地 OCR 地址，成功后不再调用远程 API。
- Token 只放在 `.env`，不会写入 SQLite，也不会进入导出 JSON。
- OCR 返回文字后，系统只做字段预填；保存前仍需人工确认。

## 阶段 1 验收清单

- [ ] 根目录存在 `frontend/`、`backend/`、`data/`、`backups/`、`docs/`、`scripts/`。
- [ ] 后端可以启动，默认监听 `127.0.0.1:8000`。
- [ ] `GET /health` 返回 `status: ok`，并包含数据库状态和 `dataVersion`。
- [ ] 显式 migration 后生成 `data/asset_dev.sqlite3`。
- [ ] SQLite 中存在 `schema_migrations`、`settings`、`alert_rules`、`assets`、`price_records`、`alert_records`、`daily_snapshots`、`task_logs` 等核心表。
- [ ] 前端可以启动并访问后端 health API。
- [ ] 前端显示真实空状态，不出现示例资产、示例收益、伪造月度变化或回撤。
- [ ] localStorage 不保存资产、提醒、价格、设置等业务数据。
- [ ] README 中的安装与启动步骤可执行。

## 阶段 2 验收清单

- [ ] `POST /api/assets` 新增现金资产后写入 SQLite，`ownerId=local_user`。
- [ ] `POST /api/assets` 新增权益资产时校验产品代码、份额、本金等必要字段。
- [ ] `GET /api/assets` 返回真实 SQLite 数据，不依赖 mock。
- [ ] `PATCH /api/assets/{asset_id}` 可编辑资产，并更新 `updatedAt`。
- [ ] `POST /api/assets/{asset_id}/deactivate` 停用资产，默认列表不返回，详情仍可查。
- [ ] `GET /api/settings` 返回默认 settings。
- [ ] `PATCH /api/settings/{setting_key}` 可保存设置，非法负数被拒绝。
- [ ] `GET /api/alert-rules` 返回默认 alert_rules。
- [ ] `PATCH /api/alert-rules/{rule_code}` 可修改开关、阈值、级别、重复提醒间隔。
- [ ] 错误字段返回 422 且不写入脏数据。

## 阶段 3 页面清单

- 今日：从 `/api/dashboard/summary` 获取资产汇总；无资产时显示真实空状态。
- 资产：列表、详情、新增、编辑、停用；新增流程为先选资产类型，再填写类型表单。
- 提醒：读取 `/api/alerts`；无提醒时说明提醒必须由后端任务持久化生成。
- 复盘：读取 `/api/monthly-reviews`；无快照/复盘时不伪造月度变化或回撤。
- 设置：以表格展示 settings、alert_rules、data_sources、task_logs。

## 阶段 3 交互说明

- 资产新增分两步：选择现金 / 固收 / 权益 / 负债，再展示对应字段。
- 现金表单不展示产品代码、份额、到期日、还款日、定投字段。
- 固收表单展示本金、预期年化、到期日、流动性。
- 权益表单展示产品代码、市场、份额、本金、价格、净值日期和定投字段。
- 负债表单展示待还余额、还款日、年化利率。
- 资产保存、编辑、停用全部通过后端 API 写入 SQLite，刷新页面后重新从 API 加载。
- 当前前端不使用 localStorage 保存任何业务数据。

## 前端 API 封装

所有 API 调用集中在 `frontend/src/api/client.ts`：

- 开发默认 baseUrl：`http://127.0.0.1:8000`；生产默认同源
- 可配置：`VITE_API_BASE_URL=http://127.0.0.1:8000`
- 统一错误处理：非 2xx 响应会抛出后端 `detail` 或 HTTP 状态错误。

## 阶段 3 验收清单

- [ ] 首次无资产时，今日、资产、提醒、复盘页面显示空状态，不出现 mock 资产。
- [ ] 主导航包含：今日、资产、提醒、复盘、设置。
- [ ] 新增现金、固收、权益、负债资产均可保存到 SQLite。
- [ ] 四类资产表单字段按数据字典区分，不是万能大表单。
- [ ] 资产可查看详情、编辑、停用。
- [ ] 设置页以表格展示 settings、alert_rules、data_sources、task_logs。
- [ ] 页面刷新后数据仍从 SQLite 加载，不丢失。

## 阶段 4：行情与手动补录

### AKShare 接入说明

- 第一数据源为 AKShare，当前通过 `fund_open_fund_info_em(symbol, indicator="单位净值走势")` 获取开放式基金净值。
- 已用测试代码验证：
  - `005911`：AKShare 返回价格日期 `2026-07-03`、单位净值 `2.5763`、日涨跌幅 `0.05`
  - `009777`：AKShare 返回价格日期 `2026-07-03`、单位净值 `0.8834`、日涨跌幅 `1.02`
- 普通沙箱无外网时会 DNS 失败；本机允许网络后可正常访问东方财富数据源。

### 数据源适配器结构

- `backend/app/data_sources/base.py`
  - `DataSourceAdapter`：统一抽象，暴露 `fetch_price(product_code)`。
  - `PriceQuote`：统一行情返回结构。
- `backend/app/data_sources/akshare_adapter.py`
  - `AkShareAdapter`：当前第一数据源。
- 后续接入 Tushare / Choice 时，只需实现同样的 `fetch_price` 返回 `PriceQuote`。

### 成功和失败样例

成功更新会：

- 写入 `price_records`，`sourceType=akshare`，`dataStatus=normal`，`isValid=true`。
- 更新资产 `latestPrice`、`priceDate`、`dailyChangePct`、`dataSourceType`、`dataStatus`。
- 权益资产 `currentValue = holdingShare × latestPrice`。

失败更新会：

- 写入 `price_records`，`dataStatus=failed`，`isValid=false`，带 `errorMessage`。
- 不覆盖资产上的上次有效 `latestPrice` 和 `currentValue`。
- 资产记录失败状态和失败原因，方便前端展示。

### 手动补录流程

1. 在资产详情页选择权益资产。
2. 填写价格日期、价格、可选日涨跌幅。
3. 点击“保存补录”。
4. 后端写入 `price_records`，`sourceType=manual`，`dataStatus=manual`。
5. 同步更新资产最新价格和当前市值。

### 阶段 4 验收清单

- [ ] AKShare 可获取 `005911`、`009777` 的净值数据。
- [ ] `POST /api/assets/{id}/price/update` 可单资产更新。
- [ ] `POST /api/tasks/price-update/run` 可手动触发权益资产批量更新并写入 `task_logs`。
- [ ] `POST /api/assets/{id}/price/manual` 可手动补录并写入 `price_records`。
- [ ] 行情失败时写入失败记录，不覆盖上次有效价格。
- [ ] 资产详情展示价格日期、数据源、数据状态和失败原因。
- [ ] 权益资产当前市值由 `holdingShare × latestPrice` 计算。

## 阶段 5：后台任务与自动提醒

### 任务注册清单

| taskType | 任务名称 | 默认计划 |
|---|---|---|
| `price_update` | 行情更新 | 每天 20:30、22:30 |
| `alert_generate` | 提醒生成 | 每天 22:40，且行情更新成功后自动触发 |
| `daily_snapshot` | 每日快照 | 每天 23:30 |
| `data_source_check` | 数据源健康检查 | 每天 08:00 |
| `auto_backup` | 自动备份 | 每天 00:30 |

所有任务由后端 APScheduler 注册。只要 FastAPI 后端仍运行，即使浏览器关闭，后台任务也会继续执行。

失败任务会写入 `task_logs.errorMessage`，并按 30 分钟间隔重试，最多 3 次。

### 任务日志样例

```json
{
  "taskLogId": "tasklog_xxx",
  "taskType": "daily_snapshot",
  "status": "success",
  "message": "每日快照已生成：2026-07-05",
  "errorMessage": null,
  "successCount": 1,
  "failedCount": 0
}
```

### 提醒规则实现说明

提醒由后端任务生成并保存到 `alert_records`，前端提醒页只读取持久化结果，不在页面打开时临时计算。

已实现规则：

- 现金不足：现金覆盖月数低于安全线。
- 现金闲置：现金覆盖月数高于闲置线。
- 权益仓位偏高：权益占比高于上限。
- 普通回撤：有历史快照且回撤高于普通提醒线。
- 强回撤：有历史快照且回撤高于强风险线；触发后不重复生成普通回撤提醒。
- 固收到期：到期日进入提前提醒窗口。
- 负债还款：还款日进入提前提醒窗口。
- 高息负债：负债利率高于阈值。
- 行情延迟：权益资产行情日期滞后超过阈值。
- 行情异常：权益资产行情状态为 `failed`、`abnormal` 或 `missing`。

提醒详情包含规则、当前值、阈值、数据日期、数据源、数据状态和触发原因。无历史快照时不计算回撤，不伪造回撤数据。

### 手动触发方式

设置页的“任务状态”表提供每个任务的“立即运行”按钮。

也可以直接调用 API：

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/price_update/run
curl -X POST http://127.0.0.1:8000/api/tasks/alert_generate/run
curl -X POST http://127.0.0.1:8000/api/tasks/daily_snapshot/run
curl -X POST http://127.0.0.1:8000/api/tasks/data_source_check/run
curl -X POST http://127.0.0.1:8000/api/tasks/auto_backup/run
```

兼容阶段 4 的行情入口仍保留：

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/price-update/run
```

### 阶段 5 验收清单

- [ ] 后端启动时注册 APScheduler 本地任务。
- [ ] `/api/tasks/status` 返回行情更新、提醒生成、每日快照、数据源健康检查、自动备份 5 类任务。
- [ ] 设置页任务状态表展示任务名称、启用状态、上次运行、下次运行、最近结果、操作。
- [ ] 点击“立即运行”或调用 `/api/tasks/{task_type}/run` 会写入 `task_logs`。
- [ ] 行情更新成功后自动触发提醒生成。
- [ ] 任务失败记录 `errorMessage`，并按 30 分钟间隔最多重试 3 次。
- [ ] 提醒生成后写入 `alert_records`，刷新页面后不丢失。
- [ ] 强回撤触发时不重复生成普通回撤提醒。
- [ ] 无历史快照时不计算或伪造回撤。
- [ ] 浏览器关闭但后端运行时，后台任务继续执行。

## 阶段 6：复盘、导入导出与备份

### 复盘生成逻辑

`POST /api/monthly-reviews/generate` 基于真实表生成月度复盘：

- `daily_snapshots`：读取指定月份月初快照和月内最后一条快照。
- `transactions`：按交易类型估算本月新增投入净额。
- `assets`：识别启用定投的资产，展示定投金额、累计投入、当前市值、收益、收益率、平均成本。
- `alert_records`：统计强提醒、必须关注提醒和未处理提醒。
- `price_records`：统计行情记录数量和失败 / 无效记录数量。

如果缺少月初快照，不会伪造月初净资产，`dataCompletenessStatus=history_insufficient`，并且 `startNetAsset`、`netAssetChange`、`investmentReturn` 保持为空。

如果月初和月末快照完整：

```text
净资产变化 = 月末净资产 - 月初净资产
投资收益 = 净资产变化 - 本月新增投入净额
```

下月关注事项只输出观察和提醒，例如补齐快照、关注未处理提醒、关注行情数据源稳定性，不输出买入、卖出、清仓、调仓等指令。

### 导出 JSON 示例

`GET /api/export` 返回完整数据包，包含 `dataVersion`、`exportedAt`、`ownerId` 和核心业务表：

```json
{
  "dataVersion": "1.4.0",
  "exportedAt": "2026-07-05T14:00:00+00:00",
  "ownerId": "local_user",
  "assets": [],
  "transactions": [],
  "priceRecords": [],
  "alertRules": [],
  "alertRecords": [],
  "dailySnapshots": [],
  "monthlyReviews": [],
  "settings": [],
  "dataSources": [],
  "taskLogs": [],
  "backups": []
}
```

导出会移除 `token`、`tokenEnvKey` 等敏感字段，不包含明文 Token。

### 导入校验逻辑

`POST /api/import` 请求：

```json
{
  "confirmOverwrite": true,
  "data": {
    "dataVersion": "1.4.0",
    "exportedAt": "2026-07-05T14:00:00+00:00",
    "ownerId": "local_user",
    "assets": [],
    "transactions": [],
    "priceRecords": [],
    "alertRules": [],
    "alertRecords": [],
    "dailySnapshots": [],
    "monthlyReviews": [],
    "settings": [],
    "dataSources": [],
    "taskLogs": [],
    "backups": []
  }
}
```

导入前必须满足：

- `confirmOverwrite=true`，前端会弹窗提示“会覆盖当前数据”。
- `dataVersion` 必须等于当前版本。
- `ownerId` 必须等于 `local_user`。
- 必填结构必须存在，核心表字段必须是数组。
- 每条记录必须能通过对应 SQLModel 模型校验。

导入会在一个事务中删除并重建业务数据；如果校验或写入失败，会回滚，不破坏当前数据库。

### 备份策略

- `POST /api/backups/run` 创建手动备份。
- `auto_backup` 后台任务创建自动备份。
- 每次备份通过 SQLite Backup API 创建验证过的副本和 manifest，并写入 `backups` 表。
- 默认读取 `backup_retention_days=30`，保留最近 30 天备份，过期备份会在创建新备份后清理。

### 阶段 6 验收清单

- [ ] `POST /api/monthly-reviews/generate` 可基于真实快照生成复盘。
- [ ] 缺少月初快照时，复盘显示历史不足，不伪造月初数据。
- [ ] 快照完整时，复盘区分净资产变化、新增投入和投资收益。
- [ ] 定投资产复盘展示定投金额、累计投入、当前市值、收益、收益率、平均成本。
- [ ] 下月关注事项只包含观察和提醒，不输出交易指令。
- [ ] `GET /api/export` 导出完整 JSON，包含 `dataVersion`、`exportedAt`、`ownerId` 和核心表。
- [ ] 导出 JSON 不包含明文 Token。
- [ ] `POST /api/import` 缺少确认、版本不一致或结构错误时返回错误，且不破坏当前数据库。
- [ ] 导入成功后刷新页面，资产、设置、提醒、快照、复盘等数据来自导入后的 SQLite。
- [ ] `POST /api/backups/run` 可手动备份并写入 `backups` 表。
- [ ] 自动备份任务继续由后端 APScheduler 执行，浏览器关闭不影响。
- [ ] 备份默认保留最近 30 天。

## 测试步骤

```bash
cd backend
.venv/bin/pytest
```

测试使用临时 SQLite 数据库、备份目录和上传目录，不污染 `data/asset_manager.sqlite3`。

## 已知限制

- 阶段 6 已完成本地后台任务、任务日志、每日快照、自动备份、核心提醒生成、月度复盘、完整 JSON 导入导出和手动备份。
- 暂未实现月度复盘定时任务、交易流水维护页面和云端多用户迁移。
- 数据源健康检查当前只做适配器可用性检查，不主动拉取测试行情。
- SQLite 使用 `SQLModel.metadata.create_all()` 初始化，并通过 `schema_migrations` 记录阶段版本；正式迁移机制在后续阶段增强。
- AKShare 依赖外网和上游接口可用性；失败时会写入失败记录，不覆盖上次有效价格。

## 边界说明

- SQLite 是正式业务数据源。
- 前端只通过 API 获取数据。
- localStorage 只允许后续保存主题、侧边栏折叠等 UI 偏好，不保存业务数据。
- 不做自动交易，不做自动投顾，不输出买入、卖出、清仓、调仓等指令。
- 设计规范执行 `投资/arounda-focusflow-dashboard-design-spec.md`，但本产品仍保持个人工具定位，不做展示型 Dashboard。
