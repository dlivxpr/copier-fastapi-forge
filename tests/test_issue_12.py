from __future__ import annotations

import difflib
import hashlib
import http.client
import json
import os
import signal
import ssl
import subprocess
import textwrap
import time
import tomllib
from collections.abc import Iterator
from itertools import combinations, product
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

import pytest
import yaml
from copier import run_copy
from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATE_ROOT = Path(__file__).parents[1]
LEGACY_FIXTURE_ROOT = TEMPLATE_ROOT / "tests" / "fixtures" / "legacy-template"
INACTIVE = "<inactive>"


class CompositeServices(TypedDict):
    postgres_id: str
    postgres_port: int
    redis_port: int


FACTOR_VALUES: dict[str, tuple[object, ...]] = {
    "database": ("none", "postgresql"),
    "orm_type": (INACTIVE, "sqlalchemy", "sqlmodel"),
    "include_example_crud": (INACTIVE, False, True),
    "background_tasks": ("none", "taskiq"),
    "enable_redis": (False, True),
    "enable_caching": (False, True),
    "enable_rate_limiting": (False, True),
    "rate_limit_storage": (INACTIVE, "memory", "redis"),
    "ai_framework": ("none", "pydantic_ai"),
    "enable_logfire": (INACTIVE, False, True),
    "enable_cors": (False, True),
    "enable_docker": (False, True),
    "reverse_proxy": (INACTIVE, "none", "nginx_external"),
    "ci_type": ("none", "github"),
}

