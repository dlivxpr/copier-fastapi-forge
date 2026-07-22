# Repository Guidelines

## Project Overview

本仓库提供唯一受支持的原生 Copier 模板，用于生成可组合的 FastAPI 后端服务。模板配置位于 `copier.yml`，模板树位于 `template/`；不再维护 Cookiecutter、自定义生成 CLI 或 legacy 生成器。

保留能力：API Key、可选 PostgreSQL（SQLAlchemy/SQLModel）、Taskiq、Redis cache/rate limit、Pydantic AI、Logfire、Docker、外部 Nginx 配置和 GitHub Actions。不要重新引入 frontend、用户/JWT、teams、billing、消息渠道、文件存储、Webhooks、RAG、Kubernetes、Helm、Traefik 或替代队列/telemetry/provider SDK。

## Architecture & Data Flow

Copier 直接读取 `copier.yml`，再以原生条件路径和 Jinja 条件渲染 `template/`。不使用 post-generation cleanup；关闭能力时，对应文件、依赖、环境变量、配置和 guidance 必须完全不生成。

生成应用始终包含薄 FastAPI route、统一异常 envelope、API Key dependency 和 async lifespan。仅启用 PostgreSQL 时生成 `route -> service -> repository -> async database` 分层；service 承载业务规则，repository 使用 `flush()/refresh()`，事务由 session manager 统一 `commit()/rollback()`。Redis、Taskiq 和数据库资源由 lifespan 或 worker process 显式初始化和关闭。Pydantic AI agent 不保存请求级可变状态，依赖由调用方构造并传入。

## Key Directories

| 路径 | 用途 |
|---|---|
| `copier.yml` | Copier 问题、默认值、choices、when 与 validator 的事实来源 |
| `template/` | 唯一生成项目模板；条件目录和文件名使用自定义 `[% ... %]` Jinja delimiters |
| `template/app/` | 生成 FastAPI runtime、可选能力与生命周期组合 |
| `template/tests/` | 生成项目的行为测试 |
| `template/AGENTS.md.jinja` | 根据所选能力生成的根级 agent guidance |
| `template/.omp/RULES.md.jinja` | 根据所选能力生成的 omp rules |
| `tests/test_template.py` | Copier public interface、生成树和实际 runtime 验收 |
| `scripts/lint_template.py` | 模板和条件路径的 Jinja 语法静态检查 |
| `.github/workflows/ci.yml` | 根模板质量检查与代表性生成矩阵 |
| `docs/adr/` | 已接受的产品和架构边界 |

## Development Commands

```bash
uv sync --all-groups
uv run python scripts/lint_template.py
uv run pytest tests/test_template.py -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

手工渲染默认项目：

```bash
uv run copier copy --defaults . <output-dir>
```

传入选项时使用 Copier 原生 `--data key=value` 或 `--data-file`。生成项目在其根目录执行：

```bash
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
uv run uvicorn app.main:app
```

## Code Conventions & Common Patterns

- Python 使用 4 空格、双引号、100 字符行宽；Ruff 负责格式与 import 排序，类型检查使用 `ty`。
- I/O、数据库、HTTP 和生命周期路径使用 `async`；测试使用 AnyIO、HTTPX `AsyncClient` + `ASGITransport`。
- 依赖通过 FastAPI DI 或显式参数传递；每个测试结束后清理 `app.dependency_overrides`，禁止模块级请求状态。
- 新增、修改或删除模板选项时，同步检查 `copier.yml`、条件路径、模板内容、依赖、环境变量、部署资产、guidance 和渲染测试。
- Jinja 模板不是普通 Python。不要对整个 `template/` 自动修复；先渲染代表性项目，再在生成结果中运行 Ruff、ty 和 pytest。
- 条件文件必须通过 Copier 原生路径条件消失，禁止恢复 cleanup hook、derived context 或兼容 alias。
- Logfire 默认关闭；启用时先 `logfire.configure()`，再按实际能力 instrument FastAPI、SQLAlchemy engine、Redis、Taskiq 和 Pydantic AI，且默认不采集模型内容。
- Docker 产物统一位于生成项目的 `deploy/`；Nginx 仅生成外部配置，不加入 compose service。

## Testing & QA

公共测试 seam 是 Copier 渲染接口和生成项目公开开发/runtime 接口。测试应验证生成树、依赖、配置、HTTP 行为、后台任务和真实数据库/Redis 交互，不断言无意义的模板源码细节。

修改时先运行最窄的相关测试和 `uv run ty check`。涉及模板条件时必须运行 `uv run python scripts/lint_template.py`，并至少渲染一个受影响配置。交付前运行完整 `uv run pytest`、Ruff check、Ruff format check 和 ty。需要 PostgreSQL/Redis 的验收使用 Docker 随机映射端口，结束后必须清理容器。

不要提交生成项目、虚拟环境、缓存、coverage 产物、`.env`、凭据或本地数据库。

## Agent skills

### Issue tracker

本仓库使用 GitHub Issues 跟踪 issue 和 PRD。详见 `docs/agents/issue-tracker.md`。

### Triage labels

本仓库使用五个默认 canonical triage 标签。详见 `docs/agents/triage-labels.md`。

### Domain docs

本仓库使用 single-context domain docs 布局。详见 `docs/agents/domain.md`。
