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
        "app/api/cache.py",
        "app/api/rate_limit.py",
        "app/api/agent.py",
        "app/repositories",
        "app/models",
        "app/agents",
        "app/tasks",
        "app/core/rate_limit.py",
        "app/core/redis.py",
        "app/schemas",
        "app/services",
        "tests/test_persistence.py",
        "tests/test_rate_limit.py",
        "tests/test_agent.py",
        "compose.yaml",
        "deploy/postgres",
        "deploy/redis",
        "frontend",
    ]
    assert not [path for path in forbidden_paths if (project / path).exists()]
    assert "DATABASE_URL" not in (project / ".env.example").read_text(encoding="utf-8")
    assert "REDIS_URL" not in (project / ".env.example").read_text(encoding="utf-8")
    assert "LLM_BASE_URL" not in (project / ".env.example").read_text(encoding="utf-8")

    raw_deps = project_metadata(project)["dependencies"]
    deps: list[str] = cast("list[str]", raw_deps)
    forbidden_dependencies = {
        "alembic",
        "asyncpg",
        "fastapi-cache2",
        "logfire",
        "pydantic-ai",
        "pydantic-ai-slim",
        "redis",
        "sqlalchemy",
        "sqlmodel",
        "taskiq",
    }
    assert forbidden_dependencies.isdisjoint(
        dep.partition(">=")[0].partition("[")[0] for dep in deps
    )


def test_pydantic_ai_renders_only_compatible_single_turn_capability(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "pydantic-ai-service",
        data={"agent_capability": "pydantic-ai"},
    )

    expected_paths = [
        "app/agents/assistant.py",
        "app/api/agent.py",
        "app/services/agent.py",
        "tests/test_agent.py",
    ]
    assert not [path for path in expected_paths if not (project / path).is_file()]

    raw_deps = project_metadata(project)["dependencies"]
    deps: list[str] = cast("list[str]", raw_deps)
    dependency_names = {dep.partition(">=")[0].partition("[")[0] for dep in deps}
    assert "pydantic-ai-slim" in dependency_names

    env_example = (project / ".env.example").read_text(encoding="utf-8")
    assert "LLM_BASE_URL=" in env_example
    assert "LLM_API_KEY=" in env_example
    assert "LLM_MODEL=" in env_example


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
    "data",
    [
        {"background_tasks": "celery"},
        {"agent_capability": "langchain"},
        {"rate_limiting": "memcached"},
        {"rate_limiting": "memory", "rate_limit_requests": 0},
        {"rate_limiting": "memory", "rate_limit_period_seconds": 0},
    ],
)
def test_copier_rejects_invalid_capability_answers_before_rendering(
    tmp_path: Path, data: dict[str, object]
) -> None:
    destination = tmp_path / "invalid"

    with pytest.raises(ValueError):
        render_project(destination, data=data)

    assert not destination.exists()


def test_disabled_limiter_has_no_redis_question_or_generated_residue(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "disabled-limiter",
        data={"rate_limiting": "none"},
    )

    assert not (project / "app" / "core" / "redis.py").exists()
    assert not (project / "compose.yaml").exists()
    assert "REDIS_URL" not in (project / ".env.example").read_text(encoding="utf-8")


def test_taskiq_renders_background_task_capability_and_shared_redis(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "taskiq-service",
        data={"background_tasks": "taskiq"},
    )

    expected_paths = [
        "app/tasks/__init__.py",
        "app/tasks/taskiq.py",
        "compose.yaml",
    ]
    assert not [path for path in expected_paths if not (project / path).is_file()]
    task_files = {
        path.relative_to(project).as_posix()
        for path in (project / "app" / "tasks").iterdir()
        if path.is_file()
    }
    assert task_files == {"app/tasks/__init__.py", "app/tasks/taskiq.py"}

    deps = cast("list[str]", project_metadata(project)["dependencies"])
    dependency_names = {dep.partition(">=")[0].partition("[")[0] for dep in deps}
    assert {"redis", "taskiq", "taskiq-redis"} <= dependency_names
    assert {"arq", "celery", "prefect"}.isdisjoint(dependency_names)
    assert "REDIS_URL" in (project / ".env.example").read_text(encoding="utf-8")


