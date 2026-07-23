from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml
from copier import run_copy

TEMPLATE_ROOT = Path(__file__).parents[1]


def render_project(destination: Path, **overrides: object) -> Path:
    answers: dict[str, object] = {
        "database": "none",
        "ai_framework": "none",
        "enable_logfire": False,
        "enable_cors": False,
        "enable_docker": False,
        "ci_type": "none",
        "background_tasks": "none",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": False,
        "include_example_crud": False,
    }
    answers.update(overrides)
    run_copy(
        src_path=str(TEMPLATE_ROOT),
        dst_path=str(destination),
        data=answers,
        defaults=True,
        unsafe=False,
    )
    return destination


def project_text(project: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(project.rglob("*"))
        if path.is_file() and path.suffix != ".lock"
    )


def parse_frontmatter(path: Path) -> dict[str, object]:
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\n"), path
    _, frontmatter, body = content.split("---", 2)
    assert body.strip(), path
    metadata = yaml.safe_load(frontmatter)
    assert isinstance(metadata, dict), path
    return metadata


def compose_config(project: Path, filename: str) -> None:
    result = subprocess.run(
        ["docker", "compose", "-f", f"deploy/{filename}", "config", "--quiet"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"{filename}:\n{result.stdout}\n{result.stderr}"


def test_docker_profiles_restore_legacy_runtime_contract_and_conditions(tmp_path: Path) -> None:
    disabled = render_project(tmp_path / "disabled")
    assert not (disabled / "deploy").exists()
    assert "docker compose" not in project_text(disabled).lower()

    minimal = render_project(
        tmp_path / "minimal-docker",
        enable_docker=True,
        reverse_proxy="none",
        backend_port=8123,
    )
    deploy = minimal / "deploy"
    for relative_path in (
        "Dockerfile",
        "Dockerfile.dockerignore",
        "compose.yaml",
        "compose.dev.yaml",
        "compose.prod.yaml",
    ):
        assert (deploy / relative_path).is_file()
    assert not (deploy / "nginx.conf").exists()

    dockerfile = (deploy / "Dockerfile").read_text(encoding="utf-8")
    for marker in (
        " AS builder",
        "FROM python:3.12-slim",
        "USER appuser",
        "HEALTHCHECK",
        "urllib.request.urlopen('http://127.0.0.1:8123/health')",
        'CMD ["python", "-m", "cli.commands", "server", "run"',
        '"8123"]',
    ):
        assert marker in dockerfile
    assert "COPY . /app" in dockerfile
    assert "COPY app ./app" not in dockerfile
    assert "httpx" not in dockerfile
    dockerignore = (deploy / "Dockerfile.dockerignore").read_text(encoding="utf-8")
    assert ".env*" in dockerignore

    for filename in ("compose.yaml", "compose.dev.yaml", "compose.prod.yaml"):
        compose_config(minimal, filename)
        compose = yaml.safe_load((deploy / filename).read_text(encoding="utf-8"))
        assert set(compose["services"]) == {"app"}
        assert compose["services"]["app"]["build"]["context"] == ".."
        assert compose["services"]["app"]["build"]["dockerfile"] == "deploy/Dockerfile"

    retained = render_project(
        tmp_path / "retained",
        database="postgresql",
        orm_type="sqlalchemy",
        enable_docker=True,
        reverse_proxy="nginx_external",
        background_tasks="taskiq",
        enable_redis=True,
        enable_caching=True,
        enable_rate_limiting=True,
        rate_limit_storage="redis",
    )
    expected_services = {"app", "db", "redis", "worker", "scheduler"}
    for filename in ("compose.yaml", "compose.dev.yaml", "compose.prod.yaml"):
        compose_config(retained, filename)
        compose = yaml.safe_load((retained / "deploy" / filename).read_text(encoding="utf-8"))
        assert set(compose["services"]) == expected_services
        assert compose["services"]["db"]["image"] == "postgres:16-alpine"
        assert compose["services"]["redis"]["image"] == "redis:7-alpine"
        assert compose["services"]["app"]["depends_on"]["db"]["condition"] == ("service_healthy")
        assert compose["services"]["app"]["depends_on"]["redis"]["condition"] == ("service_healthy")
        app_environment = compose["services"]["app"]["environment"]
        assert app_environment["POSTGRES_HOST"] == "db"
        assert "DATABASE_URL" not in app_environment
        assert compose["services"]["worker"]["command"][:5] == [
            "python",
            "-m",
            "cli.commands",
            "taskiq",
            "worker",
        ]
        assert compose["services"]["scheduler"]["command"] == [
            "python",
            "-m",
            "cli.commands",
            "taskiq",
            "scheduler",
        ]
        if filename == "compose.prod.yaml":
            assert (
                "REDIS_PASSWORD"
                in (compose["services"]["worker"]["environment"]["TASKIQ_BROKER_URL"])
            )
            assert "requirepass" in " ".join(compose["services"]["redis"]["command"])


def test_external_nginx_and_github_workflow_keep_retained_contract(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "delivery",
        database="postgresql",
        orm_type="sqlalchemy",
        enable_docker=True,
        reverse_proxy="nginx_external",
        ci_type="github",
        background_tasks="taskiq",
        enable_redis=True,
    )

    nginx = (project / "deploy" / "nginx.conf").read_text(encoding="utf-8")
    for marker in (
        "listen 80",
        "return 301 https://$host$request_uri",
        "location /.well-known/acme-challenge/",
        "listen 443 ssl",
        "ssl_certificate",
        "add_header X-Content-Type-Options",
        "add_header X-Frame-Options",
        "server host.docker.internal:8000",
        "X-Forwarded-For",
        "X-Forwarded-Proto",
        "proxy_connect_timeout",
        "proxy_read_timeout",
        "proxy_send_timeout",
    ):
        assert marker in nginx
    for removed in ("frontend", "websocket", "flower", "127.0.0.1:8000"):
        assert removed not in nginx.lower()

    workflow_path = project / ".github" / "workflows" / "ci.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["push"]["branches"] == ["main", "master"]
    assert triggers["pull_request"] is not None
    assert set(workflow["jobs"]) == {"lint", "test", "docker"}
    assert set(workflow["jobs"]["test"]["services"]) == {"postgres", "redis"}
    assert workflow["jobs"]["docker"]["needs"] == ["lint", "test"]
    assert "refs/heads/master" in workflow["jobs"]["docker"]["if"]
    assert "coverage.xml" in workflow_text
    assert "--cov=cli" in workflow_text
    assert "--cov-fail-under=0" in workflow_text
    assert "codecov/codecov-action" in workflow_text
    assert "fail_ci_if_error: false" in workflow_text
    assert "uv run ruff check app tests cli" in workflow_text
    assert "uv run ruff format --check app tests cli" in workflow_text
    for removed in ("compileall", "runtime smoke", "pip-audit", "trivy"):
        assert removed not in workflow_text.lower()

    no_infra = render_project(tmp_path / "ci-only", ci_type="github")
    no_infra_workflow = yaml.safe_load(
        (no_infra / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    assert "services" not in no_infra_workflow["jobs"]["test"]
    assert "docker" not in no_infra_workflow["jobs"]


def test_docs_and_omp_guidance_follow_generated_capabilities(tmp_path: Path) -> None:
    minimal = render_project(tmp_path / "minimal")
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
        assert (minimal / relative_path).is_file(), relative_path

    assert not (minimal / "docs" / "deploy.md").exists()
    assert not (minimal / ".omp" / "skills" / "alembic-migration").exists()
    assert not (minimal / ".omp" / "skills" / "background-task").exists()
    assert not (minimal / ".omp" / "skills" / "agent-tool").exists()
    assert not (minimal / "docs" / "howto" / "add-agent-tool.md").exists()
    assert not (minimal / "docs" / "howto" / "add-background-task.md").exists()
    assert not (minimal / "docs" / "howto" / "customize-agent-prompt.md").exists()
    assert "uv run pytest\n```" in (minimal / "AGENTS.md").read_text(encoding="utf-8")

    retained = render_project(
        tmp_path / "retained",
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
        assert (retained / relative_path).is_file(), relative_path

    for rule in (retained / ".omp" / "rules").glob("*.md"):
        metadata = parse_frontmatter(rule)
        assert isinstance(metadata.get("description"), str)
        assert isinstance(metadata.get("globs"), list)
        assert metadata["globs"]
    for skill in (retained / ".omp" / "skills").glob("*/SKILL.md"):
        metadata = parse_frontmatter(skill)
        assert metadata["name"] == skill.parent.name
        assert isinstance(metadata.get("description"), str)
    for command in (retained / ".omp" / "commands").glob("*.md"):
        metadata = parse_frontmatter(command)
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
        assert not (retained / forbidden).exists()


def test_removed_capabilities_do_not_return_in_delivery_assets(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "retained",
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
    )
    delivery_text = "\n".join(
        project_text(project / relative_path)
        if (project / relative_path).is_dir()
        else (project / relative_path).read_text(encoding="utf-8")
        for relative_path in (
            "deploy",
            ".github",
            "README.md",
            "ENV_VARS.md",
            "SECURITY.md",
            "CONTRIBUTING.md",
            "MANUAL_STEPS.md",
            "docs",
            ".omp",
        )
    ).lower()
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
        assert re.search(rf"\b{re.escape(removed)}\b", delivery_text) is None
