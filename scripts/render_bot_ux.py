"""Render Telegram bot UX screens locally without Telegram.

This script creates a small HTML review page for the main bot surfaces and
prints an audit for common content problems: missing locale keys, mojibake,
missing meridian point images, and overly long button labels.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from html import escape
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("en", "ru", "uz", "kz")
POINTS_PAGE_SIZE = 10
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
MOJIBAKE_RE = re.compile(
    r"(?:"
    r"Р[ђѓЃєµЅ¶°±Ііґё№»јњќћїЎўЈ¤Ґ¦§Ё©«¬®Ї]"
    r"|С[ЂЃ‚ѓ„…†‡€‰Љ‹ЊЌЋЏ‘’“”•–—™љ›њќћџ]"
    r"|Т[›ЇЈҮҚҢҒӨә]"
    r"|У[Ё™©]"
    r"|вЂ|вњ|рџ"
    r")"
)
SOURCE_MOJIBAKE_FRAGMENTS = (
    "Рђ", "Р‘", "РЃ", "Рќ", "Рџ", "РЎ", "Рў", "Рњ",
    "СЃ", "С‚", "С‹", "СЊ", "СЋ", "СЏ",
    "ТЇ", "Т›", "Т“", "У™", "вЂ", "рџ",
)


def load_texts() -> dict[str, dict[str, str]]:
    source = (ROOT / "bot" / "handlers.py").read_text(encoding="utf-8-sig")
    module = ast.parse(source)
    values: dict[str, Any] = {}
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in {"TEXTS", "TEXTS_UPDATE"}:
                values[target.id] = ast.literal_eval(node.value)

    texts = values.get("TEXTS", {})
    updates = values.get("TEXTS_UPDATE", {})
    for language, language_updates in updates.items():
        texts.setdefault(language, {}).update(language_updates)
    return texts


def load_json(relative_path: str) -> Any:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8-sig"))


def allow_basic_html(value: str) -> str:
    escaped = escape(value or "")
    for tag in ("b", "i"):
        escaped = escaped.replace(f"&lt;{tag}&gt;", f"<{tag}>")
        escaped = escaped.replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    return escaped


def normalize_bot_html(value: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value or "")


def localized(item: dict[str, Any], language: str, key: str, default: str = "") -> str:
    i18n = item.get("i18n", {})
    return i18n.get(language, i18n.get("en", {})).get(key, default)


def has_cyrillic(value: str) -> bool:
    return any("А" <= char <= "я" or char in "ЁёІіЇїЄєҚқҒғҰұҮүӘәӨөҺһҢң" for char in value)


def localized_location(point: dict[str, Any], language: str) -> str:
    value = localized(point, language, "location")
    if language == "ru" or not value:
        return value
    for prefix in ("Source location:", "Manbadagi joylashuv:", "Дереккөздегі орналасуы:"):
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
            break
    else:
        if not has_cyrillic(value):
            return value
    if value.lower().startswith("pending source refinement"):
        pending_labels = {
            "en": "The exact source location is being clarified. For now, use the image and the surrounding anatomical landmarks as your guide.",
            "uz": "Nuqtaning aniq joylashuvi manba bo'yicha aniqlashtirilmoqda. Hozircha rasm va atrofdagi anatomik belgilardan yo'l-yo'riq sifatida foydalaning.",
            "kz": "Нүктенің нақты орналасуы дереккөз бойынша нақтыланып жатыр. Әзірге суретті және айналасындағы анатомиялық белгілерді бағдар ретінде қолданыңыз.",
        }
        return pending_labels.get(language, pending_labels["en"])
    labels = {
        "en": "Original source location (RU)",
        "uz": "Manbadagi asl joylashuv (rus tilida)",
        "kz": "Дереккөздегі бастапқы орналасуы (орыс тілінде)",
    }
    return f"{labels.get(language, 'Original source location (RU)')}: {value}"


def format_meridian_intro(meridian: dict[str, Any], language: str) -> str:
    labels = {
        "en": ("Active", "Passive", "Points", "Direction", "Practice"),
        "ru": ("Активен", "Пассивен", "Точек", "Ход", "Практика"),
        "uz": ("Faol", "Passiv", "Nuqtalar", "Yo'nalish", "Amaliyot"),
        "kz": ("Белсенді", "Пассивті", "Нүктелер", "Бағыты", "Тәжірибе"),
    }[language]
    points = meridian.get("points", [])
    parts = [
        f"<b>{escape(localized(meridian, language, 'name', meridian.get('id', '')))}</b>",
        allow_basic_html(localized(meridian, language, "description")),
        f"<b>{labels[0]}:</b> {escape(str(meridian.get('active_time', '-')))}",
        f"<b>{labels[1]}:</b> {escape(str(meridian.get('passive_time', '-')))}",
        f"<b>{labels[2]}:</b> {len(points)}",
    ]
    direction = localized(meridian, language, "direction")
    if direction:
        parts.append(f"<b>{labels[3]}:</b> {allow_basic_html(direction)}")
    practice = localized(meridian, language, "intro_practice")
    if practice:
        parts.append(f"<i>{labels[4]}:</i> {allow_basic_html(practice)}")
    return "\n\n".join(part for part in parts if part)


def practice_note(point_index: int, language: str) -> str:
    notes = {
        "en": (
            "Begin with the first point: find it through body sensation, breath, and attention. If the sensation is weak, treat the point as not yet open: give it more time, gently massage it, and imagine breathing through it until concentration becomes steady and easy.",
            "First recall the points you have already studied. Without losing them, add the current point and connect it with the previous ones as one line of attention. If it is hard to feel, treat it as not yet open: gently massage it, breathe through it with attention, and stay longer until the sensation becomes stable.",
        ),
        "ru": (
            "Начните с первой точки: найдите её через ощущение тела, дыхание и внимание. Если ощущение слабое, считайте точку пока закрытой: уделите ей больше времени, мягко помассируйте её и представляйте вдох и выдох через неё, пока концентрация не станет лёгкой и устойчивой.",
            "Сначала вспомните и удерживайте ощущение уже пройденных точек. Не отпуская их, добавьте текущую точку и соедините её с предыдущими в одну линию внимания. Если точка не ощущается, считайте её пока закрытой: мягко помассируйте её, дышите через неё вниманием и оставайтесь дольше, пока ощущение не станет устойчивым.",
        ),
        "uz": (
            "Birinchi nuqtadan boshlang: uni tana sezgisi, nafas va diqqat orqali toping. Agar sezgi kuchsiz bo'lsa, nuqtani hali ochilmagan deb qabul qiling: unga ko'proq vaqt bering, yengil massaj qiling va diqqat barqaror bo'lguncha shu nuqta orqali nafas olayotganingizni tasavvur qiling.",
            "Avval oldin o'rganilgan nuqtalarni eslang va sezib turing. Ularni yo'qotmasdan, hozirgi nuqtani qo'shing va oldingilari bilan bitta diqqat chizig'iga ulang. Agar nuqta sezilmasa, uni hali ochilmagan deb qabul qiling: yengil massaj qiling, diqqat bilan shu nuqta orqali nafas oling va sezgi barqaror bo'lguncha turing.",
        ),
        "kz": (
            "Бірінші нүктеден бастаңыз: оны дене сезімі, тыныс және зейін арқылы табыңыз. Егер сезім әлсіз болса, нүктені әзірге ашылмаған деп қабылдаңыз: оған көбірек уақыт бөліңіз, жеңіл уқалаңыз және шоғырлану тұрақталғанша осы нүкте арқылы дем алып-шығаруды елестетіңіз.",
            "Алдымен бұрын өткен нүктелердің сезімін еске түсіріп, ұстап тұрыңыз. Оларды жібермей, қазіргі нүктені қосып, алдыңғыларымен бір зейін сызығына біріктіріңіз. Егер нүкте сезілмесе, оны әзірге ашылмаған деп қабылдаңыз: жеңіл уқалаңыз, зейінмен сол нүкте арқылы тыныстаңыз және сезім тұрақталғанша ұзағырақ болыңыз.",
        ),
    }
    return notes[language][0 if point_index == 0 else 1]


def format_meridian_point(meridian: dict[str, Any], point_index: int, language: str) -> str:
    labels = {
        "en": ("Point", "Location", "Focus", "Observe"),
        "ru": ("Точка", "Расположение", "Концентрация", "Наблюдение"),
        "uz": ("Nuqta", "Joylashuv", "Diqqat", "Kuzatish"),
        "kz": ("Нүкте", "Орналасуы", "Зейін", "Бақылау"),
    }[language]
    points = meridian.get("points", [])
    point = points[point_index]
    point_i18n = point.get("i18n", {}).get(language, point.get("i18n", {}).get("en", {}))
    parts = [
        f"<b>{escape(localized(meridian, language, 'name'))}</b>",
        f"<b>{labels[0]} {point_index + 1}/{len(points)}:</b> {escape(point.get('code', ''))} {escape(point_i18n.get('name', ''))}",
        f"<b>{labels[1]}:</b> {escape(localized_location(point, language))}",
        f"<b>{labels[2]}:</b> {escape(point_i18n.get('meditation_instruction', ''))}",
        escape(practice_note(point_index, language)),
    ]
    question = point_i18n.get("observation_question", "")
    if question:
        with_question = "\n\n".join(parts + [f"<i>{labels[3]}:</i> {escape(question)}"])
        if len(with_question) <= 1024:
            return with_question
    return "\n\n".join(parts)


def principle_group(principle_id: int, language: str) -> str:
    names = {
        "en": ("Yama", "Niyama"),
        "ru": ("Яма", "Нияма"),
        "uz": ("Yama", "Niyama"),
        "kz": ("Яма", "Нияма"),
    }[language]
    return names[0] if principle_id <= 5 else names[1]


def format_principle(principle: dict[str, Any], language: str) -> str:
    labels = {
        "en": ("Part", "Practice"),
        "ru": ("Часть", "Практика"),
        "uz": ("Qismi", "Amaliyot"),
        "kz": ("Бөлігі", "Тәжірибе"),
    }[language]
    parts = [
        f"<b>{escape(principle.get('name', ''))}</b> {escape(principle.get('emoji', ''))}",
        f"<b>{labels[0]}:</b> {escape(principle_group(int(principle.get('id', 0)), language))}",
        escape(principle.get("short_description", "")),
        escape(principle.get("description", "")),
        f"💡 <b>{labels[1]}:</b> <i>{escape(principle.get('practice_tip', ''))}</i>",
    ]
    return "\n\n".join(part for part in parts if part)


def keyboard(rows: list[list[str]]) -> str:
    rendered_rows = []
    for row in rows:
        buttons = "".join(f"<button>{escape(label)}</button>" for label in row)
        rendered_rows.append(f"<div class='keyboard-row'>{buttons}</div>")
    return f"<div class='keyboard'>{''.join(rendered_rows)}</div>"


def message(title: str, body: str, buttons: list[list[str]] | None = None) -> str:
    return (
        "<section class='screen'>"
        f"<h2>{escape(title)}</h2>"
        f"<div class='bubble'>{body.replace(chr(10), '<br>')}</div>"
        f"{keyboard(buttons or [])}"
        "</section>"
    )


def language_selection_text() -> str:
    return (
        "🕊️ <b>Journey of Ascension</b>\n\n"
        "Please choose your language.\n"
        "Пожалуйста, выберите язык.\n\n"
        "Tilni tanlang.\n"
        "Тілді таңдаңыз."
    )


def build_keyboards(texts: dict[str, str], admin: bool = False) -> dict[str, list[list[str]]]:
    main = [
        [texts["menu_principles"], texts["menu_meridians"]],
        [texts["menu_modes"], texts["menu_settings"]],
        [texts["menu_about"], texts["menu_feedback"]],
        [texts["menu_stop"]],
    ]
    if admin:
        main.insert(3, [texts["menu_test"]])
    return {
        "main": main,
        "meridians_home": [
            [texts["meridian_guided_path"]],
            [texts["meridian_free_choice"]],
            [texts["meridian_measurements"]],
            [texts["back_to_menu"]],
        ],
        "meridian_intro": [
            [texts["meridian_start_points"]],
            [texts["all_points"], texts["complete_meridian"]],
            [texts["meridian_back"]],
        ],
        "meridian_first_point": [
            [texts["next_point"]],
            [texts["all_points"], texts["complete_meridian"]],
            [texts["meridian_back"]],
        ],
        "meridian_practice": [
            [texts["prev_point"], texts["next_point"]],
            [texts["all_points"], texts["complete_meridian"]],
            [texts["meridian_back"]],
        ],
        "principles": [[texts["principles_random"], texts["principles_all"]], [texts["back_to_menu"]]],
    }


def point_page_keyboard(meridian: dict[str, Any], language: str, texts: dict[str, str], page: int = 0) -> list[list[str]]:
    points = meridian.get("points", [])
    total_pages = max(1, (len(points) + POINTS_PAGE_SIZE - 1) // POINTS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * POINTS_PAGE_SIZE
    buttons = []
    for index, point in enumerate(points[start:start + POINTS_PAGE_SIZE], start=start):
        point_i18n = point.get("i18n", {}).get(language, point.get("i18n", {}).get("en", {}))
        buttons.append([f"{index + 1}. {point.get('code', '')} {point_i18n.get('name', '')}".strip()])
    if total_pages > 1:
        row = []
        if page > 0:
            row.append("◀️ 10")
        row.append(f"{page + 1}/{total_pages}")
        if page < total_pages - 1:
            row.append("10 ▶️")
        buttons.append(row)
    buttons.append([texts["meridian_back"]])
    return buttons


def render_html(output: Path) -> None:
    texts = load_texts()
    meridians = load_json("bot/meridians.json")["meridians"]
    principles = load_json("bot/principles.json")
    lung = next(item for item in meridians if item["id"] == "lung")
    large_intestine = next(item for item in meridians if item["id"] == "large_intestine")
    stomach = next(item for item in meridians if item["id"] == "stomach")
    spleen = next(item for item in meridians if item["id"] == "spleen")
    heart = next(item for item in meridians if item["id"] == "heart")
    small_intestine = next(item for item in meridians if item["id"] == "small_intestine")
    bladder = next(item for item in meridians if item["id"] == "bladder")
    kidney = next(item for item in meridians if item["id"] == "kidney")
    pericardium = next(item for item in meridians if item["id"] == "pericardium")
    triple_burner = next(item for item in meridians if item["id"] == "triple_burner")
    gallbladder = next(item for item in meridians if item["id"] == "gallbladder")
    liver = next(item for item in meridians if item["id"] == "liver")
    conception = next(item for item in meridians if item["id"] == "conception_vessel")
    governing = next(item for item in meridians if item["id"] == "governing_vessel")

    sections = []
    for language in LANGUAGES:
        t = texts[language]
        kb = build_keyboards(t)
        principle = principles[language][0]
        sections.append(f"<div class='locale'><h1>{language.upper()}</h1>")
        sections.append(message("Language selection", allow_basic_html(language_selection_text()), [["🇺🇸 English", "🇷🇺 Русский"], ["🇺🇿 O'zbek", "🇰🇿 Қазақ"]]))
        sections.append(message("Onboarding intro", allow_basic_html(t["onboarding_intro"]), [[t["mode_meridians_only"]], [t["mode_principles_only"]], [t["mode_both"]]]))
        sections.append(message("Main menu", allow_basic_html(normalize_bot_html(t["menu"])), kb["main"]))
        sections.append(message("My Path", allow_basic_html(t["mode_menu"]), [[t["mode_principles_only"]], [t["mode_meridians_only"]], [t["mode_both"]], [t["back_to_menu"]]]))
        sections.append(message(
            "Settings",
            allow_basic_html(normalize_bot_html(t["settings_menu"])),
            [
                [t["change_modes"], t["change_meridian_time"]],
                [t["change_language"], t["change_time"]],
                [t["change_timezone"], t["change_skip_days"]],
                [t["back_to_menu"]],
            ],
        ))
        sections.append(message("About", allow_basic_html(t["about_text"]), [[t["back_to_menu"]]]))
        sections.append(message("Feature announcement", allow_basic_html(t["feature_announcement"])))
        sections.append(message("Meridians home", allow_basic_html(t["meridians_menu"]), kb["meridians_home"]))
        sections.append(message("TCM measurements", allow_basic_html(t["meridian_measurements_text"]), [[t["meridian_back"]]]))
        sections.append(message("Lung Meridian intro", format_meridian_intro(lung, language), kb["meridian_intro"]))
        sections.append(message("Lung Meridian point 1", format_meridian_point(lung, 0, language), kb["meridian_first_point"]))
        sections.append(message("Large Intestine intro", format_meridian_intro(large_intestine, language), kb["meridian_intro"]))
        sections.append(message("Large Intestine point 1", format_meridian_point(large_intestine, 0, language), kb["meridian_first_point"]))
        sections.append(message("Stomach Meridian intro", format_meridian_intro(stomach, language), kb["meridian_intro"]))
        sections.append(message("Stomach Meridian point 1", format_meridian_point(stomach, 0, language), kb["meridian_first_point"]))
        sections.append(message("Spleen Meridian intro", format_meridian_intro(spleen, language), kb["meridian_intro"]))
        sections.append(message("Spleen Meridian point 1", format_meridian_point(spleen, 0, language), kb["meridian_first_point"]))
        sections.append(message("Heart Meridian intro", format_meridian_intro(heart, language), kb["meridian_intro"]))
        sections.append(message("Heart Meridian point 1", format_meridian_point(heart, 0, language), kb["meridian_first_point"]))
        sections.append(message("Small Intestine Meridian intro", format_meridian_intro(small_intestine, language), kb["meridian_intro"]))
        sections.append(message("Small Intestine Meridian point 1", format_meridian_point(small_intestine, 0, language), kb["meridian_first_point"]))
        sections.append(message("Bladder Meridian intro", format_meridian_intro(bladder, language), kb["meridian_intro"]))
        sections.append(message("Bladder Meridian point 1", format_meridian_point(bladder, 0, language), kb["meridian_first_point"]))
        sections.append(message("Bladder points page 1", f"<b>{escape(t['all_points'])}</b><br><br>Page 1/7", point_page_keyboard(bladder, language, t)))
        sections.append(message("Kidney Meridian intro", format_meridian_intro(kidney, language), kb["meridian_intro"]))
        sections.append(message("Kidney Meridian point 1", format_meridian_point(kidney, 0, language), kb["meridian_first_point"]))
        sections.append(message("Pericardium Meridian intro", format_meridian_intro(pericardium, language), kb["meridian_intro"]))
        sections.append(message("Pericardium Meridian point 1", format_meridian_point(pericardium, 0, language), kb["meridian_first_point"]))
        sections.append(message("Triple Burner Meridian intro", format_meridian_intro(triple_burner, language), kb["meridian_intro"]))
        sections.append(message("Triple Burner Meridian point 1", format_meridian_point(triple_burner, 0, language), kb["meridian_first_point"]))
        sections.append(message("Gallbladder Meridian intro", format_meridian_intro(gallbladder, language), kb["meridian_intro"]))
        sections.append(message("Gallbladder Meridian point 1", format_meridian_point(gallbladder, 0, language), kb["meridian_first_point"]))
        sections.append(message("Liver Meridian intro", format_meridian_intro(liver, language), kb["meridian_intro"]))
        sections.append(message("Liver Meridian point 1", format_meridian_point(liver, 0, language), kb["meridian_first_point"]))
        sections.append(message("Conception Vessel intro", format_meridian_intro(conception, language), kb["meridian_intro"]))
        sections.append(message("Conception Vessel point 1", format_meridian_point(conception, 0, language), kb["meridian_first_point"]))
        sections.append(message("Conception Vessel point 3", format_meridian_point(conception, 2, language), kb["meridian_practice"]))
        sections.append(message("Governing Vessel intro", format_meridian_intro(governing, language), kb["meridian_intro"]))
        sections.append(message("Principles home", allow_basic_html(t["principles_menu"]), kb["principles"]))
        sections.append(message("Principle detail", format_principle(principle, language), kb["principles"]))
        sections.append("</div>")

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Journey of Ascension UX Preview</title>
  <style>
    body {{ margin: 0; font: 16px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #dce8c8; color: #182018; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    .locale {{ margin-bottom: 40px; }}
    .locale h1 {{ margin: 32px 0 16px; }}
    .screen {{ display: inline-block; vertical-align: top; width: min(420px, 100%); margin: 0 16px 20px 0; }}
    .screen h2 {{ margin: 0 0 8px; font-size: 15px; color: #42513f; }}
    .bubble {{ background: #fff; border-radius: 14px; padding: 18px 20px; box-shadow: 0 1px 2px rgba(0,0,0,.12); white-space: normal; }}
    .keyboard {{ margin-top: 6px; }}
    .keyboard-row {{ display: flex; gap: 4px; margin-bottom: 4px; }}
    button {{ flex: 1; min-height: 42px; border: 0; border-radius: 8px; color: white; background: rgba(69,125,58,.72); font: 600 15px/1.2 inherit; padding: 8px 10px; }}
    b {{ font-weight: 750; }}
    i {{ color: #2f4730; }}
  </style>
</head>
<body>
<main>
  <h1>Journey of Ascension UX Preview</h1>
  <p>Static preview generated from current bot texts, content JSON, and keyboard structure.</p>
  {''.join(sections)}
</main>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


def iter_strings(value: Any, path: str = ""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from iter_strings(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_strings(child, f"{path}[{index}]")


def audit() -> list[str]:
    issues: list[str] = []
    texts = load_texts()
    start_text = language_selection_text()
    if "**" in start_text:
        issues.append("language selection text leaves Markdown bold")
    if "<b>Journey of Ascension</b>" not in start_text:
        issues.append("language selection text does not bold the bot name")

    for language in LANGUAGES:
        missing = sorted(set(texts["en"].keys()) - set(texts.get(language, {}).keys()))
        if missing:
            issues.append(f"{language}: missing text keys: {', '.join(missing[:12])}")

        html_keys = (
            "menu",
            "settings_menu",
            "feedback_prompt",
            "about_text",
            "principles_menu",
            "mode_menu",
            "meridians_menu",
            "meridian_measurements_text",
            "feature_announcement",
            "skip_days_step",
            "setup_complete",
        )
        for key in html_keys:
            value = normalize_bot_html(texts.get(language, {}).get(key, ""))
            if "**" in value:
                issues.append(f"{language}: {key} leaves Markdown bold in HTML text")
            if key in {"menu", "settings_menu"} and "<b>" not in value:
                issues.append(f"{language}: {key} has no bold title after HTML normalization")

    for relative_path in ("bot/handlers.py", "bot/utils.py", "bot/scheduler.py"):
        source = (ROOT / relative_path).read_text(encoding="utf-8-sig")
        for line_number, line in enumerate(source.splitlines(), 1):
            if "???" in line:
                issues.append(f"{relative_path}:{line_number}: contains ???")
            if any(fragment in line for fragment in SOURCE_MOJIBAKE_FRAGMENTS):
                issues.append(f"{relative_path}:{line_number}: possible mojibake -> {line[:80]}")

    for relative_path in ("bot/meridians.json", "bot/principles.json"):
        data = load_json(relative_path)
        for path, value in iter_strings(data, relative_path):
            if "???" in value:
                issues.append(f"{path}: contains ???")
            if MOJIBAKE_RE.search(value):
                issues.append(f"{path}: possible mojibake -> {value[:80]}")

    meridians = load_json("bot/meridians.json")["meridians"]
    meridians_by_id = {item["id"]: item for item in meridians}
    if len(meridians) != len(EXPECTED_POINT_COUNTS):
        issues.append(f"expected {len(EXPECTED_POINT_COUNTS)} meridians, got {len(meridians)}")
    missing_meridians = sorted(set(EXPECTED_POINT_COUNTS) - set(meridians_by_id))
    if missing_meridians:
        issues.append(f"missing meridians: {missing_meridians}")
    for meridian_id, expected_count in EXPECTED_POINT_COUNTS.items():
        item = meridians_by_id.get(meridian_id)
        if not item:
            continue
        actual_count = len(item.get("points", []))
        if actual_count != expected_count:
            issues.append(f"{meridian_id}: expected {expected_count} points, got {actual_count}")

    image_dir = ROOT / "images" / "meridians"
    for meridian in meridians:
        for point in meridian.get("points", []):
            image_name = point.get("image")
            if not image_name:
                issues.append(f"missing point image field: {meridian['id']} {point.get('code')}")
            elif not (image_dir / image_name).exists():
                issues.append(f"missing point image: {meridian['id']} {point.get('code')} -> {image_name}")

    button_rows = []
    for language in LANGUAGES:
        button_rows.extend(sum(build_keyboards(texts[language]).values(), []))
    for row in button_rows:
        for label in row:
            if len(label) > 34:
                issues.append(f"long button label ({len(label)}): {label}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="tmp/ux_preview.html")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()

    issues = audit()
    if not args.audit_only:
        output = ROOT / args.output
        render_html(output)
        print(f"Rendered UX preview: {output}")

    if issues:
        print("\nAudit issues:")
        for issue in issues[:200]:
            print(f"- {issue}")
        if len(issues) > 200:
            print(f"... and {len(issues) - 200} more")
        return 1

    print("Audit passed: no obvious UX/content issues found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