PROFILE_STATES: dict[str, dict[str, object]] = {
    "minimal": {
        "database": "none",
        "orm_type": INACTIVE,
        "include_example_crud": INACTIVE,
        "background_tasks": "none",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": False,
        "rate_limit_storage": INACTIVE,
        "ai_framework": "none",
        "enable_logfire": INACTIVE,
        "enable_cors": False,
        "enable_docker": False,
        "reverse_proxy": INACTIVE,
        "ci_type": "none",
    },
    "legacy_default": {
        "database": "postgresql",
        "orm_type": "sqlalchemy",
        "include_example_crud": False,
        "background_tasks": "none",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": False,
        "rate_limit_storage": INACTIVE,
        "ai_framework": "pydantic_ai",
        "enable_logfire": True,
        "enable_cors": True,
        "enable_docker": True,
        "reverse_proxy": "nginx_external",
        "ci_type": "github",
    },
    "all_retained_sqlalchemy": {
        "database": "postgresql",
        "orm_type": "sqlalchemy",
        "include_example_crud": True,
        "background_tasks": "taskiq",
        "enable_redis": True,
        "enable_caching": True,
        "enable_rate_limiting": True,
        "rate_limit_storage": "redis",
        "ai_framework": "pydantic_ai",
        "enable_logfire": True,
        "enable_cors": True,
        "enable_docker": True,
        "reverse_proxy": "nginx_external",
        "ci_type": "github",
    },
    "all_retained_sqlmodel": {
        "database": "postgresql",
        "orm_type": "sqlmodel",
        "include_example_crud": True,
        "background_tasks": "taskiq",
        "enable_redis": True,
        "enable_caching": True,
        "enable_rate_limiting": True,
        "rate_limit_storage": "redis",
        "ai_framework": "pydantic_ai",
        "enable_logfire": True,
        "enable_cors": True,
        "enable_docker": True,
        "reverse_proxy": "nginx_external",
        "ci_type": "github",
    },
    "agent_logfire": {
        "database": "none",
        "orm_type": INACTIVE,
        "include_example_crud": INACTIVE,
        "background_tasks": "none",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": False,
        "rate_limit_storage": INACTIVE,
        "ai_framework": "pydantic_ai",
        "enable_logfire": True,
        "enable_cors": False,
        "enable_docker": False,
        "reverse_proxy": INACTIVE,
        "ci_type": "none",
    },
    "redis_consumers_taskiq": {
        "database": "none",
        "orm_type": INACTIVE,
        "include_example_crud": INACTIVE,
        "background_tasks": "taskiq",
        "enable_redis": True,
        "enable_caching": True,
        "enable_rate_limiting": True,
        "rate_limit_storage": "redis",
        "ai_framework": "none",
        "enable_logfire": INACTIVE,
        "enable_cors": False,
        "enable_docker": False,
        "reverse_proxy": INACTIVE,
        "ci_type": "none",
    },
    "sqlmodel_memory": {
        "database": "postgresql",
        "orm_type": "sqlmodel",
        "include_example_crud": False,
        "background_tasks": "none",
        "enable_redis": True,
        "enable_caching": False,
        "enable_rate_limiting": True,
        "rate_limit_storage": "memory",
        "ai_framework": "pydantic_ai",
        "enable_logfire": False,
        "enable_cors": False,
        "enable_docker": True,
        "reverse_proxy": "none",
        "ci_type": "none",
    },
    "taskiq_memory_delivery": {
        "database": "none",
        "orm_type": INACTIVE,
        "include_example_crud": INACTIVE,
        "background_tasks": "taskiq",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": True,
        "rate_limit_storage": "memory",
        "ai_framework": "none",
        "enable_logfire": INACTIVE,
        "enable_cors": True,
        "enable_docker": True,
        "reverse_proxy": "none",
        "ci_type": "github",
    },
    "sqlmodel_cache_no_rate_limit": {
        "database": "postgresql",
        "orm_type": "sqlmodel",
        "include_example_crud": True,
        "background_tasks": "taskiq",
        "enable_redis": True,
        "enable_caching": True,
        "enable_rate_limiting": False,
        "rate_limit_storage": INACTIVE,
        "ai_framework": "pydantic_ai",
        "enable_logfire": False,
        "enable_cors": True,
        "enable_docker": False,
        "reverse_proxy": INACTIVE,
        "ci_type": "github",
    },
    "sqlalchemy_item_memory_nginx": {
        "database": "postgresql",
        "orm_type": "sqlalchemy",
        "include_example_crud": True,
        "background_tasks": "none",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": True,
        "rate_limit_storage": "memory",
        "ai_framework": "none",
        "enable_logfire": INACTIVE,
        "enable_cors": False,
        "enable_docker": True,
        "reverse_proxy": "nginx_external",
        "ci_type": "none",
    },
    "sqlalchemy_cache_memory": {
        "database": "postgresql",
        "orm_type": "sqlalchemy",
        "include_example_crud": False,
        "background_tasks": "none",
        "enable_redis": True,
        "enable_caching": True,
        "enable_rate_limiting": True,
        "rate_limit_storage": "memory",
        "ai_framework": "none",
        "enable_logfire": INACTIVE,
        "enable_cors": False,
        "enable_docker": False,
        "reverse_proxy": INACTIVE,
        "ci_type": "github",
    },
    "redis_rate_limit_agent_nginx": {
        "database": "none",
        "orm_type": INACTIVE,
        "include_example_crud": INACTIVE,
        "background_tasks": "none",
        "enable_redis": True,
        "enable_caching": False,
        "enable_rate_limiting": True,
        "rate_limit_storage": "redis",
        "ai_framework": "pydantic_ai",
        "enable_logfire": False,
        "enable_cors": True,
        "enable_docker": True,
        "reverse_proxy": "nginx_external",
        "ci_type": "none",
    },
    "sqlalchemy_taskiq_no_consumers": {
        "database": "postgresql",
        "orm_type": "sqlalchemy",
        "include_example_crud": False,
        "background_tasks": "taskiq",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": False,
        "rate_limit_storage": INACTIVE,
        "ai_framework": "pydantic_ai",
        "enable_logfire": False,
        "enable_cors": False,
        "enable_docker": True,
        "reverse_proxy": "none",
        "ci_type": "none",
    },
    "sqlmodel_all_redis_consumers": {
        "database": "postgresql",
        "orm_type": "sqlmodel",
        "include_example_crud": False,
        "background_tasks": "none",
        "enable_redis": True,
        "enable_caching": True,
        "enable_rate_limiting": True,
        "rate_limit_storage": "redis",
        "ai_framework": "none",
        "enable_logfire": INACTIVE,
        "enable_cors": False,
        "enable_docker": True,
        "reverse_proxy": "none",
        "ci_type": "none",
    },
    "sqlmodel_item_agent_memory": {
        "database": "postgresql",
        "orm_type": "sqlmodel",
        "include_example_crud": True,
        "background_tasks": "none",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": True,
        "rate_limit_storage": "memory",
        "ai_framework": "pydantic_ai",
        "enable_logfire": True,
        "enable_cors": False,
        "enable_docker": True,
        "reverse_proxy": "none",
        "ci_type": "none",
    },
}


