from __future__ import annotations

import os
import subprocess
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from copier import run_copy

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


def project_answers(**overrides: object) -> dict[str, object]:
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
    return answers


def test_postgresql_questions_and_orm_rendering_follow_legacy_contract(tmp_path: Path) -> None:
    config = yaml.safe_load((TEMPLATE_ROOT / "copier.yml").read_text(encoding="utf-8"))
    assert config["database"]["default"] == "postgresql"
    assert config["orm_type"]["default"] == "sqlalchemy"
    assert config["orm_type"]["when"] == "[[ database == 'postgresql' ]]"

    without_database = render_project(tmp_path / "none", project_answers())
    assert not (without_database / "app" / "db").exists()
    assert not (without_database / "alembic").exists()
    assert not (without_database / "alembic.ini").exists()
    no_database_dependencies = (without_database / "pyproject.toml").read_text(encoding="utf-8")
    for dependency in ("alembic", "asyncpg", "psycopg2", "greenlet", "sqlalchemy", "sqlmodel"):
        assert dependency not in no_database_dependencies.lower()
    no_database_source = "\n".join(
        (without_database / relative_path).read_text(encoding="utf-8")
        for relative_path in (
            ".env.example",
            "app/core/config.py",
            "app/api/deps.py",
            "app/api/health.py",
            "cli/commands.py",
        )
    )
    for database_symbol in (
        "POSTGRES_",
        "DATABASE_URL",
        "DBSession",
        "get_db_session",
        '@cli.group("db")',
    ):
        assert database_symbol not in no_database_source

    common_dependencies = ("alembic", "asyncpg", "psycopg2-binary", "greenlet")
    for orm_type, included, excluded in (
        ("sqlalchemy", "sqlalchemy[asyncio]", "sqlmodel"),
        ("sqlmodel", "sqlmodel", "sqlalchemy[asyncio]"),
    ):
        project = render_project(
            tmp_path / orm_type,
            project_answers(database="postgresql", orm_type=orm_type),
        )
        dependencies = (project / "pyproject.toml").read_text(encoding="utf-8").lower()
        for dependency in common_dependencies:
            assert dependency in dependencies
        assert included in dependencies
        assert excluded not in dependencies

        session_module = (project / "app" / "db" / "session.py").read_text(encoding="utf-8")
        for public_name in (
            "engine",
            "async_session_maker",
            "get_db_session",
            "get_db_context",
            "get_worker_db_context",
            "close_db",
        ):
            assert public_name in session_module
        for pool_setting in ("DB_POOL_SIZE", "DB_MAX_OVERFLOW", "DB_POOL_TIMEOUT"):
            assert pool_setting in session_module


def test_postgresql_cli_health_and_lifespan_runtime_contract(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "postgresql-runtime",
        project_answers(database="postgresql", orm_type="sqlalchemy"),
    )
    sync = subprocess.run(
        ["uv", "sync", "--all-groups"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert sync.returncode == 0, sync.stderr

    cli_help = subprocess.run(
        ["uv", "run", "my_project", "db", "--help"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert cli_help.returncode == 0, cli_help.stderr
    for command in ("init", "migrate", "upgrade", "downgrade", "current", "history"):
        assert command in cli_help.stdout

    history = subprocess.run(
        ["uv", "run", "my_project", "db", "history"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert history.returncode == 0, history.stderr

    runtime_code = textwrap.dedent(
        """
        import anyio
        from httpx import ASGITransport, AsyncClient

        import app.main as main
        from app.api.deps import get_db_session

        events = []

        class FakeSession:
            async def execute(self, statement):
                events.append(str(statement))

        async def fake_session():
            yield FakeSession()

        async def fake_close_db():
            events.append("closed")

        main.app.dependency_overrides[get_db_session] = fake_session
        main.close_db = fake_close_db

        async def verify():
            async with main.app.router.lifespan_context(main.app):
                transport = ASGITransport(app=main.app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.get("/health/ready")
                    assert response.status_code == 200
                    assert response.json()["checks"]["database"]["status"] == "healthy"
            assert any("SELECT 1" in event for event in events)
            assert events[-1] == "closed"

        anyio.run(verify)
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


def test_item_crud_switch_controls_the_complete_generated_slice(tmp_path: Path) -> None:
    item_paths = (
        "app/db/models/item.py",
        "app/repositories/item.py",
        "app/services/item.py",
        "app/schemas/item.py",
        "app/api/items.py",
        "alembic/versions/0021_create_items.py",
        "tests/test_items.py",
    )
    without_items = render_project(
        tmp_path / "without-items",
        project_answers(database="postgresql", include_example_crud=False),
    )
    for relative_path in item_paths:
        assert not (without_items / relative_path).exists()

    with_items = render_project(
        tmp_path / "with-items",
        project_answers(
            database="postgresql",
            orm_type="sqlalchemy",
            include_example_crud=True,
        ),
    )
    for relative_path in item_paths:
        assert (with_items / relative_path).is_file()

    migration = (with_items / "alembic" / "versions" / "0021_create_items.py").read_text(
        encoding="utf-8"
    )
    assert 'revision = "0021_create_items"' in migration
    assert "down_revision = None" in migration
    assert "owner_id" not in migration
    assert "ForeignKey" not in migration

    generated_python = "\n".join(
        (with_items / relative_path).read_text(encoding="utf-8")
        for relative_path in item_paths
        if relative_path.endswith(".py")
    )
    assert "owner_id" not in generated_python
    assert "ItemList" not in generated_python
    assert "list_items" not in generated_python
    assert "Pagination" not in generated_python


@pytest.fixture(scope="module")
def postgresql_server() -> Iterator[tuple[str, int]]:
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--detach",
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
    assert started.returncode == 0, started.stderr
    container_id = started.stdout.strip()
    try:
        port_result = subprocess.run(
            ["docker", "port", container_id, "5432/tcp"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert port_result.returncode == 0, port_result.stderr
        port = int(port_result.stdout.strip().splitlines()[0].rsplit(":", 1)[1])

        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    container_id,
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "postgres",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            pytest.fail("PostgreSQL container did not become ready")

        yield container_id, port
    finally:
        subprocess.run(
            ["docker", "rm", "--force", container_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )


@pytest.mark.parametrize("orm_type", ["sqlalchemy", "sqlmodel"])
def test_both_orms_pass_real_postgresql_contract(
    tmp_path: Path,
    postgresql_server: tuple[str, int],
    orm_type: str,
) -> None:
    container_id, port = postgresql_server
    database_name = f"issue_8_{orm_type}"
    created_database = subprocess.run(
        ["docker", "exec", container_id, "createdb", "-U", "postgres", database_name],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert created_database.returncode == 0, created_database.stderr

    project_name = f"issue_8_{orm_type}"
    project = render_project(
        tmp_path / orm_type,
        project_answers(
            project_name=project_name,
            project_slug=project_name,
            database="postgresql",
            orm_type=orm_type,
            include_example_crud=True,
        ),
    )
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)
    environment.update(
        {
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_PORT": str(port),
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "postgres",
            "POSTGRES_DB": database_name,
        }
    )

    commands = [
        ["uv", "sync", "--all-groups"],
        ["uv", "run", project_name, "db", "upgrade"],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "ty", "check"],
        ["uv", "run", "pytest", "-q"],
        ["uv", "run", project_name, "db", "current"],
    ]
    for command in commands:
        result = subprocess.run(
            command,
            cwd=project,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"{' '.join(command)} failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        if command[-2:] == ["db", "current"]:
            assert "0021_create_items" in result.stdout
