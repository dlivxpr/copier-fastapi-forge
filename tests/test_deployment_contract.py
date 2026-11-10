from __future__ import annotations

import http.client
import json
import ssl
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
import yaml

from tests.support.generation import GeneratedProject, minimal_answers, render_project


def _write_deployment_environment(
    project: GeneratedProject, filename: str, **overrides: str
) -> None:
    env_name = ".env.prod" if filename == "compose.prod.yaml" else ".env"
    content = project.read(f"deploy/{env_name}.example")
    keys = {line.partition("=")[0] for line in content.splitlines() if "=" in line}
    values = {
        "API_KEY": "deployment-contract-key",
        "POSTGRES_PASSWORD": "database-contract-password",
        "REDIS_PASSWORD": "redis-contract-password",
        "LLM_BASE_URL": "https://model.example.test/v1",
        "LLM_API_KEY": "model-contract-key",
        "LLM_MODEL": "contract-model",
        **overrides,
    }
    content += "\n" + "\n".join(f"{key}={value}" for key, value in values.items() if key in keys)
    (project.path / "deploy" / env_name).write_text(content + "\n", encoding="utf-8")


def _compose(
    project: GeneratedProject, filename: str, *command: str
) -> subprocess.CompletedProcess[str]:
    env_name = ".env.prod" if filename == "compose.prod.yaml" else ".env"
    return project.run(
        "docker",
        "compose",
        "--env-file",
        f"deploy/{env_name}",
        "-f",
        f"deploy/{filename}",
        *command,
        timeout=90,
    )


def _compose_config(project: GeneratedProject, filename: str) -> dict[str, Any]:
    result = _compose(project, filename, "config", "--format", "json")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


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


