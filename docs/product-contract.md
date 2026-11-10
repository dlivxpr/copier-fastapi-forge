# 公开产品契约

本文定义 `copier-fastapi-forge` 当前承诺的公开产品契约。正确性由 Copier 输入与生成边界、文档化开发接口，以及生成项目的 HTTP、CLI 和运行行为共同决定；模板源码排布、完整生成树文本和历史迁移来源不属于契约。

## Copier 输入

以下问题名称、类型、choices、默认值、`when` 和 validator 属于公开接口：

|问题|契约|
|---|---|
|`project_name`|小写字母开头的小写字母、数字和下划线组合；默认 `my_project`|
|`project_slug`|同一命名约束；默认由 `project_name` 转为小写并把连字符替换为下划线|
|`project_description`|默认 `A FastAPI project`|
|`author_name` / `author_email`|默认 `Your Name` / `your@email.com`|
|`timezone`|默认 `UTC`|
|`python_version`|`3.12`、`3.13`、`3.14`；默认 `3.12`|
|`backend_port`|`1..65535`；默认 `8000`|
|`database`|`postgresql` 或 `none`；默认 `postgresql`|
|`orm_type`|数据库启用时选择 `sqlalchemy` 或 `sqlmodel`；默认 `sqlalchemy`|
|`db_pool_size` / `db_max_overflow` / `db_pool_timeout`|数据库启用时出现；默认 `5` / `10` / `30`，并拒绝负数或无效下限|
|`include_example_crud`|数据库启用时出现；默认关闭|
|`background_tasks`|`taskiq` 或 `none`；默认 `none`|
|`enable_redis`|是否生成 API 进程共享 Redis client；默认关闭|
|`enable_caching`|是否生成 Redis cache；默认关闭，启用时要求 `enable_redis`|
|`enable_rate_limiting`|是否生成 HTTP rate limiting；默认关闭|
|`rate_limit_requests` / `rate_limit_period`|rate limiting 启用时出现；默认 `100` / `60`，且必须大于零|
|`rate_limit_storage`|rate limiting 启用时选择 `memory` 或 `redis`；默认 `memory`，选择 Redis 时要求 `enable_redis`；同时启用 `enable_docker` 时只允许 `redis`（要求 `enable_redis`），`memory` 仅在非 Docker 生成中可用|
|`ai_framework`|`pydantic_ai` 或 `none`；默认 `pydantic_ai`|
|`enable_logfire`|Pydantic AI 启用时出现；默认启用|
|`enable_docker`|默认启用；与 `enable_rate_limiting` 同时启用时要求 `enable_redis` 且 `rate_limit_storage=redis`，不满足的组合在生成前被 validator 拒绝|
|`reverse_proxy`|Docker 启用时选择 `nginx_external` 或 `none`；默认 `nginx_external`|
|`ci_type`|`github` 或 `none`；默认 `github`|
|`deployment_api_key`|所有调用方共享的部署级 secret；默认开发占位值 `change-me-in-production`|

Copier 的 `--defaults`、`--data` 和 `--data-file` 对同一答案必须得到确定且等价的生成结果。本次契约只覆盖 `copier copy`，不承诺 `copier update`。

## 生成边界

生成项目位于项目根目录，始终包含 FastAPI 应用、CLI、统一异常 envelope、部署级 API Key、health probes、测试和维护文档。能力关闭时，其专属文件、依赖、配置、环境变量、部署资产、测试和 guidance 必须全部不生成；无效能力组合必须在渲染前被 `when` 或 validator 拒绝。

以下能力属于产品边界：

- 部署级 API Key 和异步 lifespan；
- 可选 PostgreSQL，启用时二选一使用 SQLAlchemy 或 SQLModel；
- 可选 Item create/get/update/delete 示例，不提供 list endpoint；
- 独立 Redis client、Redis cache、memory/Redis rate limiting；
- 使用独立 Redis Streams broker/result backend 生命周期的 Taskiq worker 与 scheduler；
- 无请求间可变状态的单轮 Pydantic AI Agent；
- 只 instrument Pydantic AI 且默认不采集模型内容的 Logfire；
- Docker 开发与压测/生产两套 Compose 编排、外部 Nginx 和 GitHub Actions；
- 根级 `AGENTS.md`。

