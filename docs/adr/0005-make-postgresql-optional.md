---
status: superseded by ADR-0013
---

# 将 PostgreSQL 作为可选持久化能力

数据库选项保留为 `none | postgresql`，默认 `none`；无数据库项目不生成 ORM、Alembic、repository、数据库 session、数据库健康检查或 PostgreSQL 容器，选择 PostgreSQL 时才生成完整异步持久化分层。删除用户身份体系后，API Key、智能体能力和后台任务均不要求数据库，因此默认无状态运行可减少不必要的基础设施。
