---
status: accepted
---

# Taskiq 改用 Redis Streams

未来生成项目的后台任务能力使用 `RedisStreamBroker`，以获得 worker 在确认任务前失联时的 pending task 接管能力。此次变更是 clean cutover：不迁移既有 Redis List backlog，不提供 List/Stream 双读，也不承诺 `copier update` 兼容。

投递语义定义为容量边界内 at-least-once，而不是 exactly-once。Stream 使用项目级可配置名称、固定 consumer group、`consumer_id="0-0"`、默认 `maxlen=100_000` 的近似裁剪，以及默认一小时的可配置 pending idle timeout；任务必须幂等。有限裁剪可能删除超出配置容量的未确认任务，因此部署方必须按峰值入队速率与最长故障恢复窗口设置容量并监控积压。

`taskiq-redis` 的基础 `RedisStreamBroker` 只会在读取到新消息后扫描 pending entries，空闲队列无法仅凭 idle timeout 恢复任务。生成项目因此使用其子类在每次 blocking read 后主动执行 pending 扫描，保证恢复不依赖后续新流量。

本决策只覆盖 worker loss 的 transport-level recovery。任务函数异常的自动重试、退避、dead-letter queue、旧 backlog 迁移和无限积压持久性均不属于此次契约。
