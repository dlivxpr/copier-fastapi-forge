from __future__ import annotations

import hashlib
import json
import subprocess
import textwrap
import tomllib
from pathlib import Path

import yaml
from copier import run_copy
from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATE_ROOT = Path(__file__).parents[1]


def render_project(destination: Path, data: dict[str, object]) -> Path:
    run_copy(
        src_path=str(TEMPLATE_ROOT),
        dst_path=str(destination),
        data=data,
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


def test_copier_questions_restore_legacy_public_defaults() -> None:
    config = yaml.safe_load((TEMPLATE_ROOT / "copier.yml").read_text(encoding="utf-8"))

    assert config["project_name"]["default"] == "my_project"
    assert config["project_slug"]["default"] == "[[ project_name.lower().replace('-', '_') ]]"
    assert config["project_description"]["default"] == "A FastAPI project"
    assert config["author_name"]["default"] == "Your Name"
    assert config["author_email"]["default"] == "your@email.com"
    assert config["timezone"]["default"] == "UTC"
    assert config["python_version"]["default"] == "3.12"
    assert config["backend_port"]["default"] == 8000
    assert config["database"]["default"] == "postgresql"
    assert config["orm_type"]["default"] == "sqlalchemy"
    assert config["ai_framework"]["default"] == "pydantic_ai"
    assert config["enable_logfire"]["default"] is True
    assert config["enable_cors"]["default"] is True
    assert config["enable_docker"]["default"] is True
    assert config["ci_type"]["default"] == "github"
    assert config["background_tasks"]["default"] == "none"
    assert config["enable_redis"]["default"] is False
    assert config["enable_caching"]["default"] is False
    assert config["enable_rate_limiting"]["default"] is False
    assert config["include_example_crud"]["default"] is False


def test_minimal_answers_render_deterministic_project_metadata(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "minimal",
        {
            **minimal_answers(),
            "project_name": "named_service",
            "project_description": "Named service",
            "author_name": "Service Owner",
            "author_email": "owner@example.com",
            "timezone": "Europe/Warsaw",
            "python_version": "3.12",
            "backend_port": 8123,
        },
    )

    pyproject = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "named_service"' in pyproject
    assert 'description = "Named service"' in pyproject
    assert 'requires-python = ">=3.12"' in pyproject
    assert not (project / "deploy").exists()
    assert not (project / ".github").exists()


def test_minimal_tree_contains_only_legacy_core_service(tmp_path: Path) -> None:
    project = render_project(tmp_path / "minimal-core", minimal_answers())

    assert (project / "app" / "core" / "logging.py").is_file()
    assert (project / "app" / "core" / "middleware.py").is_file()
    assert (project / "app" / "api" / "health.py").is_file()
    assert (project / "app" / "schemas" / "base.py").is_file()
    assert (project / "app" / "services" / "health.py").is_file()
    assert (project / "cli" / "commands.py").is_file()

    forbidden_paths = [
        "app/core/pagination.py",
        "app/api/resources.py",
        "app/models/resource.py",
        "app/repositories/resource.py",
        "app/schemas/resource.py",
        "app/services/resource.py",
        "app/api/cache.py",
        "app/api/rate_limit.py",
    ]
    for relative_path in forbidden_paths:
        assert not (project / relative_path).exists()

    generated_python = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(project.rglob("*.py"))
    )
    for forbidden in (
        "DomainError",
        "PaginationParams",
        '"/hello"',
        "SecurityHeaders",
        "WWW-Authenticate",
    ):
        assert forbidden not in generated_python


