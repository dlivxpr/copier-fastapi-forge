# Repository Guidelines

## Project Overview

本仓库用于把 `legacy/` 中导入的全栈 AI 项目生成器精简为面向后端服务的模板生成器。当前根项目仍是 Python 3.14 + uv 的最小骨架；完整实现位于 `legacy/`，且实际使用 **Cookiecutter**，不是 Copier。不要把 `legacy/README.md` 或 `legacy/AGENTS.md` 描述的全部旧功能当作目标需求；删除功能时同步收紧配置、模板、钩子和测试。

## Architecture & Data Flow

生成链路：

1. `legacy/fastapi_gen/cli.py` 的 Click CLI 收集命令行/交互输入。
2. `legacy/fastapi_gen/config.py` 的 Pydantic `ProjectConfig` 校验组合约束，并由 `to_cookiecutter_context()` 显式展开模板开关。
3. `legacy/fastapi_gen/generator.py` 调用 Cookiecutter，将上下文渲染到输出目录；已存在且非空的目标目录会被拒绝，失败时清理部分输出。
4. `legacy/template/hooks/post_gen_project.py` 根据开关删除未选文件和目录。功能精简必须同时移除变量、校验、模板分支和清理逻辑，不能只隐藏 CLI 选项。
5. 生成后端采用 `API route -> service -> repository -> async database` 分层。路由保持薄；service 承载业务规则并抛出 domain exception；repository 使用 `flush()/refresh()`，事务边界由 session 管理器统一 `commit()/rollback()`。

生成应用通过 `app/api/deps.py` 使用 FastAPI `Annotated` + `Depends` 注入 session、缓存、用户和 service；`app/main.py` 的 async lifespan 初始化并关闭共享资源。异常由 `app/core/exceptions.py` 定义、`app/api/exception_handlers.py` 统一映射为 `{ "error": { "code", "message", "details" } }`。保留 AI agent 时，依赖由调用方构造并传入，避免在 agent 内保存请求级可变状态。

## Key Directories

| 路径 | 用途 |
|---|---|
| `legacy/fastapi_gen/` | 来源生成器：CLI、配置模型、交互提示与生成调用 |
| `legacy/template/` | Cookiecutter 变量、生成后项目树及 post-generation hook |
| `legacy/template/{{cookiecutter.project_slug}}/backend/` | 目标 FastAPI 后端模板；精简工作的主要落点 |
| `legacy/tests/` | 生成器单元测试、配置守护和真实项目生成集成测试 |
| `legacy/scripts/` | 模板静态架构检查脚本 |
| `legacy/docs/` | 上游行为说明；可能随精简失效，不能作为唯一事实来源 |
| `main.py`、`pyproject.toml` | 当前根骨架；尚未承载生成器实现或测试体系 |

## Development Commands

根骨架：

```bash
uv sync
uv run python main.py
```

来源生成器（先进入 `legacy/`，避免混用两套 `pyproject.toml`）：

```bash
cd legacy
uv sync --extra dev
uv run fastapi-fullstack --help
uv run fastapi-fullstack create demo --minimal -o <output-dir>
uv run pytest tests/test_config.py -q       # 优先运行受影响的窄测试
uv run pytest -m "not slow"                 # 排除生成项目的慢检查
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run python scripts/lint_template.py
```

生成项目后，在项目根可用 `make lint`、`make test`、`make test-cov`；等价后端命令以 `uv run --directory backend ...` 执行。Windows 的 Makefile 需要 GNU Make、WSL2 或 Git Bash。

## Code Conventions & Common Patterns

