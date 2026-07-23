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
|`rate_limit_storage`|rate limiting 启用时选择 `memory` 或 `redis`；默认 `memory`，选择 Redis 时要求 `enable_redis`|
|`ai_framework`|`pydantic_ai` 或 `none`；默认 `pydantic_ai`|
|`enable_logfire`|Pydantic AI 启用时出现；默认启用|
|`enable_cors`|默认启用|
|`enable_docker`|默认启用|
|`reverse_proxy`|Docker 启用时选择 `nginx_external` 或 `none`；默认 `nginx_external`|
|`ci_type`|`github` 或 `none`；默认 `github`|
|`deployment_api_key`|所有调用方共享的部署级 secret；默认开发占位值 `change-me-in-production`|

Copier 的 `--defaults`、`--data` 和 `--data-file` 对同一答案必须得到确定且等价的生成结果。本次契约只覆盖 `copier copy`，不承诺 `copier update`。

## 生成边界

生成项目位于项目根目录，始终包含 FastAPI 应用、CLI、统一异常 envelope、部署级 API Key、health probes、测试和维护文档。能力关闭时，其专属文件、依赖、配置、环境变量、部署资产、测试和 guidance 必须全部不生成；无效能力组合必须在渲染前被 `when` 或 validator 拒绝。

以下能力属于产品边界：

- 部署级 API Key、CORS 和异步 lifespan；
- 可选 PostgreSQL，启用时二选一使用 SQLAlchemy 或 SQLModel；
- 可选 Item create/get/update/delete 示例，不提供 list endpoint；
- 独立 Redis client、Redis cache、memory/Redis rate limiting；
- 使用独立 broker/result backend 生命周期的 Taskiq worker 与 scheduler；
- 无请求间可变状态的单轮 Pydantic AI Agent；
- 只 instrument Pydantic AI 且默认不采集模型内容的 Logfire；
- Docker、三套 compose、外部 Nginx 和 GitHub Actions；
- 根级 `AGENTS.md` 与按能力生成的 omp rules、skills 和 commands。

Frontend、用户/JWT、teams、billing、消息渠道、文件存储、Webhooks、RAG、Kubernetes、Helm、Traefik、替代队列、替代 telemetry、provider SDK、分页、WebSocket Agent、多轮 conversation 和 demo routes/tasks 不属于产品边界。

## 文档化开发接口

生成项目承诺以下开发 seam：

- `app.main:create_app`、`app.main:app` 和 async lifespan；
- `app.core.config:Settings`、共享 `settings` 与 `.env.example` 中对应的环境变量；
- `AppException` 及统一 error envelope；
- `app.api.deps` 中部署级 API Key，以及按能力生成的数据库、Redis 和 Agent dependencies；
- PostgreSQL 分支的 route → service → repository → async database 分层；repository 执行 `flush()` / `refresh()`，session manager 统一 `commit()` / `rollback()`；
- API database engine 与 worker `NullPool` context 相互隔离；
- Redis、cache、rate limiting、Taskiq 和 Agent 的能力文档中明确列出的扩展 seam；
- 项目根的 tests、README、环境变量、安全、贡献、手工步骤和 how-to 文档。

未被生成文档承诺的内部模块、符号、helper 排布和源码文本可自由重构。

## HTTP 契约

- `GET /health`、`GET /health/live` 和 `GET /health/ready` 公开，不要求 API Key；readiness 只报告已启用资源。
- 所有业务 API 使用 `X-API-Key`，缺失和错误 key 返回统一错误 envelope，且不发送 Bearer challenge。
- 未处理异常返回统一 500 envelope，并保留 Request ID 和日志脱敏行为。
- Item 示例启用时提供 create、get、update 和 delete，不生成 list endpoint。
- Agent 启用时，`POST /agent/run` 返回单轮 JSON 结果，`POST /agent/stream` 返回 SSE content、tool、complete 和 error framing。
- 每次 Agent 请求只使用当前 input 和当前 dependencies；请求间不保留 conversation、历史消息或可变推理状态。
- 规范化 OpenAPI 是完整 HTTP 机器契约；测试可以保存窄范围 OpenAPI 快照，但快照不是产品规范来源。

## CLI 与运行行为

项目脚本名称为 `project_slug`，始终提供：

- `server run`：支持 `--host`、`--port` 和 `--reload`；
- `server routes`：列出已注册 HTTP method、path 和 route name。

PostgreSQL 启用时增加 `db init`、`db migrate`、`db upgrade`、`db downgrade`、`db current` 和 `db history`。Taskiq 启用时增加 `taskiq worker` 与 `taskiq scheduler`。

数据库、Redis 和 cache 资源由 API lifespan 显式初始化和关闭；Taskiq broker/result backend 由 worker process 独立拥有。真实集成必须能运行 migration、CRUD、commit/rollback、Redis 操作、rate limiting、worker/scheduler、Agent JSON/SSE 和资源 teardown。

## 部署、CI 与 guidance

- Docker 生成 multi-stage、non-root、healthcheck image，以及 base、development 和 production 三套 compose；资产位于 `deploy/`。
- 外部 Nginx 提供 TLS、HTTP→HTTPS、ACME、security headers、forwarded headers 和 timeout，并代理到外部可达 backend 地址；不作为 compose service。
- GitHub Actions 生成独立 lint/test jobs、coverage XML、非阻断 Codecov，以及按能力生成的 PostgreSQL、Redis 和 Docker 步骤。
- 生成文档、tests 和 omp guidance 必须准确反映所选能力，不得引用未生成的命令、路径、依赖或配置。

## 演进规则

公开契约变化必须在同一变更中更新本文和对应行为测试。breaking change 必须明确说明，并采用 clean cutover；兼容期只有在记录范围、期限和删除条件时才能引入。实现重构、测试重组和依赖升级只要保持本文定义的可观察行为，就不构成契约变化。