Frontend、用户/JWT、teams、billing、消息渠道、文件存储、Webhooks、RAG、Kubernetes、Helm、Traefik、替代队列、替代 telemetry、provider SDK、分页、WebSocket Agent、多轮 conversation 和 demo routes/tasks 不属于产品边界。

## 文档化开发接口

生成项目承诺以下开发 seam：

- `app.main:create_app`、`app.main:app` 和 async lifespan；
- `app.core.config:Settings`、共享 `settings` 与 `.env.example` 中对应的环境变量；
- `AppException` 及统一 error envelope；
- `app.api.deps` 中部署级 API Key，以及按能力生成的数据库、Redis 和 Agent dependencies；
- PostgreSQL 分支的 route → service → repository → async database 分层；repository 执行 `flush()` / `refresh()`，session manager 统一 `commit()` / `rollback()`；
- API database engine 与 worker `NullPool` context 相互隔离；
- README 与 `AGENTS.md` 中明确列出的 Redis、cache、rate limiting、Taskiq 和 Agent 扩展 seam；
- 项目根的 tests、README、环境变量、安全、贡献和手工步骤。

未被 README 或 `AGENTS.md` 承诺的内部模块、符号、helper 排布和源码文本可自由重构。

## HTTP 契约

- `GET /health`、`GET /health/live` 和 `GET /health/ready` 公开，不要求 API Key；readiness 只报告已启用资源。
- 所有业务 API 使用 `X-API-Key`，缺失和错误 key 返回统一错误 envelope，且不发送 Bearer challenge。
- 未处理异常返回统一 500 envelope，并保留 Request ID 和日志脱敏行为。
- 应用面向服务间调用，不提供 CORS middleware、`enable_cors` 选项或 `CORS_*` 配置；携带 `Origin` 的请求不附加 CORS 响应头，`OPTIONS` 请求交由路由匹配处理。
- Item 示例启用时提供 create、get、update 和 delete，不生成 list endpoint。
- Agent 启用时，`POST /agent/run` 返回单轮 JSON 结果，`POST /agent/stream` 返回 SSE content、tool、complete 和 error framing。
- 每次 Agent 请求只使用当前 input 和当前 dependencies；请求间不保留 conversation、历史消息或可变推理状态。
- 规范化 OpenAPI 是完整 HTTP 机器契约；测试可以保存窄范围 OpenAPI 快照，但快照不是产品规范来源。

## CLI 与运行行为

项目脚本名称为 `project_slug`，始终提供：

- `server run`：支持 `--host`、`--port` 和 `--reload`；
- `server routes`：列出已注册 HTTP method、path 和 route name。

PostgreSQL 启用时增加 `db init`、`db migrate`、`db upgrade`、`db downgrade`、`db current` 和 `db history`。Taskiq 启用时增加 `taskiq worker` 与 `taskiq scheduler`。

Item 示例启用时，生成 `alembic/versions/0001_create_items.py`，revision ID 为 `0001_create_items`，且 `down_revision = None`；它是从 `base` 开始的首个 migration。关闭 Item 示例时不生成该 migration。

数据库、Redis 和 cache 资源由 API lifespan 显式初始化和关闭；Taskiq broker/result backend 由 worker process 独立拥有。真实集成必须能运行 migration、CRUD、commit/rollback、Redis 操作、rate limiting、worker/scheduler、Agent JSON/SSE 和资源 teardown。

