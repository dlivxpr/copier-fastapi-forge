# 根 AGENTS.md 配合 OMP rules

生成项目将原 `CLAUDE.md` 的有效内容合并到根 `AGENTS.md`，删除 `CLAUDE.md`，并把 `.claude/rules/*` 迁移为 `.omp/rules/*`。根 `AGENTS.md` 由 OMP 的 `agents-md` provider 发现，`.omp/rules/*` 由 native rule provider 加载；虽然 `.omp/AGENTS.md` 具有更高发现优先级，但选择根文件可让项目主上下文继续被其他支持 `AGENTS.md` 的编码智能体共享。
