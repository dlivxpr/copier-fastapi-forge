from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tests.support.generation import minimal_answers, render_project


def test_project_metadata_and_minimal_tree_follow_public_contract(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "minimal",
        minimal_answers(
            project_name="named_service",
            project_slug="named_service",
            project_description="Named service",
            author_name="Service Owner",
            author_email="owner@example.com",
            timezone="Europe/Warsaw",
            python_version="3.12",
            backend_port=8123,
        ),
    )
    pyproject = project.read("pyproject.toml")
    assert 'name = "named_service"' in pyproject
    assert 'description = "Named service"' in pyproject
    assert 'requires-python = ">=3.12"' in pyproject
    for relative_path in (
        "app/core/logging.py",
        "app/core/middleware.py",
        "app/api/health.py",
        "app/schemas/base.py",
        "app/services/health.py",
        "cli/commands.py",
        "tests/test_api.py",
    ):
        assert (project.path / relative_path).is_file()
    for relative_path in (
        "deploy",
        ".github",
        "app/core/pagination.py",
        "app/api/resources.py",
        "app/models/resource.py",
        "app/repositories/resource.py",
        "app/schemas/resource.py",
        "app/services/resource.py",
        "app/api/cache.py",
        "app/api/rate_limit.py",
    ):
        assert not (project.path / relative_path).exists()
    generated_python = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(project.path.rglob("*.py"))
    )
    for forbidden in (
        "DomainError",
        "PaginationParams",
        '"/hello"',
        "SecurityHeaders",
        "WWW-Authenticate",
    ):
        assert forbidden not in generated_python


def test_minimal_http_error_and_cli_behavior(tmp_path: Path) -> None:
    project = render_project(tmp_path / "runtime", minimal_answers())
    project.sync()
    runtime = project.probe(
        textwrap.dedent(
            """
            import anyio
            from fastapi import APIRouter, Depends
            from httpx import ASGITransport, AsyncClient

            from app.api.deps import verify_api_key
            from app.core.exceptions import NotFoundError
            from app.main import app

            router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])

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
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        health = await client.get(
                            "/health", headers={"X-Request-ID": "request-123"}
                        )
                        assert health.status_code == 200
                        assert health.json() == {"status": "healthy", "max_upload_size_mb": 50}
                        assert health.headers["X-Request-ID"] == "request-123"
                        assert "access-control-allow-origin" not in health.headers

                        live = await client.get("/health/live")
                        assert live.status_code == 200
                        assert live.json()["status"] == "alive"
                        assert live.json()["service"] == "contract_service"
                        assert live.json()["details"] == {
                            "version": "1.0.0", "environment": "local"
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
                            "/api/v1/probe", headers={"X-API-Key": "wrong"}
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
    )
    assert "Unhandled exception" in runtime.stderr
    assert "sensitive implementation detail" in runtime.stderr

    help_result = project.assert_run("uv", "run", "contract_service", "--help")
    assert "server" in help_result.stdout
    routes = project.assert_run("uv", "run", "contract_service", "server", "routes")
    for path in ("/health", "/health/live", "/health/ready"):
        assert path in routes.stdout
    assert "/hello" not in routes.stdout


@pytest.mark.parametrize(
    ("check_name", "answers", "port_variable"),
    [
        ("redis", {"enable_redis": True}, "REDIS_PORT"),
        ("database", {"database": "postgresql"}, "POSTGRES_PORT"),
    ],
)
def test_enabled_unavailable_dependency_marks_readiness_unhealthy(
    tmp_path: Path,
    check_name: str,
    answers: dict[str, object],
    port_variable: str,
) -> None:
    project = render_project(tmp_path / f"{check_name}-readiness", {**minimal_answers(), **answers})
    project.sync()
    project.probe(
        textwrap.dedent(
            f"""
            import os
            import anyio
            from httpx import ASGITransport, AsyncClient

            os.environ["{port_variable}"] = "1"
            from app.main import app

            async def verify() -> None:
                async with app.router.lifespan_context(app):
                    transport = ASGITransport(app=app, raise_app_exceptions=False)
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.get("/health/ready")
                        assert response.status_code == 503
                        assert response.json()["status"] == "not_ready"
                        assert response.json()["checks"]["{check_name}"]["status"] == "unhealthy"

            anyio.run(verify)
            """
        )
    )


def test_minimal_generated_project_passes_its_development_interface(tmp_path: Path) -> None:
    project = render_project(tmp_path / "quality", minimal_answers())
    project.sync()
    for command in (
        ("uv", "run", "ruff", "check", "."),
        ("uv", "run", "ruff", "format", "--check", "."),
        ("uv", "run", "ty", "check"),
        ("uv", "run", "pytest"),
    ):
        project.assert_run(*command)
