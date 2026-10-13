from __future__ import annotations

import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class ServiceEndpoints:
    postgres_port: int | None = None
    redis_port: int | None = None
    postgres_container_id: str | None = None

    def environment(self, *, database: str = "postgres") -> dict[str, str]:
        values = {
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "postgres",
            "POSTGRES_DB": database,
            "REDIS_HOST": "127.0.0.1",
            "LOGFIRE_SEND_TO_LOGFIRE": "false",
        }
        if self.postgres_port is not None:
            values["POSTGRES_PORT"] = str(self.postgres_port)
        if self.redis_port is not None:
            values["REDIS_PORT"] = str(self.redis_port)
        return values

    def create_database(self, name: str) -> None:
        assert self.postgres_container_id is not None
        result = _run(
            "docker",
            "exec",
            self.postgres_container_id,
            "createdb",
            "-U",
            "postgres",
            name,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr


def _run(*command: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _published_port(container_id: str, container_port: int) -> int:
    result = _run("docker", "port", container_id, f"{container_port}/tcp", timeout=30)
    assert result.returncode == 0, result.stderr
    return int(result.stdout.strip().rsplit(":", maxsplit=1)[1])


def _cleanup(label: str) -> None:
    result = _run("docker", "ps", "--all", "--quiet", "--filter", f"label={label}", timeout=30)
    assert result.returncode == 0, result.stderr
    errors: list[str] = []
    for container_id in result.stdout.splitlines():
        removed = _run("docker", "rm", "--force", container_id, timeout=30)
        if removed.returncode != 0:
            errors.append(removed.stderr)
    remaining = _run("docker", "ps", "--all", "--quiet", "--filter", f"label={label}", timeout=30)
    assert remaining.returncode == 0, remaining.stderr
    if remaining.stdout.strip():
        errors.append(f"Containers were not removed: {remaining.stdout.strip()}")
    assert not errors, "\n".join(errors)


def _wait_for_services(postgres_id: str | None, redis_id: str | None) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        postgres_ready = postgres_id is None
        if postgres_id is not None:
            result = _run("docker", "exec", postgres_id, "pg_isready", "-U", "postgres", timeout=10)
            postgres_ready = result.returncode == 0
        redis_ready = redis_id is None
        if redis_id is not None:
            result = _run("docker", "exec", redis_id, "redis-cli", "ping", timeout=10)
            redis_ready = result.returncode == 0 and "PONG" in result.stdout
        if postgres_ready and redis_ready:
            return
        time.sleep(0.5)
    raise AssertionError("Required Docker services did not become ready")


@contextmanager
def managed_services(*, postgres: bool = False, redis: bool = False) -> Iterator[ServiceEndpoints]:
    suffix = uuid4().hex[:12]
    label = f"copier-fastapi-forge.acceptance={suffix}"
    postgres_id: str | None = None
    redis_id: str | None = None
    try:
        if postgres:
            result = _run(
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
            )
            assert result.returncode == 0, result.stderr
            postgres_id = result.stdout.strip()
        if redis:
            result = _run(
                "docker",
                "run",
                "--detach",
                "--label",
                label,
                "--publish",
                "127.0.0.1::6379",
                "redis:8-alpine",
            )
            assert result.returncode == 0, result.stderr
            redis_id = result.stdout.strip()
        _wait_for_services(postgres_id, redis_id)
        yield ServiceEndpoints(
            postgres_port=_published_port(postgres_id, 5432) if postgres_id else None,
            redis_port=_published_port(redis_id, 6379) if redis_id else None,
            postgres_container_id=postgres_id,
        )
    finally:
        _cleanup(label)
