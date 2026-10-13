---
status: accepted
---

# Pydantic AI 仅连接 OpenAI-compatible Chat API

智能体能力仅使用 Pydantic AI，模型统一通过 `LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL` 配置，并由 `OpenAIChatModel` 连接 OpenAI Chat Completions-compatible 接口。选择这一协议可适配第三方网关，同时保持单一模型接口，避免为各供应商维护独立集成。模板不提供供应商专属集成、运行时模型前缀推断、多供应商模式或 Responses API 分支。
