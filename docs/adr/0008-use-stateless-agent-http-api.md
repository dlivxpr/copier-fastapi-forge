# 智能体使用无状态 HTTP API

删除面向旧前端聊天的 WebSocket、connection manager、AgentSession、`ask_user` 暂停/恢复工具和 query 参数鉴权，智能体能力改为部署级 API Key 保护的单轮无状态 HTTP API：普通 JSON 端点返回完整结果，SSE 端点流式返回增量与工具事件。每次请求只包含当前输入，服务不接收消息历史、不拥有 conversation、不跨请求持久化推理状态；参数不足时在最终结果中说明，由调用方补齐后发起新请求。单模型配置下不提供模型列表接口。
