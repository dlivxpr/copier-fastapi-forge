from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import cast

import pytest
from copier import run_copy

TEMPLATE_ROOT = Path(__file__).parents[1]
UV: str = shutil.which("uv") or "uv"


def render_project(destination: Path, data: dict[str, object] | None = None) -> Path:
    run_copy(
        str(TEMPLATE_ROOT),
        destination,
        data=data,
        defaults=True,
        unsafe=False,
    )
    return destination


def project_metadata(project: Path) -> dict[str, object]:
    raw = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    return raw["project"]  # type: ignore[no-any-return]


def test_copier_public_api_renders_default_root_service(tmp_path: Path) -> None:
    project = render_project(tmp_path / "service")

    assert project_metadata(project)["name"] == "fastapi_service"
    assert (project / "app" / "main.py").is_file()
    assert (project / "tests" / "test_api.py").is_file()
    assert (project / "AGENTS.md").is_file()
    assert (project / ".omp" / "RULES.md").is_file()

    forbidden_paths = [
        "alembic.ini",
        "app/db",
        "app/api/resources.py",
        "app/repositories",
        "app/models",
        "app/agents",
        "app/tasks",
        "app/schemas",
        "app/services",
        "tests/test_persistence.py",
        "compose.yaml",
        "deploy/postgres",
        "deploy/redis",
        "frontend",
    ]
    assert not [path for path in forbidden_paths if (project / path).exists()]
    assert "DATABASE_URL" not in (project / ".env.example").read_text(encoding="utf-8")

    raw_deps = project_metadata(project)["dependencies"]
    deps: list[str] = cast("list[str]", raw_deps)
    forbidden_dependencies = {
        "alembic",
        "asyncpg",
        "fastapi-cache2",
        "logfire",
        "pydantic-ai",
        "redis",
        "sqlalchemy",
        "sqlmodel",
        "taskiq",
    }
    assert forbidden_dependencies.isdisjoint(
        dep.partition(">=")[0].partition("[")[0] for dep in deps
    )


@pytest.mark.parametrize(
    ("orm", "expected_dependency"),
    [
        (None, "sqlalchemy"),
        ("sqlalchemy", "sqlalchemy"),
        ("sqlmodel", "sqlmodel"),
    ],
)
def test_postgresql_renders_selected_orm_slice(
    tmp_path: Path, orm: str | None, expected_dependency: str
) -> None:
    data: dict[str, object] = {"database": "postgresql"}
    if orm is not None:
        data["orm"] = orm
    project = render_project(
        tmp_path / f"postgresql-{orm or 'default'}",
        data=data,
    )

    expected_paths = [
        "alembic.ini",
        "alembic/env.py",
        "alembic/versions/0001_create_resources.py",
        "app/db/session.py",
        "app/models/resource.py",
        "app/repositories/resource.py",
        "app/schemas/resource.py",
        "app/services/resource.py",
        "compose.yaml",
        "tests/test_persistence.py",
    ]
    assert not [path for path in expected_paths if not (project / path).is_file()]

    raw_deps = project_metadata(project)["dependencies"]
    deps: list[str] = cast("list[str]", raw_deps)
    dependency_names = {dep.partition(">=")[0].partition("[")[0] for dep in deps}
    assert {"alembic", "asyncpg", expected_dependency} <= dependency_names
    other_orm = "sqlmodel" if expected_dependency == "sqlalchemy" else "sqlalchemy"
    assert other_orm not in dependency_names


@pytest.mark.parametrize(
    ("arguments", "data_file", "expected_name"),
    [
        (
            (
                "--defaults",
                "--data",
                "project_name=CLI Service",
                "--data",
                "project_slug=cli-service",
            ),
            None,
            "cli_service",
        ),
        (
            ("--defaults",),
            "project_name: Data Service\nproject_slug: data-service\n",
            "data_service",
        ),
    ],
    ids=["command-line-data", "data-file"],
)
def test_copier_cli_accepts_automation_inputs(
    tmp_path: Path,
    arguments: tuple[str, ...],
    data_file: str | None,
    expected_name: str,
) -> None:
    destination = tmp_path / expected_name
    command = [sys.executable, "-m", "copier", "copy", *arguments]
    if data_file is not None:
        answers = tmp_path / "answers.yml"
        answers.write_text(data_file, encoding="utf-8")
        command.extend(("--data-file", str(answers)))
    command.extend((str(TEMPLATE_ROOT), str(destination)))

    subprocess.run(command, check=True, text=True, capture_output=True)

    assert project_metadata(destination)["name"] == expected_name


@pytest.mark.skipif(UV is None, reason="uv is required for generated-project acceptance")
def test_default_project_installs_and_passes_runtime_contract(tmp_path: Path) -> None:
    import os as _os

    project = render_project(tmp_path / "runtime-service")
    clean_env = {k: v for k, v in _os.environ.items() if k != "VIRTUAL_ENV"}

    subprocess.run(
        [UV, "sync", "--all-groups"],
        cwd=project,
        env=clean_env,
        check=True,
        text=True,
        capture_output=True,
    )
    exe_name = "python.exe" if sys.platform == "win32" else "python"
    python_exe = project / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / exe_name

    lint = subprocess.run(
        [str(python_exe), "-m", "ruff", "check", "."],
        cwd=project,
        text=True,
        capture_output=True,
    )
    assert lint.returncode == 0, f"ruff check failed:\n{lint.stdout}\n{lint.stderr}"

    fmt = subprocess.run(
        [str(python_exe), "-m", "ruff", "format", "--check", "."],
        cwd=project,
        text=True,
        capture_output=True,
    )
    assert fmt.returncode == 0, f"ruff format failed:\n{fmt.stdout}\n{fmt.stderr}"

    result = subprocess.run(
        [str(python_exe), "-m", "pytest", "-q"],
        cwd=project,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"

    import_check = subprocess.run(
        [str(python_exe), "-c", "from app.main import app; assert app.title"],
        cwd=project,
        text=True,
        capture_output=True,
    )
    assert import_check.returncode == 0, f"app import failed:\n{import_check.stderr}"
