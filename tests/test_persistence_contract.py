from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tests.support.generation import minimal_answers, project_answers, render_project
from tests.support.services import ServiceEndpoints


def test_database_and_item_switches_own_complete_generated_slices(tmp_path: Path) -> None:
    without_database = render_project(tmp_path / "none", minimal_answers())
    for relative_path in ("app/db", "alembic", "alembic.ini"):
        assert not (without_database.path / relative_path).exists()
    no_database_dependencies = without_database.read("pyproject.toml").lower()
    for dependency in ("alembic", "asyncpg", "psycopg2", "greenlet", "sqlalchemy", "sqlmodel"):
        assert dependency not in no_database_dependencies
    no_database_interface = "\n".join(
        without_database.read(path)
        for path in (
            ".env.example",
            "app/core/config.py",
            "app/api/deps.py",
            "app/api/health.py",
            "cli/commands.py",
        )
    )
    for marker in ("POSTGRES_", "DATABASE_URL", "DBSession", "get_db_session", '@cli.group("db")'):
        assert marker not in no_database_interface

    common_dependencies = ("alembic", "asyncpg", "psycopg2-binary", "greenlet")
    for orm_type, included, excluded in (
        ("sqlalchemy", "sqlalchemy[asyncio]", "sqlmodel"),
        ("sqlmodel", "sqlmodel", "sqlalchemy[asyncio]"),
    ):
        project = render_project(
            tmp_path / orm_type,
            project_answers(orm_type=orm_type),
        )
        dependencies = project.read("pyproject.toml").lower()
        for dependency in common_dependencies:
            assert dependency in dependencies
        assert included in dependencies
        assert excluded not in dependencies
        session_module = project.read("app/db/session.py")
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
        project_answers(include_example_crud=False),
    )
    with_items = render_project(
        tmp_path / "with-items",
        project_answers(include_example_crud=True),
    )
    for relative_path in item_paths:
        assert not (without_items.path / relative_path).exists()
        assert (with_items.path / relative_path).is_file()
    migration = with_items.read("alembic/versions/0021_create_items.py")
    assert 'revision = "0021_create_items"' in migration
    assert "down_revision = None" in migration
    generated_python = "\n".join(
        with_items.read(path) for path in item_paths if path.endswith(".py")
    )
    for removed in ("owner_id", "ItemList", "list_items", "Pagination"):
        assert removed not in generated_python


@pytest.mark.service
@pytest.mark.parametrize("orm_type", ["sqlalchemy", "sqlmodel"])
def test_both_orms_pass_real_database_and_public_item_contract(
    tmp_path: Path,
    service_endpoints: ServiceEndpoints,
    orm_type: str,
) -> None:
    database = f"contract_{orm_type}"
    service_endpoints.create_database(database)
    slug = f"persistence_{orm_type}"
    project = render_project(
        tmp_path / orm_type,
        project_answers(
            project_name=slug,
            project_slug=slug,
            orm_type=orm_type,
            include_example_crud=True,
        ),
    )
    environment = service_endpoints.environment(database=database)
    project.sync()
    project.assert_run("uv", "run", slug, "db", "upgrade", env=environment)
    current = project.assert_run("uv", "run", slug, "db", "current", env=environment)
    assert "0021_create_items" in current.stdout
    project.assert_run("uv", "run", "pytest", "-q", env=environment)

    project.probe(
        textwrap.dedent(
            """
            from typing import Any
            from uuid import UUID

            import anyio
            from fastapi import APIRouter, Depends
            from httpx import ASGITransport, AsyncClient
            from sqlalchemy.ext.asyncio import AsyncEngine
            from sqlalchemy.pool import NullPool

            from app.api.deps import DBSession, verify_api_key
            from app.db.session import get_worker_db_context
            from app.main import app
            from app.repositories import item as item_repo

            rollback_id: UUID | None = None
            router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])

            @router.post("/rollback-probe")
            async def rollback_probe(db: DBSession) -> None:
                global rollback_id
                item = await item_repo.create(db, name="rollback probe")
                rollback_id = item.id
                raise RuntimeError("force rollback")

            app.include_router(router)

            async def verify() -> None:
                transport = ASGITransport(app=app, raise_app_exceptions=False)
                headers = {"X-API-Key": "change-me-in-production"}
                async with app.router.lifespan_context(app):
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        created = await client.post(
                            "/api/v1/items",
                            headers=headers,
                            json={"name": "contract item", "is_published": False},
                        )
                        assert created.status_code == 201
                        item_id = created.json()["id"]
                        fetched = await client.get(f"/api/v1/items/{item_id}", headers=headers)
                        assert fetched.status_code == 200
                        updated = await client.patch(
                            f"/api/v1/items/{item_id}",
                            headers=headers,
                            json={"name": "updated", "is_published": True},
                        )
                        assert updated.status_code == 200
                        assert updated.json()["name"] == "updated"
                        deleted = await client.delete(f"/api/v1/items/{item_id}", headers=headers)
                        assert deleted.status_code == 204
                        missing = await client.get(f"/api/v1/items/{item_id}", headers=headers)
                        assert missing.status_code == 404

                        failed = await client.post("/api/v1/rollback-probe", headers=headers)
                        assert failed.status_code == 500
                        assert rollback_id is not None
                        rolled_back = await client.get(
                            f"/api/v1/items/{rollback_id}", headers=headers
                        )
                        assert rolled_back.status_code == 404

                disposed: list[AsyncEngine] = []
                original_dispose = AsyncEngine.dispose

                async def tracked_dispose(
                    self: AsyncEngine, *args: Any, **kwargs: Any
                ) -> None:
                    disposed.append(self)
                    await original_dispose(self, *args, **kwargs)

                AsyncEngine.dispose = tracked_dispose
                try:
                    async with get_worker_db_context() as session:
                        worker_engine = session.bind
                        assert isinstance(worker_engine, AsyncEngine)
                        assert isinstance(worker_engine.pool, NullPool)
                    assert worker_engine in disposed
                finally:
                    AsyncEngine.dispose = original_dispose

            anyio.run(verify)
            """
        ),
        env=environment,
    )
