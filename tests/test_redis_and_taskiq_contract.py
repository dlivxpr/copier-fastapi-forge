from __future__ import annotations

import os
import signal
import subprocess
import textwrap
import time
from pathlib import Path

import pytest
import yaml

from tests.support.generation import minimal_answers, render_project
from tests.support.processes import stop_process_group
from tests.support.services import ServiceEndpoints


def _redis_environment(endpoints: ServiceEndpoints) -> dict[str, str]:
    assert endpoints.redis_port is not None
    return {
        **endpoints.environment(),
        "TASKIQ_BROKER_URL": f"redis://127.0.0.1:{endpoints.redis_port}/1",
        "TASKIQ_RESULT_BACKEND_URL": f"redis://127.0.0.1:{endpoints.redis_port}/2",
    }


def test_redis_consumers_and_taskiq_have_independent_generation_boundaries(
    tmp_path: Path,
) -> None:
    minimal = render_project(tmp_path / "minimal", minimal_answers())
    for marker in (
        "RedisClient",
        "FastAPICache",
        "SlowAPIASGIMiddleware",
        "RedisStreamBroker",
        "REDIS_HOST",
        "TASKIQ_BROKER_URL",
    ):
        assert marker not in minimal.all_text()

    taskiq = render_project(
        tmp_path / "taskiq",
        minimal_answers(background_tasks="taskiq", enable_docker=True, ci_type="github"),
    )
    taskiq_text = taskiq.all_text()
    assert (taskiq.path / "app/worker/taskiq_app.py").is_file()
    assert not (taskiq.path / "app/clients/redis.py").exists()
    assert "TASKIQ_BROKER_URL" in taskiq_text
    assert "RedisStreamBroker" in taskiq_text
    assert "ListQueueBroker" not in taskiq_text
    assert "REDIS_HOST" not in taskiq_text
    assert "example_task" not in taskiq_text
    assert not (taskiq.path / "tests/test_tasks.py").exists()
    compose = yaml.safe_load(taskiq.read("deploy/compose.yaml"))
    assert compose["services"]["worker"]["command"] == [
        "python",
        "-m",
        "cli.commands",
        "taskiq",
        "worker",
    ]
    assert compose["services"]["scheduler"]["command"] == [
        "python",
        "-m",
        "cli.commands",
        "taskiq",
        "scheduler",
    ]
    assert "TASKIQ_RESULT_BACKEND_URL: redis://redis:6379/1" in taskiq.read("deploy/compose.yaml")
    for service_name in ("app", "worker", "scheduler"):
        service_environment = compose["services"][service_name]["environment"]
        assert service_environment["TASKIQ_STREAM_NAME"] == (
            "${TASKIQ_STREAM_NAME:-contract_service:taskiq}"
        )
        assert service_environment["TASKIQ_STREAM_MAXLEN"] == ("${TASKIQ_STREAM_MAXLEN:-100000}")
        assert service_environment["TASKIQ_STREAM_IDLE_TIMEOUT_MS"] == (
            "${TASKIQ_STREAM_IDLE_TIMEOUT_MS:-3600000}"
        )

    memory = render_project(
        tmp_path / "memory",
        minimal_answers(enable_rate_limiting=True, rate_limit_storage="memory"),
    )
    assert 'storage_uri="memory://"' in memory.all_text()
    assert "RedisClient" not in memory.all_text()
    assert "REDIS_HOST" not in memory.all_text()

    redis_rate_limit = render_project(
        tmp_path / "redis-rate-limit",
        minimal_answers(
            enable_redis=True,
            enable_rate_limiting=True,
            rate_limit_storage="redis",
        ),
    )
    assert "storage_uri=settings.REDIS_URL" in redis_rate_limit.all_text()
    assert (redis_rate_limit.path / "app/clients/redis.py").is_file()


@pytest.mark.service
def test_redis_cache_and_rate_limit_pass_real_public_behavior(
    tmp_path: Path,
    service_endpoints: ServiceEndpoints,
) -> None:
    project = render_project(
        tmp_path / "redis-consumers",
        minimal_answers(
            project_name="redis_contract",
            project_slug="redis_contract",
            enable_redis=True,
            enable_caching=True,
            enable_rate_limiting=True,
            rate_limit_storage="redis",
            rate_limit_requests=2,
            rate_limit_period=60,
        ),
    )
    environment = _redis_environment(service_endpoints)
    project.sync()
    project.assert_run("uv", "run", "pytest", "-q", env=environment)
    project.probe(
        textwrap.dedent(
            """
            import anyio
            from fastapi import APIRouter, Depends, Request
            from httpx import ASGITransport, AsyncClient

            from app.api.deps import Redis, verify_api_key
            from app.main import app
            from app.core.rate_limit import limiter

            router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_api_key)])

            @router.get("/redis-probe")
            @limiter.limit("2/minute")
            async def redis_probe(request: Request, redis: Redis) -> dict[str, str | None]:
                await redis.set("contract-key", "contract-value")
                value = await redis.get("contract-key")
                await redis.delete("contract-key")
                return {"value": value}

            app.include_router(router)

            async def verify() -> None:
                headers = {"X-API-Key": "change-me-in-production"}
                transport = ASGITransport(app=app, raise_app_exceptions=False)
                async with app.router.lifespan_context(app):
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        first = await client.get("/api/v1/redis-probe", headers=headers)
                        second = await client.get("/api/v1/redis-probe", headers=headers)
                        limited = await client.get("/api/v1/redis-probe", headers=headers)
                        assert first.status_code == second.status_code == 200
                        assert first.json() == {"value": "contract-value"}
                        assert limited.status_code == 429
                        ready = await client.get("/health/ready")
                        assert ready.status_code == 200
                        assert ready.json()["checks"]["redis"]["status"] == "healthy"

            anyio.run(verify)
            """
        ),
        env=environment,
    )


