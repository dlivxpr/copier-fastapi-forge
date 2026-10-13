# Copier FastAPI Forge

使用 [Copier](https://copier.readthedocs.io/) 从 GitHub 直接生成可组合的 FastAPI 后端项目。按需选择数据库、Redis、后台任务、AI Agent、可观测性和部署能力；未启用的能力不会出现在生成结果中。

## 生成的项目包含什么

- FastAPI、异步 lifespan、统一异常响应、健康检查和 API Key 鉴权
- 可选 PostgreSQL，以及 SQLAlchemy / SQLModel 二选一
- 可选 Redis client、缓存和内存或 Redis rate limiting
- 可选 Taskiq worker 与 scheduler
- 可选 Pydantic AI Agent 和 Logfire
- 可选 Docker、外部 Nginx 配置和 GitHub Actions
- 与所选能力匹配的测试、配置、开发文档和 AI coding guidance

## 前置条件

- [uv](https://docs.astral.sh/uv/)
- Git 2.27 或更高版本

生成的项目可选择 Python 3.12、3.13 或 3.14，默认使用 Python 3.12。无需克隆本仓库，也无需全局安装 Copier。

## 快速开始

直接从 GitHub 交互式生成项目：

```bash
uvx copier copy gh:dlivxpr/copier-fastapi-forge.git my_service
```

Copier 会询问项目名称、Python 版本和需要启用的能力，并将结果写入 `my_service/`。

如需跳过问答并使用全部默认选项：

```bash
uvx copier copy --defaults gh:dlivxpr/copier-fastapi-forge.git my_service
```

也可以通过 `--data` 预设部分或全部选项：

```bash
uvx copier copy \
  --data project_name=my_service \
  --data python_version=3.13 \
  --data database=postgresql \
  --data orm_type=sqlalchemy \
  gh:dlivxpr/copier-fastapi-forge.git my_service
```

## 常用选项

| 选项 | 可选值 | 默认值 |
|---|---|---|
| `python_version` | `3.12`、`3.13`、`3.14` | `3.12` |
| `database` | `postgresql`、`none` | `postgresql` |
| `orm_type` | `sqlalchemy`、`sqlmodel` | `sqlalchemy` |
| `include_example_crud` | `true`、`false` | `false` |
| `background_tasks` | `taskiq`、`none` | `none` |
| `enable_redis` | `true`、`false` | `false` |
| `enable_caching` | `true`、`false` | `false` |
| `enable_rate_limiting` | `true`、`false` | `false` |
| `ai_framework` | `pydantic_ai`、`none` | `pydantic_ai` |
| `enable_logfire` | `true`、`false` | `true` |
| `enable_docker` | `true`、`false` | `true` |
| `reverse_proxy` | `nginx_external`、`none` | `nginx_external` |
| `ci_type` | `github`、`none` | `github` |

部分选项会根据前置选择出现。例如，`orm_type` 仅在启用 PostgreSQL 时可选，Redis cache 要求同时启用 `enable_redis`。所有输入、默认值和组合约束见 [`docs/product-contract.md`](docs/product-contract.md)。

## 运行生成的项目

进入生成目录并安装依赖：

```bash
cd my_service
uv sync --all-groups
cp .env.example .env
```

Windows PowerShell 使用：

```powershell
Copy-Item .env.example .env
```

检查 `.env`，替换 API Key、数据库密码和外部服务凭据等开发占位值，然后启动服务：

```bash
uv run my_service server run
```

默认地址：

- API 文档：<http://localhost:8000/docs>
- 健康状态：<http://localhost:8000/health>
- 存活探针：<http://localhost:8000/health/live>
- 就绪探针：<http://localhost:8000/health/ready>

除健康探针外，业务 API 默认使用 `X-API-Key` 请求头。

## 使用 Docker

启用 Docker 时，可从项目根目录启动默认编排：

```bash
docker compose -f deploy/compose.yaml up --build
```

生成项目还包含开发和生产编排：

- `deploy/compose.dev.yaml`
- `deploy/compose.prod.yaml`

## 下一步

每个生成项目都会提供与已选能力匹配的使用说明：

- `README.md`：本地运行、数据库、Redis、Taskiq、Agent 和 Docker 指南
- `ENV_VARS.md`：环境变量
- `SECURITY.md`：安全与凭据配置
- `MANUAL_STEPS.md`：生成后需要完成的手工步骤
- `docs/`：架构、测试、命令和扩展方式

当前版本支持从模板创建新项目，不承诺通过 `copier update` 升级既有项目。

## 维护模板

根仓库使用 Python 3.14。完整验收需要运行中的 Docker Engine 和 Docker Compose；测试会创建随机端口的 PostgreSQL、Redis、应用与 Nginx 容器，并在结束时清理。临时 TLS 证书由应用验收镜像内的 OpenSSL 生成，不要求宿主机安装 OpenSSL。

```bash
uv sync --locked --all-groups
uv run python scripts/lint_template.py
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest --durations=20
```

定位问题时可按测试文件或测试名称缩小范围，例如：

```bash
uv run pytest tests/test_core_runtime_contract.py --durations=5
uv run pytest tests/test_profile_contract.py --durations=10
```

生成项目在各自的 `uv` 环境中验收，不能导入根仓库的 Python 进程。局部测试用于缩短反馈循环，不替代完整验收；CI 也必须覆盖全部契约测试。

测试会在每次 pytest 会话开始时复制当前 `copier.yml` 和 `template/`，包括未提交的模板改动。契约测试使用 Copier 的本地目录模式，避免逐文件 Git 查询；独立的原生 CLI 验收保留真实 Git 源复制、`--defaults`、`--data-file` 和 `--data` 覆盖行为。修改模板后须重新启动 pytest 会话。

生成项目之间不共享 `.venv`。用例结束后并发清理各自的环境，pytest 退出前等待清理完成并报告错误；Windows 清理使用扩展路径以支持超过 `MAX_PATH` 的依赖文件。生成源码仍保留在 pytest 临时目录中，便于排查失败。

本地 pytest 默认使用两个 worker，并将同一文件的用例放在同一 worker；数据库和 Redis 容器按 worker 隔离。调试时用 `uv run pytest -n 0` 恢复串行运行。CI 已按测试域分片，每个分片使用 `-n 0`，避免重复叠加并发。

根 CI 独立执行质量检查，并按 generator、runtime、services 三个互不重叠的测试域并行验收。缓存覆盖根依赖锁、模板依赖声明和 Python 安装；同一分支的新运行会取消过期运行。