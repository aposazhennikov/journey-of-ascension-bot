"""Sensation diary: how a point responded, one tap under the point message and in the map.

A point is marked warm, cool, tense, empty or silent; the last mark per point is kept in User.point_feel
as {map code: {"f": feel, "d": "YYYY-MM-DD"}}. Silent and empty points are the ones worth returning to,
the meridians menu lists them.
"""

from datetime import date
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .webapp import map_point_code

if TYPE_CHECKING:
    from .utils import MeridiansManager

FEELS = ("warm", "cool", "tense", "empty", "silent")
RETURN_FEELS = ("silent", "empty")
FEEL_ICONS = {"warm": "☀️", "cool": "❄️", "tense": "⚡️", "empty": "🫧", "silent": "🤫"}
MAX_MARKS = 600

FEEL_LABELS = {
    "ru": {"warm": "Тёплая", "cool": "Прохладная", "tense": "Напряжённая", "empty": "Пустая", "silent": "Молчит"},
    "en": {"warm": "Warm", "cool": "Cool", "tense": "Tense", "empty": "Empty", "silent": "Silent"},
    "uz": {"warm": "Iliq", "cool": "Salqin", "tense": "Tarang", "empty": "Bo'sh", "silent": "Jim"},
    "kz": {"warm": "Жылы", "cool": "Салқын", "tense": "Кернеулі", "empty": "Бос", "silent": "Үнсіз"},
}

TEXTS = {
    "ru": {
        "ask": "📝 Как отозвалась точка?",
        "marked": "📝 Точка: {icon} {label}",
        "back": "↩ Назад",
        "saved": "Записано в дневник: {label}",
        "cleared": "Отметка убрана",
        "menu": "📓 Дневник точек",
        "title": "<b>Дневник ощущений</b>",
        "count": "Отмечено точек: {n}",
        "none": "Пока ни одной отметки. После точки нажмите «Как отозвалась точка?»: тёплая, прохладная, "
                "напряжённая, пустая или молчит. Здесь соберутся точки, к которым стоит вернуться.",
        "return": "К молчащим и пустым точкам стоит вернуться: точка часто отзывается не с первого раза. "
                  "Нажмите на точку, чтобы открыть её.",
        "all_heard": "Молчащих и пустых точек нет.",
        "more": "И ещё {n}.",
    },
    "en": {
        "ask": "📝 How did the point respond?",
        "marked": "📝 Point: {icon} {label}",
        "back": "↩ Back",
        "saved": "Saved to the diary: {label}",
        "cleared": "Mark removed",
        "menu": "📓 Point diary",
        "title": "<b>Sensation diary</b>",
        "count": "Points marked: {n}",
        "none": "No marks yet. After a point, tap \"How did the point respond?\": warm, cool, tense, empty "
                "or silent. The points worth coming back to will gather here.",
        "return": "Silent and empty points are worth coming back to: a point often responds on a later try. "
                  "Tap a point to open it.",
        "all_heard": "No silent or empty points.",
        "more": "And {n} more.",
    },
    "uz": {
        "ask": "📝 Nuqta qanday javob berdi?",
        "marked": "📝 Nuqta: {icon} {label}",
        "back": "↩ Orqaga",
        "saved": "Kundalikka yozildi: {label}",
        "cleared": "Belgi olib tashlandi",
        "menu": "📓 Nuqtalar kundaligi",
        "title": "<b>Sezgilar kundaligi</b>",
        "count": "Belgilangan nuqtalar: {n}",
        "none": "Hali belgi yo'q. Nuqtadan keyin «Nuqta qanday javob berdi?» tugmasini bosing: iliq, salqin, "
                "tarang, bo'sh yoki jim. Qaytish kerak bo'lgan nuqtalar shu yerda yig'iladi.",
        "return": "Jim va bo'sh nuqtalarga qaytgan ma'qul: nuqta ko'pincha birinchi urinishda javob bermaydi. "
                  "Ochish uchun nuqtani bosing.",
        "all_heard": "Jim yoki bo'sh nuqtalar yo'q.",
        "more": "Yana {n} ta.",
    },
    "kz": {
        "ask": "📝 Нүкте қалай жауап берді?",
        "marked": "📝 Нүкте: {icon} {label}",
        "back": "↩ Артқа",
        "saved": "Күнделікке жазылды: {label}",
        "cleared": "Белгі алынды",
        "menu": "📓 Нүктелер күнделігі",
        "title": "<b>Сезімдер күнделігі</b>",
        "count": "Белгіленген нүктелер: {n}",
        "none": "Әзірге белгі жоқ. Нүктеден кейін «Нүкте қалай жауап берді?» батырмасын басыңыз: жылы, салқын, "
                "кернеулі, бос немесе үнсіз. Қайта оралатын нүктелер осында жиналады.",
        "return": "Үнсіз және бос нүктелерге қайта оралған жөн: нүкте көбіне бірінші реттен жауап бермейді. "
                  "Ашу үшін нүктені басыңыз.",
        "all_heard": "Үнсіз немесе бос нүктелер жоқ.",
        "more": "Тағы {n}.",
    },
}

