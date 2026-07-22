from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, StrictUndefined, TemplateSyntaxError

ROOT = Path(__file__).parents[1]
TEMPLATE_ROOT = ROOT / "template"


def template_environment() -> Environment:
    return Environment(
        block_start_string="[%",
        block_end_string="%]",
        variable_start_string="[[",
        variable_end_string="]]",
        comment_start_string="[#",
        comment_end_string="#]",
        undefined=StrictUndefined,
        autoescape=False,
    )


def lint_template() -> list[str]:
    environment = template_environment()
    errors: list[str] = []

    for path in sorted(TEMPLATE_ROOT.rglob("*")):
        if path.is_dir():
            continue
        relative_path = path.relative_to(TEMPLATE_ROOT)
        try:
            for part in relative_path.parts:
                environment.parse(part)
            if path.suffix == ".jinja":
                environment.parse(path.read_text(encoding="utf-8"))
        except (TemplateSyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"{relative_path.as_posix()}: {exc}")

    return errors


def main() -> int:
    errors = lint_template()
    if errors:
        print("\n".join(errors))
        return 1
    print("Template syntax check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
