"""Generate an interactive local simulator for the bot's main UX flows.

The simulator is intentionally lightweight: it does not talk to Telegram and
does not import bot handlers. Instead it renders the same texts and content
data, then models the critical user journeys in a browser.
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
RECOMMENDED_PATH = (
    "conception_vessel",
    "governing_vessel",
    "lung",
    "large_intestine",
    "stomach",
    "spleen",
    "heart",
    "small_intestine",
    "bladder",
    "kidney",
    "pericardium",
    "triple_burner",
    "gallbladder",
    "liver",
)
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
SOURCE_LOCATION_PREFIXES = (
    "Source location:",
    "Manbadagi joylashuv:",
    "Дереккөздегі орналасуы:",
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


def safe_html(value: str) -> str:
    escaped = escape(value or "")
    for tag in ("b", "i"):
        escaped = escaped.replace(f"&lt;{tag}&gt;", f"<{tag}>")
        escaped = escaped.replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    return escaped.replace("\n", "<br>")


def localized(item: dict[str, Any], language: str, key: str, default: str = "") -> str:
    i18n = item.get("i18n", {})
    return i18n.get(language, i18n.get("en", {})).get(key, default)


def has_cyrillic(value: str) -> bool:
    return bool(re.search(r"[\u0400-\u04FF]", value or ""))


def localized_location(point: dict[str, Any], language: str) -> str:
    value = localized(point, language, "location")
    if language == "ru" or not value:
        return value
    for prefix in SOURCE_LOCATION_PREFIXES:
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


def location_translation_status(meridians: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Count point locations that still depend on source-language wording."""
    status = {
        language: {"total": 0, "source": 0, "pending": 0}
        for language in LANGUAGES
    }
    for meridian in meridians:
        for point in meridian.get("points", []):
            for language in LANGUAGES:
                location = localized(point, language, "location")
                if not location:
                    continue
                status[language]["total"] += 1
                if location.startswith(SOURCE_LOCATION_PREFIXES):
                    status[language]["source"] += 1
                if "pending source refinement" in location.lower():
                    status[language]["pending"] += 1
    return status


def location_translation_tasks(
    meridians: list[dict[str, Any]],
    limit_per_language: int = 8,
) -> dict[str, list[dict[str, str]]]:
    """Return concrete point-location translation tasks for the QA sidebar."""
    tasks = {language: [] for language in LANGUAGES if language != "ru"}
    path_order = {meridian_id: index for index, meridian_id in enumerate(RECOMMENDED_PATH)}
    ordered_meridians = sorted(
        meridians,
        key=lambda meridian: path_order.get(meridian.get("id", ""), len(path_order)),
    )
    for meridian in ordered_meridians:
        meridian_id = meridian.get("id", "")
        for point in meridian.get("points", []):
            code = point.get("code", "")
            for language in tasks:
                if len(tasks[language]) >= limit_per_language:
                    continue
                location = localized(point, language, "location")
                if not location.startswith(SOURCE_LOCATION_PREFIXES):
                    continue
                tasks[language].append(
                    {
                        "meridianId": meridian_id,
                        "meridian": localized(meridian, language, "name", meridian_id),
                        "code": code,
                        "point": localized(point, language, "name", code),
                        "status": "pending" if "pending source refinement" in location.lower() else "source",
                    }
                )
    return tasks


def principle_group(principle_id: int, language: str) -> str:
    values = {
        "en": ("Yama", "Niyama"),
        "ru": ("Яма", "Нияма"),
        "uz": ("Yama", "Niyama"),
        "kz": ("Яма", "Нияма"),
    }
    return values[language][0 if principle_id <= 5 else 1]


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
    return "<br><br>".join(part for part in parts if part)


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
        safe_html(localized(meridian, language, "description")),
        f"<b>{labels[0]}:</b> {escape(str(meridian.get('active_time', '-')))}",
        f"<b>{labels[1]}:</b> {escape(str(meridian.get('passive_time', '-')))}",
        f"<b>{labels[2]}:</b> {len(points)}",
    ]
    direction = localized(meridian, language, "direction")
    if direction:
        parts.append(f"<b>{labels[3]}:</b> {safe_html(direction)}")
    practice = localized(meridian, language, "intro_practice")
    if practice:
        parts.append(f"<i>{labels[4]}:</i> {safe_html(practice)}")
    return "<br><br>".join(part for part in parts if part)


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
        parts.append(f"<i>{labels[3]}:</i> {escape(question)}")
    return "<br><br>".join(parts)


