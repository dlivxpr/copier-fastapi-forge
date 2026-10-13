from __future__ import annotations

from pathlib import Path

from tests.support.generation import REPOSITORY_ROOT, minimal_answers, render_project


def test_agent_and_logfire_own_complete_generated_slices(tmp_path: Path) -> None:
    disabled = render_project(tmp_path / "disabled", minimal_answers())
    for relative_path in (
        "app/agents",
        "app/services/agent.py",
        "app/api/agent.py",
        "app/core/telemetry.py",
        "tests/test_agent.py",
    ):
        assert not (disabled.path / relative_path).exists()
    for marker in (
        "pydantic-ai",
        "LLM_BASE_URL",
        "LOGFIRE_TOKEN",
        "OpenAIChatModel",
        "instrument_pydantic_ai",
    ):
        assert marker not in disabled.all_text()

    enabled = render_project(
        tmp_path / "enabled",
        minimal_answers(ai_framework="pydantic_ai", enable_logfire=True),
    )
    for relative_path in (
        "app/agents/assistant.py",
        "app/agents/prompts.py",
        "app/services/agent.py",
        "app/api/agent.py",
        "app/core/telemetry.py",
        "tests/test_agent.py",
    ):
        assert (enabled.path / relative_path).is_file()
    text = enabled.all_text()
    for marker in (
        "pydantic-ai-slim[openai]>=",
        "OpenAIChatModel",
        "OpenAIProvider",
        "LLM_BASE_URL",
        "include_content=False",
        "include_binary_content=False",
        '"complete"',
        '"error"',
    ):
        assert marker in text
    for excluded in (
        "AgentSession",
        "conversation_id",
        "message_history",
        "WebSocket",
        "configured_model",
        "instrument_fastapi",
        "instrument_sqlalchemy",
        "instrument_redis",
        "instrument_taskiq",
        "instrument_httpx",
    ):
        assert excluded not in "\n".join(
            path.read_text(encoding="utf-8") for path in enabled.path.joinpath("app").rglob("*.py")
        )
    manifest = enabled.read("pyproject.toml")
    assert '"pydantic-ai-slim[openai]>=' in manifest
    assert '"logfire>=' in manifest
    assert "logfire[" not in manifest


def test_agent_json_sse_statelessness_and_telemetry_are_independently_exercised(
    tmp_path: Path,
) -> None:
    project = render_project(
        tmp_path / "runtime",
        minimal_answers(
            project_name="agent_contract",
            project_slug="agent_contract",
            ai_framework="pydantic_ai",
            enable_logfire=True,
        ),
    )
    environment = {"LOGFIRE_SEND_TO_LOGFIRE": "false"}
    project.sync()
    project.assert_run("uv", "run", "pytest", "tests/test_agent.py", "-q", env=environment)
    probe = (REPOSITORY_ROOT / "tests/support/probes/agent_contract.py.txt").read_text(
        encoding="utf-8"
    )
    project.probe(probe, env=environment)
