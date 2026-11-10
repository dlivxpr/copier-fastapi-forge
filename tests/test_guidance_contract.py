from __future__ import annotations

import re
from pathlib import Path

from tests.support.generation import minimal_answers, render_project

GUIDANCE_FILES = (
    "README.md",
    "ENV_VARS.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "MANUAL_STEPS.md",
    "AGENTS.md",
)


def test_guidance_follows_generated_capabilities(tmp_path: Path) -> None:
    minimal = render_project(tmp_path / "minimal", minimal_answers())
    retained = render_project(
        tmp_path / "retained",
        minimal_answers(
            database="postgresql",
            orm_type="sqlalchemy",
            enable_docker=True,
            reverse_proxy="nginx_external",
            ci_type="github",
            background_tasks="taskiq",
            enable_redis=True,
            enable_caching=True,
            enable_rate_limiting=True,
            rate_limit_storage="redis",
            ai_framework="pydantic_ai",
            enable_logfire=True,
        ),
    )
    for project in (minimal, retained):
        for relative_path in GUIDANCE_FILES:
            path = project.path / relative_path
            assert path.is_file(), relative_path
            content = path.read_text(encoding="utf-8")
            assert "docs/" not in content, (project.path.name, relative_path)
            assert ".agents" not in content, (project.path.name, relative_path)
    for forbidden in (
        ".claude",
        ".omp",
        "docs",
        ".agents",
    ):
        for project in (minimal, retained):
            assert not (project.path / forbidden).exists(), forbidden


def test_delivery_assets_contain_only_current_product_language(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "retained",
        minimal_answers(
            database="postgresql",
            orm_type="sqlalchemy",
            enable_docker=True,
            reverse_proxy="nginx_external",
            ci_type="github",
            background_tasks="taskiq",
            enable_redis=True,
            enable_caching=True,
            enable_rate_limiting=True,
            rate_limit_storage="redis",
            ai_framework="pydantic_ai",
            enable_logfire=True,
        ),
    )
    delivery_text = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (
            project.path / "deploy",
            project.path / ".github",
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )
    delivery_text += "\n" + "\n".join(project.read(path) for path in GUIDANCE_FILES)
    for removed in (
        "frontend",
        "websocket",
        "flower",
        "kubernetes",
        "helm",
        "traefik",
        "celery",
        "rag",
        "billing",
        "pip-audit",
        "trivy",
        "compileall",
    ):
        assert re.search(rf"\b{re.escape(removed)}\b", delivery_text.lower()) is None