def build_payload() -> dict[str, Any]:
    texts = load_texts()
    principles = load_json("bot/principles.json")
    meridians = load_json("bot/meridians.json")["meridians"]
    payload: dict[str, Any] = {
        "texts": texts,
        "languages": LANGUAGES,
        "recommendedPath": RECOMMENDED_PATH,
        "translationCoverage": location_translation_status(meridians),
        "translationTasks": location_translation_tasks(meridians),
        "meridians": [],
        "principles": {},
    }

    for language in LANGUAGES:
        payload["principles"][language] = [
            {
                "id": item.get("id"),
                "button": f"{item.get('emoji', '')} {item.get('name', '')}".strip(),
                "detail": format_principle(item, language),
            }
            for item in principles[language]
        ]

    for meridian in meridians:
        payload["meridians"].append(
            {
                "id": meridian["id"],
                "names": {language: localized(meridian, language, "name", meridian["id"]) for language in LANGUAGES},
                "pointsCount": len(meridian.get("points", [])),
                "intro": {language: format_meridian_intro(meridian, language) for language in LANGUAGES},
                "points": [
                    {
                        "code": point.get("code", ""),
                        "image": point.get("image"),
                        "names": {
                            language: point.get("i18n", {}).get(language, point.get("i18n", {}).get("en", {})).get("name", "")
                            for language in LANGUAGES
                        },
                        "detail": {
                            language: format_meridian_point(meridian, index, language)
                            for language in LANGUAGES
                        },
                    }
                    for index, point in enumerate(meridian.get("points", []))
                ],
            }
        )
    return payload


def strip_html(value: str) -> str:
    return (
        value.replace("<br>", "\n")
        .replace("<b>", "")
        .replace("</b>", "")
        .replace("<i>", "")
        .replace("</i>", "")
    )


