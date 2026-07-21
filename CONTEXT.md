# 后端服务模板生成

本上下文描述用于生成后端 API 项目的模板产品；算法与智能体只是同一后端服务可能承载的能力。

## Language

**后端服务（Backend Service）**：
通过 API 对外提供算法、智能体或其他业务能力的统一服务类型。
_Avoid_：算法服务、智能体服务、服务形态

**智能体能力（Agent Capability）**：
后端服务可按需启用的智能体开发能力，以 Pydantic AI 为唯一智能体框架。
_Avoid_：智能体服务、AI 服务、框架选择


**部署级 API Key（Deployment API Key）**：
由一次服务部署的全部调用方共享、用于访问受保护 API 的单一密钥，不代表用户或客户端身份。
_Avoid_：用户 API Key、客户端凭据、访问令牌

**后台任务能力（Background Task Capability）**：
后端服务可按需启用的分布式异步任务能力；未启用时不生成独立 worker 或 scheduler。
_Avoid_：Taskiq 服务、任务服务

**持久化能力（Persistence Capability）**：
后端服务可按需启用的关系型数据持久化能力；未启用时，服务保持无数据库运行边界。
_Avoid_：数据库服务、数据服务

**模型接口（Model Interface）**：
智能体能力连接模型时采用的 OpenAI Chat Completions 兼容接口，由基础 URL、API Key 和模型名共同标识。
_Avoid_：OpenAI 供应商、LLM 供应商选择、多模型路由

**单轮智能体调用（Single-turn Agent Invocation）**：
一次仅携带当前输入的独立 HTTP 请求；服务不接收历史消息，不拥有 conversation，也不跨请求保存推理状态。
_Avoid_：多轮对话、聊天会话、Agent session、消息历史
