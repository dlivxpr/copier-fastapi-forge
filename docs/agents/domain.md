# Domain docs

本文件规定 engineering skills 在探索代码库时如何读取本仓库的 domain documentation。

## 探索前读取

- 根目录的 `CONTEXT.md`；或
- 如果根目录存在 `CONTEXT-MAP.md`，读取它指向的、与当前主题相关的各个 `CONTEXT.md`；
- `docs/adr/` 中涉及当前工作区域的 ADR。multi-context 仓库还需检查 `src/<context>/docs/adr/` 中的 context-scoped decisions。

如果这些文件不存在，静默继续，不要报告缺失，也不要建议预先创建。`/domain-modeling` skill（可由 `/grill-with-docs` 和 `/improve-codebase-architecture` 触发）会在术语或决策真正明确时按需创建。

## 文件结构

本仓库采用 single-context 布局：

```text
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

## 使用 glossary 的 vocabulary

当输出需要命名 domain concept（如 issue title、refactor proposal、hypothesis 或 test name）时，使用 `CONTEXT.md` 定义的术语，不要改用 glossary 明确排除的同义词。

如果 glossary 尚未定义所需 concept，说明当前可能在引入项目未使用的语言，或存在真实缺口；应重新考虑，并在必要时记录给 `/domain-modeling`。

## 标明 ADR 冲突

如果输出与现有 ADR 冲突，必须明确指出，而不是静默覆盖：

> 与 ADR-0007（event-sourced orders）冲突，但值得重新讨论，因为……
