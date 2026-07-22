# 后端服务模板生成

本上下文描述用于生成后端 API 项目的模板产品；算法与智能体只是同一后端服务可能承载的能力。

## Language

**减法迁移（Subtractive Migration）**：
以 `legacy/` 对应实现为规范性基线，仅减去 V1 删除能力及其引用，并叠加已封闭列举的必要迁移变换与批准差异；不包含借迁移进行的重构、重命名或重新设计。
_Avoid_：参考实现、prior art、重新实现、现代化改造

**V1 能力边界（V1 Capability Boundary）**：
V1 已确认的保留能力与删除能力集合；迁移实现不得以重新设计为由扩张或缩减该集合。
_Avoid_：候选能力、待定范围、迁移建议

**默认生成剖面（Default Generation Profile）**：
调用方不覆盖任何答案时生成的能力组合；保留能力的默认启用状态属于 legacy 行为，不因迁移到 Copier 而改变。
_Avoid_：lean default、推荐组合、新默认值

**保留能力开关（Retained Capability Toggle）**：
legacy 中用于启用或关闭某项 V1 保留能力的用户选择；迁移后继续表达同一选择，且默认值不变。
_Avoid_：冗余选项、固定能力、实现细节

**对应实现（Corresponding Implementation）**：
`legacy/` 中承载同一保留能力、公开 contract 或运行行为的具体文件、符号与测试，是目标文件进入 V1 的可追溯来源。
_Avoid_：灵感来源、相似示例、参考架构

**批准差异（Approved Deviation）**：
相对对应实现的显式例外，必须记录原因、最小影响范围和独立验收；未记录差异一律视为迁移回归。
_Avoid_：顺手优化、合理调整、等价重构

**迁移等价性（Migration Equivalence）**：
目标生成树在扣除已声明的路径、条件、删除引用、兼容修改与批准差异后，与 legacy 对应实现的内容和行为一致。
_Avoid_：大致一致、功能相似、测试能过

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