Taskiq 使用项目级命名的 Redis Stream、固定 consumer group，并从 `0-0` 创建新 group，确保 worker 首次启动前已发布的任务可被消费。`TASKIQ_STREAM_MAXLEN` 默认 `100000` 且使用近似裁剪；`TASKIQ_STREAM_IDLE_TIMEOUT_MS` 默认 `3600000`。在配置的积压容量与故障恢复窗口内，worker 确认前失联的任务按 at-least-once 重新交付，因此 task 必须幂等；超过容量边界时不承诺恢复。该保证不包含 task exception 自动重试、DLQ、exactly-once、旧 Redis List backlog 迁移或 List/Stream 兼容运行。

## 部署、CI 与 guidance

- Docker 生成 multi-stage、non-root、healthcheck image，资产位于 `deploy/`；image 默认 CMD 直接以 Gunicorn 和 `uvicorn_worker.UvicornWorker` 运行 API，固定 `--workers 2`，不读取 `WEB_CONCURRENCY`，非 Docker CLI 行为不变。
- 仅生成开发（`deploy/compose.yaml` + `deploy/.env`）与压测/生产（`deploy/compose.prod.yaml` + `deploy/.env.prod`）两套编排，命令必须显式 `--env-file`；env 只生成 `deploy/.env.example` 与 `deploy/.env.prod.example` 模板，实际文件手工复制、缺失即失败，且被 Git 与 image 排除。根 `.env.example`/`.env` 与非 Docker 行为保持不变。
- 两套编排使用独立 top-level project name（`<project_slug>_dev` / `<project_slug>_prod`），容器、网络和卷相互隔离；已有卷不删除、不自动迁移。开发编排只读挂载 app/cli 源码并启用 `--reload`，经仅开发引用的 `deploy/gunicorn.dev.conf.py`（`worker_int` hook）使变更 worker 正常重启，重载后恢复为 2 个；该文件随镜像分发，改动需重建镜像生效。生产无 reload、preload 或源码挂载，也不引用该配置文件。
- `DB_POOL_*` 按每个 API worker 计（默认 `5`/`10` 时两个 worker 最多 30 个数据库连接），Docker 部署不自动减半。
- 生产必填非空：`API_KEY`；PostgreSQL 启用时 `POSTGRES_PASSWORD`；Redis 或 Taskiq 启用时 `REDIS_PASSWORD`；Agent 启用时 `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`；Logfire 启用时 `LOGFIRE_TOKEN` 可选。缺失时 Compose 以 `${VAR:?}` 语义在解析阶段失败，不新增联网或强度验证。
- 基础设施变量统一为 `BACKEND_BIND_HOST`（默认 `127.0.0.1`）、`BACKEND_PORT`（宿主 API 端口，默认 `backend_port`）、`POSTGRES_PUBLISHED_PORT`（仅开发且启用 PostgreSQL，默认 `5432`）和 `REDIS_PUBLISHED_PORT`（仅开发且启用 Redis 或 Taskiq，默认 `6379`）。开发编排发布的全部宿主端口绑定 `127.0.0.1`；生产编排除 API 外不发布任何宿主端口，API 默认绑定 localhost，可为远程压测显式放开且应由防火墙保护。
- 外部 Nginx 提供 TLS、HTTP→HTTPS、ACME、security headers、forwarded headers 和 timeout；不作为 compose service，其容器加入 `<project_slug>_prod_backend` 网络并以 `app:<backend_port>` 为 upstream，不依赖 `host.docker.internal`。
- GitHub Actions 生成独立 lint/test jobs、coverage XML、非阻断 Codecov，以及按能力生成的 PostgreSQL、Redis 和 Docker 步骤。
- 生成的 tests 和 agent guidance 必须准确反映所选能力，不得引用未生成的命令、路径、依赖或配置。
- 生成项目不包含 `docs/`、`.agents/`、`.omp/` 或 `.claude/`；根级 `AGENTS.md` 是唯一 agent guidance。

## 演进规则

公开契约变化必须在同一变更中更新本文和对应行为测试。breaking change 必须明确说明，并采用 clean cutover；兼容期只有在记录范围、期限和删除条件时才能引入。实现重构、测试重组和依赖升级只要保持本文定义的可观察行为，就不构成契约变化。
