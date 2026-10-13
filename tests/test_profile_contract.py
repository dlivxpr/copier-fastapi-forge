from __future__ import annotations

from pathlib import Path

import pytest

from tests.profiles import DEEP_PROFILES, PROFILE_STATES, profile_answers
from tests.support.generation import render_project
from tests.support.services import ServiceEndpoints


@pytest.mark.service
@pytest.mark.parametrize("profile_name", DEEP_PROFILES)
def test_named_profile_passes_generated_development_and_runtime_interfaces(
    tmp_path: Path,
    service_endpoints: ServiceEndpoints,
    profile_name: str,
) -> None:
    project = render_project(tmp_path / profile_name, profile_answers(profile_name))
    state = PROFILE_STATES[profile_name]
    database = f"profile_{profile_name}"
    environment = service_endpoints.environment(database=database)
    assert service_endpoints.redis_port is not None
    environment.update(
        {
            "REDIS_PASSWORD": "",
            "REDIS_DB": "0",
            "TASKIQ_BROKER_URL": f"redis://127.0.0.1:{service_endpoints.redis_port}/1",
            "TASKIQ_RESULT_BACKEND_URL": (f"redis://127.0.0.1:{service_endpoints.redis_port}/2"),
        }
    )
    if state["database"] == "postgresql":
        service_endpoints.create_database(database)

    project.sync()
    for command in (
        ("uv", "run", "ruff", "check", "."),
        ("uv", "run", "ruff", "format", "--check", "."),
        ("uv", "run", "ty", "check"),
    ):
        project.assert_run(*command, env=environment)
    if state["database"] == "postgresql":
        project.assert_run("uv", "run", "profile_service", "db", "upgrade", env=environment)
    project.assert_run("uv", "run", "pytest", "-q", env=environment, timeout=900)
    routes = project.assert_run("uv", "run", "profile_service", "server", "routes", env=environment)
    for path in ("/health", "/health/live", "/health/ready"):
        assert path in routes.stdout
