from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml
from copier import run_copy

TEMPLATE_ROOT = Path(__file__).parents[1]


def render_project(destination: Path, data: dict[str, object]) -> Path:
    run_copy(
        src_path=str(TEMPLATE_ROOT),
        dst_path=str(destination),
        data=data,
        defaults=True,
        unsafe=False,
    )
    return destination


def project_answers(**overrides: object) -> dict[str, object]:
    answers: dict[str, object] = {
        "database": "none",
        "ai_framework": "none",
        "enable_logfire": False,
        "enable_cors": False,
        "enable_docker": False,
        "ci_type": "none",
        "background_tasks": "none",
        "enable_redis": False,
        "enable_caching": False,
        "enable_rate_limiting": False,
        "include_example_crud": False,
    }
    answers.update(overrides)
    return answers


def all_text(project: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in project.rglob("*") if path.is_file()
    )


def test_agent_and_logfire_generation_boundaries_follow_legacy_defaults(tmp_path: Path) -> None:
    config = yaml.safe_load((TEMPLATE_ROOT / "copier.yml").read_text(encoding="utf-8"))
    assert config["ai_framework"]["default"] == "pydantic_ai"
    assert config["enable_logfire"]["default"] is True
    assert config["enable_logfire"]["when"] == "[[ ai_framework == 'pydantic_ai' ]]"

    disabled = render_project(
        tmp_path / "disabled",
        project_answers(ai_framework="none", enable_logfire=True),
    )
    disabled_text = all_text(disabled)
    for relative_path in (
        "app/agents",
        "app/services/agent.py",
        "app/api/agent.py",
        "app/core/telemetry.py",
        "tests/test_agent.py",
    ):
        assert not (disabled / relative_path).exists()
    for marker in (
        "pydantic-ai",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LOGFIRE_TOKEN",
        "get_agent_service",
        "POST /agent/run",
    ):
        assert marker not in disabled_text

    enabled = render_project(
        tmp_path / "enabled",
        project_answers(ai_framework="pydantic_ai", enable_logfire=True),
    )
    enabled_app_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (enabled / "app").rglob("*.py")
        if path.is_file()
    )
    for relative_path in (
        "app/agents/assistant.py",
        "app/agents/prompts.py",
        "app/agents/utils.py",
        "app/services/agent.py",
        "app/api/agent.py",
        "app/core/telemetry.py",
        "tests/test_agent.py",
    ):
        assert (enabled / relative_path).is_file()

    enabled_text = all_text(enabled)
    for marker in (
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "OpenAIChatModel",
        "class AssistantAgent",
        "class Deps",
        "current_datetime",
        "# Personality",
        "# Answering",
        "# Output",
        "POST /agent/run",
        "POST /agent/stream",
    ):
        assert marker in enabled_text
    for excluded in (
        "configured_model",
        "AgentSession",
        "conversation_id",
        "message_history",
        "ask_user",
        "WebSocket",
        "OpenAIResponsesModel",
        "AnthropicModel",
        "GoogleModel",
        "OpenRouterModel",
    ):
        assert excluded not in enabled_app_text

    manifest = (enabled / "pyproject.toml").read_text(encoding="utf-8")
    assert '"pydantic-ai-slim[openai]>=' in manifest
    assert '"logfire>=' in manifest
    assert "logfire[" not in manifest


def run_project_command(
    project: Path,
    environment: dict[str, str],
    command: list[str],
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert result.returncode == 0, (
        f"{' '.join(command)} failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


def test_agent_and_logfire_pass_real_chat_completions_contract(tmp_path: Path) -> None:
    project = render_project(
        tmp_path / "runtime",
        project_answers(
            project_name="agent_service",
            project_slug="agent_service",
            ai_framework="pydantic_ai",
            enable_logfire=True,
        ),
    )
    environment = {
        **os.environ,
        "LOGFIRE_SEND_TO_LOGFIRE": "false",
    }

    run_project_command(project, environment, ["uv", "sync", "--all-groups"], timeout=600)
    run_project_command(project, environment, ["uv", "run", "ruff", "check", "."])
    run_project_command(project, environment, ["uv", "run", "ruff", "format", "--check", "."])
    run_project_command(project, environment, ["uv", "run", "ty", "check"])
    run_project_command(
        project,
        environment,
        ["uv", "run", "pytest", "tests/test_agent.py", "-q"],
    )
