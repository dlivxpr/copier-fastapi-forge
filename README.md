# Copier FastAPI Forge

用于生成可组合 FastAPI 后端服务的原生 Copier 模板。公开 questions、能力生成边界和生成项目行为见 [`docs/product-contract.md`](docs/product-contract.md)。

```bash
uv sync --all-groups
uv run copier copy --defaults . <output-dir>
```

模板维护者使用以下命令执行完整质量检查：

```bash
uv run python scripts/lint_template.py
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```