def test_cache_renders_shared_redis_and_http_contract(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "cache-service",
        data={"enable_caching": True},
    )

    expected_paths = [
        "app/core/redis.py",
        "app/api/cache.py",
        "compose.yaml",
    ]
    assert not [path for path in expected_paths if not (project / path).is_file()]

    deps = cast("list[str]", project_metadata(project)["dependencies"])
    dependency_names = {dep.partition(">=")[0].partition("[")[0] for dep in deps}
    assert {"fastapi-cache2", "redis"} <= dependency_names
    assert "REDIS_URL" in (project / ".env.example").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("storage", "expects_redis"),
    [("memory", False), ("redis", True)],
)
def test_rate_limiter_renders_selected_storage(
    tmp_path: Path, storage: str, expects_redis: bool
) -> None:
    project = render_project(
        tmp_path / f"limiter-{storage}",
        data={
            "rate_limiting": storage,
            "rate_limit_requests": 2,
            "rate_limit_period_seconds": 1,
        },
    )

    assert (project / "app" / "core" / "rate_limit.py").is_file()
    assert (project / "app" / "api" / "rate_limit.py").is_file()
    assert (project / "tests" / "test_rate_limit.py").is_file()
    assert (project / "app" / "core" / "redis.py").exists() is expects_redis
    assert (project / "compose.yaml").exists() is expects_redis


def test_redis_consumers_share_one_configuration_and_deployment(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "combined-redis",
        data={
            "background_tasks": "taskiq",
            "enable_caching": True,
            "rate_limiting": "redis",
        },
    )

    env_example = (project / ".env.example").read_text(encoding="utf-8")
    compose = (project / "compose.yaml").read_text(encoding="utf-8")
    config = (project / "app" / "core" / "config.py").read_text(encoding="utf-8")
    deps = cast("list[str]", project_metadata(project)["dependencies"])
    dependency_names = [dep.partition(">=")[0].partition("[")[0] for dep in deps]

    assert env_example.count("REDIS_URL=") == 1
    assert config.count("redis_url:") == 1
    assert compose.count("  redis:") == 1
    assert dependency_names.count("redis") == 1
    assert (project / "app" / "core" / "redis.py").is_file()


