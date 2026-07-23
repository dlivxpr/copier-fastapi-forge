from __future__ import annotations

import os
import signal
import subprocess
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


def run_project_command(
    project: Path,
    environment: dict[str, str],
    command: list[str],
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
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
        f"{' '.join(command)} failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


def test_issue_9_generation_boundaries(tmp_path: Path) -> None:
    config = yaml.safe_load((TEMPLATE_ROOT / "copier.yml").read_text(encoding="utf-8"))
    assert config["enable_redis"]["default"] is False
    assert config["enable_caching"]["default"] is False
    assert config["enable_rate_limiting"]["default"] is False
    assert config["background_tasks"]["default"] == "none"

    minimal = render_project(tmp_path / "minimal", project_answers())
    minimal_text = "\n".join(
        path.read_text(encoding="utf-8") for path in minimal.rglob("*") if path.is_file()
    )
    for marker in (
        "RedisClient",
        "FastAPICache",
        "SlowAPIASGIMiddleware",
        "ListQueueBroker",
        "REDIS_HOST",
        "TASKIQ_BROKER_URL",
    ):
        assert marker not in minimal_text

    taskiq = render_project(
        tmp_path / "taskiq",
        project_answers(
            background_tasks="taskiq",
            enable_docker=True,
            ci_type="github",
        ),
    )
    taskiq_text = "\n".join(
        path.read_text(encoding="utf-8") for path in taskiq.rglob("*") if path.is_file()
    )
    assert (taskiq / "app" / "worker" / "taskiq_app.py").is_file()
    assert not (taskiq / "app" / "clients" / "redis.py").exists()
    assert "TASKIQ_BROKER_URL" in taskiq_text
    assert "REDIS_HOST" not in taskiq_text
    assert "example_task" not in taskiq_text
    assert not (taskiq / "tests" / "test_tasks.py").exists()
    compose = (taskiq / "deploy" / "compose.yaml").read_text(encoding="utf-8")
    workflow = (taskiq / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    compose_config = yaml.safe_load(compose)
    assert compose_config["services"]["worker"]["command"] == [
        "python",
        "-m",
        "cli.commands",
        "taskiq",
        "worker",
    ]
    assert compose_config["services"]["scheduler"]["command"] == [
        "python",
        "-m",
        "cli.commands",
        "taskiq",
        "scheduler",
    ]
    assert "TASKIQ_RESULT_BACKEND_URL: redis://redis:6379/1" in compose
    assert "image: redis:7-alpine" in workflow


def test_memory_rate_limit_uses_no_redis(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "memory",
        project_answers(enable_rate_limiting=True, rate_limit_storage="memory"),
    )
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in project.rglob("*") if path.is_file()
    )

    assert 'storage_uri="memory://"' in text
    assert "RedisClient" not in text
    assert "REDIS_HOST" not in text
    assert not (project / "app" / "clients" / "redis.py").exists()


@pytest.fixture(scope="module")
def redis_server() -> Iterator[tuple[str, int]]:
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--detach",
            "--publish",
            "127.0.0.1::6379",
            "redis:8-alpine",
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
            ["docker", "port", container_id, "6379/tcp"],
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
                ["docker", "exec", container_id, "redis-cli", "ping"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if ready.returncode == 0 and ready.stdout.strip() == "PONG":
                break
            time.sleep(0.5)
        else:
            pytest.fail("Redis container did not become ready")

        yield container_id, port
    finally:
        removed = subprocess.run(
            ["docker", "rm", "--force", container_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert removed.returncode == 0, removed.stderr


def redis_environment(port: int) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)
    environment.update(
        {
            "REDIS_HOST": "127.0.0.1",
            "REDIS_PORT": str(port),
            "TASKIQ_BROKER_URL": f"redis://127.0.0.1:{port}/1",
            "TASKIQ_RESULT_BACKEND_URL": f"redis://127.0.0.1:{port}/2",
        }
    )
    return environment


def test_redis_consumers_pass_real_redis_contract(
    tmp_path: Path,
    redis_server: tuple[str, int],
) -> None:
    _, port = redis_server
    project = render_project(
        tmp_path / "redis-consumers",
        project_answers(
            project_name="issue_9_redis",
            project_slug="issue_9_redis",
            enable_redis=True,
            enable_caching=True,
            enable_rate_limiting=True,
            rate_limit_storage="redis",
        ),
    )
    environment = redis_environment(port)

    for command in (
        ["uv", "sync", "--all-groups"],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "ty", "check"],
        ["uv", "run", "pytest", "-q"],
    ):
        run_project_command(project, environment, command)


def stop_process_group(process: subprocess.Popen[str]) -> tuple[str, bool]:
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
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
        stdout, _ = process.communicate(timeout=30)
    return stdout, forced


def smoke_taskiq_process(
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
                message = (
                    f"{' '.join(command)} exited during startup with "
                    f"{process.returncode}:\n{output}"
                )
                pytest.fail(message)
            time.sleep(0.5)
    finally:
        forced = False
        if process.poll() is None:
            output, forced = stop_process_group(process)
    assert not forced, f"{' '.join(command)} required a forced shutdown:\n{output}"
    expected_return_codes = {0, 0xC000013A} if os.name == "nt" else {0, 130, -signal.SIGINT}
    assert process.returncode in expected_return_codes, output


def test_taskiq_process_commands_start_and_stop_against_real_redis(
    tmp_path: Path,
    redis_server: tuple[str, int],
) -> None:
    _, port = redis_server
    project = render_project(
        tmp_path / "taskiq",
        project_answers(
            project_name="issue_9_taskiq",
            project_slug="issue_9_taskiq",
            background_tasks="taskiq",
        ),
    )
    environment = redis_environment(port)

    run_project_command(project, environment, ["uv", "sync", "--all-groups"])
    run_project_command(project, environment, ["uv", "run", "pytest", "-q"])
    executable = "issue_9_taskiq.exe" if os.name == "nt" else "issue_9_taskiq"
    cli = project / ".venv" / ("Scripts" if os.name == "nt" else "bin") / executable
    environment["PATH"] = f"{cli.parent}{os.pathsep}{environment['PATH']}"
    for args in (
        ["taskiq", "worker", "--workers=1"],
        ["taskiq", "scheduler"],
    ):
        smoke_taskiq_process(
            project,
            environment,
            [str(cli), *args],
        )
