# 后端服务模板生成

本上下文描述用于生成后端 API 项目的模板产品；算法与智能体只是同一后端服务可能承载的能力。

## Language

**原生演进基线（Native Evolution Baseline）**：
以 Copier 公开问题与生成边界、生成项目公开 API 和运行行为共同定义的产品契约；模板实现、历史迁移来源和输出快照都不是规范。
_Avoid_：历史实现基线、内容等价门禁、当前测试即规范

**公开产品契约（Public Product Contract）**：
调用方可观察并依赖的 Copier 输入与生成边界，以及生成项目的开发接口、HTTP API 和运行行为。
_Avoid_：实现细节、文件内容快照、历史实现 contract

**契约保持切换（Contract-preserving Cutover）**：
在不改变现有公开产品契约的前提下，将规范来源和验收架构一次性切换到原生演进基线；产品行为变更必须另行决策。
_Avoid_：顺带重设计、迁移即改版、自由清理

**文档化开发接口（Documented Development Interface）**：
生成项目文档明确承诺的文件、命令、环境变量、import 和扩展 seam；未文档化内部模块、符号及源码文本不属于兼容面。
_Avoid_：全部生成实现、偶然可导入符号、源码快照

**迁移兼容垫片（Migration Compatibility Shim）**：
仅为复现迁移前实现或绕过迁移期依赖差异而存在的版本限制、workaround 或兼容分支；不包括公开产品契约或模型接口的协议兼容性。
_Avoid_：所有 compatibility、公开兼容承诺、Chat Completions-compatible

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

**容量边界内至少一次投递（Capacity-bounded At-least-once Delivery）**：
在配置的积压容量与故障恢复窗口内，未确认任务可在执行者失联后重新交付；同一任务可能执行多次，任务实现必须幂等。超过容量边界时不承诺恢复。
_Avoid_：恰好一次投递、无限积压持久性、业务异常自动重试

**持久化能力（Persistence Capability）**：
后端服务可按需启用的关系型数据持久化能力；未启用时，服务保持无数据库运行边界。
_Avoid_：数据库服务、数据服务

**模型接口（Model Interface）**：
智能体能力连接模型时采用的 OpenAI Chat Completions 兼容接口，由基础 URL、API Key 和模型名共同标识。
_Avoid_：OpenAI 供应商、LLM 供应商选择、多模型路由

**单轮智能体调用（Single-turn Agent Invocation）**：
一次仅携带当前输入的独立 HTTP 请求；服务不接收历史消息，不拥有 conversation，也不跨请求保存推理状态。
_Avoid_：多轮对话、聊天会话、Agent session、消息历史
