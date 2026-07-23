from __future__ import annotations

import re
from pathlib import Path

import yaml

from tests.support.generation import minimal_answers, render_project


def _frontmatter(path: Path) -> dict[str, object]:
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\n"), path
    _, metadata, body = content.split("---", 2)
    assert body.strip(), path
    parsed = yaml.safe_load(metadata)
    assert isinstance(parsed, dict), path
    return parsed


def test_docs_and_omp_guidance_follow_generated_capabilities(tmp_path: Path) -> None:
    minimal = render_project(tmp_path / "minimal", minimal_answers())
    for relative_path in (
        "README.md",
        "ENV_VARS.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "MANUAL_STEPS.md",
        "AGENTS.md",
        "docs/adding_features.md",
        "docs/howto/add-api-endpoint.md",
        "docs/architecture.md",
        "docs/commands.md",
        "docs/configuration.md",
        "docs/patterns.md",
        "docs/testing.md",
        ".omp/rules/api-conventions.md",
        ".omp/rules/architecture.md",
        ".omp/rules/code-style.md",
        ".omp/rules/exceptions-security.md",
        ".omp/rules/schemas-models.md",
        ".omp/rules/testing.md",
        ".omp/skills/pytest-suite/SKILL.md",
        ".omp/commands/add-endpoint.md",
        ".omp/commands/fix-issue.md",
        ".omp/commands/review.md",
    ):
        assert (minimal.path / relative_path).is_file(), relative_path
    for relative_path in (
        "docs/deploy.md",
        ".omp/skills/alembic-migration",
        ".omp/skills/background-task",
        ".omp/skills/agent-tool",
        "docs/howto/add-agent-tool.md",
        "docs/howto/add-background-task.md",
        "docs/howto/customize-agent-prompt.md",
    ):
        assert not (minimal.path / relative_path).exists(), relative_path
    assert "uv run pytest\n```" in minimal.read("AGENTS.md")

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
    for relative_path in (
        "docs/deploy.md",
        ".omp/skills/alembic-migration/SKILL.md",
        ".omp/skills/background-task/SKILL.md",
        ".omp/skills/agent-tool/SKILL.md",
        "docs/howto/add-api-endpoint.md",
        "docs/howto/add-agent-tool.md",
        "docs/howto/add-background-task.md",
        "docs/howto/customize-agent-prompt.md",
    ):
        assert (retained.path / relative_path).is_file(), relative_path
    for rule in (retained.path / ".omp/rules").glob("*.md"):
        metadata = _frontmatter(rule)
        assert isinstance(metadata.get("description"), str)
        assert isinstance(metadata.get("globs"), list)
        assert metadata["globs"]
    for skill in (retained.path / ".omp/skills").glob("*/SKILL.md"):
        metadata = _frontmatter(skill)
        assert metadata["name"] == skill.parent.name
        assert isinstance(metadata.get("description"), str)
    for command in (retained.path / ".omp/commands").glob("*.md"):
        metadata = _frontmatter(command)
        assert isinstance(metadata.get("description"), str)
        assert "argument-hint" not in metadata
        assert "$ARGUMENTS" in command.read_text(encoding="utf-8")
    for forbidden in (
        ".claude",
        ".omp/AGENTS.md",
        ".omp/RULES.md",
        ".omp/config.yml",
        ".omp/config.yaml",
    ):
        assert not (retained.path / forbidden).exists()


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
            project.path / "docs",
            project.path / ".omp",
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )
    delivery_text += "\n" + "\n".join(
        project.read(path)
        for path in (
            "README.md",
            "ENV_VARS.md",
            "SECURITY.md",
            "CONTRIBUTING.md",
            "MANUAL_STEPS.md",
            "AGENTS.md",
        )
    )
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
