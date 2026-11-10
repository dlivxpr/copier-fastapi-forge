---
status: accepted
---

# 限流 Redis 存储独立于 API Redis client

`rate_limit_storage=redis` 原先把 `enable_redis=true` 作为硬前提，并用 `enable_docker` 上的运行期 validator 拒绝 `memory`。这两条约束都会在交互式 `copier copy` 中产生无法纠正的死路：Copier 只为 `input`、`password`、`path` 和 checkbox 挂 `validate` 回调，`select` 与 `confirm` 的答案给出后不会再被校验；唯一残留的校验点是下一题的默认值渲染，用户看到的报错落在与问题无关的 `enable_docker` 上，且没有“返回上一题”，只能整轮重来。

依赖本身也不成立。SlowAPI 通过 `Limiter(storage_uri=...)` 让 `limits` 库自建同步连接，生成的 `app/core/rate_limit.py` 只引用 `settings.REDIS_URL`，从不使用 API lifespan 拥有的 async `RedisClient`。真正缺的只是 `REDIS_*` 配置项和部署基础设施，二者与共享 client 无关。

因此：`rate_limit_storage=redis` 自行生成 `REDIS_*` 配置、`redis` 依赖、compose `redis` service、CI service 和必填凭据，不再要求 `enable_redis`；`enable_redis` 只表示“生成 API 进程共享 async client”。约束改为在 `rate_limit_storage` 的 choices 上用 Copier 原生 `{value, validator}` 扩展语法表达：启用 Docker 时 `memory` 选项被禁用并附带原因，默认值随 `enable_docker` 变为 `redis`。该 disablement 同时覆盖 `--data` 路径（`parse_answer` 抛 `Invalid choice`），是一条可解释的校验，而不再依赖事后 validator。

`enable_docker` 与 `reverse_proxy` 前移到 rate limiting 之前，使 `rate_limit_storage` 能引用 `enable_docker`。Docker 镜像固定 `--workers 2`，进程内计数会让配额成倍放大，这个约束保留，只是表达方式从拒绝组合变为禁用选项。

## 影响

- `enable_docker` 不再有 validator；非法组合在提问阶段即不可选。
- 生成边界新增一种组合：`enable_rate_limiting=true`、`rate_limit_storage=redis`、`enable_redis=false`。该组合生成 `REDIS_*`、`redis` 依赖与基础设施，但不生成 `app/clients/redis.py`、`Redis` dependency 和 readiness 的 Redis 检查。
- 交互流程不再存在无法纠正的拒绝，也不再出现与问题无关的默认值报错。
