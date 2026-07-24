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