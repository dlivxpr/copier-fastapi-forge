# 仅使用 Copier 原生接口

生成器彻底删除自定义 Python 包和 Click CLI，仅通过 Copier 原生 CLI 执行生成与更新。原有的可组合选项、条件问题和派生配置迁入 `copier.yml`；这避免长期维护一层与 Copier 能力重叠的包装接口，同时保留交互式问答、data file 和命令行传值能力。

与之类似，生成项目不包含 Kubernetes manifests 和对应 Copier 选项，但仍保留 FastAPI readiness/liveness 健康探针供任何容器平台使用。
