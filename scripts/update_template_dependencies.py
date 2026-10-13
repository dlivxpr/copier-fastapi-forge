# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "packaging>=25.0",
# ]
# ///

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).parents[1]
TEMPLATE_PYPROJECT = ROOT / "template" / "pyproject.toml.jinja"
MINIMUM_PYTHON = Version("3.12")
PYPI_SIMPLE_MEDIA_TYPE = "application/vnd.pypi.simple.v1+json"
REQUEST_TIMEOUT_SECONDS = 30

SECTION_PATTERN = re.compile(r"^\[([^]]+)]$")
ARRAY_START_PATTERN = re.compile(r"^[A-Za-z0-9_-]+\s*=\s*\[$")
ARRAY_REQUIREMENT_PATTERN = re.compile(r'^\s*"([^"]+)",\s*$')
INLINE_REQUIRES_PATTERN = re.compile(r"^requires\s*=\s*\[(.*)]$")
QUOTED_VALUE_PATTERN = re.compile(r'"([^"]+)"')


class UpdateError(Exception):
    """A dependency update error safe to show to the user."""


@dataclass(frozen=True)
class DeclaredDependency:
    raw: str
    name: str
    current_version: Version | None
    current_specifier: str | None


def parse_declared_dependency(raw: str) -> DeclaredDependency:
    try:
        requirement = Requirement(raw)
    except InvalidRequirement as exc:
        raise UpdateError(f"Invalid dependency requirement: {raw}") from exc

    if requirement.url is not None:
        raise UpdateError(f"Dependency must use a >= lower bound, not a URL: {raw}")

    specifiers = list(requirement.specifier)
    if not specifiers:
        return DeclaredDependency(
            raw=raw,
            name=requirement.name,
            current_version=None,
            current_specifier=None,
        )
    if len(specifiers) != 1 or specifiers[0].operator != ">=":
        raise UpdateError(f"Dependency must use exactly one >= lower bound: {raw}")

    try:
        current_version = Version(specifiers[0].version)
    except InvalidVersion as exc:
        raise UpdateError(f"Invalid dependency version in requirement: {raw}") from exc

    return DeclaredDependency(
        raw=raw,
        name=requirement.name,
        current_version=current_version,
        current_specifier=f">={specifiers[0].version}",
    )


