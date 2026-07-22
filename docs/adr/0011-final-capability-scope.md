---
status: superseded by ADR-0013
---

# 最终能力矩阵边界

以下选项在需求访谈最后一批确认：

- **Admin Panel (SQLAdmin)：删除。**
  依赖已删除的 User model、身份验证和登录会话，无独立用途。

- **缓存 (fastapi-cache)：保留，可选，默认关闭。**
  需要 Redis 时可用，简单无副作用；已有 Redis 依赖校验。

- **限流：保留，可选，默认关闭。**
  内存/Redis 两种存储，不依赖已删除模块。

- **文件存储：删除。**
  V1 没有已确认的文件消费场景；不生成本地文件 API、对象存储后端或 Agent 附件集成。

- **Webhooks：删除。**
  V1 没有已确认的业务事件；不生成投递基础设施、订阅资源或外部调用配置。

- **Legacy 业务产品能力：删除。**
  不生成 teams、billing、email、newsletter、contact、Slack/Telegram channels 或 message ratings。

- **生成应用通用 CLI：删除。**
  V1 没有已确认的独立运维命令用例，不把 legacy CLI 命令面迁入生成项目。

- **分页：始终生成，移除 Copier 选项。**
  零成本 helper，不需要提问。

- **CORS：始终生成，移除 Copier 选项。**
  无 API 可避开，保留 origin 环境变量即可。

- **反向代理：收敛为 `none | nginx`，默认 `none`。**
  删除 Traefik 全部选项（包含镜像、纯标签），删除内嵌 Nginx 服务；仅保留外部 Nginx 配置模板。

- **CI/CD：收敛为 `none | github`，默认 `github`。**
  仅保留 GitHub Actions workflow 模板；删除 GitLab CI 配置分支。
