---
status: superseded by ADR-0015
---

# 以迁移等价性逐项验收 V1

V1 验收必须同时证明来源、生成边界、实现等价和运行行为，不能用少数 current smoke tests 代替。每项保留能力先建立 ADR-0012 要求的追溯表，再执行逐能力关闭/开启渲染、pairwise 组合和高风险命名配置；受保护文件在应用已声明的路径、条件、删除引用、兼容修改和批准差异归一化后，必须与 legacy render 等价。

## 结构与 contract

- 每个保留开关至少渲染 disabled/enabled 两个项目：关闭时对应文件、依赖、环境变量、部署资产、tests、docs 和 omp guidance 全部不存在；开启时只能出现追溯表列出的 target。删除能力的文件和术语不得回流。
- 精确验证 `copier.yml` 的问题、choices、默认值、`when` 和 validator，以及生成 `Settings` 的字段、类型、默认值、validator、环境变量名和 `.env.example`。
- 每个保留 HTTP endpoint 验证 method/path、API Key 边界、query/body schema、status、headers、成功与失败 envelope，并对归一化 OpenAPI 生成物做 snapshot。批准的 Agent JSON/SSE、删除 Item list、删除 demo routes 和 deployment API Key 替换单独列明。
- docs 与 omp assets 做结构和内容校验：Markdown/frontmatter、rule globs、skill name/description、command 参数、命令与路径引用必须有效；不依赖联网启动 omp，也不生成 `.claude`、`.omp/config.yml`、`.omp/AGENTS.md` 或 `.omp/RULES.md`。

## 真实集成

- SQLAlchemy 与 SQLModel 两个分支都使用随机映射端口的真实 PostgreSQL，运行 Alembic，并验证 Item create/get/update/delete、`flush/refresh`、成功 commit、异常 rollback 和 worker context 隔离。
- RedisClient、FastAPICache、slowapi memory/Redis 配置和 Taskiq broker/result backend/scheduler 使用真实 Redis，验证初始化、操作、连接和资源关闭；不为测试向生成项目加入 demo route 或业务 task。
- Agent 测试启动本地 OpenAI Chat Completions-compatible fake server，通过真实 `OpenAIChatModel` 验证 `/agent/run`、`/agent/stream`、API Key、validation/error、SSE 和请求间无历史串联；同时验证 Logfire instrumentation 默认不采集模型或 binary content。
- 三套 compose 均执行 `docker compose config`；Dockerfile 实际 build、启动并请求 legacy health contract；外部 Nginx 在容器中执行 `nginx -t`；GitHub Actions workflow 做 YAML、表达式、路径和条件静态校验。

## 组合策略与放行规则

组合采用“逐能力正反 + pairwise + 高风险命名配置”，至少深测 minimal、legacy-default、all-retained(SQLAlchemy)、all-retained(SQLModel)、Agent+Logfire，以及 Redis/cache/rate-limit/Taskiq 组合；不以全笛卡尔积替代真实集成。PostgreSQL、Redis 和 Nginx/Docker 资源使用随机端口并在验收后清理。

任何非白名单 diff 都先视为迁移回归。即使现有行为测试通过，也必须先记录新的批准差异、影响与独立验收，才能修改 golden、归一化规则、追溯表或预期结果。
