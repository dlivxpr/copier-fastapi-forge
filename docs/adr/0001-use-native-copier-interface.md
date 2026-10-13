# 仅使用 Copier 原生接口

生成器仅通过 Copier 原生 CLI 执行 `copier copy`，不维护自定义 Python 生成包或包装 CLI。可组合选项、条件问题和验证规则直接定义在 `copier.yml`，避免重复维护一层生成接口，同时保留交互式问答、data file 和命令行传值能力。当前不承诺 `copier update`。

与之类似，生成项目不包含 Kubernetes manifests 和对应 Copier 选项，但仍保留 FastAPI readiness/liveness 健康探针供任何容器平台使用。
