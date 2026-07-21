# Pydantic AI 仅连接 OpenAI-compatible Chat API

智能体能力保持可选且默认关闭，启用时只生成 Pydantic AI，不提供其他智能体框架或模型供应商选择。模型统一通过 `LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL` 配置，并由 `OpenAIChatModel` 连接 OpenAI Chat Completions wire format；删除供应商专属 SDK、环境变量、运行时模型前缀推断、`all` 多供应商模式和 Responses API 分支，以适配第三方网关并保持单一模型接口。模板不内置外部网络、前端图表协议、模型生成代码执行、运行时 Agent Skills、Deep Research、Subagents 或 Agent Todo，因此删除相关工具、依赖、配置、持久化和前端事件协议；供开发智能体使用的 OMP 项目上下文不属于运行时 Agent Skills。
