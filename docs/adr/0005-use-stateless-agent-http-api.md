# 智能体使用无状态 HTTP API

智能体能力使用部署级 API Key 保护的单轮无状态 HTTP API：`POST /agent/run` 返回完整 JSON 结果，`POST /agent/stream` 通过 SSE 流式返回增量与工具事件，不提供 WebSocket 或 query 参数鉴权。每次请求只包含当前输入，服务不接收消息历史、不拥有 conversation、不跨请求持久化推理状态；参数不足时在最终结果中说明，由调用方补齐后发起新请求。单模型配置下不提供模型列表接口。
