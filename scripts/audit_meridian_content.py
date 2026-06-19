"""Audit meridian content without needing Telegram or app dependencies.

This script is intentionally standalone: it checks JSON structure and local
image coverage even on a fresh machine where requirements are not installed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


LANGUAGES = ("en", "ru", "uz", "kz")
MERIDIAN_FIELDS = (
    "name",
    "description",
    "direction",
    "intro_practice",
)
POINT_FIELDS = (
    "name",
    "location",
    "meditation_instruction",
    "observation_question",
)
IMAGE_EXTENSIONS = (".jpg", ".png", ".gif")

EXPECTED_POINT_COUNTS = {
    "lung": 11,
    "large_intestine": 20,
    "stomach": 45,
    "spleen": 21,
    "heart": 9,
    "small_intestine": 19,
    "bladder": 67,
    "kidney": 27,
    "pericardium": 9,
    "triple_burner": 23,
    "gallbladder": 44,
    "liver": 14,
    "governing_vessel": 28,
    "conception_vessel": 24,
}

SOURCE_TAIL_PATTERNS = (
    r"\bsource\b",
    r"https?://",
    r"источник",
    r"рис\.\s*\d+",
    r"fig\.\s*\d+",
    r"в\s+книге",
    r"говорится",
    r"секретные\s+рецепты",
)


def has_image(images_dir: Path, stem: str) -> bool:
    return any((images_dir / f"{stem}{extension}").exists() for extension in IMAGE_EXTENSIONS)


def plain(value: Any) -> str:
    return str(value or "").strip()


def contains_source_tail(text: str) -> bool:
    normalized = text.lower()
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in SOURCE_TAIL_PATTERNS)


def is_clear_short_location(text: str) -> bool:
    normalized = text.lower()
    return any(marker in normalized for marker in ("center", "центр", "markaz", "ортас"))


def audit() -> tuple[list[str], list[str]]:
    root = Path(__file__).resolve().parents[1]
    meridians_path = root / "bot" / "meridians.json"
    images_dir = root / "images" / "meridians"

    data = json.loads(meridians_path.read_text(encoding="utf-8"))
    meridians = data.get("meridians", [])
    errors: list[str] = []
    warnings: list[str] = []

    if len(meridians) != len(EXPECTED_POINT_COUNTS):
        errors.append(f"expected {len(EXPECTED_POINT_COUNTS)} meridians, found {len(meridians)}")

    total_points = 0
    for meridian in meridians:
        meridian_id = plain(meridian.get("id"))
        points = meridian.get("points", [])
        total_points += len(points)

        expected_points = EXPECTED_POINT_COUNTS.get(meridian_id)
        if expected_points is None:
            errors.append(f"{meridian_id}: unexpected meridian id")
        elif len(points) != expected_points:
            errors.append(f"{meridian_id}: expected {expected_points} points, found {len(points)}")

        if not has_image(images_dir, meridian_id):
            errors.append(f"{meridian_id}: missing overview image")

        for field in ("active_time", "passive_time"):
            if not plain(meridian.get(field)):
                errors.append(f"{meridian_id}: missing meridian field {field}")

        for language in LANGUAGES:
            localized = meridian.get("i18n", {}).get(language, {})
            for field in MERIDIAN_FIELDS:
                if not plain(localized.get(field)):
                    errors.append(f"{meridian_id}/{language}: missing meridian field {field}")
            description = plain(localized.get("description"))
            if len(description) < 120:
                warnings.append(f"{meridian_id}/{language}: short meridian description")

        seen_codes: set[str] = set()
        for index, point in enumerate(points, start=1):
            code = plain(point.get("code"))
            if not code:
                errors.append(f"{meridian_id} point {index}: missing code")
                continue
            if code in seen_codes:
                errors.append(f"{meridian_id}: duplicate point code {code}")
            seen_codes.add(code)

            if not has_image(images_dir, f"{meridian_id}_{code}"):
                errors.append(f"{meridian_id} {code}: missing point image")

            for language in LANGUAGES:
                localized = point.get("i18n", {}).get(language, {})
                for field in POINT_FIELDS:
                    if not plain(localized.get(field)):
                        errors.append(f"{meridian_id} {code}/{language}: missing point field {field}")

                location = plain(localized.get("location"))
                instruction = plain(localized.get("meditation_instruction"))
                question = plain(localized.get("observation_question"))
                if len(location) < 18 and not is_clear_short_location(location):
                    warnings.append(f"{meridian_id} {code}/{language}: very short location")
                if len(instruction) < 80:
                    warnings.append(f"{meridian_id} {code}/{language}: meditation instruction may be too thin")
                if len(question) < 40:
                    warnings.append(f"{meridian_id} {code}/{language}: observation question may be too thin")
                if contains_source_tail(location):
                    warnings.append(f"{meridian_id} {code}/{language}: location may contain source/editorial tail")

    expected_total = sum(EXPECTED_POINT_COUNTS.values())
    if total_points != expected_total:
        errors.append(f"expected {expected_total} total points, found {total_points}")

    print(f"Meridians: {len(meridians)}")
    print(f"Points: {total_points}")
    print(f"Images directory: {images_dir}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    if errors:
        print("\nErrors:")
        for item in errors[:200]:
            print(f"- {item}")
    if warnings:
        print("\nWarnings:")
        for item in warnings[:80]:
            print(f"- {item}")
        if len(warnings) > 80:
            print(f"- ... {len(warnings) - 80} more warnings")
    return errors, warnings


if __name__ == "__main__":
    found_errors, _ = audit()
    sys.exit(1 if found_errors else 0)