def _is_valid_state(state: dict[str, object]) -> bool:
    if state["database"] == "none":
        if state["orm_type"] != INACTIVE or state["include_example_crud"] != INACTIVE:
            return False
    elif state["orm_type"] == INACTIVE or state["include_example_crud"] == INACTIVE:
        return False
    if state["enable_caching"] and not state["enable_redis"]:
        return False
    if (not state["enable_rate_limiting"] and state["rate_limit_storage"] != INACTIVE) or (
        state["enable_rate_limiting"]
        and (
            state["rate_limit_storage"] == INACTIVE
            or (state["rate_limit_storage"] == "redis" and not state["enable_redis"])
        )
    ):
        return False
    if state["ai_framework"] == "none":
        if state["enable_logfire"] != INACTIVE:
            return False
    elif state["enable_logfire"] == INACTIVE:
        return False
    if not state["enable_docker"]:
        return state["reverse_proxy"] == INACTIVE
    return state["reverse_proxy"] != INACTIVE


def _all_valid_states() -> list[dict[str, object]]:
    factors = tuple(FACTOR_VALUES)
    return [
        state
        for values in product(*(FACTOR_VALUES[factor] for factor in factors))
        if _is_valid_state(state := dict(zip(factors, values, strict=True)))
    ]


def _pairs(state: dict[str, object]) -> set[tuple[tuple[str, object], tuple[str, object]]]:
    return {
        ((left, state[left]), (right, state[right]))
        for left, right in combinations(FACTOR_VALUES, 2)
    }


def profile_answers(name: str) -> dict[str, Any]:
    state = PROFILE_STATES[name]
    answers: dict[str, Any] = {
        "project_name": "equivalence_service",
        "project_slug": "equivalence_service",
        "project_description": "Equivalence service",
        "author_name": "Migration Owner",
        "author_email": "migration@example.com",
        "timezone": "UTC",
        "python_version": "3.12",
        "backend_port": 8000,
        "db_pool_size": 5,
        "db_max_overflow": 10,
        "db_pool_timeout": 30,
        "rate_limit_requests": 100,
        "rate_limit_period": 60,
        "include_example_crud": False,
        "enable_logfire": False,
        "deployment_api_key": "change-me-in-production",
    }
    answers.update({key: value for key, value in state.items() if value != INACTIVE})
    return answers


def render_project(destination: Path, profile_name: str) -> Path:
    run_copy(
        str(TEMPLATE_ROOT),
        destination,
        data=profile_answers(profile_name),
        defaults=True,
        unsafe=True,
        quiet=True,
    )
    return destination


@pytest.fixture(scope="module")
def pairwise_projects(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("issue-12-profiles")
    return {name: render_project(root / name, name) for name in PROFILE_STATES}


def test_named_profiles_cover_every_valid_capability_pair(
    pairwise_projects: dict[str, Path],
) -> None:
    required_profiles = {
        "minimal",
        "legacy_default",
        "all_retained_sqlalchemy",
        "all_retained_sqlmodel",
        "agent_logfire",
        "redis_consumers_taskiq",
    }
    assert required_profiles <= PROFILE_STATES.keys()
    assert all(_is_valid_state(state) for state in PROFILE_STATES.values())

    valid_pairs = set().union(*(_pairs(state) for state in _all_valid_states()))
    covered_pairs = set().union(*(_pairs(state) for state in PROFILE_STATES.values()))
    assert covered_pairs == valid_pairs

    for _name, project in pairwise_projects.items():
        generated = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in sorted(project.rglob("*"))
            if path.is_file()
        )
        assert "[%" not in generated
        assert "[[" not in generated


def _normalize_content(content: str) -> str:
    return "\n".join(line.rstrip() for line in content.replace("\r\n", "\n").splitlines())


def _digest(content: str) -> str:
    return hashlib.sha256(f"{content}\n".encode()).hexdigest()


def _content_digest(content: str) -> str:
    return _digest(_normalize_content(content))


def _normalized_diff(legacy_content: str, target_content: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            _normalize_content(legacy_content).splitlines(),
            _normalize_content(target_content).splitlines(),
            fromfile="legacy",
            tofile="target",
            lineterm="",
        )
    )


def _diff_digest(legacy_content: str, target_content: str) -> str:
    normalized_diff = _normalized_diff(legacy_content, target_content)
    return _digest(normalized_diff)


