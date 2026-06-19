"""Audit localized UI text keys that are actually used by handlers."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("en", "ru", "uz", "kz")


def _load_texts_and_tree() -> tuple[dict[str, dict[str, str]], ast.AST]:
    source = (ROOT / "bot" / "handlers.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in {"TEXTS", "TEXTS_UPDATE", "LIVE_TEXT_OVERRIDES"}:
                values[target.id] = ast.literal_eval(node.value)

    texts = values.get("TEXTS", {})
    for updates in (values.get("TEXTS_UPDATE", {}), values.get("LIVE_TEXT_OVERRIDES", {})):
        for language, language_updates in updates.items():
            texts.setdefault(language, {}).update(language_updates)
    return texts, tree


def _literal_string(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _collect_used_keys(tree: ast.AST) -> set[str]:
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"_get_text", "_text_html"} and node.args:
                key = _literal_string(node.args[0])
                if key:
                    keys.add(key)
        if isinstance(node, ast.Subscript):
            # Capture direct TEXTS["en"]["english"] style access used in language keyboards.
            outer_key = _literal_string(node.slice)
            if not outer_key:
                continue
            value = node.value
            if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name) and value.value.id == "TEXTS":
                keys.add(outer_key)
    return keys


def main() -> int:
    texts, tree = _load_texts_and_tree()
    used_keys = _collect_used_keys(tree)
    issues: list[str] = []

    for language in LANGUAGES:
        language_texts = texts.get(language, {})
        if not language_texts:
            issues.append(f"{language}: missing language dictionary")
            continue
        for key in sorted(used_keys):
            value = language_texts.get(key)
            if value is None:
                issues.append(f"{language}: missing used text key {key!r}")
                continue
            if value == key:
                issues.append(f"{language}: used text key {key!r} resolves to raw key")
            if isinstance(value, str) and ("???" in value or "**" in value):
                issues.append(f"{language}: used text key {key!r} contains placeholder or Markdown bold")

    print(f"Used localized keys checked: {len(used_keys)}")
    if issues:
        print("Localization key audit issues:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Localization key audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
