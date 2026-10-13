from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from copier import run_copy
from plumbum import local

REPOSITORY_ROOT = Path(__file__).parents[2]

# Untracked junk that a real `git clone` source never renders but a verbatim
# working-tree copy would carry over.
_SNAPSHOT_IGNORE = shutil.ignore_patterns(
    ".git",
    ".copier-answers.yml",
    "__pycache__",
    "*.py[oc]",
    ".venv",
    ".ruff_cache",
    ".pytest_cache",
)

_active_template_source: Path | None = None


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
        # CI pins the root interpreter; generated projects select their own
        # Python version and must never install into the root environment.
        for name in ("VIRTUAL_ENV", "UV_PYTHON", "UV_PROJECT_ENVIRONMENT"):
            environment.pop(name, None)
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


def remove_generated_tree(path: Path) -> None:
    """Remove one generated tree, including Windows paths beyond MAX_PATH."""
    target = str(path.absolute())
    if os.name == "nt" and not target.startswith("\\\\?\\"):
        target = "\\\\?\\UNC\\" + target[2:] if target.startswith("\\\\") else "\\\\?\\" + target
    shutil.rmtree(target)


@contextmanager
def use_template_source(source: Path) -> Generator[Path]:
    """Bind the template source rendered by :func:`render_project`.

    The binding is ambient so every existing ``render_project`` call site keeps
    its ``(destination, data)`` signature; callers bind once per scope instead
    of threading a source path through every render. Nesting restores the
    outer binding.
    """
    global _active_template_source
    previous = _active_template_source
    _active_template_source = source
    try:
        yield source
    finally:
        _active_template_source = previous


@contextmanager
def template_snapshot() -> Generator[Path]:
    """Copy the current template once per test session, including uncommitted edits."""
    root = Path(tempfile.mkdtemp(prefix="forge-template-src."))
    try:
        shutil.copy2(REPOSITORY_ROOT / "copier.yml", root / "copier.yml")
        shutil.copytree(REPOSITORY_ROOT / "template", root / "template", ignore=_SNAPSHOT_IGNORE)
        yield root
    finally:
        remove_generated_tree(root)


def render_project(
    destination: Path,
    data: dict[str, object] | None = None,
) -> GeneratedProject:
    # Local Copier sources do not require Git. Keep its per-file Git probes out
    # of domain tests; the native CLI test separately covers the Git source path.
    with local.env(PATH=""):
        run_copy(
            str(_active_template_source or REPOSITORY_ROOT),
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
