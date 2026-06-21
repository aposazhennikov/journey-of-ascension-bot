"""Audit production message formatters for Telegram limits and media paths.

This is intentionally separate from the UX simulator. The simulator renders a
browser-friendly model; this script imports the real formatter functions used by
the bot and checks the constraints that usually fail only at Telegram runtime.
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("en", "ru", "uz", "kz")
TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_TEXT_LIMIT = 4096
SUPPORTED_TAGS = ("b", "i")


def _parse_point_selector(value: str) -> tuple[str, int]:
    """Parse meridian_id:point_number for formatter previews."""
    if ":" not in value:
        raise argparse.ArgumentTypeError("Use MERIDIAN_ID:POINT_NUMBER, for example conception_vessel:24")
    meridian_id, point_number = value.split(":", 1)
    meridian_id = meridian_id.strip()
    if not meridian_id:
        raise argparse.ArgumentTypeError("Meridian id is empty")
    try:
        index = int(point_number) - 1
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Point number must be an integer") from exc
    if index < 0:
        raise argparse.ArgumentTypeError("Point number must be 1 or greater")
    return meridian_id, index


def _install_import_stubs() -> None:
    """Allow formatter-only audits without installing async runtime packages."""
    if "pytz" not in sys.modules:
        pytz_stub = types.ModuleType("pytz")
        pytz_stub.timezone = lambda name: None
        pytz_stub.utc = None
        sys.modules["pytz"] = pytz_stub

    if "aiofiles" not in sys.modules:
        aiofiles_stub = types.ModuleType("aiofiles")
        aiofiles_stub.open = None
        sys.modules["aiofiles"] = aiofiles_stub


def _tag_balance_issues(text: str) -> list[str]:
    issues: list[str] = []
    for tag in SUPPORTED_TAGS:
        opens = text.count(f"<{tag}>")
        closes = text.count(f"</{tag}>")
        if opens != closes:
            issues.append(f"unbalanced <{tag}> tags: {opens} open, {closes} close")
    return issues


def _load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def _print_preview(args: argparse.Namespace) -> int:
    _install_import_stubs()
    sys.path.insert(0, str(ROOT))

    from bot.utils import (  # pylint: disable=import-error,import-outside-toplevel
        fit_html_caption,
        format_meridian_intro,
        format_meridian_point,
        format_principle_message,
        get_meridian_image_path,
    )

    principles = _load_json("bot/principles.json")
    meridians_payload = _load_json("bot/meridians.json")
    meridians = meridians_payload["meridians"] if isinstance(meridians_payload, dict) else meridians_payload
    meridians_by_id = {item["id"]: item for item in meridians}

    if args.preview_point:
        meridian_id, point_index = args.preview_point
        meridian = meridians_by_id.get(meridian_id)
        if not meridian:
            print(f"Unknown meridian id: {meridian_id}")
            return 1
        points = meridian.get("points", [])
        if point_index >= len(points):
            print(f"{meridian_id} has only {len(points)} points")
            return 1
        point_code = points[point_index].get("code")
        text = format_meridian_point(meridian, point_index, args.language)
        print(f"Preview: {meridian_id} point {point_index + 1}/{len(points)} ({args.language})")
        print(f"Image: {get_meridian_image_path(meridian_id, point_code)}")
        print(f"Chars: {len(text)} | fitted caption: {len(fit_html_caption(text))}")
        print()
        print(text)
        return 0

    if args.preview_meridian:
        meridian = meridians_by_id.get(args.preview_meridian)
        if not meridian:
            print(f"Unknown meridian id: {args.preview_meridian}")
            return 1
        text = format_meridian_intro(meridian, args.language)
        print(f"Preview: {args.preview_meridian} intro ({args.language})")
        print(f"Image: {get_meridian_image_path(args.preview_meridian)}")
        print(f"Chars: {len(text)} | fitted caption: {len(fit_html_caption(text))}")
        print()
        print(text)
        return 0

    if args.preview_principle:
        language_principles = principles.get(args.language, [])
        principle = next((item for item in language_principles if int(item.get("id", 0) or 0) == args.preview_principle), None)
        if not principle:
            print(f"Unknown principle id for {args.language}: {args.preview_principle}")
            return 1
        text = format_principle_message(principle, args.language)
        print(f"Preview: principle {args.preview_principle} ({args.language})")
        print(f"Chars: {len(text)} | fitted caption: {len(fit_html_caption(text))}")
        print()
        print(text)
        return 0

    return _run_audit(principles, meridians)


def _run_audit(principles, meridians) -> int:
    from bot.utils import (  # pylint: disable=import-error,import-outside-toplevel
        fit_html_caption,
        format_meridian_intro,
        format_meridian_point,
        format_principle_message,
        get_meridian_image_path,
    )

    issues: list[str] = []
    max_principle = (0, "", "")
    max_intro = (0, "", "")
    max_point = (0, "", "")

    for language in LANGUAGES:
        for principle in principles.get(language, []):
            text = format_principle_message(principle, language)
            max_principle = max(max_principle, (len(text), language, str(principle.get("id"))))
            if len(text) > TELEGRAM_CAPTION_LIMIT:
                issues.append(f"{language} principle {principle.get('id')}: caption is {len(text)} chars")
            if principle.get("practice_tip") and ("💡" not in text or "<i>" not in text):
                issues.append(f"{language} principle {principle.get('id')}: practice block missing")
            if "**" in text or "???" in text:
                issues.append(f"{language} principle {principle.get('id')}: stale markup or placeholder")
            for tag_issue in _tag_balance_issues(text):
                issues.append(f"{language} principle {principle.get('id')}: {tag_issue}")

    for meridian in meridians:
        meridian_id = meridian["id"]
        if not get_meridian_image_path(meridian_id):
            issues.append(f"{meridian_id}: missing overview image")

        for language in LANGUAGES:
            intro = format_meridian_intro(meridian, language)
            fitted_intro = fit_html_caption(intro)
            max_intro = max(max_intro, (len(intro), meridian_id, language))
            if len(intro) > TELEGRAM_TEXT_LIMIT:
                issues.append(f"{meridian_id}/{language}: intro exceeds Telegram text limit")
            if len(fitted_intro) > TELEGRAM_CAPTION_LIMIT:
                issues.append(f"{meridian_id}/{language}: fitted intro caption exceeds Telegram limit")
            if "**" in intro or "???" in intro:
                issues.append(f"{meridian_id}/{language}: stale intro markup or placeholder")
            for tag_issue in _tag_balance_issues(fitted_intro):
                issues.append(f"{meridian_id}/{language}: fitted intro {tag_issue}")

        for index, point in enumerate(meridian.get("points", [])):
            point_code = point.get("code")
            if not get_meridian_image_path(meridian_id, point_code):
                issues.append(f"{meridian_id} {point_code}: missing point image")

            for language in LANGUAGES:
                text = format_meridian_point(meridian, index, language)
                fitted_text = fit_html_caption(text)
                max_point = max(max_point, (len(text), meridian_id, f"{index + 1}/{language}"))
                if len(text) > TELEGRAM_CAPTION_LIMIT:
                    issues.append(f"{meridian_id} {point_code}/{language}: point caption is {len(text)} chars")
                if len(fitted_text) > TELEGRAM_CAPTION_LIMIT:
                    issues.append(f"{meridian_id} {point_code}/{language}: fitted point caption exceeds Telegram limit")
                if "**" in text or "???" in text:
                    issues.append(f"{meridian_id} {point_code}/{language}: stale markup or placeholder")
                if "<b>" not in text:
                    issues.append(f"{meridian_id} {point_code}/{language}: missing bold heading")
                for tag_issue in _tag_balance_issues(text):
                    issues.append(f"{meridian_id} {point_code}/{language}: {tag_issue}")

    print(f"Principles max caption: {max_principle}")
    print(f"Meridian intro max text: {max_intro}")
    print(f"Meridian point max caption: {max_point}")
    print(f"Meridians checked: {len(meridians)}")
    print(f"Points checked: {sum(len(m.get('points', [])) for m in meridians)}")

    if issues:
        print("Runtime formatter audit issues:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Runtime formatter audit passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit or preview production Telegram formatters.")
    parser.add_argument("--language", choices=LANGUAGES, default="ru", help="Preview language.")
    parser.add_argument("--preview-point", type=_parse_point_selector, help="Print one meridian point card, e.g. conception_vessel:24.")
    parser.add_argument("--preview-meridian", help="Print one meridian intro card by id.")
    parser.add_argument("--preview-principle", type=int, help="Print one Yama/Niyama principle card by id.")
    args = parser.parse_args()

    preview_count = sum(bool(value) for value in (args.preview_point, args.preview_meridian, args.preview_principle))
    if preview_count > 1:
        parser.error("Choose only one preview target.")

    return _print_preview(args)


if __name__ == "__main__":
    raise SystemExit(main())
