from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).parents[1]
SCRIPT = runpy.run_path(str(REPOSITORY_ROOT / "scripts" / "check_migration_goldens.py"))
ensure_append_only = cast(Callable[[Any, Any], None], SCRIPT["ensure_append_only"])


def test_ci_enforces_append_only_goldens_for_pull_requests_and_pushes() -> None:
    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["template-quality"]["steps"]
    by_name = {step.get("name"): step for step in steps}

    assert by_name["Migration goldens are append-only"]["if"] == (
        "github.event_name == 'pull_request'"
    )
    assert (
        "github.event.pull_request.base.sha" in by_name["Migration goldens are append-only"]["run"]
    )
    assert (
        "github.event_name == 'push'" in by_name["Migration goldens are append-only on push"]["if"]
    )
    assert "github.event.before" in by_name["Migration goldens are append-only on push"]["run"]


def test_append_only_gate_accepts_new_keys_and_records() -> None:
    base = {
        "protected": {"path": {"sha256": "fixed"}},
        "target": [{"target": "app/main.py", "approved": ["fixed"]}],
    }
    current = {
        "protected": {
            "path": {"sha256": "fixed"},
            "new-path": {"sha256": "new"},
        },
        "target": [
            {"target": "app/main.py", "approved": ["fixed"]},
            {"target": "app/new.py", "approved": ["new"]},
        ],
    }

    ensure_append_only(base, current)


@pytest.mark.parametrize(
    "current",
    [
        {"protected": {"path": {"sha256": "changed"}}},
        {"protected": {}},
        {
            "protected": {"path": {"sha256": "fixed"}},
            "target": [{"target": "replacement.py"}],
        },
    ],
)
def test_append_only_gate_rejects_changed_removed_or_reordered_values(
    current: dict[str, object],
) -> None:
    base = {
        "protected": {"path": {"sha256": "fixed"}},
        "target": [{"target": "app/main.py"}],
    }

    with pytest.raises(ValueError, match="Protected"):
        ensure_append_only(base, current)