- Python 使用 4 空格、双引号、100 字符行宽；Ruff 负责格式与 import 排序，类型检查使用 `ty`，不要沿用旧指南中的 `mypy` 命令。
- 名称遵循 `snake_case`（模块、函数、变量）、`PascalCase`（类、Pydantic model、enum）；测试文件和函数使用 `test_*.py` / `test_*`。
- I/O、数据库、HTTP 和生命周期路径使用 `async`；测试用 AnyIO 的 asyncio backend、HTTPX `AsyncClient` + `ASGITransport`。
- 依赖通过 FastAPI DI 或显式参数传递。每个测试结束后清理 `app.dependency_overrides`；不要引入模块级请求状态。
- 新增或保留一个模板选项时，按同一条链检查 `config.py`、`prompts.py`、`cookiecutter.json`、模板条件、post-gen hook 和测试。删除选项也必须完成同样的反向清理。
- Jinja 文件不是普通 Python/TypeScript：不要对整个 `legacy/template/` 直接运行自动修复。用 `scripts/lint_template.py` 检查 Jinja 平衡、事务边界、内联 import 和直接 `fetch` 等模板规则。
- 精准精简：不要保留失去调用方的兼容别名、空开关或死模板分支；不要顺手重构仍被保留的相邻功能。

## Important Files

| 文件 | 关注点 |
|---|---|
| `pyproject.toml` | 根项目名、Python 3.14 与 uv 骨架状态 |
| `legacy/pyproject.toml` | 来源 CLI entry point、依赖、Hatchling、Ruff、ty、pytest、coverage |
| `legacy/fastapi_gen/cli.py` | `fastapi-fullstack` 命令入口 |
| `legacy/fastapi_gen/config.py` | 功能枚举、组合约束、派生开关和模板上下文 |
| `legacy/fastapi_gen/generator.py` | 模板定位、输出目录保护和 Cookiecutter 调用 |
| `legacy/template/cookiecutter.json` | 模板变量及默认值的事实来源 |
| `legacy/template/hooks/post_gen_project.py` | 条件功能的文件/目录清理 |
| `legacy/template/{{cookiecutter.project_slug}}/backend/app/main.py` | 生成后 FastAPI app 与 lifespan 入口 |
| `legacy/template/{{cookiecutter.project_slug}}/backend/app/api/deps.py` | 生成后依赖注入组合点 |
| `legacy/.github/workflows/ci.yml` | 来源生成器与生成项目的 CI 场景 |

## Runtime/Tooling Preferences

- 根项目：Python `>=3.14`，版本由 `.python-version` 固定；包管理和命令执行统一使用 uv。
- `legacy/`：Python `>=3.11`，CI 测试 3.11–3.13；它有独立 `uv.lock`，必须在其项目上下文安装和运行。
- 构建后端为 Hatchling；生成器依赖 Cookiecutter。除非迁移方案明确完成，不要编写或声称存在 Copier 配置。
- 生成后端使用 uv；仅在保留可选前端时使用 Bun。不要用 npm/yarn/pnpm 替代模板既有 Bun 命令。
- 不提交生成项目、虚拟环境、缓存、coverage 产物、`.env` 或凭据。

## Testing & QA

根项目当前没有 `tests/`、pytest 配置或测试依赖。`legacy/` 使用 pytest：

- `tests/test_config.py`、`test_cli.py`、`test_generator.py` 覆盖配置、CLI 和生成调用。
- `tests/test_integration.py`、`test_template_integration.py` 等生成真实临时项目并验证结构、导入和质量命令；慢场景标记 `slow`。
- `tests/test_context_files.py`、`test_template_docs.py` 守护生成上下文和模板变量文档的一致性。
- 生成后端自带独立测试，使用 AnyIO、FastAPI dependency overrides 和 HTTPX ASGI transport；其 coverage 配置要求 `fail_under = 100`。

修改生成器时先运行最窄的相关测试，再运行 `uv run pytest -m "not slow"`；涉及模板结构、条件变量或 hook 时，必须额外生成至少一个受影响配置并执行 `scripts/lint_template.py`。交付前运行 Ruff check、format check、`ty check`；只有影响完整生成矩阵时才运行包含 `slow` 的全套测试。测试应验证可观察的生成结果和运行行为，不要断言无意义的源码文本细节。