CALLBACK_PREFIX = "meridian_feel"


def text(key: str, language: str, **kw: Any) -> str:
    value = TEXTS.get(language, TEXTS["en"]).get(key) or TEXTS["en"][key]
    return value.format(**kw) if kw else value


def feel_label(feel: str, language: str) -> str:
    return FEEL_LABELS.get(language, FEEL_LABELS["en"]).get(feel, feel)


def normalize_point_feel(value: Any) -> Dict[str, Dict[str, str]]:
    """Clean stored marks: known feelings, map codes, at most MAX_MARKS (the newest kept)."""
    if not isinstance(value, dict):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for code, entry in value.items():
        feel = entry.get("f") if isinstance(entry, dict) else entry
        mapped = map_point_code(str(code))
        if feel not in FEELS or not mapped:
            continue
        day = entry.get("d") if isinstance(entry, dict) else ""
        out[mapped] = {"f": feel, "d": str(day or "")[:10]}
    if len(out) > MAX_MARKS:
        out = dict(sorted(out.items(), key=lambda item: item[1]["d"])[-MAX_MARKS:])
    return out


def set_feel(marks: Dict[str, Dict[str, str]], code: str, feel: str, today: Optional[date] = None) -> bool:
    """Set (or clear with "" / the same feeling) a point's mark. Returns True when it is set afterwards."""
    mapped = map_point_code(code)
    if not mapped:
        return False
    if not feel or feel not in FEELS:
        marks.pop(mapped, None)
        return False
    marks[mapped] = {"f": feel, "d": (today or date.today()).isoformat()}
    return True


def feel_of(marks: Optional[Dict[str, Dict[str, str]]], code: Optional[str]) -> Optional[str]:
    if not marks or not code:
        return None
    entry = marks.get(map_point_code(code))
    return entry.get("f") if entry else None


# ---------------------------------------------------------------- bot keyboards

def _is_feel_row(row: List[InlineKeyboardButton]) -> bool:
    return any((getattr(b, "callback_data", None) or "").startswith(CALLBACK_PREFIX) for b in row)


def collapsed_rows(meridian_id: str, point_index: int, current: Optional[str], language: str) -> List[List[InlineKeyboardButton]]:
    label = (text("marked", language, icon=FEEL_ICONS[current], label=feel_label(current, language).lower())
             if current else text("ask", language))
    return [[InlineKeyboardButton(label, callback_data=f"{CALLBACK_PREFIX}:{meridian_id}:{point_index}")]]


def open_rows(meridian_id: str, point_index: int, current: Optional[str], language: str) -> List[List[InlineKeyboardButton]]:
    def button(feel: str) -> InlineKeyboardButton:
        mark = "✓ " if feel == current else ""
        return InlineKeyboardButton(
            f"{mark}{FEEL_ICONS[feel]} {feel_label(feel, language)}",
            callback_data=f"{CALLBACK_PREFIX}set:{meridian_id}:{point_index}:{feel}",
        )
    return [
        [button("warm"), button("cool")],
        [button("tense"), button("empty")],
        [button("silent"), InlineKeyboardButton(text("back", language), callback_data=f"{CALLBACK_PREFIX}back:{meridian_id}:{point_index}")],
    ]


