# 后端代码位于生成项目根目录

后端代码与项目配置直接位于生成项目根目录，不设置额外的 `backend/` 层级。该布局以单一后端服务为边界，使本地开发、测试、容器构建和编辑器配置不再需要额外指定 `backend/` 路径；若未来需要多个可独立部署的服务，应重新评估项目边界，而不是预留空泛的多服务结构。Docker 保持 Copier 可选且默认启用，启用时将 Dockerfile、Dockerfile-specific ignore、Compose 和反向代理配置统一生成到 `deploy/`，禁用时不留下 Docker 命令或空目录。
