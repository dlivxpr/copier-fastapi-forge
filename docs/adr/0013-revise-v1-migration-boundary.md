---
status: superseded by ADR-0015
---

# 修订 V1 迁移边界与批准差异

V1 继续保留既有产品大类，但撤销由 prior-art 思路产生的实现重设计。保留 API Key、可选 PostgreSQL（SQLAlchemy/SQLModel）、Taskiq、独立 Redis、Redis cache/rate limit、Pydantic AI、Logfire、Docker、外部 Nginx 和 GitHub Actions；继续删除 frontend、用户/JWT、teams、billing、email/newsletter/contact、Slack/Telegram、message ratings、文件存储、Webhooks、RAG、Kubernetes、Helm、Traefik 和替代队列/telemetry/provider SDK。除本 ADR 列出的批准差异外，各保留能力均按 ADR-0012 回到 legacy 对应实现。

本 ADR 取代 ADR-0004、ADR-0005、ADR-0006、ADR-0007、ADR-0009、ADR-0010 和 ADR-0011；其中 ADR-0007 的 OpenAI Chat Completions-compatible 模型接口被本 ADR 作为批准差异保留。ADR-0003 的 deployment API Key 和 ADR-0008 的单轮 Agent HTTP API 继续有效。

## 生成器与默认边界

- 保留 legacy 的 `project_name`、`project_slug`、`project_description`、`author_name`、`author_email`、`timezone`、`python_version`、`backend_port` 等问题、默认值和验证语义；派生 `use_*` 值改写为 Copier 条件，不作为重复问题。
- 保留能力的 legacy 开关及默认启用状态不变。默认继续启用 PostgreSQL、Pydantic AI、Logfire、CORS、Docker 和 GitHub Actions；Taskiq、独立 Redis、cache、rate limit 和 Item 示例沿用各自 legacy 默认。PostgreSQL 仍可选择 `none`，启用时仍在 SQLAlchemy 与 SQLModel 之间选择且默认 SQLAlchemy。
- 恢复独立 `enable_redis`；cache 和 Redis rate limit 通过 `when`/validator 表达依赖，Taskiq 使用独立 broker/result backend 配置，不因此把 RedisClient 注入 API process。
- 删除分页能力、开关、依赖、helper、schema 和初始化；可选 Item CRUD 也不生成 list endpoint。

## 运行时基线

- 可选 Item 示例恢复 legacy model、`0021_create_items` migration、repository、service、schema、route 和 tests；删除用户能力导致的 `owner_id`、user foreign key、身份参数和查询范围，migration 保留名称并改为初始 revision。删除 current 通用 Resource CRUD、固定抛错 Item route 和 `/hello`。
- 恢复 legacy `AppException` 职责、code/status、统一 envelope、未处理异常兜底和日志；删除已移除能力的异常类及 JWT `WWW-Authenticate: Bearer` 引用，不保留 current `DomainError`/handler `status_map`。
- 恢复 legacy `Settings` 字段、环境变量、默认值、validator、共享 `settings` 与 `.env.example`；恢复 database session/transaction、worker `NullPool` context、`RedisClient`、`slowapi`、Taskiq app、health contract、`create_app()`/lifespan、Request ID middleware，以及减去用户/JWT 模式后的 logging redaction。
- deployment API Key 保护所有保留业务 API，health probes 公开。CORS 恢复 legacy 开关和默认值。
- cache 和 rate limit 只保留 legacy 基础设施，删除 current cache demo 与 `/limited`；Taskiq 恢复 `ListQueueBroker`、独立 broker/result URL、scheduler 和 hooks，但不生成虚构的 echo task 或定时任务。
- 删除 legacy 中未接线且不属于 V1 能力的 API versioning 与 SecurityHeaders 工具。
- 保留减法后的应用 CLI：server commands 始终存在，database 与 Taskiq commands 按对应能力生成，用户及其他已删除能力命令不生成。

## 批准差异

- Agent 对外采用 ADR-0008 的 `POST /agent/run` JSON 与 `POST /agent/stream` SSE 单轮 contract，不迁移 `/ws/agent`、`AgentSession`、conversation 或跨请求历史。允许一个只负责 JSON/SSE 转换和失败封装的最小 `AgentInvocationService` transport adapter。
- Agent 上游采用 ADR-0007 的 `OpenAIChatModel` 与 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`；其余 Agent 类、依赖、prompt、错误和示例从 legacy 减去已删除工具与多轮状态。删除 current `configured_model` tool，保留清理后的 legacy Personality/Answering/Output prompt，并仅加入单轮约束。
- Logfire 仍执行 `logfire.configure()`，但只 instrument Pydantic AI；不 instrument FastAPI、SQLAlchemy/asyncpg、Redis、Taskiq 或 HTTPX。默认 `include_content=False` 且 `include_binary_content=False`。未启用 Pydantic AI 时不增加其他观测对象。
- Claude 专属资产不生成。保留根 `AGENTS.md`；将减法清理后的 legacy `.claude/rules`、skills 和 commands 分别转换为 `.omp/rules`、`.omp/skills` 和 `.omp/commands`。不生成 `.omp/AGENTS.md`、`.omp/RULES.md` 或 `.omp/config.yml`，因为 legacy command-pattern permission allowlist 没有纯配置的 omp 等价表达。

## 生成资产

- 普通文档与生成项目 tests 也执行减法迁移：保留 README、ENV_VARS、SECURITY、CONTRIBUTING、MANUAL_STEPS、`docs/` 及保留能力测试，逐节删除已移除能力并调整根目录路径。
- Docker 保留清理后的 legacy multi-stage/non-root/healthcheck Dockerfile，以及 base、dev、prod 三套 backend compose；仅删除已移除服务并迁到 `deploy/`。外部 Nginx 保留 backend TLS、HTTP→HTTPS、ACME、security headers、forwarded headers 和 timeout，删除 WebSocket/frontend/Flower，upstream 改为外部可达地址。
- GitHub Actions 保留 main/master push 与 pull_request 触发、独立 lint/test jobs、legacy Ruff 目标范围、coverage XML 与非阻断 Codecov、可选 Docker build；删除 pip-audit、Trivy、compileall 和 import-only smoke。已删除 frontend job，PostgreSQL/Redis services 与 Docker job按 Copier 条件生成。
