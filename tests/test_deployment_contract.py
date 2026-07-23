from __future__ import annotations

import http.client
import json
import ssl
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from tests.support.generation import GeneratedProject, minimal_answers, render_project


def _compose_config(project: GeneratedProject, filename: str) -> None:
    project.assert_run(
        "docker", "compose", "-f", f"deploy/{filename}", "config", "--quiet", timeout=60
    )


def _docker(*command: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("docker", *command),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _published_port(container_id: str, container_port: int) -> int:
    result = _docker("port", container_id, f"{container_port}/tcp", timeout=30)
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
                    "127.0.0.1", port, timeout=2, context=context
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


def test_docker_compose_and_capability_conditions_are_public_contract(tmp_path: Path) -> None:
    disabled = render_project(tmp_path / "disabled", minimal_answers())
    assert not (disabled.path / "deploy").exists()
    assert "docker compose" not in disabled.all_text().lower()

    minimal = render_project(
        tmp_path / "minimal-docker",
        minimal_answers(enable_docker=True, reverse_proxy="none", backend_port=8123),
    )
    deploy = minimal.path / "deploy"
    for relative_path in (
        "Dockerfile",
        "Dockerfile.dockerignore",
        "compose.yaml",
        "compose.dev.yaml",
        "compose.prod.yaml",
    ):
        assert (deploy / relative_path).is_file()
    assert not (deploy / "nginx.conf").exists()
    dockerfile = minimal.read("deploy/Dockerfile")
    for marker in (
        " AS builder",
        "FROM python:3.12-slim",
        "USER appuser",
        "HEALTHCHECK",
        "urllib.request.urlopen('http://127.0.0.1:8123/health')",
        'CMD ["python", "-m", "cli.commands", "server", "run"',
        '"8123"]',
        "COPY . /app",
    ):
        assert marker in dockerfile
    assert "COPY app ./app" not in dockerfile
    assert "httpx" not in dockerfile
    assert ".env*" in minimal.read("deploy/Dockerfile.dockerignore")

    for filename in ("compose.yaml", "compose.dev.yaml", "compose.prod.yaml"):
        _compose_config(minimal, filename)
        compose = yaml.safe_load(minimal.read(f"deploy/{filename}"))
        assert set(compose["services"]) == {"app"}
        assert compose["services"]["app"]["build"] == {
            "context": "..",
            "dockerfile": "deploy/Dockerfile",
        }

    retained = render_project(
        tmp_path / "retained",
        minimal_answers(
            database="postgresql",
            orm_type="sqlalchemy",
            background_tasks="taskiq",
            enable_redis=True,
            enable_caching=True,
            enable_rate_limiting=True,
            rate_limit_storage="redis",
            enable_docker=True,
            reverse_proxy="nginx_external",
        ),
    )
    expected_services = {"app", "db", "redis", "worker", "scheduler"}
    for filename in ("compose.yaml", "compose.dev.yaml", "compose.prod.yaml"):
        _compose_config(retained, filename)
        compose = yaml.safe_load(retained.read(f"deploy/{filename}"))
        assert set(compose["services"]) == expected_services
        assert compose["services"]["db"]["image"] == "postgres:16-alpine"
        assert compose["services"]["redis"]["image"] == "redis:7-alpine"
        assert compose["services"]["app"]["depends_on"]["db"]["condition"] == "service_healthy"
        assert compose["services"]["app"]["depends_on"]["redis"]["condition"] == ("service_healthy")
        assert compose["services"]["app"]["environment"]["POSTGRES_HOST"] == "db"
        assert "DATABASE_URL" not in compose["services"]["app"]["environment"]
        assert compose["services"]["worker"]["command"][:5] == [
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


def test_external_nginx_and_generated_workflow_have_documented_structure(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "delivery",
        minimal_answers(
            database="postgresql",
            orm_type="sqlalchemy",
            enable_docker=True,
            reverse_proxy="nginx_external",
            ci_type="github",
            background_tasks="taskiq",
            enable_redis=True,
        ),
    )
    nginx = project.read("deploy/nginx.conf")
    for marker in (
        "listen 80",
        "return 301 https://$host$request_uri",
        "location /.well-known/acme-challenge/",
        "listen 443 ssl",
        "ssl_certificate",
        "add_header X-Content-Type-Options",
        "add_header X-Frame-Options",
        "server host.docker.internal:8000",
        "X-Forwarded-For",
        "X-Forwarded-Proto",
        "proxy_connect_timeout",
        "proxy_read_timeout",
        "proxy_send_timeout",
    ):
        assert marker in nginx
    for removed in ("frontend", "websocket", "flower", "127.0.0.1:8000"):
        assert removed not in nginx.lower()

    workflow_text = project.read(".github/workflows/ci.yml")
    workflow = yaml.safe_load(workflow_text)
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["push"]["branches"] == ["main", "master"]
    assert triggers["pull_request"] is not None
    assert set(workflow["jobs"]) == {"lint", "test", "docker"}
    assert set(workflow["jobs"]["test"]["services"]) == {"postgres", "redis"}
    assert workflow["jobs"]["docker"]["needs"] == ["lint", "test"]
    assert "refs/heads/master" in workflow["jobs"]["docker"]["if"]
    for marker in (
        "actions/checkout@v7",
        "astral-sh/setup-uv@v9.0.0",
        "coverage.xml",
        "--cov=cli",
        "--cov-fail-under=0",
        "codecov/codecov-action",
        "fail_ci_if_error: false",
        "uv run ruff check app tests cli",
        "uv run ruff format --check app tests cli",
    ):
        assert marker in workflow_text
    for removed in ("compileall", "runtime smoke", "pip-audit", "trivy"):
        assert removed not in workflow_text.lower()


@pytest.mark.docker
def test_container_image_and_external_nginx_run_on_random_ports(tmp_path: Path) -> None:
    info = _docker("info", timeout=30)
    assert info.returncode == 0, info.stderr
    project = render_project(
        tmp_path / "docker-nginx",
        minimal_answers(
            project_name="container_contract",
            project_slug="container_contract",
            enable_docker=True,
            reverse_proxy="nginx_external",
        ),
    )
    backend_port = 8000
    suffix = uuid4().hex[:12]
    image = f"copier-fastapi-forge-contract:{suffix}"
    label = f"copier-fastapi-forge.contract={suffix}"
    network = f"copier-fastapi-forge-contract-{suffix}"
    backend_container = ""
    nginx_container = ""
    image_built = False
    network_created = False
    try:
        build = project.run(
            "docker",
            "build",
            "--tag",
            image,
            "--file",
            "deploy/Dockerfile",
            ".",
            timeout=900,
        )
        assert build.returncode == 0, build.stderr
        image_built = True
        created = _docker("network", "create", "--label", label, network, timeout=30)
        assert created.returncode == 0, created.stderr
        network_created = True
        backend = _docker(
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
            timeout=60,
        )
        assert backend.returncode == 0, backend.stderr
        backend_container = backend.stdout.strip()
        status, body = _wait_for_http(_published_port(backend_container, backend_port))
        assert status == 200
        assert json.loads(body) == {"status": "healthy", "max_upload_size_mb": 50}

        certificate_dir = tmp_path / "nginx-certificates"
        certificate_dir.mkdir()
        certificate = subprocess.run(
            (
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
            ),
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert certificate.returncode == 0, certificate.stderr
        nginx = _docker(
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
            f"{(project.path / 'deploy/nginx.conf').resolve().as_posix()}"
            ":/etc/nginx/conf.d/default.conf:ro",
            "--volume",
            f"{certificate_dir.resolve().as_posix()}:/etc/nginx/ssl:ro",
            "nginx:1.27-alpine",
            timeout=60,
        )
        assert nginx.returncode == 0, nginx.stderr
        nginx_container = nginx.stdout.strip()
        config = _docker("exec", nginx_container, "nginx", "-t", timeout=30)
        assert config.returncode == 0, config.stderr
        status, body = _wait_for_http(_published_port(nginx_container, 443), tls=True)
        assert status == 200
        assert json.loads(body) == {"status": "healthy", "max_upload_size_mb": 50}
        connection = http.client.HTTPConnection(
            "127.0.0.1", _published_port(nginx_container, 80), timeout=5
        )
        connection.request("GET", "/health")
        response = connection.getresponse()
        response.read()
        connection.close()
        assert response.status == 301
        assert response.headers["Location"].startswith("https://")
    finally:
        errors: list[str] = []
        for container_id in (nginx_container, backend_container):
            if container_id:
                removed = _docker("rm", "--force", container_id, timeout=30)
                if removed.returncode != 0:
                    errors.append(removed.stderr)
        if network_created:
            removed = _docker("network", "rm", network, timeout=30)
            if removed.returncode != 0:
                errors.append(removed.stderr)
        if image_built:
            removed = _docker("image", "rm", "--force", image, timeout=60)
            if removed.returncode != 0:
                errors.append(removed.stderr)
        assert not errors, "\n".join(errors)
