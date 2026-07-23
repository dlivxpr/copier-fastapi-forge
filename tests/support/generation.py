from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from copier import run_copy

REPOSITORY_ROOT = Path(__file__).parents[2]


@dataclass(frozen=True)
class GeneratedProject:
    """A rendered project exercised only through its own dependency environment."""

    path: Path

    def run(
        self,
        *command: str,
        env: dict[str, str] | None = None,
        timeout: int = 600,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        if env is not None:
            environment.update(env)
        return subprocess.run(
            command,
            cwd=self.path,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def assert_run(
        self,
        *command: str,
        env: dict[str, str] | None = None,
        timeout: int = 600,
    ) -> subprocess.CompletedProcess[str]:
        result = self.run(*command, env=env, timeout=timeout)
        assert result.returncode == 0, (
            f"{' '.join(command)} failed in {self.path}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        return result

    def sync(self) -> None:
        self.assert_run("uv", "sync", "--all-groups", timeout=1200)

    def probe(
        self,
        source: str,
        *,
        env: dict[str, str] | None = None,
        timeout: int = 600,
    ) -> subprocess.CompletedProcess[str]:
        return self.assert_run("uv", "run", "python", "-c", source, env=env, timeout=timeout)

    def read(self, relative_path: str) -> str:
        return (self.path / relative_path).read_text(encoding="utf-8")

    def all_text(self) -> str:
        return "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(self.path.rglob("*"))
            if path.is_file() and ".venv" not in path.parts
        )


def render_project(
    destination: Path,
    data: dict[str, object] | None = None,
) -> GeneratedProject:
    run_copy(
        str(REPOSITORY_ROOT),
        destination,
        data=data or {},
        defaults=True,
        unsafe=True,
        quiet=True,
    )
    return GeneratedProject(destination)


def minimal_answers(**overrides: object) -> dict[str, object]:
    answers: dict[str, object] = {
        "project_name": "contract_service",
        "project_slug": "contract_service",
        "project_description": "Contract service",
        "author_name": "Template Maintainer",
        "author_email": "maintainer@example.com",
        "timezone": "UTC",
        "python_version": "3.12",
        "backend_port": 8000,
        "database": "none",
        "background_tasks": "none",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": False,
        "ai_framework": "none",
        "enable_cors": False,
        "enable_docker": False,
        "ci_type": "none",
        "deployment_api_key": "change-me-in-production",
    }
    answers.update(overrides)
    return answers


def project_answers(**overrides: object) -> dict[str, object]:
    answers = minimal_answers(
        database="postgresql",
        orm_type="sqlalchemy",
        include_example_crud=False,
        db_pool_size=5,
        db_max_overflow=10,
        db_pool_timeout=30,
    )
    answers.update(overrides)
    return answers


def normalized_files(project: GeneratedProject) -> dict[str, str]:
    return {
        path.relative_to(project.path).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(project.path.rglob("*"))
        if path.is_file() and ".venv" not in path.parts
    }


def parse_toml_dependencies(project: GeneratedProject) -> str:
    return project.read("pyproject.toml").lower()


def assert_paths(project: GeneratedProject, paths: tuple[str, ...], *, present: bool) -> None:
    for relative_path in paths:
        assert (project.path / relative_path).exists() is present, relative_path


def assert_no_template_tokens(project: GeneratedProject) -> None:
    for content in normalized_files(project).values():
        assert "[[" not in content
        assert "[%" not in content


def command_environment(**values: Any) -> dict[str, str]:
    return {key: str(value) for key, value in values.items()}