def discover_dependencies(template: str) -> list[DeclaredDependency]:
    dependencies: list[DeclaredDependency] = []
    section = ""
    active_array = ""
    found_project_dependencies = False
    found_build_requires = False
    found_dependency_group = False

    for line_number, line in enumerate(template.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("[%") or stripped.startswith("#"):
            continue

        section_match = SECTION_PATTERN.fullmatch(stripped)
        if section_match and not active_array:
            section = section_match.group(1)
            continue

        if active_array:
            if stripped == "]":
                active_array = ""
                continue
            requirement_match = ARRAY_REQUIREMENT_PATTERN.fullmatch(line)
            if not requirement_match:
                raise UpdateError(f"Unexpected dependency entry on line {line_number}: {stripped}")
            dependencies.append(parse_declared_dependency(requirement_match.group(1)))
            continue

        if section == "project" and stripped == "dependencies = [":
            found_project_dependencies = True
            active_array = "project.dependencies"
            continue

        if section == "dependency-groups" and ARRAY_START_PATTERN.fullmatch(stripped):
            found_dependency_group = True
            active_array = "dependency-group"
            continue

        if section == "build-system":
            requires_match = INLINE_REQUIRES_PATTERN.fullmatch(stripped)
            if requires_match:
                raw_requirements = QUOTED_VALUE_PATTERN.findall(requires_match.group(1))
                if not raw_requirements:
                    raise UpdateError("[build-system].requires must not be empty")
                dependencies.extend(map(parse_declared_dependency, raw_requirements))
                found_build_requires = True

    if active_array:
        raise UpdateError(f"Unclosed dependency array: {active_array}")
    if not found_project_dependencies:
        raise UpdateError("Missing [project].dependencies")
    if not found_build_requires:
        raise UpdateError("Missing [build-system].requires")
    if not found_dependency_group:
        raise UpdateError("Missing [dependency-groups]")
    if not dependencies:
        raise UpdateError("No dependencies found")

    return dependencies


def fetch_json(url: str, accept: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "copier-fastapi-forge-template-dependency-updater",
        },
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except (HTTPError, URLError, HTTPException, TimeoutError, json.JSONDecodeError) as exc:
        raise UpdateError(f"PyPI request failed for {url}: {exc}") from exc

    if not isinstance(payload, dict):
        raise UpdateError(f"PyPI returned an invalid response for {url}")
    return payload


def release_files(name: str, raw_version: str) -> list[dict[str, Any]]:
    project = quote(canonicalize_name(name), safe="")
    version = quote(raw_version, safe="")
    payload = fetch_json(
        f"https://pypi.org/pypi/{project}/{version}/json",
        "application/json",
    )
    files = payload.get("urls")
    if not isinstance(files, list) or not all(isinstance(file, dict) for file in files):
        raise UpdateError(f"PyPI returned invalid release files for {name} {raw_version}")
    return files


def supports_minimum_python(files: Iterable[dict[str, Any]]) -> bool:
    for file in files:
        requires_python = file.get("requires_python")
        if requires_python is None:
            return True
        if not isinstance(requires_python, str):
            raise UpdateError("PyPI returned an invalid Requires-Python value")
        try:
            if SpecifierSet(requires_python).contains(MINIMUM_PYTHON, prereleases=True):
                return True
        except InvalidSpecifier as exc:
            raise UpdateError(f"PyPI returned invalid Requires-Python: {requires_python}") from exc
    return False


def latest_version(name: str) -> Version:
    project = quote(canonicalize_name(name), safe="")
    payload = fetch_json(
        f"https://pypi.org/simple/{project}/",
        PYPI_SIMPLE_MEDIA_TYPE,
    )
    raw_versions = payload.get("versions")
    if not isinstance(raw_versions, list) or not raw_versions:
        raise UpdateError(f"PyPI returned no versions for {name}")

    versions: list[tuple[Version, str]] = []
    for raw_version in raw_versions:
        if not isinstance(raw_version, str):
            raise UpdateError(f"PyPI returned an invalid version for {name}")
        try:
            versions.append((Version(raw_version), raw_version))
        except InvalidVersion as exc:
            raise UpdateError(f"PyPI returned invalid version for {name}: {raw_version}") from exc

    stable = sorted(
        (item for item in versions if not item[0].is_prerelease),
        reverse=True,
    )
    prerelease = sorted(
        (item for item in versions if item[0].is_prerelease),
        reverse=True,
    )

    for candidates in (stable, prerelease):
        for candidate, raw_candidate in candidates:
            files = release_files(name, raw_candidate)
            available_files = [file for file in files if file.get("yanked") is False]
            if not available_files:
                continue
            if not supports_minimum_python(available_files):
                raise UpdateError(
                    f"Latest release of {name} ({candidate}) does not support "
                    f"Python {MINIMUM_PYTHON}"
                )
            return candidate

    raise UpdateError(f"PyPI returned no non-yanked releases for {name}")


def replace_versions(
    template: str,
    dependencies: Iterable[DeclaredDependency],
    latest_versions: dict[str, Version],
) -> str:
    updated = template
    for dependency in dependencies:
        latest = latest_versions[canonicalize_name(dependency.name)]
        if dependency.current_version is not None and latest < dependency.current_version:
            raise UpdateError(
                f"Refusing to downgrade {dependency.name} from "
                f"{dependency.current_version} to {latest}"
            )
        if latest == dependency.current_version:
            continue

        if dependency.current_specifier is None:
            requirement, separator, marker = dependency.raw.partition(";")
            updated_requirement = f"{requirement}>={latest}"
            if separator:
                updated_requirement = f"{updated_requirement};{marker}"
        else:
            updated_requirement = dependency.raw.replace(
                dependency.current_specifier,
                f">={latest}",
                1,
            )
        quoted_current = f'"{dependency.raw}"'
        if quoted_current not in updated:
            raise UpdateError(f"Could not locate dependency requirement: {dependency.raw}")
        updated = updated.replace(quoted_current, f'"{updated_requirement}"')

    return updated


def write_atomically(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    try:
        template = TEMPLATE_PYPROJECT.read_text(encoding="utf-8")
        dependencies = discover_dependencies(template)

        latest_versions: dict[str, Version] = {}
        for dependency in dependencies:
            canonical_name = canonicalize_name(dependency.name)
            if canonical_name not in latest_versions:
                latest_versions[canonical_name] = latest_version(dependency.name)
            current = dependency.current_version or "unversioned"
            print(f"{dependency.name}: {current} -> {latest_versions[canonical_name]}")

        updated = replace_versions(template, dependencies, latest_versions)
        if updated == template:
            print("Template dependencies are already up to date")
            return 0

        write_atomically(TEMPLATE_PYPROJECT, updated)
        print(f"Updated {TEMPLATE_PYPROJECT.relative_to(ROOT)}")
        return 0
    except (OSError, UpdateError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