def _smoke_taskiq_process(
    project_path: Path,
    environment: dict[str, str],
    command: list[str],
    *,
    completion_marker: Path | None = None,
) -> None:
    process = subprocess.Popen(
        command,
        cwd=project_path,
        env={**os.environ, **environment},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )
    output = ""
    try:
        deadline = time.monotonic() + (20 if completion_marker is not None else 10)
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.communicate(timeout=5)[0]
                pytest.fail(
                    f"{' '.join(command)} exited during startup with "
                    f"{process.returncode}:\n{output}"
                )
            if completion_marker is not None and completion_marker.exists():
                time.sleep(0.5)
                break
            time.sleep(0.1 if completion_marker is not None else 0.5)
        else:
            if completion_marker is not None:
                pytest.fail(f"{' '.join(command)} did not deliver {completion_marker}")
    finally:
        forced = False
        if process.poll() is None:
            output, forced = stop_process_group(process)
    assert not forced, f"{' '.join(command)} required forced shutdown:\n{output}"
    expected = {0, 0xC000013A} if os.name == "nt" else {0, 1, 130, -signal.SIGINT}
    assert process.returncode in expected, output
    if process.returncode == 1:
        assert "Aborted!" in output


@pytest.mark.service
def test_taskiq_stream_delivery_recovery_and_process_lifecycle(
    tmp_path: Path,
    service_endpoints: ServiceEndpoints,
) -> None:
    slug = "taskiq_contract"
    project = render_project(
        tmp_path / "taskiq",
        minimal_answers(project_name=slug, project_slug=slug, background_tasks="taskiq"),
    )
    environment = _redis_environment(service_endpoints)
    project.sync()
    project.assert_run("uv", "run", "pytest", "-q", env=environment)

    taskiq_app = project.path / "app/worker/taskiq_app.py"
    taskiq_app.write_text(
        taskiq_app.read_text(encoding="utf-8")
        + textwrap.dedent(
            """

            from pathlib import Path


            @broker.task
            async def write_contract_marker(marker_path: str) -> None:
                Path(marker_path).write_text("delivered", encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )

    executable = f"{slug}.exe" if os.name == "nt" else slug
    cli = project.path / ".venv" / ("Scripts" if os.name == "nt" else "bin") / executable
    environment["PATH"] = f"{cli.parent}{os.pathsep}{os.environ['PATH']}"
    worker_command = [str(cli), "taskiq", "worker", "--workers=1"]

    prestart_marker = tmp_path / "prestart-delivered"
    prestart_environment = {
        **environment,
        "TASKIQ_STREAM_NAME": f"{slug}:prestart",
        "TASKIQ_STREAM_IDLE_TIMEOUT_MS": "100",
    }
    project.probe(
        textwrap.dedent(
            f"""
            import anyio
            from redis.asyncio import Redis

            from app.core.config import settings
            from app.worker.taskiq_app import broker, write_contract_marker


            async def prepare() -> None:
                client = Redis.from_url(settings.TASKIQ_BROKER_URL)
                try:
                    await client.delete(settings.TASKIQ_STREAM_NAME)
                    await broker.startup()
                    try:
                        await write_contract_marker.kiq({str(prestart_marker)!r})
                    finally:
                        await broker.shutdown()
                finally:
                    await client.aclose()


            anyio.run(prepare)
            """
        ),
        env=prestart_environment,
    )
    _smoke_taskiq_process(
        project.path,
        prestart_environment,
        worker_command,
        completion_marker=prestart_marker,
    )
    assert prestart_marker.read_text(encoding="utf-8") == "delivered"

    recovered_marker = tmp_path / "pending-recovered"
    recovery_environment = {
        **environment,
        "TASKIQ_STREAM_NAME": f"{slug}:recovery",
        "TASKIQ_STREAM_IDLE_TIMEOUT_MS": "100",
    }
    project.probe(
        textwrap.dedent(
            f"""
            import anyio
            from redis.asyncio import Redis

            from app.core.config import settings
            from app.worker.taskiq_app import broker, write_contract_marker


            async def prepare() -> None:
                client = Redis.from_url(settings.TASKIQ_BROKER_URL)
                try:
                    await client.delete(settings.TASKIQ_STREAM_NAME)
                    await client.xgroup_create(
                        settings.TASKIQ_STREAM_NAME,
                        "taskiq",
                        id="0-0",
                        mkstream=True,
                    )
                    await broker.startup()
                    try:
                        await write_contract_marker.kiq({str(recovered_marker)!r})
                        pending = await client.xreadgroup(
                            "taskiq",
                            "lost-worker",
                            streams={{settings.TASKIQ_STREAM_NAME: ">"}},
                            count=1,
                        )
                        assert len(pending) == 1
                    finally:
                        await broker.shutdown()
                finally:
                    await client.aclose()


            anyio.run(prepare)
            """
        ),
        env=recovery_environment,
    )
    time.sleep(0.2)
    _smoke_taskiq_process(
        project.path,
        recovery_environment,
        worker_command,
        completion_marker=recovered_marker,
    )
    assert recovered_marker.read_text(encoding="utf-8") == "delivered"

    _smoke_taskiq_process(
        project.path,
        environment,
        [str(cli), "taskiq", "scheduler"],
    )
