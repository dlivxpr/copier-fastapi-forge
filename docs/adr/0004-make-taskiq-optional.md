---
status: superseded by ADR-0013
---

# 将 Taskiq 作为唯一可选任务队列

后台任务选项收敛为 `none | taskiq`，默认 `none`；选择 Taskiq 时自动启用 Redis，并生成 broker、result backend、worker、scheduler 和可运行示例，未选择时不保留分布式任务脚手架。Redis 同时保留为可独立启用的集成，但依赖关系仅为 Taskiq 必须启用 Redis，不能反向推导为启用 Redis 就生成 Taskiq。删除 Celery、Prefect 与 ARQ 的全部配置和实现，以降低依赖与生成矩阵，同时避免不需要异步任务的服务承担额外基础设施。
