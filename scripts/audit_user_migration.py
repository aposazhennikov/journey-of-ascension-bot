"""Audit legacy user JSON migration into the current User model."""

from __future__ import annotations

import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _install_import_stubs() -> None:
    if "aiofiles" not in sys.modules:
        aiofiles_stub = types.ModuleType("aiofiles")
        aiofiles_stub.open = None
        sys.modules["aiofiles"] = aiofiles_stub


def main() -> int:
    _install_import_stubs()
    sys.path.insert(0, str(ROOT))

    from bot.storage import User  # pylint: disable=import-error,import-outside-toplevel

    samples = [
        {
            "chat_id": "100",
            "language": "ru",
            "timezone": "Utc",
            "time_for_send": "8:00",
            "skip_day_id": ["5", 6, 9, "bad", 5],
            "is_active": "true",
            "unknown_old_field": "ignored",
        },
        {
            "chat_id": 200,
            "language": "bad",
            "timezone": "",
            "time_for_send": "29:70",
            "meridian_time_for_send": "7:05",
            "skip_day_id": "not-a-list",
            "principles_enabled": "false",
            "meridians_enabled": "yes",
            "current_point_index": "3",
            "completed_meridians": ["lung", "lung", None, "kidney"],
            "meridian_learning_mode": "strange",
        },
    ]

    first = User.from_dict(samples[0])
    second = User.from_dict(samples[1])

    expectations = [
        (first.chat_id == 100, "chat_id string should become int"),
        (first.timezone == "UTC", "legacy Utc timezone should become UTC"),
        (first.time_for_send == "08:00", "single-digit hour should be padded"),
        (first.skip_day_id == [5, 6], "skip days should be valid unique integers"),
        (first.is_active is True, "string true should become bool True"),
        (first.principles_enabled is True, "missing principles flag should default to True"),
        (first.meridians_enabled is False, "missing meridians flag should default to False"),
        (second.language == "en", "unknown language should fall back to English"),
        (second.timezone == "Europe/Moscow", "empty timezone should fall back safely"),
        (second.time_for_send == "06:00", "invalid principle time should fall back"),
        (second.meridian_time_for_send == "07:05", "single-digit meridian time should be padded"),
        (second.skip_day_id == [], "invalid skip days container should become empty list"),
        (second.principles_enabled is False, "string false should become bool False"),
        (second.meridians_enabled is True, "string yes should become bool True"),
        (second.current_point_index == 3, "point index should become int"),
        (second.completed_meridians == ["lung", "kidney"], "completed meridians should be unique strings"),
        (second.meridian_learning_mode is None, "unknown learning mode should be cleared"),
    ]

    issues = [message for ok, message in expectations if not ok]
    if issues:
        print("User migration audit issues:")
        for issue in issues:
            print(f"- {issue}")
        print("First:", first)
        print("Second:", second)
        return 1

    print("User migration audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