def test_minimal_project_passes_http_and_cli_runtime_contract(tmp_path: Path) -> None:
    project = render_project(tmp_path / "runtime", minimal_answers())
    sync = subprocess.run(
        ["uv", "sync", "--all-groups"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert sync.returncode == 0, sync.stderr

    runtime_code = textwrap.dedent(
        """
        import anyio
        from fastapi import APIRouter, Depends
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import verify_api_key
        from app.core.exceptions import NotFoundError
        from app.main import app

        router = APIRouter(
            prefix="/api/v1",
            dependencies=[Depends(verify_api_key)],
        )

        @router.get("/probe")
        async def probe() -> None:
            raise NotFoundError(details={"resource": "probe"})

        @router.get("/crash")
        async def crash() -> None:
            raise RuntimeError("sensitive implementation detail")

        app.include_router(router)

        async def run() -> None:
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with app.router.lifespan_context(app):
                async with AsyncClient(
                    transport=transport,
                    base_url="http://test",
                ) as client:
                    health = await client.get(
                        "/health",
                        headers={"X-Request-ID": "request-123"},
                    )
                    assert health.status_code == 200
                    assert health.json() == {
                        "status": "healthy",
                        "max_upload_size_mb": 50,
                    }
                    assert health.headers["X-Request-ID"] == "request-123"
                    assert "access-control-allow-origin" not in health.headers

                    live = await client.get("/health/live")
                    assert live.status_code == 200
                    assert live.json()["status"] == "alive"
                    assert live.json()["service"] == "my_project"
                    assert live.json()["details"] == {
                        "version": "1.0.0",
                        "environment": "local",
                    }
                    assert "timestamp" in live.json()

                    ready = await client.get("/health/ready")
                    assert ready.status_code == 200
                    assert ready.json()["status"] == "ready"
                    assert ready.json()["checks"] == {}

                    missing = await client.get("/api/v1/probe")
                    assert missing.status_code == 401
                    assert missing.json() == {
                        "error": {
                            "code": "AUTHENTICATION_ERROR",
                            "message": "API Key header missing",
                            "details": None,
                        }
                    }
                    assert "www-authenticate" not in missing.headers

                    invalid = await client.get(
                        "/api/v1/probe",
                        headers={"X-API-Key": "wrong"},
                    )
                    assert invalid.status_code == 403
                    assert invalid.json()["error"]["code"] == "AUTHORIZATION_ERROR"

                    known = await client.get(
                        "/api/v1/probe",
                        headers={"X-API-Key": "change-me-in-production"},
                    )
                    assert known.status_code == 404
                    assert known.json() == {
                        "error": {
                            "code": "NOT_FOUND",
                            "message": "Resource not found",
                            "details": {"resource": "probe"},
                        }
                    }

                    unknown = await client.get(
                        "/api/v1/crash",
                        headers={"X-API-Key": "change-me-in-production"},
                    )
                    assert unknown.status_code == 500
                    assert unknown.json() == {
                        "error": {
                            "code": "INTERNAL_ERROR",
                            "message": "An unexpected error occurred",
                            "details": None,
                        }
                    }

        anyio.run(run)
        """
    )
    runtime = subprocess.run(
        ["uv", "run", "python", "-c", runtime_code],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert runtime.returncode == 0, runtime.stderr
    assert "Unhandled exception" in runtime.stderr
    assert "sensitive implementation detail" in runtime.stderr

    cli_help = subprocess.run(
        ["uv", "run", "my_project", "--help"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert cli_help.returncode == 0, cli_help.stderr
    assert "server" in cli_help.stdout

    routes = subprocess.run(
        ["uv", "run", "my_project", "server", "routes"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert routes.returncode == 0, routes.stderr
    assert "/health" in routes.stdout
    assert "/health/live" in routes.stdout
    assert "/health/ready" in routes.stdout
    assert "/hello" not in routes.stdout


def test_minimal_generated_project_passes_quality_commands(tmp_path: Path) -> None:
    project = render_project(tmp_path / "quality", minimal_answers())
    commands = [
        ["uv", "sync", "--all-groups"],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "ty", "check"],
        ["uv", "run", "pytest"],
    ]
    for command in commands:
        result = subprocess.run(
            command,
            cwd=project,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"{' '.join(command)} failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def _normalized_digest(content: str) -> str:
    normalized = "\n".join(line.rstrip() for line in content.replace("\r\n", "\n").splitlines())
    return hashlib.sha256(f"{normalized}\n".encode()).hexdigest()


def _legacy_context(profile: dict[str, object]) -> dict[str, object]:
    defaults = json.loads(
        (TEMPLATE_ROOT / "legacy" / "template" / "cookiecutter.json").read_text(encoding="utf-8")
    )
    defaults.update(profile)
    defaults.update(
        {
            "auth": "api_key",
            "use_api_key": True,
            "use_auth": True,
            "use_database": profile["database"] == "postgresql",
            "use_jwt": False,
            "use_postgresql": profile["database"] == "postgresql",
            "use_pydantic_ai": profile["ai_framework"] == "pydantic_ai",
            "use_ai": profile["ai_framework"] == "pydantic_ai",
        }
    )
    return defaults


def test_migration_equivalence_manifest_rejects_unregistered_content(
    tmp_path: Path,
) -> None:
    trace = tomllib.loads(
        (TEMPLATE_ROOT / "docs" / "migration-traceability.toml").read_text(encoding="utf-8")
    )
    manifest = tomllib.loads(
        (TEMPLATE_ROOT / "tests" / "migration-equivalence.toml").read_text(encoding="utf-8")
    )
    records = trace["target"]
    protected = manifest["protected"]
    assert {record["target"] for record in records} == set(protected)
    for record in records:
        assert record["legacy_source"]
        assert record["allowed_transformations"]
        assert record["removed_references"]
        assert record["approved_deviation"]
        assert record["verification"]

    profile = {
        **minimal_answers(),
        "project_name": "equivalence_service",
        "project_slug": "equivalence_service",
        "project_description": "Equivalence service",
        "author_name": "Migration Owner",
        "author_email": "migration@example.com",
        "timezone": "UTC",
        "python_version": "3.12",
        "backend_port": 8000,
        "deployment_api_key": "change-me-in-production",
    }
    project = render_project(tmp_path / "target", profile)
    legacy_root = TEMPLATE_ROOT / "legacy" / "template" / "{{cookiecutter.project_slug}}"
    environment = Environment(
        loader=FileSystemLoader(legacy_root),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    context = {"cookiecutter": _legacy_context(profile)}

    observed: dict[str, dict[str, str]] = {}
    for record in records:
        target_path = record["target"]
        source_path = record["legacy_source"].removeprefix(
            "legacy/template/{{cookiecutter.project_slug}}/"
        )
        legacy_content = environment.get_template(source_path).render(context)
        target_content = (project / target_path).read_text(encoding="utf-8")
        observed[target_path] = {
            "legacy_sha256": _normalized_digest(legacy_content),
            "target_sha256": _normalized_digest(target_content),
        }

    assert observed == protected
