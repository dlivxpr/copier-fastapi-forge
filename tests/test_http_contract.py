from __future__ import annotations

import json
import textwrap
from pathlib import Path

from tests.profiles import profile_answers
from tests.support.generation import REPOSITORY_ROOT, render_project


def test_normalized_openapi_matches_narrow_public_snapshot(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "openapi",
        profile_answers("all_retained_sqlalchemy"),
    )
    project.sync()
    collected = project.probe(
        textwrap.dedent(
            """
            import json
            import anyio
            from httpx import ASGITransport, AsyncClient

            from app.core.rate_limit import limiter
            from app.main import app

            limiter.enabled = False

            def normalized_openapi() -> dict:
                schema = app.openapi()
                operations = []
                for path, path_item in schema["paths"].items():
                    for method, operation in path_item.items():
                        if method not in {"get", "post", "patch", "delete"}:
                            continue
                        operations.append(
                            {
                                "path": path,
                                "method": method,
                                "security": "api_key" if operation.get("security") else "public",
                                "responses": sorted(operation["responses"]),
                            }
                        )
                return {
                    "operations": sorted(
                        operations, key=lambda item: (item["path"], item["method"])
                    ),
                    "security_schemes": schema["components"]["securitySchemes"],
                    "agent_stream_content": schema["paths"]["/agent/stream"]["post"]
                    ["responses"]["200"]["content"],
                    "agent_request": schema["components"]["schemas"]["AgentInvocationRequest"],
                    "required_schemas": [
                        name for name in ("ItemRead",) if name in schema["components"]["schemas"]
                    ],
                    "forbidden_schemas": [
                        name
                        for name in ("ErrorResponse",)
                        if name not in schema["components"]["schemas"]
                    ],
                }

            async def runtime_contract() -> dict:
                transport = ASGITransport(app=app, raise_app_exceptions=False)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    health = await client.get(
                        "/health", headers={"X-Request-ID": "contract-request"}
                    )
                    missing_item_key = await client.post(
                        "/api/v1/items", json={"name": "protected"}
                    )
                    wrong_agent_key = await client.post(
                        "/agent/run",
                        headers={"X-API-Key": "wrong"},
                        json={"input": "hello"},
                    )
                    deleted_routes = {
                        path: (
                            await client.get(
                                path,
                                headers={"X-API-Key": "change-me-in-production"},
                            )
                        ).status_code
                        for path in ("/api/v1/items", "/hello", "/limited", "/cache")
                    }
                return {
                    "health_status": health.status_code,
                    "health_body": health.json(),
                    "request_id": health.headers["X-Request-ID"],
                    "missing_item_key": {
                        "status": missing_item_key.status_code,
                        "body": missing_item_key.json(),
                        "content_type": missing_item_key.headers["content-type"],
                    },
                    "wrong_agent_key": {
                        "status": wrong_agent_key.status_code,
                        "body": wrong_agent_key.json(),
                    },
                    "deleted_routes": deleted_routes,
                }

            async def collect() -> None:
                print(json.dumps({
                    "openapi": normalized_openapi(),
                    "runtime": await runtime_contract(),
                }, sort_keys=True))

            anyio.run(collect)
            """
        ),
        env={"LOGFIRE_SEND_TO_LOGFIRE": "false"},
    )
    contract = json.loads(collected.stdout.strip().splitlines()[-1])
    observed = contract["openapi"]
    expected = json.loads(
        (REPOSITORY_ROOT / "tests/snapshots/openapi/all_retained.json").read_text(encoding="utf-8")
    )
    expected["operations"] = sorted(
        expected["operations"], key=lambda item: (item["path"], item["method"])
    )
    assert observed == expected
    assert contract["runtime"] == {
        "health_status": 200,
        "health_body": {"status": "healthy", "max_upload_size_mb": 50},
        "request_id": "contract-request",
        "missing_item_key": {
            "status": 401,
            "body": {
                "error": {
                    "code": "AUTHENTICATION_ERROR",
                    "message": "API Key header missing",
                    "details": None,
                }
            },
            "content_type": "application/json",
        },
        "wrong_agent_key": {
            "status": 403,
            "body": {
                "error": {
                    "code": "AUTHORIZATION_ERROR",
                    "message": "Invalid API Key",
                    "details": None,
                }
            },
        },
        "deleted_routes": {
            "/api/v1/items": 405,
            "/cache": 404,
            "/hello": 404,
            "/limited": 404,
        },
    }
