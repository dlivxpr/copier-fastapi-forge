from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.support.generation import remove_generated_tree, template_snapshot, use_template_source
from tests.support.services import ServiceEndpoints, managed_services


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "service: requires Docker-backed external services")
    config.addinivalue_line("markers", "docker: builds or validates deployment containers")


@pytest.fixture(scope="session", autouse=True)
def template_source() -> Iterator[None]:
    """Bind every harness render to one session-scoped template snapshot.

    Taken once at session start so uncommitted template edits still render
    without paying a git clone per render; the directory is removed at
    teardown. ``render_project`` callers outside pytest keep the repository
    root working tree.
    """
    with template_snapshot() as source, use_template_source(source):
        yield


@pytest.fixture(scope="session")
def environment_cleanup() -> Iterator[Callable[[Path], None]]:
    """Overlap environment removal with tests, waiting for all work at teardown."""
    futures: list[Future[None]] = []
    with ThreadPoolExecutor(max_workers=2) as executor:

        def remove_environment(path: Path) -> None:
            futures.append(executor.submit(remove_generated_tree, path))

        yield remove_environment
    for future in futures:
        future.result()


@pytest.fixture(autouse=True)
def _release_generated_environments(
    tmp_path: Path,
    environment_cleanup: Callable[[Path], None],
) -> Iterator[None]:
    """Keep rendered files for debugging without retaining thousands of venv files."""
    yield
    for environment in tmp_path.glob("*/.venv"):
        environment_cleanup(environment)


@pytest.fixture(scope="session")
def service_endpoints() -> Iterator[ServiceEndpoints]:
    with managed_services(postgres=True, redis=True) as endpoints:
        yield endpoints
