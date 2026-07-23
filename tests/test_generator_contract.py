from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.profiles import FACTOR_VALUES, PROFILE_STATES, all_valid_states, pairs, profile_answers
from tests.support.generation import (
    REPOSITORY_ROOT,
    assert_no_template_tokens,
    minimal_answers,
    normalized_files,
    render_project,
)

PUBLIC_QUESTIONS = (
    "project_name",
    "project_slug",
    "project_description",
    "author_name",
    "author_email",
    "timezone",
    "python_version",
    "backend_port",
    "database",
    "orm_type",
    "db_pool_size",
    "db_max_overflow",
    "db_pool_timeout",
    "include_example_crud",
    "background_tasks",
    "enable_redis",
    "enable_caching",
    "enable_rate_limiting",
    "rate_limit_requests",
    "rate_limit_period",
    "rate_limit_storage",
    "ai_framework",
    "enable_logfire",
    "enable_cors",
    "enable_docker",
    "reverse_proxy",
    "ci_type",
    "deployment_api_key",
)


def _config() -> dict[str, Any]:
    return yaml.safe_load((REPOSITORY_ROOT / "copier.yml").read_text(encoding="utf-8"))


def test_public_questions_have_documented_order_choices_conditions_and_defaults() -> None:
    config = _config()
    questions = {key: value for key, value in config.items() if not key.startswith("_")}
    assert tuple(questions) == PUBLIC_QUESTIONS
    assert {
        name: tuple(question["choices"].values())
        for name, question in questions.items()
        if "choices" in question
    } == {
        "python_version": ("3.12", "3.13", "3.14"),
        "database": ("postgresql", "none"),
        "orm_type": ("sqlalchemy", "sqlmodel"),
        "background_tasks": ("none", "taskiq"),
        "rate_limit_storage": ("memory", "redis"),
        "ai_framework": ("pydantic_ai", "none"),
        "reverse_proxy": ("nginx_external", "none"),
        "ci_type": ("github", "none"),
    }
    assert {
        name: question["when"] for name, question in questions.items() if "when" in question
    } == {
        "orm_type": "[[ database == 'postgresql' ]]",
        "db_pool_size": "[[ database == 'postgresql' ]]",
        "db_max_overflow": "[[ database == 'postgresql' ]]",
        "db_pool_timeout": "[[ database == 'postgresql' ]]",
        "include_example_crud": "[[ database == 'postgresql' ]]",
        "rate_limit_requests": "[[ enable_rate_limiting ]]",
        "rate_limit_period": "[[ enable_rate_limiting ]]",
        "rate_limit_storage": "[[ enable_rate_limiting ]]",
        "enable_logfire": "[[ ai_framework == 'pydantic_ai' ]]",
        "reverse_proxy": "[[ enable_docker ]]",
    }
    assert {name for name, question in questions.items() if "validator" in question} == {
        "project_name",
        "project_slug",
        "backend_port",
        "db_pool_size",
        "db_max_overflow",
        "db_pool_timeout",
        "enable_caching",
        "rate_limit_requests",
        "rate_limit_period",
        "rate_limit_storage",
    }
    assert {name: questions[name]["default"] for name in PUBLIC_QUESTIONS} == {
        "project_name": "my_project",
        "project_slug": "[[ project_name.lower().replace('-', '_') ]]",
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
    }
    assert questions["deployment_api_key"]["secret"] is True


