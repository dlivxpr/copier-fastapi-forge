from __future__ import annotations

import argparse
import subprocess
import tomllib
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).parents[1]
PROTECTED_FILES = (
    Path("docs/migration-traceability.toml"),
    Path("tests/migration-equivalence.toml"),
    Path("tests/pairwise-equivalence.toml"),
)


def ensure_append_only(
    base: Any,
    current: Any,
    path: tuple[str, ...] = (),
) -> None:
    location = ".".join(path) or "<root>"
    if isinstance(base, dict):
        if not isinstance(current, dict):
            raise ValueError(f"Protected value changed type at {location}")
        for key, value in base.items():
            if key not in current:
                raise ValueError(f"Protected key was removed at {location}.{key}")
            ensure_append_only(value, current[key], (*path, str(key)))
        return
    if isinstance(base, list):
        if not isinstance(current, list) or len(current) < len(base):
            raise ValueError(f"Protected list was shortened at {location}")
        for index, value in enumerate(base):
            ensure_append_only(value, current[index], (*path, str(index)))
        return
    if base != current:
        raise ValueError(f"Protected value changed at {location}")


def _read_base_file(base_ref: str, path: Path) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{base_ref}:{path.as_posix()}"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout if result.returncode == 0 else None


def check_migration_goldens(base_ref: str) -> None:
    verified = subprocess.run(
        ["git", "rev-parse", "--verify", base_ref],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if verified.returncode != 0:
        raise ValueError(f"Unknown base ref {base_ref}: {verified.stderr.strip()}")

    for relative_path in PROTECTED_FILES:
        base_content = _read_base_file(base_ref, relative_path)
        if base_content is None:
            continue
        current_content = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        ensure_append_only(
            tomllib.loads(base_content),
            tomllib.loads(current_content),
            (relative_path.as_posix(),),
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reject edits or removals of existing migration golden entries."
    )
    parser.add_argument("base_ref", help="Git ref used as the append-only baseline")
    arguments = parser.parse_args()
    check_migration_goldens(arguments.base_ref)
    print(f"Migration goldens are append-only relative to {arguments.base_ref}")


if __name__ == "__main__":
    main()