def audit_payload(payload: dict[str, Any]) -> list[str]:
    """Check core UX-flow invariants modeled by the simulator."""
    issues: list[str] = []
    texts = payload["texts"]
    meridians = payload["meridians"]
    meridians_by_id = {item["id"]: item for item in meridians}
    ready_ids = [item["id"] for item in meridians if item["pointsCount"] > 0]

    if tuple(payload["languages"]) != LANGUAGES:
        issues.append(f"languages mismatch: {payload['languages']}")

    if has_cyrillic("What changes when attention rests here"):
        issues.append("cyrillic detector treats plain English as Cyrillic")
    if not has_cyrillic("меридиан"):
        issues.append("cyrillic detector misses Cyrillic text")

    translation_coverage = payload.get("translationCoverage", {})
    translation_tasks = payload.get("translationTasks", {})
    for language in LANGUAGES:
        item = translation_coverage.get(language)
        if not item:
            issues.append(f"{language}: missing translation coverage")
            continue
        if item["source"] > item["total"] or item["pending"] > item["total"]:
            issues.append(f"{language}: impossible translation coverage values {item}")
        tasks = translation_tasks.get(language, [])
        if language == "ru":
            if tasks:
                issues.append("ru: should not have location translation tasks")
        elif item["source"] and not tasks:
            issues.append(f"{language}: source-backed locations exist but no translation tasks are shown")
        if len(tasks) > 8:
            issues.append(f"{language}: too many translation tasks shown")
        task_path_indexes = [
            RECOMMENDED_PATH.index(task["meridianId"])
            for task in tasks
            if task.get("meridianId") in RECOMMENDED_PATH
        ]
        if task_path_indexes != sorted(task_path_indexes):
            issues.append(f"{language}: translation tasks should follow recommended path order")
        for task in tasks:
            missing_task_keys = {"meridianId", "meridian", "code", "point", "status"} - set(task)
            if missing_task_keys:
                issues.append(f"{language}: incomplete translation task {task}")
            if task.get("status") not in {"source", "pending"}:
                issues.append(f"{language}: invalid translation task status {task.get('status')!r}")

    for language in LANGUAGES:
        language_texts = texts.get(language, {})
        missing = sorted(set(texts["en"].keys()) - set(language_texts.keys()))
        if missing:
            issues.append(f"{language}: missing text keys: {', '.join(missing[:12])}")

        onboarding = language_texts.get("onboarding_intro", "")
        for marker in ("<b>", "Yama", "Meridian"):
            if marker == "Yama" and language in {"ru", "kz"}:
                marker = "Яма"
            if marker == "Meridian" and language in {"ru", "kz"}:
                marker = "Меридиан"
            if marker == "Meridian" and language == "uz":
                marker = "Meridian"
            if marker not in onboarding:
                issues.append(f"{language}: onboarding does not mention {marker!r}")

        energy_markers = {
            "en": "energy",
            "ru": "энерг",
            "uz": "energiya",
            "kz": "энерг",
        }
        if energy_markers[language] not in onboarding.lower():
            issues.append(f"{language}: onboarding does not explain energy")

        for key in ("mode_menu", "about_text", "meridians_menu", "meridian_measurements_text"):
            value = language_texts.get(key, "")
            if "<b>" not in value:
                issues.append(f"{language}: {key} has no bold formatting")
            if "???" in value:
                issues.append(f"{language}: {key} contains ???")

    if len(meridians) != len(EXPECTED_POINT_COUNTS):
        issues.append(f"expected {len(EXPECTED_POINT_COUNTS)} meridians, got {len(meridians)}")

    missing_meridians = sorted(set(EXPECTED_POINT_COUNTS) - set(meridians_by_id))
    if missing_meridians:
        issues.append(f"missing meridians: {missing_meridians}")

    for meridian_id, expected_count in EXPECTED_POINT_COUNTS.items():
        item = meridians_by_id.get(meridian_id)
        if not item:
            continue
        actual_count = item["pointsCount"]
        if actual_count != expected_count:
            issues.append(f"{meridian_id}: expected {expected_count} points, got {actual_count}")

    first_ready = next((mid for mid in payload["recommendedPath"] if mid in ready_ids), None)
    if first_ready != "conception_vessel":
        issues.append(f"recommended path should start with conception_vessel, got {first_ready}")

    for meridian_id in ready_ids:
        meridian = meridians_by_id[meridian_id]
        if not meridian["points"]:
            issues.append(f"{meridian_id}: marked ready but has no point payload")
        for language in LANGUAGES:
            if "<b>" not in meridian["intro"][language]:
                issues.append(f"{meridian_id}/{language}: intro has no bold title")
        for index, point in enumerate(meridian["points"]):
            if not re.match(r"^[A-Z]+[0-9]+$", point["code"]):
                issues.append(f"{meridian_id} point {index + 1}: non-normalized point code {point['code']!r}")
            if not point.get("image"):
                issues.append(f"{meridian_id} point {index + 1}: missing simulator image")
            for language in LANGUAGES:
                detail = point["detail"][language]
                plain = strip_html(detail)
                if "???" in plain:
                    issues.append(f"{meridian_id} point {index + 1}/{language}: contains ???")
                if "pending source refinement" in plain.lower():
                    issues.append(f"{meridian_id} point {index + 1}/{language}: pending source refinement leaked")
                if language != "ru" and any(
                    prefix in plain
                    for prefix in ("Source location:", "Manbadagi joylashuv:", "Дереккөздегі орналасуы:")
                ):
                    issues.append(f"{meridian_id} point {index + 1}/{language}: raw source location prefix leaked")
                if "<b>" not in detail:
                    issues.append(f"{meridian_id} point {index + 1}/{language}: no bold formatting")
                if language == "ru" and index == 0 and "закрыт" not in plain:
                    issues.append(f"{meridian_id} point 1/ru: missing closed-point guidance")
                if language == "ru" and index > 0 and "уже пройденных точек" not in plain:
                    issues.append(f"{meridian_id} point {index + 1}/ru: missing cumulative-point guidance")

    for item in meridians:
        if item["pointsCount"] == 0:
            for language in LANGUAGES:
                if not texts[language].get("coming_soon"):
                    issues.append(f"{language}: missing coming_soon label for unavailable meridians")

    for language in LANGUAGES:
        long_buttons = []
        button_sources = [
            texts[language].get("mode_principles_only", ""),
            texts[language].get("mode_meridians_only", ""),
            texts[language].get("mode_both", ""),
            texts[language].get("meridian_measurements", ""),
            texts[language].get("meridian_change_path", ""),
        ]
        button_sources.extend(item["names"][language] for item in meridians)
        for label in button_sources:
            if len(label) > 42:
                long_buttons.append(label)
        if long_buttons:
            issues.append(f"{language}: long button labels: {long_buttons[:5]}")

    return issues


