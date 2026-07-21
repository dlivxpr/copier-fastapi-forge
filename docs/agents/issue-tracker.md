# Issue tracker：GitHub

本仓库的 issue 和 PRD 存放在 GitHub Issues 中。所有操作使用 `gh` CLI。

## 约定

- **创建 issue**：`gh issue create --title "..." --body "..."`。多行正文使用 heredoc。
- **读取 issue**：`gh issue view <number> --comments`，使用 `jq` 过滤评论，并同时获取 labels。
- **列出 issues**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，按需添加 `--label` 和 `--state` 过滤条件。
- **评论 issue**：`gh issue comment <number> --body "..."`
- **添加/移除 labels**：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **关闭 issue**：`gh issue close <number> --comment "..."`

仓库从 `git remote -v` 推断；在 clone 内运行时，`gh` 会自动处理。

## 将 pull request 作为 triage 入口

**PRs as a request surface: no.**（如果本仓库将外部 PR 视为 feature request，可改为 `yes`；`/triage` 会读取此标志。）

设置为 `yes` 后，PR 使用与 issue 相同的 labels 和状态，并改用对应的 `gh pr` 命令：

- **读取 PR**：`gh pr view <number> --comments`；使用 `gh pr diff <number>` 读取 diff。
- **列出待 triage 的外部 PR**：`gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`，仅保留 `authorAssociation` 为 `CONTRIBUTOR`、`FIRST_TIME_CONTRIBUTOR` 或 `NONE` 的记录，排除 `OWNER`、`MEMBER` 和 `COLLABORATOR`。
- **评论/标记/关闭**：`gh pr comment`、`gh pr edit --add-label` / `--remove-label`、`gh pr close`。

GitHub 的 issue 和 PR 共用编号空间，因此裸编号 `#42` 可能指任意一种对象；先运行 `gh pr view 42`，失败后再运行 `gh issue view 42`。

## 当 skill 要求“publish to the issue tracker”

创建一个 GitHub issue。

## 当 skill 要求“fetch the relevant ticket”

运行 `gh issue view <number> --comments`。

## Wayfinding 操作

供 `/wayfinder` 使用。**Map** 是一个 issue，**child** issues 是其 tickets。

- **Map**：单个带 `wayfinder:map` label 的 issue，正文包含 Notes / Decisions-so-far / Fog。使用 `gh issue create --label wayfinder:map` 创建。
- **Child ticket**：以 GitHub sub-issue 关联到 map（通过 `gh api` 调用 sub-issues endpoint）。若 sub-issues 不可用，则把 child 加入 map 正文的 task list，并在 child 正文顶部写入 `Part of #<map>`。Labels 使用 `wayfinder:<type>`，其中 type 为 `research`、`prototype`、`grilling` 或 `task`。ticket 被 claim 后，分配给当前开发者。
- **Blocking**：优先使用 GitHub 原生 issue dependencies。通过 `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>` 添加依赖，其中 `<blocker-db-id>` 是 blocker 的数字 database id（通过 `gh api repos/<owner>/<repo>/issues/<n> --jq .id` 获取），不是 `#number` 或 `node_id`。GitHub 的 `issue_dependencies_summary.blocked_by` 表示 open blockers 数量。若 dependencies 不可用，则在 child 正文顶部使用 `Blocked by: #<n>, #<n>`。所有 blocker 关闭后，ticket 才解除阻塞。
- **Frontier query**：列出 map 的 open children，排除存在 open blocker 或已有 assignee 的项；按 map 中的顺序选择第一项。
- **Claim**：`gh issue edit <n> --add-assignee @me`；这是 session 的首次写操作。
- **Resolve**：运行 `gh issue comment <n> --body "<answer>"`，再运行 `gh issue close <n>`，最后把 context pointer（gist + link）追加到 map 的 Decisions-so-far。
