from __future__ import annotations

from pathlib import Path

import pytest
from copier import run_copy

TEMPLATE_ROOT = Path(__file__).parents[1]


def render_project(destination: Path, data: dict[str, object] | None = None) -> Path:
    run_copy(
        src_path=str(TEMPLATE_ROOT),
        dst_path=str(destination),
        data=data or {},
        defaults=True,
        unsafe=False,
    )
    return destination


def minimal_answers() -> dict[str, object]:
    return {
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


def generated_text(project: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(project.rglob("*"))
        if path.is_file() and path.suffix not in {".pyc", ".lock"}
    )


def test_default_profile_restores_legacy_enabled_and_disabled_capabilities(
    tmp_path: Path,
) -> None:
    project = render_project(tmp_path / "default")
    text = generated_text(project)

    assert (project / "app" / "db" / "session.py").is_file()
    assert "sqlalchemy[asyncio]" in text
    assert "pydantic-ai-slim[openai]" in text
    assert '"logfire>=4.0.0"' in text
    assert "logfire[" not in text
    assert (project / "app" / "agents" / "assistant.py").is_file()
    assert "CORS_ORIGINS" in text
    assert (project / "deploy" / "Dockerfile").is_file()
    assert (project / "deploy" / "nginx.conf").is_file()
    assert (project / ".github" / "workflows" / "ci.yml").is_file()

    assert "taskiq-redis" not in text
    assert "fastapi-cache2" not in text
    assert "slowapi" not in text
    assert "REDIS_HOST" not in (project / ".env.example").read_text(encoding="utf-8")
    assert not (project / "app" / "models" / "item.py").exists()


@pytest.mark.parametrize(
    ("disabled", "enabled", "markers", "paths"),
    [
        (
            {"database": "none"},
            {"database": "postgresql", "orm_type": "sqlalchemy"},
            ("asyncpg>=", "POSTGRES_HOST=", "DATABASE_URL", "DatabaseError"),
            ("app/db/session.py", "app/db/base.py", "alembic.ini", "alembic/env.py"),
        ),
        (
            {"background_tasks": "none"},
            {"background_tasks": "taskiq"},
            (
                "taskiq-redis>=",
                "ListQueueBroker",
                "TASKIQ_BROKER_URL=",
                "TASKIQ_RESULT_BACKEND_URL=",
            ),
            ("app/worker/taskiq_app.py",),
        ),
        (
            {"enable_redis": False},
            {"enable_redis": True},
            ("redis>=6.2.0", "REDIS_HOST=", "RedisClient"),
            ("app/clients/redis.py", "tests/test_redis.py"),
        ),
        (
            {"enable_redis": False, "enable_caching": False},
            {"enable_redis": True, "enable_caching": True},
            ("fastapi-cache2>=", "FastAPICache", "RedisBackend"),
            ("app/core/cache.py",),
        ),
        (
            {"enable_rate_limiting": False},
            {"enable_rate_limiting": True},
            ("slowapi>=", "RATE_LIMIT_REQUESTS=", "SlowAPIASGIMiddleware"),
            ("app/core/rate_limit.py",),
        ),
        (
            {"ai_framework": "none"},
            {"ai_framework": "pydantic_ai"},
            ("pydantic-ai-slim[openai]>=", "LLM_BASE_URL"),
            (
                "app/agents/assistant.py",
                "app/services/agent.py",
                "app/api/agent.py",
                "tests/test_agent.py",
            ),
        ),
        (
            {"ai_framework": "pydantic_ai", "enable_logfire": False},
            {"ai_framework": "pydantic_ai", "enable_logfire": True},
            ("logfire>=4.0.0", "LOGFIRE_TOKEN", "configure_telemetry"),
            ("app/core/telemetry.py",),
        ),
        (
            {"enable_cors": False},
            {"enable_cors": True},
            ("CORS_ORIGINS=", "CORSMiddleware"),
            (),
        ),
    ],
)
def test_connected_capability_switches_have_disabled_and_enabled_output(
    tmp_path: Path,
    disabled: dict[str, object],
    enabled: dict[str, object],
    markers: tuple[str, ...],
    paths: tuple[str, ...],
) -> None:
    case_name = next(iter(enabled))
    without = render_project(
        tmp_path / f"without-{case_name}",
        {**minimal_answers(), **disabled},
    )
    with_capability = render_project(
        tmp_path / f"with-{case_name}",
        {**minimal_answers(), **enabled},
    )
    without_text = generated_text(without)
    with_text = generated_text(with_capability)

    for marker in markers:
        assert marker not in without_text
        assert marker in with_text
    for relative_path in paths:
        assert not (without / relative_path).exists()
        assert (with_capability / relative_path).is_file()


def test_taskiq_is_independent_from_api_redis_and_has_no_demo_tasks(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "taskiq-only",
        {
            **minimal_answers(),
            "background_tasks": "taskiq",
        },
    )
    text = generated_text(project)
    env = (project / ".env.example").read_text(encoding="utf-8")
    main = (project / "app" / "main.py").read_text(encoding="utf-8")
    cli = (project / "cli" / "commands.py").read_text(encoding="utf-8")

    assert "TASKIQ_BROKER_URL=redis://localhost:6379/1" in env
    assert "TASKIQ_RESULT_BACKEND_URL=redis://localhost:6379/1" in env
    assert "REDIS_HOST" not in env
    assert "RedisClient" not in main
    assert not (project / "app" / "clients" / "redis.py").exists()
    assert '"app.worker.taskiq_app:broker"' in cli
    assert '"app.worker.taskiq_app:scheduler"' in cli
    assert "example_task" not in text
    assert "scheduled_health" not in text
    assert "/limited" not in text
    assert not (project / "tests" / "test_tasks.py").exists()


def test_memory_rate_limit_has_no_redis_client_residue(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "memory-rate-limit",
        {
            **minimal_answers(),
            "enable_rate_limiting": True,
            "rate_limit_storage": "memory",
        },
    )
    text = generated_text(project)
    env = (project / ".env.example").read_text(encoding="utf-8")

    assert 'storage_uri="memory://"' in text
    assert "REDIS_HOST" not in env
    assert "RedisClient" not in text
    assert not (project / "app" / "clients" / "redis.py").exists()


def test_redis_rate_limit_uses_shared_api_redis_storage(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "redis-rate-limit",
        {
            **minimal_answers(),
            "enable_redis": True,
            "enable_rate_limiting": True,
            "rate_limit_storage": "redis",
        },
    )
    text = generated_text(project)

    assert "storage_uri=settings.REDIS_URL" in text
    assert (project / "app" / "clients" / "redis.py").is_file()


def test_deployment_asset_switches_remove_whole_trees(tmp_path: Path) -> None:
    without = render_project(tmp_path / "without-deploy", minimal_answers())
    with_deploy = render_project(
        tmp_path / "with-deploy",
        {
            **minimal_answers(),
            "enable_docker": True,
            "reverse_proxy": "nginx_external",
            "ci_type": "github",
        },
    )
    without_nginx = render_project(
        tmp_path / "without-nginx",
        {
            **minimal_answers(),
            "enable_docker": True,
            "reverse_proxy": "none",
        },
    )

    assert not (without / "deploy").exists()
    assert not (without / ".github").exists()
    assert (with_deploy / "deploy" / "Dockerfile").is_file()
    assert (with_deploy / "deploy" / "nginx.conf").is_file()
    assert (with_deploy / ".github" / "workflows" / "ci.yml").is_file()
    assert not (without_nginx / "deploy" / "nginx.conf").exists()


@pytest.mark.parametrize(
    "data",
    [
        {"project_name": "Invalid-Name"},
        {"backend_port": 0},
        {"enable_rate_limiting": True, "rate_limit_requests": 0},
        {"enable_rate_limiting": True, "rate_limit_period": 0},
        {"enable_redis": False, "enable_caching": True},
        {
            "enable_redis": False,
            "enable_rate_limiting": True,
            "rate_limit_storage": "redis",
        },
    ],
)
def test_invalid_public_answers_fail_before_rendering(
    tmp_path: Path,
    data: dict[str, object],
) -> None:
    destination = tmp_path / "invalid"
    with pytest.raises(ValueError, match="Validation error"):
        render_project(destination, data)
    assert not destination.exists()


def test_defaults_and_explicit_automation_profile_are_deterministic(tmp_path: Path) -> None:
    implicit = render_project(tmp_path / "implicit")
    explicit = render_project(
        tmp_path / "explicit",
        {
            "project_name": "my_project",
            "project_slug": "my_project",
            "project_description": "A FastAPI project",
            "author_name": "Your Name",
            "author_email": "your@email.com",
            "timezone": "UTC",
            "python_version": "3.12",
            "backend_port": 8000,
            "database": "postgresql",
            "orm_type": "sqlalchemy",
            "db_pool_size": 5,
            "db_max_overflow": 10,
            "db_pool_timeout": 30,
            "include_example_crud": False,
            "background_tasks": "none",
            "enable_redis": False,
            "enable_caching": False,
            "enable_rate_limiting": False,
            "rate_limit_requests": 100,
            "rate_limit_period": 60,
            "rate_limit_storage": "memory",
            "ai_framework": "pydantic_ai",
            "enable_logfire": True,
            "enable_cors": True,
            "enable_docker": True,
            "reverse_proxy": "nginx_external",
            "ci_type": "github",
            "deployment_api_key": "change-me-in-production",
        },
    )

    implicit_files = {
        path.relative_to(implicit): path.read_bytes()
        for path in implicit.rglob("*")
        if path.is_file()
    }
    explicit_files = {
        path.relative_to(explicit): path.read_bytes()
        for path in explicit.rglob("*")
        if path.is_file()
    }
    assert implicit_files == explicit_files
