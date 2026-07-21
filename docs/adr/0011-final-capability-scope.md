# 最终能力矩阵边界

以下选项在需求访谈最后一批确认：

- **Admin Panel (SQLAdmin)：删除。**
  依赖已删除的 User model、身份验证和登录会话，无独立用途。

- **缓存 (fastapi-cache)：保留，可选，默认关闭。**
  需要 Redis 时可用，简单无副作用；已有 Redis 依赖校验。

- **限流：保留，可选，默认关闭。**
  内存/Redis 两种存储，不依赖已删除模块。

- **文件存储：保留，可选，默认关闭。**
  基础文件上传与检索，对算法服务输入和 Agent 附件都有价值。

- **Webhooks：保留，可选，默认关闭。**
  主动外部调用 infrastructure，不依赖已删除模块。

- **分页：始终生成，移除 Copier 选项。**
  零成本 helper，不需要提问。

- **CORS：始终生成，移除 Copier 选项。**
  无 API 可避开，保留 origin 环境变量即可。

- **反向代理：收敛为 `none | nginx`，默认 `none`。**
  删除 Traefik 全部选项（包含镜像、纯标签），删除内嵌 Nginx 服务；仅保留外部 Nginx 配置模板。

- **CI/CD：收敛为 `none | github`，默认 `github`。**
  仅保留 GitHub Actions workflow 模板；删除 GitLab CI 配置分支。