def render(output: Path) -> None:
    payload = build_payload()
    payload_json = json.dumps(payload, ensure_ascii=False)
    html = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Journey of Ascension Flow Simulator</title>
  <style>
    :root {{ color-scheme: light; --green:#6f9f5f; --dark:#243022; --paper:#fff; --bg:#dfeccc; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 16px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--dark); }}
    .app {{ max-width: 980px; margin: 0 auto; padding: 22px; display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 18px; }}
    .phone {{ max-width: 520px; min-height: 680px; background: linear-gradient(140deg, #e6f2d2, #b8d59d 55%, #83b98f); border-radius: 24px; padding: 18px 14px; box-shadow: 0 20px 60px rgba(36,48,34,.22); }}
    .top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; color: rgba(36,48,34,.8); font-weight: 700; }}
    .bubble {{ background: var(--paper); border-radius: 18px; padding: 18px 20px; box-shadow: 0 1px 2px rgba(0,0,0,.16); max-height: 450px; overflow: auto; }}
    .bubble b {{ font-weight: 760; }}
    .bubble i {{ color: #3b5a38; }}
    .media {{ width: calc(100% + 40px); margin: -18px -20px 16px; display: block; max-height: 360px; object-fit: cover; border-radius: 18px 18px 4px 4px; background: #edf1ea; }}
    .keyboard {{ display: grid; gap: 6px; margin-top: 8px; }}
    .row {{ display: grid; gap: 6px; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); }}
    button {{ border: 0; min-height: 46px; border-radius: 10px; padding: 8px 12px; background: rgba(73,121,61,.76); color: white; font: 700 16px/1.18 inherit; cursor: pointer; }}
    button:hover {{ background: rgba(54,101,45,.86); }}
    button:disabled {{ cursor: not-allowed; opacity: .5; }}
    .panel {{ background: rgba(255,255,255,.72); border-radius: 16px; padding: 14px; align-self: start; }}
    .panel h2 {{ margin: 0 0 10px; font-size: 17px; }}
    .field {{ display: grid; gap: 6px; margin-bottom: 12px; }}
    select {{ min-height: 38px; border: 1px solid rgba(36,48,34,.2); border-radius: 8px; padding: 6px 8px; font: inherit; }}
    .state {{ margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(36,48,34,.18); font-size: 14px; }}
    .muted {{ color: rgba(36,48,34,.68); }}
    .coverage {{ display: grid; gap: 6px; margin-top: 10px; font-size: 14px; }}
    .bar {{ display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; }}
    .task {{ padding: 6px 0; border-top: 1px solid rgba(36,48,34,.14); line-height: 1.25; }}
    .task small {{ display: block; color: rgba(36,48,34,.68); margin-top: 2px; }}
    @media (max-width: 820px) {{ .app {{ grid-template-columns: 1fr; }} .phone {{ max-width: none; }} }}
  </style>
</head>
<body>
  <main class="app">
    <section class="phone" aria-label="Telegram-like bot simulator">
      <div class="top"><span>Journey of Ascension</span><span id="screenName"></span></div>
      <div id="bubble" class="bubble"></div>
      <div id="keyboard" class="keyboard"></div>
    </section>
    <aside class="panel">
      <h2>Local UX Simulator</h2>
      <div class="field">
        <label for="language">Language</label>
        <select id="language"></select>
      </div>
      <div class="field">
        <label for="scenario">Quick scenario</label>
        <select id="scenario">
          <option value="onboarding">New user onboarding</option>
          <option value="main">Main menu</option>
          <option value="meridians">Meridians section</option>
          <option value="currentPoint">Current meridian point</option>
          <option value="principles">Yama/Niyama section</option>
        </select>
      </div>
      <button id="reset">Open scenario</button>
      <div class="state">
        <b>Simulated state</b>
        <div id="state"></div>
      </div>
      <div class="state">
        <b>Content coverage</b>
        <div id="coverage" class="coverage"></div>
      </div>
      <div class="state">
        <b>Location translation</b>
        <div id="translationCoverage" class="coverage"></div>
      </div>
      <div class="state">
        <b>Next location tasks</b>
        <div id="translationTasks" class="coverage"></div>
      </div>
    </aside>
  </main>
  <script id="payload" type="application/json">{payload_json}</script>
  <script>
    const payload = JSON.parse(document.getElementById('payload').textContent);
    const languageSelect = document.getElementById('language');
    const scenarioSelect = document.getElementById('scenario');
    const bubble = document.getElementById('bubble');
    const keyboard = document.getElementById('keyboard');
    const screenName = document.getElementById('screenName');
    const stateBox = document.getElementById('state');
    const coverageBox = document.getElementById('coverage');
    const translationCoverageBox = document.getElementById('translationCoverage');
    const translationTasksBox = document.getElementById('translationTasks');

    const state = {{
      language: 'ru',
      screen: 'onboarding',
      principlesEnabled: true,
      meridiansEnabled: false,
      learningMode: null,
      currentMeridianId: 'conception_vessel',
      currentPointIndex: -1,
      currentPointsPage: 0,
      completed: [],
    }};

    for (const lang of payload.languages) {{
      const option = document.createElement('option');
      option.value = lang;
      option.textContent = lang.toUpperCase();
      languageSelect.append(option);
    }}
    languageSelect.value = state.language;

    function t(key) {{ return payload.texts[state.language][key] || payload.texts.en[key] || key; }}
    function fmt(value) {{ return (value || '').replaceAll('\\n', '<br>').replace(/\\*\\*(.*?)\\*\\*/g, '<b>$1</b>'); }}
    function meridian() {{ return payload.meridians.find((item) => item.id === state.currentMeridianId) || payload.meridians[0]; }}
    function pointImageUrl(point) {{ return point && point.image ? `../images/meridians/${{encodeURIComponent(point.image)}}` : null; }}
    function firstReadyMeridian() {{
      for (const id of payload.recommendedPath) {{
        const item = payload.meridians.find((candidate) => candidate.id === id && candidate.pointsCount > 0);
        if (item) return item;
      }}
      return payload.meridians.find((item) => item.pointsCount > 0) || payload.meridians[0];
    }}
    function setScreen(name) {{ state.screen = name; render(); }}
    function rows(items) {{
      keyboard.innerHTML = '';
      for (const row of items) {{
        const element = document.createElement('div');
        element.className = 'row';
        element.style.setProperty('--cols', row.length);
        for (const item of row) {{
          const button = document.createElement('button');
          button.textContent = item.label;
          button.disabled = Boolean(item.disabled);
          button.addEventListener('click', item.action);
          element.append(button);
        }}
        keyboard.append(element);
      }}
    }}
    function show(title, html, buttons, mediaUrl = null) {{
      screenName.textContent = title;
      bubble.innerHTML = `${{mediaUrl ? `<img class="media" src="${{mediaUrl}}" alt="">` : ''}}${{html}}`;
      rows(buttons);
      renderState();
    }}

    function renderState() {{
      stateBox.innerHTML = `
        <div>language: <b>${{state.language}}</b></div>
        <div>principles: <b>${{state.principlesEnabled ? 'on' : 'off'}}</b></div>
        <div>meridians: <b>${{state.meridiansEnabled ? 'on' : 'off'}}</b></div>
        <div>path: <b>${{state.learningMode || '-'}}</b></div>
        <div>meridian: <b>${{meridian().names[state.language]}}</b></div>
        <div>point: <b>${{state.currentPointIndex + 1 || 'intro'}}</b></div>
      `;
    }}

    function renderCoverage() {{
      coverageBox.innerHTML = payload.meridians.map((item) => `
        <div class="bar"><span>${{item.names[state.language]}}</span><b>${{item.pointsCount}}</b></div>
      `).join('');
      translationCoverageBox.innerHTML = payload.languages.map((language) => {{
        const item = payload.translationCoverage[language];
        const ready = Math.max(0, item.total - item.source);
        return `
          <div class="bar"><span>${{language.toUpperCase()}} ready locations</span><b>${{ready}}/${{item.total}}</b></div>
          <div class="bar muted"><span>source RU / pending</span><b>${{item.source}} / ${{item.pending}}</b></div>
        `;
      }}).join('');
      translationTasksBox.innerHTML = payload.languages
        .filter((language) => language !== 'ru')
        .map((language) => {{
          const tasks = (payload.translationTasks[language] || []).slice(0, 4);
          const items = tasks.map((task) => `
            <div class="task">
              <b>${{language.toUpperCase()}} · ${{task.code}}</b> · ${{task.meridian}}
              <small>${{task.point}}${{task.status === 'pending' ? ' · pending source' : ' · source RU'}}</small>
            </div>
          `).join('');
          return `<div class="muted">${{language.toUpperCase()}}</div>${{items || '<div class="muted">No open tasks</div>'}}`;
        }}).join('');
    }}

    function chooseMode(mode) {{
      state.principlesEnabled = mode === 'principles' || mode === 'both';
      state.meridiansEnabled = mode === 'meridians' || mode === 'both';
      setScreen('timezone');
    }}

    function renderOnboarding() {{
      show('Onboarding', fmt(t('onboarding_intro')), [
        [{{ label: t('mode_meridians_only'), action: () => chooseMode('meridians') }}],
        [{{ label: t('mode_principles_only'), action: () => chooseMode('principles') }}],
        [{{ label: t('mode_both'), action: () => chooseMode('both') }}],
      ]);
    }}

    function renderTimezone() {{
      const key = state.principlesEnabled && state.meridiansEnabled
        ? 'timezone_step_both'
        : state.meridiansEnabled ? 'timezone_step_meridians' : 'timezone_step_principles';
      show('Timezone', fmt(t(key)), [
        [{{ label: '🇷🇺 Москва +3', action: () => setScreen('time') }}, {{ label: '🇺🇿 Ташкент +5', action: () => setScreen('time') }}],
        [{{ label: '🇰🇿 Алматы +5', action: () => setScreen('time') }}, {{ label: '🌍 UTC +0', action: () => setScreen('time') }}],
      ]);
    }}

    function renderTime() {{
      const key = state.principlesEnabled && state.meridiansEnabled
        ? 'time_step_both'
        : state.meridiansEnabled ? 'time_step_meridians' : 'time_step_principles';
      show('Time', fmt(t(key)), [
        [{{ label: '08:00', action: () => setScreen(state.principlesEnabled ? 'skipDays' : 'main') }}, {{ label: '20:00', action: () => setScreen(state.principlesEnabled ? 'skipDays' : 'main') }}],
      ]);
    }}

    function renderSkipDays() {{
      const note = state.language === 'en'
        ? 'No days selected - messages will be sent daily'
        : state.language === 'ru'
          ? 'Дни не выбраны - сообщения будут отправляться ежедневно'
          : state.language === 'uz'
            ? 'Kunlar tanlanmagan - xabarlar har kuni yuboriladi'
            : 'Күндер таңдалмаған - хабарлар күн сайын жіберіледі';
      show('Skip days', `${{fmt(t('skip_days_step'))}}<br><br><b>${{note}}</b>`, [
        [{{ label: '🎯 ' + (t('no_skip_days') || 'No skip days'), action: () => setScreen('main') }}],
        [{{ label: '📅 Weekends', action: () => setScreen('main') }}],
      ]);
    }}

    function renderMain() {{
      show('Main menu', fmt(t('menu')), [
        [{{ label: t('menu_principles'), action: () => setScreen('principles') }}, {{ label: t('menu_meridians'), action: () => setScreen('meridians') }}],
        [{{ label: t('menu_modes'), action: () => setScreen('modes') }}, {{ label: t('menu_settings'), action: () => setScreen('settings') }}],
        [{{ label: t('menu_about'), action: () => setScreen('about') }}, {{ label: t('menu_feedback'), action: () => setScreen('feedback') }}],
        [{{ label: t('menu_stop'), action: () => setScreen('stop') }}],
      ]);
    }}

    function renderModes() {{
      show('My Path', fmt(t('mode_menu')), [
        [{{ label: t('mode_principles_only'), action: () => chooseMode('principles') }}],
        [{{ label: t('mode_meridians_only'), action: () => chooseMode('meridians') }}],
        [{{ label: t('mode_both'), action: () => chooseMode('both') }}],
        [{{ label: t('back_to_menu'), action: () => setScreen('main') }}],
      ]);
    }}

    function renderMeridians() {{
      show('Meridians', fmt(t('meridians_menu')), [
        [{{ label: t('current_meridian'), action: () => state.learningMode ? setScreen('currentMeridian') : setScreen('meridianPath') }}],
        [{{ label: t('meridian_change_path'), action: () => setScreen('meridianPath') }}, {{ label: t('meridian_measurements'), action: () => setScreen('measurements') }}],
        [{{ label: t('back_to_menu'), action: () => setScreen('main') }}],
      ]);
    }}

    function renderMeridianPath() {{
      show('Path', fmt(t('meridian_mode_menu')), [
        [{{ label: t('meridian_guided_path'), action: () => {{ state.learningMode = 'guided'; state.currentMeridianId = firstReadyMeridian().id; setScreen('currentMeridian'); }} }}],
        [{{ label: t('meridian_free_choice'), action: () => {{ state.learningMode = 'free'; setScreen('chooseMeridian'); }} }}],
        [{{ label: t('meridian_back'), action: () => setScreen('meridians') }}],
      ]);
    }}

    function renderCurrentMeridian() {{
      const item = meridian();
      const point = state.currentPointIndex >= 0 ? item.points[state.currentPointIndex] : null;
      const html = state.currentPointIndex >= 0 && item.points[state.currentPointIndex]
        ? item.points[state.currentPointIndex].detail[state.language]
        : item.intro[state.language];
      const buttons = state.currentPointIndex < 0
        ? [
          [{{ label: t('meridian_start_points'), action: nextPoint, disabled: item.pointsCount === 0 }}],
          [{{ label: t('all_points'), action: () => {{ state.currentPointsPage = 0; setScreen('allPoints'); }}, disabled: item.pointsCount === 0 }}, {{ label: t('complete_meridian'), action: completeMeridian }}],
          [{{ label: t('meridian_back'), action: () => setScreen('meridians') }}],
        ]
        : [
          [
            ...(state.currentPointIndex > 0 ? [{{ label: t('prev_point'), action: prevPoint, disabled: item.pointsCount === 0 }}] : []),
            ...(state.currentPointIndex < item.pointsCount - 1 ? [{{ label: t('next_point'), action: nextPoint, disabled: item.pointsCount === 0 }}] : []),
          ],
          [{{ label: t('all_points'), action: () => {{ state.currentPointsPage = 0; setScreen('allPoints'); }}, disabled: item.pointsCount === 0 }}, {{ label: t('complete_meridian'), action: completeMeridian }}],
          [{{ label: t('meridian_back'), action: () => setScreen('meridians') }}],
        ];
      show('Current focus', html, buttons, pointImageUrl(point));
    }}

    function nextPoint() {{
      const item = meridian();
      state.currentPointIndex = Math.min(state.currentPointIndex + 1, item.pointsCount - 1);
      setScreen('currentMeridian');
    }}

    function prevPoint() {{
      state.currentPointIndex = Math.max(state.currentPointIndex - 1, 0);
      setScreen('currentMeridian');
    }}

    function completeMeridian() {{
      if (!state.completed.includes(state.currentMeridianId)) state.completed.push(state.currentMeridianId);
      const ready = payload.recommendedPath
        .map((id) => payload.meridians.find((item) => item.id === id && item.pointsCount > 0))
        .filter(Boolean);
      const index = ready.findIndex((item) => item.id === state.currentMeridianId);
      if (state.learningMode === 'guided' && ready[index + 1]) {{
        state.currentMeridianId = ready[index + 1].id;
        state.currentPointIndex = -1;
      }}
      setScreen('meridians');
    }}

    function renderChooseMeridian() {{
      const buttons = [];
      const items = payload.meridians;
      for (let index = 0; index < items.length; index += 2) {{
        buttons.push(items.slice(index, index + 2).map((item) => ({{
          label: `${{item.names[state.language]}} (${{item.pointsCount}})`,
          action: () => {{ state.currentMeridianId = item.id; state.currentPointIndex = -1; state.learningMode = 'free'; setScreen('currentMeridian'); }},
          disabled: item.pointsCount === 0,
        }})));
      }}
      buttons.push([{{ label: t('meridian_back'), action: () => setScreen('meridians') }}]);
      show('Choose meridian', t('choose_meridian'), buttons);
    }}

    function renderAllPoints() {{
      const item = meridian();
      const pageSize = 10;
      const totalPages = Math.max(1, Math.ceil(item.points.length / pageSize));
      state.currentPointsPage = Math.max(0, Math.min(state.currentPointsPage, totalPages - 1));
      const start = state.currentPointsPage * pageSize;
      const buttons = item.points.slice(start, start + pageSize).map((point, offset) => {{
        const index = start + offset;
        return [{{ label: `${{index + 1}}. ${{point.code}} ${{point.names[state.language]}}`, action: () => {{ state.currentPointIndex = index; setScreen('currentMeridian'); }} }}];
      }});
      if (totalPages > 1) {{
        const nav = [];
        if (state.currentPointsPage > 0) nav.push({{ label: '◀️ 10', action: () => {{ state.currentPointsPage -= 1; setScreen('allPoints'); }} }});
        nav.push({{ label: `${{state.currentPointsPage + 1}}/${{totalPages}}`, action: () => {{}} }});
        if (state.currentPointsPage < totalPages - 1) nav.push({{ label: '10 ▶️', action: () => {{ state.currentPointsPage += 1; setScreen('allPoints'); }} }});
        buttons.push(nav);
      }}
      buttons.push([{{ label: t('meridian_back'), action: () => setScreen('currentMeridian') }}]);
      const pageNote = totalPages > 1 ? `<br><br>Page ${{state.currentPointsPage + 1}}/${{totalPages}}` : '';
      show('All points', `<b>${{t('all_points')}}</b>${{pageNote}}`, buttons);
    }}

    function renderPrinciples() {{
      show('Yama/Niyama', t('principles_menu').replaceAll('\\n', '<br>'), [
        [{{ label: t('principles_random'), action: () => setScreen('principleDetail') }}, {{ label: t('principles_all'), action: () => setScreen('allPrinciples') }}],
        [{{ label: t('back_to_menu'), action: () => setScreen('main') }}],
      ]);
    }}

    function renderPrincipleDetail(index = 0) {{
      const item = payload.principles[state.language][index] || payload.principles[state.language][0];
      show('Principle', item.detail, [
        [{{ label: t('principles_random'), action: () => renderPrincipleDetail((index + 3) % payload.principles[state.language].length) }}, {{ label: t('principles_all'), action: () => setScreen('allPrinciples') }}],
        [{{ label: t('back_to_menu'), action: () => setScreen('principles') }}],
      ]);
    }}

    function renderAllPrinciples() {{
      const buttons = payload.principles[state.language].map((item, index) => [{{ label: item.button, action: () => renderPrincipleDetail(index) }}]);
      buttons.push([{{ label: t('back_to_menu'), action: () => setScreen('principles') }}]);
      show('All principles', `<b>${{t('principles_all')}}</b>`, buttons);
    }}

    function renderSimple(key, title = key) {{
      show(title, fmt(t(key) || key), [[{{ label: t('back_to_menu'), action: () => setScreen('main') }}]]);
    }}

    function render() {{
      renderCoverage();
      const routes = {{
        onboarding: renderOnboarding,
        timezone: renderTimezone,
        time: renderTime,
        main: renderMain,
        modes: renderModes,
        meridians: renderMeridians,
        meridianPath: renderMeridianPath,
        currentMeridian: renderCurrentMeridian,
        chooseMeridian: renderChooseMeridian,
        allPoints: renderAllPoints,
        skipDays: renderSkipDays,
        measurements: () => show('Measurements', fmt(t('meridian_measurements_text')), [[{{ label: t('meridian_back'), action: () => setScreen('meridians') }}]]),
        principles: renderPrinciples,
        principleDetail: () => renderPrincipleDetail(0),
        allPrinciples: renderAllPrinciples,
        about: () => renderSimple('about_text', 'About'),
        settings: () => renderSimple('settings_menu', 'Settings'),
        feedback: () => renderSimple('feedback_prompt', 'Feedback'),
        stop: () => renderSimple('stop_feedback_prompt', 'Stop'),
      }};
      (routes[state.screen] || renderMain)();
    }}

    languageSelect.addEventListener('change', () => {{
      state.language = languageSelect.value;
      render();
    }});
    document.getElementById('reset').addEventListener('click', () => {{
      const scenario = scenarioSelect.value;
      if (scenario === 'currentPoint') {{
        state.principlesEnabled = true;
        state.meridiansEnabled = true;
        state.learningMode = 'guided';
        state.currentMeridianId = firstReadyMeridian().id;
        state.currentPointIndex = 0;
        state.screen = 'currentMeridian';
      }} else if (scenario === 'meridians') {{
        state.learningMode = null;
        state.currentPointIndex = -1;
        state.screen = 'meridians';
      }} else if (scenario === 'principles') {{
        state.screen = 'principles';
      }} else if (scenario === 'main') {{
        state.screen = 'main';
      }} else {{
        state.screen = 'onboarding';
      }}
      render();
    }});
    render();
  </script>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"Rendered flow simulator: {output}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="tmp/ux_simulator.html")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    payload = build_payload()
    issues = audit_payload(payload)
    if not args.audit_only:
        render(ROOT / args.output)

    if issues:
        print("Simulator audit issues:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Simulator audit passed: critical UX flows look consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
