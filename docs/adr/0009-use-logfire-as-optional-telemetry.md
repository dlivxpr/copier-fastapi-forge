---
status: superseded by ADR-0013
---

# Logfire 是唯一可选遥测方案

删除 LangSmith、Sentry 与独立 Prometheus instrumentation，仅保留 Logfire，且默认关闭以避免生成项目在未明确选择时外发请求、prompt、模型输出或工具数据。启用后按已选择的 FastAPI、PostgreSQL、Redis 与 Pydantic AI 能力安装并注册对应 instrumentation，保证先 `logfire.configure()` 再调用 `instrument_*()`；模型内容采集仍需具体项目显式决定。
