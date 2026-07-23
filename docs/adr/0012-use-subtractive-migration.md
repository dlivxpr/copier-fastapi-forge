---
status: superseded by ADR-0015
---

# 以 legacy 对应实现执行减法迁移

Issue #1 的迁移不是以 `legacy/` 为 prior art 重新设计模板，而是减法迁移：`legacy/` 中承载同一保留能力、公开 contract 或运行行为的具体文件、符号与测试是规范性基线；目标实现只能减去 V1 删除能力及其引用，再叠加原生 Copier 语法与条件路径、backend 到项目根目录的迁移、失败证据支持的依赖兼容修改，以及已显式批准的差异。不得借迁移改变异常处理、API contract、schema、service/repository、配置、生命周期、命名或具体示例，也不得用“现代化”“简化”或测试通过替代来源等价性。

## 允许变换

允许变换采用封闭清单：

- Cookiecutter 变量和条件改写为 Copier 原生问题、Jinja 表达式与条件路径；关闭能力时相关文件、依赖、环境变量、部署资产和 guidance 完全不生成。
- 将 legacy 的 `backend/` 内容迁到生成项目根目录，并只修改由该路径变化直接导致的 import、命令、working directory、COPY、volume 和文档路径。
- 删除 V1 排除能力的文件、分支和引用；不得用新抽象替换被删除能力。
- 只有 legacy 约束实际出现 lock、安装、import、typecheck 或行为失败，或者当前官方文档明确删除旧 API 时，才允许最小依赖兼容修改；证据和修改必须进入迁移追溯表。
- 只有 ADR-0013 或后续明确 ADR 记录的批准差异可以偏离对应实现；没有 legacy 来源的新文件、符号、route、schema、helper 或示例默认不得进入 V1。

## 迁移追溯

每项保留能力必须建立逐行可审查的追溯表，至少记录 legacy source 文件/符号、Copier target、使用的允许变换、删除引用、批准差异和验证用例。任何归一化比较之外的新 diff 默认是迁移回归；即使行为测试通过，也必须先形成显式决策，不能直接更新 golden、归一化规则或验收预期。