@pytest.mark.parametrize("storage", ["memory", "redis"])
def test_rate_limiter_project_passes_http_runtime_contract(tmp_path: Path, storage: str) -> None:
    import os

    if storage == "redis" and shutil.which("docker") is None:
        pytest.skip("Docker is required for Redis smoke")
    project = render_project(
        tmp_path / f"limiter-runtime-{storage}",
        data={
            "rate_limiting": storage,
            "rate_limit_requests": 2,
            "rate_limit_period_seconds": 1,
        },
    )
    clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    subprocess.run(
        [UV, "sync", "--all-groups"],
        cwd=project,
        env=clean_env,
        check=True,
        text=True,
        capture_output=True,
    )
    container: str | None = None
    runtime_env = clean_env
    try:
        if storage == "redis":
            container = subprocess.run(
                ["docker", "run", "--rm", "-d", "-P", "redis:8-alpine"],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            port_output = subprocess.run(
                ["docker", "port", container, "6379/tcp"],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            redis_port = port_output.rsplit(":", 1)[1]
            runtime_env = clean_env | {"REDIS_URL": f"redis://127.0.0.1:{redis_port}/0"}

        result = subprocess.run(
            [
                UV,
                "run",
                "pytest",
                "tests/test_rate_limit.py",
                "-q",
                "--no-cov",
            ],
            cwd=project,
            env=runtime_env,
            text=True,
            capture_output=True,
            timeout=60,
        )
        assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    finally:
        if container is not None:
            subprocess.run(
                ["docker", "stop", container],
                check=False,
                text=True,
                capture_output=True,
            )


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is required for Redis smoke")
def test_cache_project_passes_http_runtime_contract(tmp_path: Path) -> None:
    import os

    project = render_project(
        tmp_path / "cache-runtime",
        data={"enable_caching": True},
    )
    clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    subprocess.run(
        [UV, "sync", "--all-groups"],
        cwd=project,
        env=clean_env,
        check=True,
        text=True,
        capture_output=True,
    )
    container = subprocess.run(
        ["docker", "run", "--rm", "-d", "-P", "redis:8-alpine"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    try:
        port_output = subprocess.run(
            ["docker", "port", container, "6379/tcp"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        redis_port = port_output.rsplit(":", 1)[1]
        runtime_env = clean_env | {"REDIS_URL": f"redis://127.0.0.1:{redis_port}/0"}
        result = subprocess.run(
            [
                UV,
                "run",
                "pytest",
                "tests/test_cache.py::test_cache_hit_and_invalidation_are_observable",
                "-q",
                "--no-cov",
            ],
            cwd=project,
            env=runtime_env,
            text=True,
            capture_output=True,
            timeout=60,
        )
        assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    finally:
        subprocess.run(
            ["docker", "stop", container],
            check=False,
            text=True,
            capture_output=True,
        )


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is required for Redis smoke")
def test_taskiq_worker_executes_task_and_scheduler_starts(tmp_path: Path) -> None:
    import os
    import time

    project = render_project(
        tmp_path / "taskiq-runtime",
        data={"background_tasks": "taskiq"},
    )
    clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
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
    container = subprocess.run(
        ["docker", "run", "--rm", "-d", "-P", "redis:8-alpine"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    worker: subprocess.Popen[str] | None = None
    scheduler: subprocess.Popen[str] | None = None
    try:
        port_output = subprocess.run(
            ["docker", "port", container, "6379/tcp"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        redis_port = port_output.rsplit(":", 1)[1]
        runtime_env = clean_env | {"REDIS_URL": f"redis://127.0.0.1:{redis_port}/0"}
        worker = subprocess.Popen(
            [str(python_exe), "-m", "taskiq", "worker", "app.tasks.taskiq:broker"],
            cwd=project,
            env=runtime_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        time.sleep(2)
        assert worker.poll() is None, worker.stdout.read() if worker.stdout else ""

        task_result = subprocess.run(
            [
                str(python_exe),
                "-c",
                (
                    "import asyncio\n"
                    "from app.tasks.taskiq import broker, example_task\n"
                    "async def run():\n"
                    "    await broker.startup()\n"
                    "    task = await example_task.kiq('worker-ok')\n"
                    "    result = await task.wait_result(timeout=10)\n"
                    "    print(result.return_value['value'])\n"
                    "    await broker.shutdown()\n"
                    "asyncio.run(run())\n"
                ),
            ],
            cwd=project,
            env=runtime_env,
            text=True,
            capture_output=True,
            timeout=20,
        )
        assert task_result.returncode == 0, task_result.stderr
        assert task_result.stdout.strip() == "worker-ok"

        scheduler = subprocess.Popen(
            [
                str(python_exe),
                "-m",
                "taskiq",
                "scheduler",
                "app.tasks.taskiq:scheduler",
            ],
            cwd=project,
            env=runtime_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        time.sleep(2)
        assert scheduler.poll() is None, scheduler.stdout.read() if scheduler.stdout else ""
    finally:
        for process in (scheduler, worker):
            if process is not None:
                process.terminate()
                process.wait(timeout=10)
        subprocess.run(
            ["docker", "stop", container],
            check=False,
            text=True,
            capture_output=True,
        )


@pytest.mark.parametrize(
    ("data", "needs_redis"),
    [
        ({"background_tasks": "taskiq"}, True),
        ({"agent_capability": "pydantic-ai"}, False),
        ({"enable_caching": True}, True),
        (
            {
                "rate_limiting": "memory",
                "rate_limit_requests": 2,
                "rate_limit_period_seconds": 1,
            },
            False,
        ),
        (
            {
                "rate_limiting": "redis",
                "rate_limit_requests": 2,
                "rate_limit_period_seconds": 1,
            },
            True,
        ),
        (
            {
                "background_tasks": "taskiq",
                "enable_caching": True,
                "rate_limiting": "redis",
                "rate_limit_requests": 2,
                "rate_limit_period_seconds": 1,
            },
            True,
        ),
    ],
    ids=["taskiq", "pydantic-ai", "cache", "memory-limiter", "redis-limiter", "combined"],
)
def test_representative_capability_project_quality(
    tmp_path: Path, data: dict[str, object], needs_redis: bool
) -> None:
    import os

    if needs_redis and shutil.which("docker") is None:
        pytest.skip("Docker is required for Redis acceptance")
    project = render_project(tmp_path / "quality", data=data)
    clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
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
    container: str | None = None
    runtime_env = clean_env
    try:
        if needs_redis:
            container = subprocess.run(
                ["docker", "run", "--rm", "-d", "-P", "redis:8-alpine"],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            port_output = subprocess.run(
                ["docker", "port", container, "6379/tcp"],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            redis_port = port_output.rsplit(":", 1)[1]
            runtime_env = clean_env | {"REDIS_URL": f"redis://127.0.0.1:{redis_port}/0"}

        commands = [
            [str(python_exe), "-m", "ruff", "check", "."],
            [str(python_exe), "-m", "ruff", "format", "--check", "."],
            [str(python_exe), "-m", "ty", "check"],
            [str(python_exe), "-m", "pytest", "-q"],
            [str(python_exe), "-c", "from app.main import app; assert app.title"],
        ]
        for command in commands:
            result = subprocess.run(
                command,
                cwd=project,
                env=runtime_env,
                text=True,
                capture_output=True,
                timeout=90,
            )
            assert result.returncode == 0, (
                f"{' '.join(command)} failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
    finally:
        if container is not None:
            subprocess.run(
                ["docker", "stop", container],
                check=False,
                text=True,
                capture_output=True,
            )


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