def _trace_authorization_digest(
    records: list[dict[str, Any]],
    target_paths: list[str],
) -> str:
    selected = [
        {
            "target": str(record["target"]),
            "legacy_source": str(record["legacy_source"]),
            "profile": str(record.get("profile", "minimal")),
            "allowed_transformations": record["allowed_transformations"],
            "removed_references": record["removed_references"],
            "approved_deviation": record["approved_deviation"],
            "verification": record["verification"],
        }
        for record in records
        if str(record["target"]) in target_paths
    ]
    selected.sort(key=lambda record: (record["target"], record["profile"]))
    return _digest(
        json.dumps(
            selected,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _legacy_context(profile: dict[str, Any]) -> dict[str, Any]:
    defaults = json.loads((LEGACY_FIXTURE_ROOT / "cookiecutter.json").read_text(encoding="utf-8"))
    defaults.update(profile)
    defaults.update(
        {
            "auth": "api_key",
            "use_api_key": True,
            "use_auth": True,
            "use_database": profile["database"] == "postgresql",
            "use_jwt": False,
            "use_postgresql": profile["database"] == "postgresql",
            "use_sqlalchemy": profile.get("orm_type") == "sqlalchemy",
            "use_sqlmodel": profile.get("orm_type") == "sqlmodel",
            "use_pydantic_ai": profile["ai_framework"] == "pydantic_ai",
            "use_ai": profile["ai_framework"] == "pydantic_ai",
            "use_taskiq": profile["background_tasks"] == "taskiq",
            "rate_limit_storage_memory": profile.get("rate_limit_storage") == "memory",
            "rate_limit_storage_redis": profile.get("rate_limit_storage") == "redis",
            "use_github_actions": profile.get("ci_type") == "github",
            "use_nginx": profile.get("reverse_proxy") == "nginx_external",
        }
    )
    return defaults


def test_each_pairwise_profile_has_protected_legacy_equivalence(
    pairwise_projects: dict[str, Path],
) -> None:
    trace = tomllib.loads(
        (TEMPLATE_ROOT / "docs" / "migration-traceability.toml").read_text(encoding="utf-8")
    )
    profile_manifest = tomllib.loads(
        (TEMPLATE_ROOT / "tests" / "pairwise-equivalence.toml").read_text(encoding="utf-8")
    )

    sources_by_target: dict[str, str] = {}
    for record in trace["target"]:
        target = str(record["target"])
        source = str(record["legacy_source"])
        assert sources_by_target.setdefault(target, source) == source
        assert record["allowed_transformations"]
        assert record["removed_references"]
        assert record["approved_deviation"]
        assert record["verification"]

    generated_union = {
        path.relative_to(project).as_posix()
        for project in pairwise_projects.values()
        for path in project.rglob("*")
        if path.is_file()
    }
    assert generated_union == sources_by_target.keys()

    legacy_root = LEGACY_FIXTURE_ROOT
    environment = Environment(
        loader=FileSystemLoader(legacy_root),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )

    assert set(profile_manifest["profiles"]) == set(PROFILE_STATES)
    for name, project in pairwise_projects.items():
        generated_paths = sorted(
            path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_file()
        )
        expected_profile = profile_manifest["profiles"][name]
        expected_content = expected_profile["content_sha256"]
        assert set(expected_content) == set(generated_paths)
        answers = profile_answers(name)
        answers_json = json.dumps(
            answers,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        assert expected_profile["answers_sha256"] == _digest(answers_json)
        assert expected_profile["trace_sha256"] == _trace_authorization_digest(
            trace["target"],
            generated_paths,
        )
        context = _legacy_context(answers)
        for target_path in generated_paths:
            source = sources_by_target[target_path]
            source_path = source.removeprefix("legacy/template/{{cookiecutter.project_slug}}/")
            legacy_content = environment.get_template(source_path).render({"cookiecutter": context})
            target_content = (project / target_path).read_text(encoding="utf-8")
            observed_content = _digest(
                "\0".join(
                    (
                        _content_digest(legacy_content),
                        _content_digest(target_content),
                        _diff_digest(legacy_content, target_content),
                    )
                )
            )
            assert observed_content == expected_content[target_path], (
                f"Unapproved pairwise content for {name}:{target_path}\n"
                f"{_normalized_diff(legacy_content, target_content)}"
            )


def test_all_retained_openapi_and_http_contract_are_protected(tmp_path: Path) -> None:
    project = render_project(tmp_path / "openapi", "all_retained_sqlalchemy")
    sync = subprocess.run(
        ["uv", "sync", "--all-groups"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert sync.returncode == 0, sync.stderr

    output_path = project / "acceptance-contract.json"
    runtime_code = textwrap.dedent(
        """
        import json
        import sys
        from pathlib import Path

        import anyio
        from httpx import ASGITransport, AsyncClient

        from app.main import app
        from app.core.rate_limit import limiter

        limiter.enabled = False


        async def collect() -> None:
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                health = await client.get(
                    "/health",
                    headers={"X-Request-ID": "issue-12-request"},
                )
                missing_item_key = await client.post(
                    "/api/v1/items",
                    json={"name": "protected"},
                )
                wrong_agent_key = await client.post(
                    "/agent/run",
                    headers={"X-API-Key": "wrong"},
                    json={"input": "hello"},
                )
                deleted_routes = {
                    path: (await client.get(
                        path,
                        headers={"X-API-Key": "change-me-in-production"},
                    )).status_code
                    for path in ("/api/v1/items", "/hello", "/limited", "/cache")
                }

            payload = {
                "openapi": app.openapi(),
                "runtime": {
                    "health_status": health.status_code,
                    "health_body": health.json(),
                    "request_id": health.headers["X-Request-ID"],
                    "missing_item_key": {
                        "status": missing_item_key.status_code,
                        "body": missing_item_key.json(),
                        "content_type": missing_item_key.headers["content-type"],
                    },
                    "wrong_agent_key": {
                        "status": wrong_agent_key.status_code,
                        "body": wrong_agent_key.json(),
                    },
                    "deleted_routes": deleted_routes,
                },
            }
            Path(sys.argv[1]).write_text(
                json.dumps(payload, sort_keys=True),
                encoding="utf-8",
            )


        anyio.run(collect)
        """
    )
    environment = os.environ.copy()
    environment["LOGFIRE_SEND_TO_LOGFIRE"] = "false"
    collected = subprocess.run(
        ["uv", "run", "python", "-c", runtime_code, str(output_path)],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert collected.returncode == 0, collected.stderr
    contract = json.loads(output_path.read_text(encoding="utf-8"))
    openapi = contract["openapi"]
    runtime = contract["runtime"]

    operations = {
        (path, method)
        for path, path_item in openapi["paths"].items()
        for method in path_item
        if method in {"get", "post", "patch", "delete"}
    }
    assert operations == {
        ("/health", "get"),
        ("/health/live", "get"),
        ("/health/ready", "get"),
        ("/agent/run", "post"),
        ("/agent/stream", "post"),
        ("/api/v1/items", "post"),
        ("/api/v1/items/{item_id}", "get"),
        ("/api/v1/items/{item_id}", "patch"),
        ("/api/v1/items/{item_id}", "delete"),
    }
    assert openapi["components"]["securitySchemes"] == {
        "APIKeyHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        }
    }
    for path, method in operations:
        operation = openapi["paths"][path][method]
        if path.startswith("/health"):
            assert "security" not in operation
        else:
            assert operation["security"] == [{"APIKeyHeader": []}]

    assert set(openapi["paths"]["/api/v1/items"]["post"]["responses"]) == {"201", "422"}
    item_path = openapi["paths"]["/api/v1/items/{item_id}"]
    assert set(item_path["get"]["responses"]) == {"200", "422"}
    assert set(item_path["patch"]["responses"]) == {"200", "422"}
    assert set(item_path["delete"]["responses"]) == {"204", "422"}
    assert openapi["paths"]["/agent/stream"]["post"]["responses"]["200"]["content"] == {
        "text/event-stream": {
            "itemSchema": {
                "type": "object",
                "properties": {
                    "data": {"type": "string"},
                    "event": {"type": "string"},
                    "id": {"type": "string"},
                    "retry": {"type": "integer", "minimum": 0},
                },
            }
        }
    }
    assert openapi["components"]["schemas"]["AgentInvocationRequest"] == {
        "type": "object",
        "title": "AgentInvocationRequest",
        "required": ["input"],
        "additionalProperties": False,
        "properties": {
            "input": {
                "type": "string",
                "minLength": 1,
                "title": "Input",
            }
        },
    }
    assert "ItemRead" in openapi["components"]["schemas"]
    assert "ErrorResponse" not in openapi["components"]["schemas"]

    assert runtime == {
        "health_status": 200,
        "health_body": {"status": "healthy", "max_upload_size_mb": 50},
        "request_id": "issue-12-request",
        "missing_item_key": {
            "status": 401,
            "body": {
                "error": {
                    "code": "AUTHENTICATION_ERROR",
                    "message": "API Key header missing",
                    "details": None,
                }
            },
            "content_type": "application/json",
        },
        "wrong_agent_key": {
            "status": 403,
            "body": {
                "error": {
                    "code": "AUTHORIZATION_ERROR",
                    "message": "Invalid API Key",
                    "details": None,
                }
            },
        },
        "deleted_routes": {
            "/api/v1/items": 405,
            "/cache": 404,
            "/hello": 404,
            "/limited": 404,
        },
    }


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


def test_copier_questions_choices_conditions_and_validators_are_protected() -> None:
    config = yaml.safe_load((TEMPLATE_ROOT / "copier.yml").read_text(encoding="utf-8"))
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
    assert questions["deployment_api_key"]["secret"] is True


def _run_generated_command(
    project: Path,
    environment: dict[str, str],
    command: list[str],
    *,
    timeout: int = 600,
) -> None:
    result = subprocess.run(
        command,
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert result.returncode == 0, (
        f"{' '.join(command)} failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_high_risk_valid_metadata_profile_passes_generated_quality_gates(
    tmp_path: Path,
) -> None:
    project = tmp_path / "high-risk-metadata"
    answers = profile_answers("minimal")
    answers.update(
        {
            "project_name": "class",
            "project_slug": "class",
            "project_description": "高风险 ${PATH} {service} 'quoted'",
            "author_name": "Renée O'Connor",
            "author_email": "migration+pairwise@example.com",
            "timezone": "America/St_Johns",
            "python_version": "3.13",
            "backend_port": 65535,
        }
    )
    run_copy(
        str(TEMPLATE_ROOT),
        str(project),
        data=answers,
        defaults=True,
        unsafe=True,
        quiet=True,
    )
    pyproject = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "class"' in pyproject
    assert "高风险 ${PATH} {service} 'quoted'" in pyproject
    assert 'class = "cli.commands:cli"' in pyproject
    assert "TIMEZONE=America/St_Johns" in (project / ".env.example").read_text(encoding="utf-8")

    environment = os.environ.copy()
    for command in (
        ["uv", "sync", "--all-groups"],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "ty", "check"],
        ["uv", "run", "pytest", "-q"],
        ["uv", "run", "class", "--help"],
    ):
        _run_generated_command(project, environment, command)


def _cleanup_command(
    command: list[str],
    *,
    timeout: int,
) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    if result.returncode != 0:
        return result, result.stderr
    return result, None


def _cleanup_labeled_containers(label: str) -> list[str]:
    errors: list[str] = []
    containers, error = _cleanup_command(
        ["docker", "ps", "--all", "--quiet", "--filter", f"label={label}"],
        timeout=30,
    )
    if error:
        errors.append(error)
    elif containers is not None:
        for container_id in containers.stdout.splitlines():
            _, error = _cleanup_command(
                ["docker", "rm", "--force", container_id],
                timeout=30,
            )
            if error:
                errors.append(error)
    remaining, error = _cleanup_command(
        ["docker", "ps", "--all", "--quiet", "--filter", f"label={label}"],
        timeout=30,
    )
    if error:
        errors.append(error)
    elif remaining is not None and remaining.stdout.strip():
        errors.append(f"Containers were not removed: {remaining.stdout.strip()}")
    return errors


@pytest.fixture(scope="module")
def composite_services() -> Iterator[CompositeServices]:
    suffix = uuid4().hex[:12]
    label = f"copier-fastapi-forge.issue-12-services={suffix}"
    try:
        postgres = subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--label",
                label,
                "--env",
                "POSTGRES_PASSWORD=postgres",
                "--publish",
                "127.0.0.1::5432",
                "postgres:17-alpine",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert postgres.returncode == 0, postgres.stderr
        postgres_id = postgres.stdout.strip()
        redis = subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--label",
                label,
                "--publish",
                "127.0.0.1::6379",
                "redis:7-alpine",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert redis.returncode == 0, redis.stderr
        redis_id = redis.stdout.strip()
        postgres_port = _published_port(postgres_id, 5432)
        redis_port = _published_port(redis_id, 6379)

        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            postgres_ready = subprocess.run(
                ["docker", "exec", postgres_id, "pg_isready", "-U", "postgres"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            redis_ready = subprocess.run(
                ["docker", "exec", redis_id, "redis-cli", "ping"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if postgres_ready.returncode == 0 and "PONG" in redis_ready.stdout:
                break
            time.sleep(0.5)
        else:
            pytest.fail("PostgreSQL and Redis did not become ready")

        yield {
            "postgres_id": postgres_id,
            "postgres_port": postgres_port,
            "redis_port": redis_port,
        }
    finally:
        errors = _cleanup_labeled_containers(label)
        assert not errors, "\n".join(errors)


def _stop_process_group(process: subprocess.Popen[str]) -> tuple[str, bool]:
    if os.name == "nt":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        os.killpg(process.pid, signal.SIGINT)
    forced = False
    try:
        stdout, _ = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        forced = True
        if os.name == "nt":
            killed = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert killed.returncode == 0, killed.stderr
        else:
            os.killpg(process.pid, signal.SIGKILL)
        stdout, _ = process.communicate(timeout=30)
    return stdout, forced


def _smoke_taskiq_process(
    project: Path,
    environment: dict[str, str],
    command: list[str],
) -> None:
    process = subprocess.Popen(
        command,
        cwd=project,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )
    output = ""
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.communicate(timeout=5)[0]
                pytest.fail(f"{' '.join(command)} exited with {process.returncode}\n{output}")
            time.sleep(0.5)
    finally:
        forced = False
        if process.poll() is None:
            output, forced = _stop_process_group(process)
    assert not forced, f"{' '.join(command)} required forced shutdown\n{output}"
    expected = {0, 0xC000013A} if os.name == "nt" else {0, 1, 130, -signal.SIGINT}
    assert process.returncode in expected, output
    if process.returncode == 1:
        assert "Aborted!" in output


@pytest.mark.parametrize(
    "profile_name",
    ["all_retained_sqlalchemy", "all_retained_sqlmodel", "redis_consumers_taskiq"],
)
def test_named_composite_profiles_pass_real_service_quality_and_runtime(
    profile_name: str,
    tmp_path: Path,
    composite_services: CompositeServices,
) -> None:
    project = render_project(tmp_path / profile_name, profile_name)
    postgres_id = composite_services["postgres_id"]
    postgres_port = composite_services["postgres_port"]
    redis_port = composite_services["redis_port"]
    database_name = f"issue_12_{profile_name}"
    environment = os.environ.copy()
    environment.update(
        {
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_PORT": str(postgres_port),
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "postgres",
            "POSTGRES_DB": database_name,
            "REDIS_HOST": "127.0.0.1",
            "REDIS_PORT": str(redis_port),
            "REDIS_PASSWORD": "",
            "REDIS_DB": "0",
            "TASKIQ_BROKER_URL": f"redis://127.0.0.1:{redis_port}/1",
            "TASKIQ_RESULT_BACKEND_URL": f"redis://127.0.0.1:{redis_port}/1",
            "LOGFIRE_SEND_TO_LOGFIRE": "false",
        }
    )
    if PROFILE_STATES[profile_name]["database"] == "postgresql":
        created = subprocess.run(
            ["docker", "exec", postgres_id, "createdb", "-U", "postgres", database_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert created.returncode == 0, created.stderr

    _run_generated_command(project, environment, ["uv", "sync", "--all-groups"])
    for command in (
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "ty", "check"],
    ):
        _run_generated_command(project, environment, command)
    if PROFILE_STATES[profile_name]["database"] == "postgresql":
        _run_generated_command(
            project,
            environment,
            ["uv", "run", "equivalence_service", "db", "upgrade"],
        )
    _run_generated_command(
        project,
        environment,
        ["uv", "run", "pytest", "-q"],
        timeout=900,
    )
    _run_generated_command(
        project,
        environment,
        ["uv", "run", "equivalence_service", "server", "routes"],
    )

    if profile_name == "redis_consumers_taskiq":
        executable = "equivalence_service.exe" if os.name == "nt" else "equivalence_service"
        cli = project / ".venv" / ("Scripts" if os.name == "nt" else "bin") / executable
        environment["PATH"] = f"{cli.parent}{os.pathsep}{environment['PATH']}"
        for args in (
            ["taskiq", "worker", "--workers=1"],
            ["taskiq", "scheduler"],
        ):
            _smoke_taskiq_process(project, environment, [str(cli), *args])


def _published_port(container_id: str, container_port: int) -> int:
    result = subprocess.run(
        ["docker", "port", container_id, f"{container_port}/tcp"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return int(result.stdout.strip().rsplit(":", maxsplit=1)[1])


def _wait_for_http(port: int, *, tls: bool = False) -> tuple[int, str]:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if tls:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                connection: http.client.HTTPConnection = http.client.HTTPSConnection(
                    "127.0.0.1",
                    port,
                    timeout=2,
                    context=context,
                )
            else:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("GET", "/health")
            response = connection.getresponse()
            body = response.read().decode()
            connection.close()
            return response.status, body
        except OSError:
            time.sleep(0.5)
    pytest.fail(f"HTTP service on port {port} did not become ready")


def test_container_image_and_external_nginx_run_with_random_ports(
    tmp_path: Path,
) -> None:
    docker = subprocess.run(
        ["docker", "info"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert docker.returncode == 0, docker.stderr

    project = tmp_path / "docker-nginx"
    answers = profile_answers("minimal")
    answers.update(
        {
            "project_name": "issue_12_container",
            "project_slug": "issue_12_container",
            "enable_docker": True,
            "reverse_proxy": "nginx_external",
        }
    )
    backend_port = int(answers["backend_port"])
    run_copy(
        str(TEMPLATE_ROOT),
        str(project),
        data=answers,
        defaults=True,
        unsafe=True,
        quiet=True,
    )
    suffix = uuid4().hex[:12]
    image = f"copier-fastapi-forge-issue-12:{suffix}"
    label = f"copier-fastapi-forge.issue-12={suffix}"
    network = f"copier-fastapi-forge-issue-12-{suffix}"
    backend_container = ""
    nginx_container = ""
    image_built = False
    network_created = False

    try:
        build = subprocess.run(
            [
                "docker",
                "build",
                "--tag",
                image,
                "--file",
                "deploy/Dockerfile",
                ".",
            ],
            cwd=project,
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
        )
        assert build.returncode == 0, build.stderr
        image_built = True
        network_result = subprocess.run(
            ["docker", "network", "create", "--label", label, network],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert network_result.returncode == 0, network_result.stderr
        network_created = True

        backend = subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--label",
                label,
                "--network",
                network,
                "--network-alias",
                "host.docker.internal",
                "--publish",
                f"127.0.0.1::{backend_port}",
                image,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert backend.returncode == 0, backend.stderr
        backend_container = backend.stdout.strip()
        backend_host_port = _published_port(backend_container, backend_port)
        status, body = _wait_for_http(backend_host_port)
        assert status == 200
        assert json.loads(body) == {"status": "healthy", "max_upload_size_mb": 50}

        certificate_dir = tmp_path / "nginx-certificates"
        certificate_dir.mkdir()
        certificate = subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-nodes",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(certificate_dir / "key.pem"),
                "-out",
                str(certificate_dir / "cert.pem"),
                "-subj",
                "/CN=localhost",
                "-days",
                "1",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert certificate.returncode == 0, certificate.stderr

        nginx = subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--label",
                label,
                "--network",
                network,
                "--publish",
                "127.0.0.1::80",
                "--publish",
                "127.0.0.1::443",
                "--volume",
                f"{(project / 'deploy' / 'nginx.conf').resolve().as_posix()}"
                ":/etc/nginx/conf.d/default.conf:ro",
                "--volume",
                f"{certificate_dir.resolve().as_posix()}:/etc/nginx/ssl:ro",
                "nginx:1.27-alpine",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert nginx.returncode == 0, nginx.stderr
        nginx_container = nginx.stdout.strip()

        config = subprocess.run(
            ["docker", "exec", nginx_container, "nginx", "-t"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert config.returncode == 0, config.stderr
        http_port = _published_port(nginx_container, 80)
        https_port = _published_port(nginx_container, 443)
        status, body = _wait_for_http(https_port, tls=True)
        assert status == 200
        assert json.loads(body) == {"status": "healthy", "max_upload_size_mb": 50}

        connection = http.client.HTTPConnection("127.0.0.1", http_port, timeout=5)
        connection.request("GET", "/health")
        response = connection.getresponse()
        response.read()
        connection.close()
        assert response.status == 301
        assert response.headers["Location"].startswith("https://")
    finally:
        errors = _cleanup_labeled_containers(label)
        if network_created:
            _, error = _cleanup_command(
                ["docker", "network", "rm", network],
                timeout=30,
            )
            if error:
                errors.append(error)
        if image_built:
            _, error = _cleanup_command(
                ["docker", "image", "rm", "--force", image],
                timeout=60,
            )
            if error:
                errors.append(error)
        assert not errors, "\n".join(errors)