def swap_feel_rows(markup: Optional[InlineKeyboardMarkup], rows: List[List[InlineKeyboardButton]]) -> Optional[InlineKeyboardMarkup]:
    """The message's own keyboard with its diary rows replaced (the point message may come from the
    scheduler or from the menu, both keep their other buttons as they were)."""
    if markup is None:
        return None
    old = [list(row) for row in markup.inline_keyboard]
    first = next((i for i, row in enumerate(old) if _is_feel_row(row)), None)
    if first is None:
        return None
    kept = [row for row in old if not _is_feel_row(row)]
    return InlineKeyboardMarkup(kept[:first] + rows + kept[first:])


def parse_callback(data: str) -> Optional[Tuple[str, str, int, str]]:
    """("open" | "set" | "back", meridian id, point index, feel) of a diary button, None for others."""
    if not data.startswith(CALLBACK_PREFIX):
        return None
    head, _, rest = data[len(CALLBACK_PREFIX):].partition(":")
    kind = {"": "open", "set": "set", "back": "back"}.get(head)
    parts = rest.split(":")
    if kind is None or len(parts) < 2:
        return None
    try:
        index = int(parts[1])
    except ValueError:
        return None
    feel = parts[2] if kind == "set" and len(parts) > 2 else ""
    if kind == "set" and feel not in FEELS:
        return None
    return kind, parts[0], index, feel


# ---------------------------------------------------------------- diary page in the bot

def point_lookup(meridians_manager: "MeridiansManager") -> Dict[str, Tuple[str, int, Dict[str, Any]]]:
    """Map code -> (meridian id, point index, point) over the study path."""
    out: Dict[str, Tuple[str, int, Dict[str, Any]]] = {}
    for meridian in meridians_manager.get_recommended_path_meridians():
        for index, point in enumerate(meridian.get("points", [])):
            code = map_point_code(point.get("code") or "")
            if code and code not in out:
                out[code] = (meridian.get("id"), index, point)
    return out


def diary_page(marks: Dict[str, Dict[str, str]], meridians_manager: "MeridiansManager", language: str,
               point_title, limit: int = 12) -> Tuple[str, List[List[InlineKeyboardButton]]]:
    """Text and point buttons of the diary: the counts per feeling and the points to return to."""
    lines = [text("title", language), ""]
    if not marks:
        lines.append(text("none", language))
        return "\n".join(lines), []
    lookup = point_lookup(meridians_manager)
    counts = [f"{FEEL_ICONS[f]} {feel_label(f, language)}: {sum(1 for e in marks.values() if e['f'] == f)}"
              for f in FEELS if any(e["f"] == f for e in marks.values())]
    lines.append(text("count", language, n=len(marks)))
    lines.append(" · ".join(counts))
    lines.append("")
    back_to = sorted(
        ((code, entry) for code, entry in marks.items() if entry["f"] in RETURN_FEELS and code in lookup),
        key=lambda item: (RETURN_FEELS.index(item[1]["f"]), item[1]["d"]),
    )
    rows: List[List[InlineKeyboardButton]] = []
    if not back_to:
        lines.append(text("all_heard", language))
        return "\n".join(lines), rows
    lines.append(text("return", language))
    for code, entry in back_to[:limit]:
        meridian_id, index, point = lookup[code]
        rows.append([InlineKeyboardButton(
            f"{FEEL_ICONS[entry['f']]} {point_title(point, language)}"[:60],
            callback_data=f"meridian_point:{meridian_id}:{index}",
        )])
    if len(back_to) > limit:
        lines.append(text("more", language, n=len(back_to) - limit))
    return "\n".join(lines), rows