def _worker_pids(container_id: str) -> set[str]:
    result = _docker(
        "exec",
        container_id,
        "python",
        "-c",
        "from pathlib import Path; print(Path('/proc/1/task/1/children').read_text())",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return set(result.stdout.split())


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
    assert "gunicorn" not in disabled.read("pyproject.toml")
    assert "uvicorn-worker" not in disabled.read("pyproject.toml")

    minimal = render_project(
        tmp_path / "minimal-docker",
        minimal_answers(enable_docker=True, reverse_proxy="none", backend_port=8123),
    )
    deploy = minimal.path / "deploy"
    assert {path.name for path in deploy.glob("compose*.yaml")} == {
        "compose.yaml",
        "compose.prod.yaml",
    }
    for relative_path in (
        "Dockerfile",
        "Dockerfile.dockerignore",
        ".env.example",
        ".env.prod.example",
    ):
        assert (deploy / relative_path).is_file()
    assert not (deploy / "nginx.conf").exists()
    assert not (deploy / ".env").exists()
    assert not (deploy / ".env.prod").exists()
    for filename in ("compose.yaml", "compose.prod.yaml"):
        _write_deployment_environment(minimal, filename)
        compose = _compose_config(minimal, filename)
        assert set(compose["services"]) == {"app"}
        port = compose["services"]["app"]["ports"][0]
        assert port["target"] == 8123
        assert port["host_ip"] == "127.0.0.1"

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
    for filename in ("compose.yaml", "compose.prod.yaml"):
        _write_deployment_environment(retained, filename)
        services = _compose_config(retained, filename)["services"]
        assert set(services) == {"app", "db", "redis", "worker", "scheduler"}
        assert services["app"]["depends_on"]["db"]["condition"] == "service_healthy"
        assert services["app"]["depends_on"]["redis"]["condition"] == "service_healthy"
        for service_name in ("app", "worker", "scheduler"):
            environment = services[service_name]["environment"]
            assert environment["POSTGRES_HOST"] == "db"
            assert environment["REDIS_HOST"] == "redis"
            assert environment["TASKIQ_STREAM_NAME"] == "contract_service:taskiq"
            for url_name in ("TASKIQ_BROKER_URL", "TASKIQ_RESULT_BACKEND_URL"):
                assert urlsplit(environment[url_name]).password == environment["REDIS_PASSWORD"]


def test_deployment_environment_isolation_and_required_production_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = render_project(
        tmp_path / "environment-boundaries",
        minimal_answers(
            database="postgresql",
            enable_redis=True,
            background_tasks="taskiq",
            ai_framework="pydantic_ai",
            enable_logfire=True,
            enable_docker=True,
            reverse_proxy="none",
        ),
    )
    required = (
        "API_KEY",
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
    )
    for variable in required:
        monkeypatch.delenv(variable, raising=False)
    (project.path / ".env").write_text(
        "API_KEY=root-key-must-not-be-used\nPOSTGRES_PASSWORD=root-password\n",
        encoding="utf-8",
    )
    configurations = {}
    for filename in ("compose.yaml", "compose.prod.yaml"):
        _write_deployment_environment(project, filename, DB_POOL_SIZE="7")
        compose = _compose_config(project, filename)
        configurations[filename] = compose
        services = compose["services"]
        for name in ("app", "worker", "scheduler"):
            environment = services[name]["environment"]
            assert environment["API_KEY"] == "deployment-contract-key"
            assert environment["POSTGRES_PASSWORD"] == "database-contract-password"
            assert environment["LLM_API_KEY"] == "model-contract-key"
            assert environment["DB_POOL_SIZE"] == "7"
            assert environment["ENVIRONMENT"] == (
                "production" if filename == "compose.prod.yaml" else "local"
            )
            assert environment["DEBUG"] == ("false" if filename == "compose.prod.yaml" else "true")
        for name in ("db", "redis"):
            environment = services[name]["environment"]
            assert "API_KEY" not in environment
            assert "LLM_API_KEY" not in environment
        if filename == "compose.yaml":
            for name in ("app", "db", "redis"):
                assert all(port["host_ip"] == "127.0.0.1" for port in services[name]["ports"])
            assert services["app"]["volumes"]
        else:
            assert not services["db"].get("ports")
            assert not services["redis"].get("ports")
            for name in ("app", "worker", "scheduler"):
                assert not services[name].get("volumes")
            assert services["app"]["ports"][0]["host_ip"] == "127.0.0.1"
    assert configurations["compose.yaml"]["name"] == "contract_service_dev"
    assert configurations["compose.prod.yaml"]["name"] == "contract_service_prod"
    for volume_name in ("postgres_data", "redis_data"):
        assert (
            configurations["compose.yaml"]["volumes"][volume_name]["name"]
            != configurations["compose.prod.yaml"]["volumes"][volume_name]["name"]
        )

    for variable in required:
        _write_deployment_environment(project, "compose.prod.yaml", **{variable: ""})
        rejected = _compose(project, "compose.prod.yaml", "config", "--quiet")
        assert rejected.returncode != 0
        assert variable in rejected.stderr

    _write_deployment_environment(project, "compose.prod.yaml", BACKEND_BIND_HOST="0.0.0.0")
    exposed = _compose_config(project, "compose.prod.yaml")
    assert exposed["services"]["app"]["ports"][0]["host_ip"] == "0.0.0.0"

    (project.path / "deploy/.env.prod").unlink()
    missing = _compose(project, "compose.prod.yaml", "config", "--quiet")
    assert missing.returncode != 0
    assert ".env.prod" in missing.stderr


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

    workflow_text = project.read(".github/workflows/ci.yml")
    workflow = yaml.safe_load(workflow_text)
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["push"]["branches"] == ["main", "master"]
    assert triggers["pull_request"] is not None
    assert set(workflow["jobs"]) == {"lint", "test", "docker"}

    lint_steps = workflow["jobs"]["lint"]["steps"]
    lint_run_commands = [step.get("run", "") for step in lint_steps]
    assert any(command.startswith("uv sync") for command in lint_run_commands)
    assert any("ruff check app tests cli" in command for command in lint_run_commands)
    assert any("ruff format --check app tests cli" in command for command in lint_run_commands)
    assert any("ty check" in command for command in lint_run_commands)

    assert set(workflow["jobs"]["test"]["services"]) == {"postgres", "redis"}
    test_steps = workflow["jobs"]["test"]["steps"]
    test_run_commands = [step.get("run", "") for step in test_steps]
    assert any(command.startswith("uv sync") for command in test_run_commands)
    assert any("pytest tests" in command for command in test_run_commands)
    coverage_step = next(
        (step for step in test_steps if step.get("uses", "").startswith("codecov/codecov-action")),
        None,
    )
    assert coverage_step is not None
    assert coverage_step["with"]["fail_ci_if_error"] is False

    assert workflow["jobs"]["docker"]["needs"] == ["lint", "test"]
    assert "refs/heads/master" in workflow["jobs"]["docker"]["if"]
    assert coverage_step["with"]["files"] == "./coverage.xml"
    assert any("--cov-report=xml" in command for command in test_run_commands)
    assert any("--cov=app" in command for command in test_run_commands)
    assert any("--cov=cli" in command for command in test_run_commands)


@pytest.mark.docker
def test_container_image_and_external_nginx_run_on_random_ports(tmp_path: Path) -> None:
    info = _docker("info", timeout=30)
    assert info.returncode == 0, info.stderr
    suffix = uuid4().hex[:12]
    project = render_project(
        tmp_path / "docker-nginx",
        minimal_answers(
            project_name="container_contract",
            project_slug=f"container_{suffix}",
            enable_docker=True,
            reverse_proxy="nginx_external",
        ),
    )
    for relative_path in (".env", "deploy/.env", "deploy/.env.prod"):
        (project.path / relative_path).write_text(
            "API_KEY=must-not-enter-image\nMAX_UPLOAD_SIZE_MB=99\n", encoding="utf-8"
        )
    backend_port = 8000
    image = f"copier-fastapi-forge-contract:{suffix}"
    label = f"copier-fastapi-forge.contract={suffix}"
    network = f"copier-fastapi-forge-contract-{suffix}"
    backend_container = ""
    nginx_container = ""
    image_built = False
    network_created = False
    development_started = False
    development_image = ""
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
            "app",
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
        assert len(_worker_pids(backend_container)) == 2
        secrets = _docker(
            "exec",
            backend_container,
            "python",
            "-c",
            "import json; from pathlib import Path; "
            "print(json.dumps([name for name in ('.env', 'deploy/.env', 'deploy/.env.prod') "
            "if (Path('/app') / name).exists()]))",
            timeout=30,
        )
        assert secrets.returncode == 0, secrets.stderr
        assert json.loads(secrets.stdout) == []

        certificate_dir = tmp_path / "nginx-certificates"
        certificate_dir.mkdir()
        certificate = _docker(
            "run",
            "--rm",
            "--label",
            label,
            "--user",
            "0",
            "--volume",
            f"{certificate_dir.resolve().as_posix()}:/certificates",
            "--entrypoint",
            "openssl",
            image,
            "req",
            "-x509",
            "-nodes",
            "-newkey",
            "rsa:2048",
            "-keyout",
            "/certificates/key.pem",
            "-out",
            "/certificates/cert.pem",
            "-subj",
            "/CN=localhost",
            "-days",
            "1",
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

        _write_deployment_environment(project, "compose.yaml", BACKEND_PORT="0")
        development = _compose_config(project, "compose.yaml")
        development_image = development["services"]["app"]["image"]
        tagged = _docker("tag", image, development_image, timeout=30)
        assert tagged.returncode == 0, tagged.stderr
        development_started = True
        started = _compose(project, "compose.yaml", "up", "--detach", "--no-build", "app")
        assert started.returncode == 0, started.stderr
        app = _compose(project, "compose.yaml", "ps", "--quiet", "app")
        assert app.returncode == 0, app.stderr
        development_container = app.stdout.strip()
        development_port = _published_port(development_container, backend_port)
        assert _wait_for_http(development_port)[0] == 200
        before = _worker_pids(development_container)
        assert len(before) == 2
        (project.path / "app/api/health.py").touch()
        deadline = time.monotonic() + 30
        after = before
        while time.monotonic() < deadline:
            after = _worker_pids(development_container)
            if len(after) == 2 and after.isdisjoint(before):
                break
            time.sleep(0.5)
        assert len(after) == 2 and after.isdisjoint(before), (before, after)
        status, body = _wait_for_http(development_port)
        assert status == 200
        assert json.loads(body) == {"status": "healthy", "max_upload_size_mb": 50}
    finally:
        errors: list[str] = []
        for container_id in (nginx_container, backend_container):
            if container_id:
                removed = _docker("rm", "--force", container_id, timeout=30)
                if removed.returncode != 0:
                    errors.append(removed.stderr)
        if development_started:
            stopped = _compose(project, "compose.yaml", "down", "--volumes", "--remove-orphans")
            if stopped.returncode != 0:
                errors.append(stopped.stderr)
        if network_created:
            removed = _docker("network", "rm", network, timeout=30)
            if removed.returncode != 0:
                errors.append(removed.stderr)
        if image_built:
            images = (image, development_image) if development_image else (image,)
            removed = _docker("image", "rm", "--force", *images, timeout=60)
            if removed.returncode != 0:
                errors.append(removed.stderr)
        assert not errors, "\n".join(errors)