def test_default_profile_has_documented_capability_boundary(tmp_path: Path) -> None:
    project = render_project(tmp_path / "default")
    text = project.all_text()
    for relative_path in (
        "app/db/session.py",
        "app/agents/assistant.py",
        "app/core/telemetry.py",
        "deploy/Dockerfile",
        "deploy/nginx.conf",
        ".github/workflows/ci.yml",
    ):
        assert (project.path / relative_path).is_file()
    for marker in ("sqlalchemy[asyncio]", "pydantic-ai-slim[openai]", '"logfire>=4.0.0"'):
        assert marker in text
    for marker in ("taskiq-redis", "fastapi-cache2", "slowapi", "REDIS_HOST"):
        assert marker not in text
    assert not (project.path / "app/models/item.py").exists()


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
            ("taskiq-redis>=", "ListQueueBroker", "TASKIQ_BROKER_URL="),
            ("app/worker/taskiq_app.py",),
        ),
        (
            {"enable_redis": False},
            {"enable_redis": True},
            ("redis>=", "REDIS_HOST=", "RedisClient"),
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
            ("app/agents/assistant.py", "app/services/agent.py", "app/api/agent.py"),
        ),
        (
            {"ai_framework": "pydantic_ai", "enable_logfire": False},
            {"ai_framework": "pydantic_ai", "enable_logfire": True},
            ("logfire>=", "LOGFIRE_TOKEN", "configure_telemetry"),
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
def test_capability_switches_prune_every_owned_output(
    tmp_path: Path,
    disabled: dict[str, object],
    enabled: dict[str, object],
    markers: tuple[str, ...],
    paths: tuple[str, ...],
) -> None:
    case_name = next(iter(enabled))
    without = render_project(tmp_path / f"without-{case_name}", {**minimal_answers(), **disabled})
    with_capability = render_project(
        tmp_path / f"with-{case_name}", {**minimal_answers(), **enabled}
    )
    without_text = without.all_text()
    with_text = with_capability.all_text()
    for marker in markers:
        assert marker not in without_text
        assert marker in with_text
    for relative_path in paths:
        assert not (without.path / relative_path).exists()
        assert (with_capability.path / relative_path).is_file()


@pytest.mark.parametrize(
    "data",
    [
        {"project_name": "Invalid-Name"},
        {"project_slug": "Invalid-Slug"},
        {"python_version": "3.11"},
        {"backend_port": 0},
        {"backend_port": 65536},
        {"database": "postgresql", "db_pool_size": 0},
        {"database": "postgresql", "db_max_overflow": -1},
        {"database": "postgresql", "db_pool_timeout": 0},
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
def test_invalid_answers_fail_before_rendering(tmp_path: Path, data: dict[str, object]) -> None:
    destination = tmp_path / "invalid"
    with pytest.raises(ValueError, match=r"Validation error|Invalid choice"):
        render_project(destination, data)
    assert not destination.exists()


def test_defaults_and_explicit_answers_render_identically(tmp_path: Path) -> None:
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
    assert normalized_files(implicit) == normalized_files(explicit)


def test_fixed_profiles_cover_every_valid_capability_pair(tmp_path: Path) -> None:
    valid_states = all_valid_states()
    uncovered = set().union(*(pairs(state) for state in valid_states))
    for name, state in PROFILE_STATES.items():
        assert state in valid_states
        uncovered -= pairs(state)
        project = render_project(tmp_path / name, profile_answers(name))
        assert_no_template_tokens(project)
    assert not uncovered
    assert set(FACTOR_VALUES) == set(next(iter(PROFILE_STATES.values())))


def test_valid_high_risk_metadata_passes_generated_development_interface(
    tmp_path: Path,
) -> None:
    answers = profile_answers("minimal")
    answers.update(
        {
            "project_name": "class",
            "project_slug": "class",
            "project_description": "高风险 ${PATH} {service} 'quoted'",
            "author_name": "Renée O'Connor",
            "author_email": "maintainer+pairwise@example.com",
            "timezone": "America/St_Johns",
            "python_version": "3.13",
            "backend_port": 65535,
        }
    )
    project = render_project(tmp_path / "high-risk-metadata", answers)
    assert 'name = "class"' in project.read("pyproject.toml")
    assert "高风险 ${PATH} {service} 'quoted'" in project.read("pyproject.toml")
    assert 'class = "cli.commands:cli"' in project.read("pyproject.toml")
    assert "TIMEZONE=America/St_Johns" in project.read(".env.example")
    project.sync()
    for command in (
        ("uv", "run", "ruff", "check", "."),
        ("uv", "run", "ruff", "format", "--check", "."),
        ("uv", "run", "ty", "check"),
        ("uv", "run", "pytest", "-q"),
        ("uv", "run", "class", "--help"),
    ):
        project.assert_run(*command)
