from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.support.services import ServiceEndpoints, managed_services


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "service: requires Docker-backed external services")
    config.addinivalue_line("markers", "docker: builds or validates deployment containers")


@pytest.fixture(scope="session")
def service_endpoints() -> Iterator[ServiceEndpoints]:
    with managed_services(postgres=True, redis=True) as endpoints:
        yield endpoints
