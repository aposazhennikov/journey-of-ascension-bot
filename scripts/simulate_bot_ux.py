"""Generate an interactive local simulator for the bot's main UX flows.

The simulator is intentionally lightweight: it does not talk to Telegram and
does not import bot handlers. Instead it renders the same texts and content
data, then models the critical user journeys in a browser.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
import types
from html import escape, unescape
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("en", "ru", "uz", "kz")
OBSERVATION_LABELS = {
    "en": "Observe:",
    "ru": "Наблюдение:",
    "uz": "Kuzatish:",
    "kz": "Бақылау:",
}
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
SOURCE_NOTE_PHRASES = (
    "Classical note:",
    "Klassik izoh:",
    "Классическая заметка:",
    "Классическое пояснение:",
    "Классикалық түсіндірме:",
    "Original source location",
    "Manbadagi asl joylashuv",
    "Дереккөздегі бастапқы орналасуы",
)
HARD_MEDICAL_PHRASES = (
    "treatment",
    "disease",
    "diagnosis",
    "cure",
    "acupuncture therapy",
    "tonification",
    "sedation",
    "иглотерап",
    "тонизац",
    "седатир",
    "лечени",
    "болезн",
    "диагноз",
)
SOURCE_EDITORIAL_TAILS = (
    "В книге",
    "Для нахождения точки",
    "пациент",
    "Секретные рецепты",
    "In the book",
    "To find the point",
    "(рис.",
    "(fig.",
)


def load_text_definitions() -> dict[str, Any]:
    source = (ROOT / "bot" / "handlers.py").read_text(encoding="utf-8-sig")
    module = ast.parse(source)
    values: dict[str, Any] = {}
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in {"TEXTS", "TEXTS_UPDATE", "LIVE_TEXT_OVERRIDES"}:
                values[target.id] = ast.literal_eval(node.value)
    return values


def load_texts() -> dict[str, dict[str, str]]:
    values = load_text_definitions()
    texts = values.get("TEXTS", {})
    updates = values.get("TEXTS_UPDATE", {})
    for language, language_updates in updates.items():
        texts.setdefault(language, {}).update(language_updates)
    overrides = values.get("LIVE_TEXT_OVERRIDES", {})
    for language, language_overrides in overrides.items():
        texts.setdefault(language, {}).update(language_overrides)
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


def has_source_or_medical_leak(value: str) -> bool:
    lowered = value.lower()
    return any(phrase in value for phrase in SOURCE_NOTE_PHRASES) or any(phrase in lowered for phrase in HARD_MEDICAL_PHRASES)


def localized_point_name(point: dict[str, Any], language: str) -> str:
    name = localized(point, language, "name")
    if language in {"en", "uz"} and has_cyrillic(name):
        return ""
    return name


def localized_location(point: dict[str, Any], language: str) -> str:
    value = localized(point, language, "location")
    if language in {"ru", "kz"} or not value:
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
        "en": ("Part", "Today's focus", "Practice"),
        "ru": ("Часть", "Фокус дня", "Практика"),
        "uz": ("Qismi", "Bugungi fokus", "Amaliyot"),
        "kz": ("Бөлігі", "Бүгінгі фокус", "Тәжірибе"),
    }[language]
    reminders = {
        "en": "Keep this principle especially visible today. The rest are not paused; we are simply giving one of them more attention.",
        "ru": "Сегодня держите этот принцип особенно близко. Остальные не выключаются; мы просто даём одному из них больше внимания.",
        "uz": "Bugun shu tamoyilni ayniqsa yaqin tuting. Qolganlari to'xtamaydi; biz faqat bittasiga ko'proq e'tibor beramiz.",
        "kz": "Бүгін осы қағиданы ерекше жақын ұстаңыз. Қалғандары тоқтамайды; біз тек біреуіне көбірек назар береміз.",
    }[language]
    description = principle.get("description", "")
    if len(description) > 220:
        candidate = description[:217].rstrip()
        sentence_end = max(candidate.rfind("."), candidate.rfind("!"), candidate.rfind("?"))
        description = candidate[:sentence_end + 1] if sentence_end >= 99 else candidate.rstrip(",;:") + "..."
    parts = [
        f"<b>{escape(principle.get('name', ''))}</b> {escape(principle.get('emoji', ''))}",
        f"<b>{labels[0]}:</b> {escape(principle_group(int(principle.get('id', 0)), language))}",
        escape(principle.get("short_description", "")),
        f"<b>{labels[1]}:</b> {escape(reminders)}",
        escape(description),
        f"💡 <b>{labels[2]}:</b> <i>{escape(principle.get('practice_tip', ''))}</i>",
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
            "Begin with the first point: find it through body sensation, breath, and attention. If it feels weak, treat it as not yet open: stay longer, massage it gently, and breathe through it with attention.",
            "Recall the points you have already studied. Keep them in the background, add the current point, and connect them as one line of attention. If it is hard to feel, massage it gently and stay until the sensation becomes steadier.",
        ),
        "ru": (
            "Начните с первой точки: найдите её через ощущение тела, дыхание и внимание. Если ощущение слабое, считайте точку пока закрытой: побудьте дольше, мягко помассируйте её и дышите через неё вниманием.",
            "Вспомните ощущение уже пройденных точек. Удерживая их фоном, добавьте текущую и соедините всё в одну линию внимания. Если точка не ощущается, мягко помассируйте её и оставайтесь дольше, пока ощущение не станет устойчивее.",
        ),
        "uz": (
            "Birinchi nuqtadan boshlang: uni tana sezgisi, nafas va diqqat orqali toping. Agar sezgi kuchsiz bo'lsa, nuqtani hali ochilmagan deb qabul qiling: uzoqroq turing, yengil massaj qiling va diqqat bilan shu nuqta orqali nafas oling.",
            "Oldin o'rganilgan nuqtalarni eslang. Ularni fon sifatida ushlab, hozirgi nuqtani qo'shing va bitta diqqat chizig'iga ulang. Agar nuqta sezilmasa, yengil massaj qiling va sezgi barqarorroq bo'lguncha turing.",
        ),
        "kz": (
            "Бірінші нүктеден бастаңыз: оны дене сезімі, тыныс және зейін арқылы табыңыз. Егер сезім әлсіз болса, нүктені әзірге ашылмаған деп қабылдаңыз: ұзағырақ болыңыз, жеңіл уқалаңыз және зейінмен сол нүкте арқылы тыныстаңыз.",
            "Бұрын өткен нүктелерді еске түсіріңіз. Оларды фон ретінде ұстап, қазіргі нүктені қосыңыз да, бәрін бір зейін сызығына біріктіріңіз. Егер нүкте сезілмесе, жеңіл уқалап, сезім тұрақтырақ болғанша ұзағырақ болыңыз.",
        ),
    }
    return notes[language][0 if point_index == 0 else 1]


def point_area_practice_hint(location: str, language: str) -> str:
    normalized = (location or "").lower()
    cues = {
        "ru": (
            (("пуп", "живот", "лобков", "промеж", "анус", "половых", "мошон"), "Смягчите живот и таз; пусть дыхание не толкает ощущение, а будто освобождает для него место."),
            (("позвон", "крестц", "копчик", "спин", "затыл"), "Выпрямитесь без напряжения и почувствуйте, как точка включается в заднюю срединную линию."),
            (("груд", "ребр", "ключиц"), "Дайте грудной клетке чуть больше пространства; наблюдайте, меняется ли глубина дыхания."),
            (("горл", "ше", "подбород", "губ", "нос", "лиц", "лоб", "тем", "голов"), "Расслабьте лицо, язык и горло; иногда точка откликается только после этого."),
            (("рук", "кист", "пал", "локт", "плеч"), "Отпустите плечо и кисть, чтобы внимание не застревало только в поверхности кожи."),
            (("стоп", "пят", "лодыж", "голен", "колен", "бедр"), "Почувствуйте опору и вес тела; так точка легче соединяется с общей линией меридиана."),
        ),
        "en": (
            (("navel", "abdomen", "pubic", "perine", "anus", "genital", "scrot"), "Soften the belly and pelvis; let the breath make room for the sensation instead of pushing it."),
            (("vertebra", "sacral", "coccyx", "spine", "back", "occip"), "Lengthen the spine without strain and feel how the point joins the central back line."),
            (("chest", "rib", "clavicle"), "Give the chest a little more space and notice whether the depth of breathing changes."),
            (("throat", "neck", "chin", "lip", "nose", "face", "forehead", "head"), "Relax the face, tongue, and throat; sometimes the point responds only after that."),
            (("arm", "hand", "finger", "elbow", "shoulder"), "Release the shoulder and hand so attention does not stay only on the surface of the skin."),
            (("foot", "heel", "ankle", "leg", "knee", "thigh"), "Feel the support and weight of the body; the point can then connect more easily with the meridian line."),
        ),
        "uz": (
            (("kindik", "qorin", "pub", "oraliq", "anus", "jinsiy"), "Qorin va tosni yumshating; nafas sezgini itarmasin, unga joy ochsin."),
            (("umurtqa", "dumg'aza", "dum", "orqa", "ensa"), "Umurtqani zo'riqmasdan tik tuting va nuqta orqa o'rta chiziqqa qanday qo'shilishini sezing."),
            (("ko'krak", "qovurg", "o'mrov"), "Ko'krak qafasiga biroz kenglik bering va nafas chuqurligi o'zgaradimi, kuzating."),
            (("tomoq", "bo'yin", "iyak", "lab", "burun", "yuz", "peshona", "bosh"), "Yuz, til va tomoqni bo'shating; ba'zan nuqta shundan keyingina javob beradi."),
            (("qo'l", "kaft", "barmoq", "tirsak", "yelka"), "Yelka va kaftni bo'shating, shunda diqqat faqat teri yuzasida qolib ketmaydi."),
            (("oyoq", "tovon", "to'piq", "boldir", "tizza", "son"), "Tana tayanchini va og'irligini sezing; shunda nuqta meridian chizig'iga osonroq ulanadi."),
        ),
        "kz": (
            (("кіндік", "іш", "қасаға", "аралық", "анус", "жыныс"), "Іш пен жамбасты жұмсартыңыз; тыныс сезімді итермей, оған орын ашсын."),
            (("омыртқа", "сегізкөз", "құйымшақ", "арқа", "шүйде"), "Омыртқаны күш салмай түзеу ұстап, нүктенің артқы ортаңғы сызыққа қалай қосылатынын сезіңіз."),
            (("кеуде", "қабырға", "бұғана"), "Кеуде қуысына аздап кеңістік беріп, тыныс тереңдігі өзгере ме, байқаңыз."),
            (("тамақ", "мойын", "иек", "ерін", "мұрын", "бет", "маңдай", "бас"), "Бет, тіл және тамақты босатыңыз; кейде нүкте содан кейін ғана жауап береді."),
            (("қол", "алақан", "саусақ", "шынтақ", "иық"), "Иық пен алақанды босатыңыз, сонда зейін тек тері бетінде қалып қоймайды."),
            (("аяқ", "өкше", "тобық", "балтыр", "тізе", "сан"), "Дененің тірегі мен салмағын сезіңіз; сонда нүкте меридиан сызығына жеңілірек қосылады."),
        ),
    }.get(language, ())
    for keywords, cue in cues:
        if any(keyword in normalized for keyword in keywords):
            return cue
    return ""


def short_point_area(location: str, limit: int = 96) -> str:
    if not location:
        return ""
    area = location.strip().split(".")[0].split(";")[0]
    if len(area) <= limit:
        return area
    return area[:limit].rsplit(" ", 1)[0].rstrip(",") + "..."


def compact_point_location(location: str, limit: int = 260) -> str:
    if len(location) <= limit:
        return location
    return location[:limit].rsplit(" ", 1)[0].rstrip(",") + "..."


def clean_point_location(location: str) -> str:
    if not location:
        return ""
    stop_markers = (
        ". В книге",
        ". Для нахождения",
        ". При использовании",
        ". Находят",
        ". Используют",
        ". Находят и используют",
        ". Точка расположена",
        ". Цзин-цюй",
        ". Нүкте",
        ". Nuqta",
        ". The point",
        ". To find",
        ". In the book",
    )
    cleaned = location.strip()
    for marker in stop_markers:
        index = cleaned.find(marker)
        if index > 0:
            cleaned = cleaned[:index].rstrip()
            break
    cleaned = re.sub(r"\s*\((?:рис|fig)\.?\s*\d+[a-zа-я]?\)\s*", " ", cleaned, flags=re.IGNORECASE).strip()
    return cleaned.rstrip(":;,.") + ("." if cleaned and not cleaned.endswith(".") else "")


def point_observation_prompt(point: dict[str, Any], point_index: int, language: str, point_title: str, location: str) -> str:
    area = short_point_area(location)
    title = point_title or point.get("code", "")
    if language == "ru":
        if point_index == 0:
            return f"Что первым откликается в точке {title}: тепло, давление, пульсация, пустота или сопротивление внимания?{f' Проверьте область: {area}.' if area else ''}"
        return f"Удерживая предыдущие точки, что меняется, когда вы добавляете {title}: линия становится яснее, теплее, плотнее или где-то обрывается?{f' Проверьте область: {area}.' if area else ''}"
    if language == "uz":
        if point_index == 0:
            return f"{title} nuqtasida birinchi nima javob beradi: iliqlik, bosim, pulsatsiya, bo'shliq yoki diqqatga qarshilik?{f' Soha: {area}.' if area else ''}"
        return f"Oldingi nuqtalarni ushlab turib, {title} qo'shilganda nima o'zgaradi: chiziq aniqroq, iliqroq, zichroq bo'ladimi yoki qayerdadir uziladimi?{f' Soha: {area}.' if area else ''}"
    if language == "kz":
        if point_index == 0:
            return f"{title} нүктесінде алдымен не жауап береді: жылу, қысым, соғу, бос кеңістік немесе зейінге қарсылық па?{f' Аймақ: {area}.' if area else ''}"
        return f"Алдыңғы нүктелерді ұстап тұрып, {title} қосылғанда не өзгереді: сызық анығырақ, жылырақ, тығызырақ бола ма, әлде бір жерде үзіле ме?{f' Аймақ: {area}.' if area else ''}"
    if point_index == 0:
        return f"What responds first at {title}: warmth, pressure, pulsation, emptiness, or resistance to attention?{f' Check the area: {area}.' if area else ''}"
    return f"While holding the previous points, what changes when {title} is added: does the line become clearer, warmer, denser, or does it break somewhere?{f' Check the area: {area}.' if area else ''}"


def format_meridian_point(meridian: dict[str, Any], point_index: int, language: str) -> str:
    labels = {
        "en": ("Point", "Location", "Focus", "Observe"),
        "ru": ("Точка", "Расположение", "Концентрация", "Наблюдение"),
        "uz": ("Nuqta", "Joylashuv", "Diqqat", "Kuzatish"),
        "kz": ("Нүкте", "Орналасуы", "Зейін", "Бақылау"),
    }[language]
    points = meridian.get("points", [])
    point = points[point_index]
    point_title = " ".join(part for part in (point.get("code", ""), localized_point_name(point, language)) if part)
    location = clean_point_location(localized_location(point, language))
    parts = [
        f"<b>{escape(localized(meridian, language, 'name'))}</b>",
        f"<b>{labels[0]} {point_index + 1}/{len(points)}:</b> {escape(point_title)}",
        f"<b>{labels[1]}:</b> {escape(compact_point_location(location))}",
    ]
    practice_parts = [practice_note(point_index, language)]
    area_hint = point_area_practice_hint(location, language)
    if area_hint:
        practice_parts.append(area_hint)
    parts.append(f"<b>{labels[2]}:</b> {escape(' '.join(practice_parts))}")
    question = point_observation_prompt(point, point_index, language, point_title, location)
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
        overview_image = None
        for extension in (".jpg", ".png", ".gif"):
            candidate = ROOT / "images" / "meridians" / f"{meridian['id']}{extension}"
            if candidate.exists():
                overview_image = candidate.name
                break
        payload["meridians"].append(
            {
                "id": meridian["id"],
                "overviewImage": overview_image,
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


def fit_html_caption(text: str, max_length: int = 1024) -> str:
    if len(text) <= max_length:
        return text

    def fit_plain(source: str, budget: int) -> str:
        if budget <= 3:
            return "..."[:max(0, budget)]
        plain = unescape(strip_html(source))
        low, high = 0, len(plain)
        best = ""
        while low <= high:
            middle = (low + high) // 2
            candidate = escape(plain[:middle].rstrip()) + "..."
            if len(candidate) <= budget:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        return best or "..."

    def plain_fallback(source: str) -> str:
        return fit_plain(source, max_length)

    normalized = text.replace("<br><br>", "\n\n")
    parts = normalized.split("\n\n")
    kept = []
    for part in parts:
        candidate = "\n\n".join([*kept, part]) if kept else part
        if len(candidate) <= max_length - 3:
            kept.append(part)
        else:
            if kept:
                prefix = "\n\n".join(kept)
                separator = "\n\n"
                budget = max_length - len(prefix) - len(separator)
                if budget > 3:
                    return prefix + separator + fit_plain(part, budget)
            break

    if kept:
        fitted = "\n\n".join(kept) + "..."
        if len(fitted) <= max_length:
            return fitted

    return plain_fallback(text)


def load_real_bot_utils():
    """Import bot.utils for audit-only checks without requiring optional local deps."""
    if "pytz" not in sys.modules:
        pytz_stub = types.ModuleType("pytz")
        pytz_stub.exceptions = types.SimpleNamespace(UnknownTimeZoneError=Exception)
        pytz_stub.timezone = lambda _name: None
        sys.modules["pytz"] = pytz_stub
    if "aiofiles" not in sys.modules:
        sys.modules["aiofiles"] = types.ModuleType("aiofiles")

    spec = importlib.util.spec_from_file_location("audit_bot_utils", ROOT / "bot" / "utils.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def audit_payload(payload: dict[str, Any]) -> list[str]:
    """Check core UX-flow invariants modeled by the simulator."""
    issues: list[str] = []
    texts = payload["texts"]
    text_definitions = load_text_definitions()
    meridians = payload["meridians"]
    meridians_by_id = {item["id"]: item for item in meridians}
    raw_meridians_by_id = {item["id"]: item for item in load_json("bot/meridians.json")["meridians"]}
    ready_ids = [item["id"] for item in meridians if item["pointsCount"] > 0]

    if tuple(payload["languages"]) != LANGUAGES:
        issues.append(f"languages mismatch: {payload['languages']}")

    if has_cyrillic("What changes when attention rests here"):
        issues.append("cyrillic detector treats plain English as Cyrillic")
    if not has_cyrillic("меридиан"):
        issues.append("cyrillic detector misses Cyrillic text")

    bot_utils = load_real_bot_utils()
    principles = load_json("bot/principles.json")
    for language in LANGUAGES:
        for principle in principles.get(language, []):
            caption = bot_utils.format_principle_message(principle, language, max_length=1024)
            if len(caption) > 1024:
                issues.append(f"{language} principle {principle.get('id')}: caption exceeds Telegram photo limit")
            if principle.get("practice_tip") and ("💡" not in caption or "<i>" not in caption):
                issues.append(f"{language} principle {principle.get('id')}: practice block disappeared from caption")

    translation_coverage = payload.get("translationCoverage", {})
    for language in LANGUAGES:
        item = translation_coverage.get(language)
        if not item:
            issues.append(f"{language}: missing translation coverage")
            continue
        if item["source"] > item["total"] or item["pending"] > item["total"]:
            issues.append(f"{language}: impossible translation coverage values {item}")

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

        ahimsa_markers = {
            "en": "Ahimsa",
            "ru": "Ахимса",
            "uz": "Ahimsa",
            "kz": "Ахимса",
        }
        if ahimsa_markers[language] not in onboarding:
            issues.append(f"{language}: onboarding does not give Ahimsa as an energy example")

        stale_patterns = (
            "Yoga Principles Bot",
            "Yoga Bot",
            "daily yoga principles",
            "Two languages",
            "Два языка",
            "Бот для тренировки Ямы/Ниямы",
            "Yoga tamoyillari boti",
            "Йога принциптері боты",
        )
        visible_keys = (
            "welcome",
            "onboarding_intro",
            "menu",
            "about_text",
            "principles_menu",
            "mode_menu",
            "meridians_menu",
            "setup_complete",
            "already_subscribed",
            "feature_announcement",
        )
        for key in visible_keys:
            value = language_texts.get(key, "")
            for pattern in stale_patterns:
                if pattern in value:
                    issues.append(f"{language}: {key} contains stale branding {pattern!r}")

        raw_language_texts = text_definitions.get("TEXTS", {}).get(language, {})
        for key in visible_keys:
            value = raw_language_texts.get(key, "")
            for pattern in stale_patterns:
                if pattern in value:
                    issues.append(f"{language}: raw TEXTS.{key} contains stale branding {pattern!r}")

        for key in ("mode_menu", "about_text", "meridians_menu", "meridian_measurements_text", "meridian_point_help_text"):
            value = language_texts.get(key, "")
            if "<b>" not in value:
                issues.append(f"{language}: {key} has no bold formatting")
            if "???" in value:
                issues.append(f"{language}: {key} contains ???")

        completion = language_texts.get("meridian_completed", "")
        completion_markers = {
            "en": ("whole channel", "goes silent"),
            "ru": ("весь канал", "молчит"),
            "uz": ("butun kanal", "jim"),
            "kz": ("бүкіл арнаны", "үнсіз"),
        }[language]
        for marker in completion_markers:
            if marker not in completion:
                issues.append(f"{language}: meridian completion text does not guide reflective channel review")

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

    central_vessel_markers = {
        "conception_vessel": {
            "en": ("Yin system", "does not have a fixed hourly activity period", "sea of all Yin meridians"),
            "ru": ("системе инь", "не имеет поэтому определенной почасовой активности", "морем всех иньских меридианов"),
            "uz": ("Yin tizimiga", "aniq soatlik faollik davriga ega emas", "barcha Yin meridianlari dengizi"),
            "kz": ("Инь жүйесіне", "нақты сағаттық белсенділік кезеңі жоқ", "барлық Инь меридиандарының теңізі"),
        },
        "governing_vessel": {
            "en": ("Yang system", "does not have a fixed hourly activity period", "inner verticality"),
            "ru": ("системе ян", "не имеет поэтому определенной почасовой активности", "внутренней вертикали"),
            "uz": ("Yang tizimiga", "aniq soatlik faollik davriga ega emas", "ichki tiklik"),
            "kz": ("Ян жүйесіне", "нақты сағаттық белсенділік кезеңі жоқ", "ішкі тік ось"),
        },
    }
    for meridian_id, language_markers in central_vessel_markers.items():
        raw_meridian = raw_meridians_by_id.get(meridian_id, {})
        for language, markers in language_markers.items():
            description = raw_meridian.get("i18n", {}).get(language, {}).get("description", "")
            for marker in markers:
                if marker not in description:
                    issues.append(f"{meridian_id}/{language}: central vessel intro is missing marker {marker!r}")

    paired_channel_markers = {
        "lung": {
            "en": ("Yin system", "Liver Meridian", "Large Intestine Meridian", "breath"),
            "ru": ("системе инь", "Меридиана печени", "Меридиану толстой кишки", "дыхание"),
            "uz": ("Yin tizimiga", "Jigar meridianidan", "Yo'g'on ichak meridianiga", "nafas"),
            "kz": ("Инь жүйесіне", "Бауыр меридианынан", "Тоқ ішек меридианына", "тыныс"),
        },
        "large_intestine": {
            "en": ("Yang system", "Lung Meridian", "Stomach Meridian", "releasing"),
            "ru": ("системе ян", "Меридиана лёгких", "Меридиану желудка", "отпускать"),
            "uz": ("Yang tizimiga", "O'pka meridianidan", "Oshqozon meridianiga", "qo'yib yuborish"),
            "kz": ("Ян жүйесіне", "Өкпе меридианынан", "Асқазан меридианына", "босату"),
        },
        "stomach": {
            "en": ("Yang system", "Large Intestine Meridian", "Spleen Meridian", "digest"),
            "ru": ("системе ян", "Меридиана толстой кишки", "Меридиану селезёнки", "переваривать"),
            "uz": ("Yang tizimiga", "Yo'g'on ichak meridianidan", "Taloq meridianiga", "o'zlashtirish"),
            "kz": ("Ян жүйесіне", "Тоқ ішек меридианынан", "Көкбауыр меридианына", "сіңіру"),
        },
        "spleen": {
            "en": ("Yin system", "Stomach Meridian", "Heart Meridian", "steadiness"),
            "ru": ("системе инь", "Меридиана желудка", "Меридиану сердца", "устойчивость"),
            "uz": ("Yin tizimiga", "Oshqozon meridianidan", "Yurak meridianiga", "barqarorlik"),
            "kz": ("Инь жүйесіне", "Асқазан меридианынан", "Жүрек меридианына", "тұрақтылық"),
        },
        "heart": {
            "en": ("Yin system", "Spleen Meridian", "Small Intestine Meridian", "emotion"),
            "ru": ("системе инь", "Меридиана селезёнки", "Меридиану тонкой кишки", "эмоции"),
            "uz": ("Yin tizimiga", "Taloq meridianidan", "Ingichka ichak meridianiga", "hissiyot"),
            "kz": ("Инь жүйесіне", "Көкбауыр меридианынан", "Ащы ішек меридианына", "эмоция"),
        },
        "small_intestine": {
            "en": ("Yang system", "Heart Meridian", "Bladder Meridian", "discernment"),
            "ru": ("системе ян", "Меридиана сердца", "Меридиану мочевого пузыря", "различения"),
            "uz": ("Yang tizimiga", "Yurak meridianidan", "Siydik pufagi meridianiga", "farqlash"),
            "kz": ("Ян жүйесіне", "Жүрек меридианынан", "Қуық меридианына", "ажырату"),
        },
        "bladder": {
            "en": ("Yang system", "Small Intestine Meridian", "Kidney Meridian", "back line"),
            "ru": ("системе ян", "Меридиана тонкой кишки", "Меридиану почек", "задняя линия"),
            "uz": ("Yang tizimiga", "Ingichka ichak meridianidan", "Buyrak meridianiga", "orqa chiziq"),
            "kz": ("Ян жүйесіне", "Ащы ішек меридианынан", "Бүйрек меридианына", "артқы сызық"),
        },
        "kidney": {
            "en": ("Yin system", "Bladder Meridian", "Pericardium Meridian", "deep resource"),
            "ru": ("системе инь", "Меридиана мочевого пузыря", "Меридиану перикарда", "глубинный ресурс"),
            "uz": ("Yin tizimiga", "Siydik pufagi meridianidan", "Perikard meridianiga", "chuqur resurs"),
            "kz": ("Инь жүйесіне", "Қуық меридианынан", "Перикард меридианына", "терең ресурс"),
        },
        "pericardium": {
            "en": ("Yin system", "Kidney Meridian", "Triple Burner Meridian", "protection"),
            "ru": ("системе инь", "Меридиана почек", "Меридиану трёх обогревателей", "защита"),
            "uz": ("Yin tizimiga", "Buyrak meridianidan", "Uch isituvchi meridianiga", "himoya"),
            "kz": ("Инь жүйесіне", "Бүйрек меридианынан", "Үш жылытқыш меридианына", "қорғаныс"),
        },
        "triple_burner": {
            "en": ("Yang system", "Pericardium Meridian", "Gallbladder Meridian", "warmth"),
            "ru": ("системе ян", "Меридиана перикарда", "Меридиану желчного пузыря", "тепло"),
            "uz": ("Yang tizimiga", "Perikard meridianidan", "O't pufagi meridianiga", "issiqlik"),
            "kz": ("Ян жүйесіне", "Перикард меридианынан", "Өт қабы меридианына", "жылу"),
        },
        "gallbladder": {
            "en": ("Yang system", "Triple Burner Meridian", "Liver Meridian", "decision"),
            "ru": ("системе ян", "Меридиана трёх обогревателей", "Меридиану печени", "решение"),
            "uz": ("Yang tizimiga", "Uch isituvchi meridianidan", "Jigar meridianiga", "qaror"),
            "kz": ("Ян жүйесіне", "Үш жылытқыш меридианынан", "Бауыр меридианына", "шешім"),
        },
        "liver": {
            "en": ("Yin system", "Gallbladder Meridian", "Lung Meridian", "paired-channel cycle"),
            "ru": ("системе инь", "Меридиана желчного пузыря", "Меридиану лёгких", "круг парных каналов"),
            "uz": ("Yin tizimiga", "O't pufagi meridianidan", "O'pka meridianiga", "juft kanallar aylanasini"),
            "kz": ("Инь жүйесіне", "Өт қабы меридианынан", "Өкпе меридианына", "жұпты арналар айналымының"),
        },
    }
    for meridian_id, language_markers in paired_channel_markers.items():
        raw_meridian = raw_meridians_by_id.get(meridian_id, {})
        for language, markers in language_markers.items():
            description = raw_meridian.get("i18n", {}).get(language, {}).get("description", "")
            for marker in markers:
                if marker not in description:
                    issues.append(f"{meridian_id}/{language}: paired-channel intro is missing marker {marker!r}")

    for meridian_id in ready_ids:
        meridian = meridians_by_id[meridian_id]
        if not meridian.get("overviewImage"):
            issues.append(f"{meridian_id}: missing overview image")
        elif not (ROOT / "images" / "meridians" / meridian["overviewImage"]).exists():
            issues.append(f"{meridian_id}: overview image file does not exist: {meridian['overviewImage']}")
        if not meridian["points"]:
            issues.append(f"{meridian_id}: marked ready but has no point payload")
        raw_meridian = raw_meridians_by_id.get(meridian_id, {})
        for language in LANGUAGES:
            raw_i18n = raw_meridian.get("i18n", {}).get(language, {})
            for key in ("name", "description", "direction", "intro_practice"):
                if not raw_i18n.get(key):
                    issues.append(f"{meridian_id}/{language}: missing meridian i18n field {key}")
            stale_description_patterns = {
                "en": ("is used here",),
                "ru": ("здесь используется",),
                "uz": ("bu yerda", "xaritasi sifatida ishlatiladi"),
                "kz": ("бұл жерде", "картасы ретінде қолданылады"),
            }[language]
            description = raw_i18n.get("description", "")
            for pattern in stale_description_patterns:
                if pattern in description:
                    issues.append(f"{meridian_id}/{language}: meridian intro still uses stale template phrase {pattern!r}")
        for language in LANGUAGES:
            intro = meridian["intro"][language]
            if "<b>" not in intro:
                issues.append(f"{meridian_id}/{language}: intro has no bold title")
            if has_source_or_medical_leak(strip_html(intro)):
                issues.append(f"{meridian_id}/{language}: source note or hard medical claim leaked into visible intro")
            if len(fit_html_caption(intro)) > 1024:
                issues.append(f"{meridian_id}/{language}: fitted intro caption exceeds Telegram limit")
        for index, point in enumerate(meridian["points"]):
            if not re.match(r"^[A-Z]+[0-9]+$", point["code"]):
                issues.append(f"{meridian_id} point {index + 1}: non-normalized point code {point['code']!r}")
            if not point.get("image"):
                issues.append(f"{meridian_id} point {index + 1}: missing simulator image")
            elif not (ROOT / "images" / "meridians" / point["image"]).exists():
                issues.append(f"{meridian_id} point {index + 1}: image file does not exist: {point['image']}")
            raw_point = raw_meridian.get("points", [])[index] if index < len(raw_meridian.get("points", [])) else {}
            for language in LANGUAGES:
                raw_i18n = raw_point.get("i18n", {}).get(language, {})
                for key in ("name", "location", "meditation_instruction", "observation_question"):
                    if not raw_i18n.get(key):
                        issues.append(f"{meridian_id} point {index + 1}/{language}: missing point i18n field {key}")
            for language, localized_point in point.get("raw", {}).get("i18n", {}).items():
                if "meaning" in localized_point:
                    issues.append(f"{meridian_id} point {index + 1}/{language}: raw source meaning should not be stored in user-facing meridians.json")
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
                if language in {"en", "uz"} and has_cyrillic(plain):
                    issues.append(f"{meridian_id} point {index + 1}/{language}: Cyrillic leaked into visible point detail")
                if has_source_or_medical_leak(plain):
                    issues.append(f"{meridian_id} point {index + 1}/{language}: source note or hard medical claim leaked into visible point detail")
                if any(marker in plain for marker in SOURCE_EDITORIAL_TAILS):
                    issues.append(f"{meridian_id} point {index + 1}/{language}: source-editorial location tail leaked")
                if "<b>" not in detail:
                    issues.append(f"{meridian_id} point {index + 1}/{language}: no bold formatting")
                if OBSERVATION_LABELS[language] not in plain:
                    issues.append(f"{meridian_id} point {index + 1}/{language}: missing observation prompt")
                if len(detail.replace("<br><br>", "\n\n")) > 1024:
                    issues.append(f"{meridian_id} point {index + 1}/{language}: raw point caption exceeds Telegram limit")
                if len(fit_html_caption(detail)) > 1024:
                    issues.append(f"{meridian_id} point {index + 1}/{language}: fitted point caption exceeds Telegram limit")
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
            texts[language].get("current_meridian", ""),
            texts[language].get("mode_principles_only", ""),
            texts[language].get("mode_meridians_only", ""),
            texts[language].get("mode_both", ""),
            texts[language].get("meridian_measurements", ""),
            texts[language].get("meridian_point_help", ""),
            texts[language].get("meridian_change_path", ""),
            texts[language].get("back_to_current_focus", ""),
        ]
        button_sources.extend(item["names"][language] for item in meridians)
        for label in button_sources:
            if len(label) > 42:
                long_buttons.append(label)
        if long_buttons:
            issues.append(f"{language}: long button labels: {long_buttons[:5]}")

        meridian_home_buttons = [
            texts[language].get("current_meridian", ""),
            texts[language].get("meridian_change_path", ""),
            texts[language].get("meridian_measurements", ""),
            texts[language].get("back_to_menu", ""),
        ]
        if any(texts[language].get(key, "") in meridian_home_buttons for key in ("prev_point", "next_point", "all_points", "complete_meridian")):
            issues.append(f"{language}: meridians home contains point-navigation controls")
        if not texts[language].get("meridian_measurements") or not texts[language].get("meridian_change_path"):
            issues.append(f"{language}: meridians home is missing path or cun guide entry")
        measurements_label = texts[language].get("meridian_measurements", "").lower()
        if "cun" not in measurements_label and "цун" not in measurements_label:
            issues.append(f"{language}: meridian measurements button does not clearly mention cun")
        if len(meridian_home_buttons) > 4:
            issues.append(f"{language}: meridians home has too many top-level buttons")
        path_label = texts[language].get("meridian_change_path", "").lower()
        path_action_markers = {
            "en": ("start", "choose"),
            "ru": ("начать", "выбрать"),
            "uz": ("boshlash", "tanlash"),
            "kz": ("бастау", "таңдау"),
        }[language]
        if not any(marker in path_label for marker in path_action_markers):
            issues.append(f"{language}: meridian path button should sound like starting or choosing, got {path_label!r}")

        choose_meridian_text = strip_html(texts[language].get("choose_meridian", ""))
        if len(choose_meridian_text) < 80:
            issues.append(f"{language}: choose_meridian text is too terse for free-choice mode")
        if language == "ru" and "текущим фокусом" not in choose_meridian_text:
            issues.append("ru: choose_meridian does not explain the selected meridian becomes current focus")
        if language == "en" and "current practice focus" not in choose_meridian_text:
            issues.append("en: choose_meridian does not explain the selected meridian becomes current focus")

    scheduler_source = (ROOT / "bot" / "scheduler.py").read_text(encoding="utf-8-sig")
    storage_source = (ROOT / "bot" / "storage.py").read_text(encoding="utf-8-sig")
    if "def from_dict" not in storage_source or "User(**user_data)" in storage_source:
        issues.append("storage does not safely migrate stored user records with unknown fields")
    if "astimezone().astimezone(tz=None)" in scheduler_source:
        issues.append("scheduler converts user send times through the machine local timezone")
    if "astimezone(timezone.utc).replace(tzinfo=None)" not in scheduler_source:
        issues.append("scheduler does not explicitly convert scheduled jobs to UTC")
    if "user.current_point_index < -1 or user.current_point_index >= len(points)" not in scheduler_source:
        issues.append("scheduler does not normalize stale meridian point indexes")
    if "not user.principles_enabled" not in scheduler_source:
        issues.append("scheduler can send a stale principle job after principle practice is disabled")
    if "current_user and current_user.is_active and current_user.principles_enabled" not in scheduler_source:
        issues.append("scheduler can keep chaining principle jobs after principle practice is disabled")
    if "current_user and current_user.is_active and current_user.meridians_enabled" not in scheduler_source:
        issues.append("scheduler can keep chaining meridian jobs after meridian practice is disabled")
    send_meridian_start = scheduler_source.find("async def _send_meridian_to_user")
    send_meridian_end = scheduler_source.find("async def _send_meridian_message_with_retry")
    if send_meridian_start != -1 and send_meridian_end != -1:
        send_meridian_source = scheduler_source[send_meridian_start:send_meridian_end]
        if re.search(r"current_point_index\s*[+\-]=", send_meridian_source):
            issues.append("daily meridian reminder changes the current point automatically")
        if "user.current_point_index = -1" not in send_meridian_source:
            issues.append("daily meridian reminder does not reset invalid point index to the meridian intro")

    handlers_source = (ROOT / "bot" / "handlers.py").read_text(encoding="utf-8-sig")
    if "user and user.meridians_enabled and user.current_meridian_id" not in handlers_source:
        issues.append("meridians home can show continue practice while meridian mode is disabled")
    simulator_source = Path(__file__).read_text(encoding="utf-8-sig")
    if "state.meridiansEnabled && state.currentMeridianId" not in simulator_source:
        issues.append("simulator can show continue practice while meridian mode is disabled")
    if 't("back_to_current_focus")' not in simulator_source:
        issues.append("all-points screen does not label return-to-current-focus honestly")
    if "point_index >= points_count - 1" not in handlers_source or "user.current_point_index < len(points) - 1" not in handlers_source:
        issues.append("meridian completion can appear or fire before the last point")
    if "state.currentPointIndex >= item.pointsCount - 1" not in simulator_source:
        issues.append("simulator shows meridian completion before the last point")
    if "meridian_measurements_text" in handlers_source and "callback_data=\"meridian_point_help\"" not in handlers_source:
        issues.append("meridian measurements screen does not lead to point-search help")
    if "_create_meridian_help_keyboard(language, user)" not in handlers_source:
        issues.append("meridian point-help screen does not use the safe reference keyboard")
    if "if (state.currentMeridianId) buttons.push" not in simulator_source:
        issues.append("simulator point-help screen always shows current focus even when none is selected")
    callback_values = sorted(set(re.findall(r"callback_data=(?:f)?[\"']([^\"']+)", handlers_source)))
    callback_patterns = [
        re.compile(ast.literal_eval(match))
        for match in re.findall(r"CallbackQueryHandler\([^)]*pattern=([\"'][^\"']+[\"'])", handlers_source)
    ]
    for callback_value in callback_values:
        if not any(pattern.search(callback_value) for pattern in callback_patterns):
            issues.append(f"callback is not covered by any registered CallbackQueryHandler pattern: {callback_value}")

    stop_handler_start = handlers_source.find("async def _handle_stop")
    settings_handler_start = handlers_source.find("async def _handle_settings")
    if stop_handler_start != -1 and settings_handler_start != -1:
        stop_handler_source = handlers_source[stop_handler_start:settings_handler_start]
        if "parse_mode='Markdown'" in stop_handler_source:
            issues.append("/stop handler still sends the stop UX with Markdown parse mode")
        if "_as_html" not in stop_handler_source:
            issues.append("/stop handler does not normalize stop text for HTML parse mode")

    feedback_handler_start = handlers_source.find("async def _handle_feedback_input")
    stop_feedback_handler_start = handlers_source.find("async def _handle_stop_feedback_input")
    principle_detail_start = handlers_source.find("async def _show_principle_detail")
    if feedback_handler_start != -1 and stop_feedback_handler_start != -1:
        feedback_handler_source = handlers_source[feedback_handler_start:stop_feedback_handler_start]
        if "admin_text" in feedback_handler_source and "parse_mode='Markdown'" in feedback_handler_source:
            issues.append("feedback handler sends user-authored admin text through Markdown parse mode")
        if "reply_text(text, reply_markup=keyboard, parse_mode='Markdown')" in feedback_handler_source:
            issues.append("feedback handler replies with menu text through Markdown parse mode")
        if "self._as_html(text)" not in feedback_handler_source:
            issues.append("feedback handler does not normalize menu text for HTML parse mode")
    if stop_feedback_handler_start != -1 and principle_detail_start != -1:
        stop_feedback_handler_source = handlers_source[stop_feedback_handler_start:principle_detail_start]
        if "parse_mode='Markdown'" in stop_feedback_handler_source:
            issues.append("stop feedback handler still uses Markdown parse mode")

    meridian_handler_start = handlers_source.find("async def _handle_meridian_callback")
    broadcast_handler_start = handlers_source.find("async def _handle_broadcast_callback")
    if meridian_handler_start != -1 and broadcast_handler_start != -1:
        meridian_handler_source = handlers_source[meridian_handler_start:broadcast_handler_start]
        if "meridian_completed" in meridian_handler_source and "format_meridian_intro(next_meridian" in meridian_handler_source:
            issues.append("meridian completion still concatenates the next meridian intro into one caption")
        if "user.current_point_index < -1 or user.current_point_index >= len(points)" not in meridian_handler_source:
            issues.append("meridian callback does not normalize stale point indexes before rendering")

    detail_formatter_start = handlers_source.find("def _format_principle_detail")
    start_handler_start = handlers_source.find("async def _handle_start")
    if detail_formatter_start != -1 and start_handler_start != -1:
        detail_formatter_source = handlers_source[detail_formatter_start:start_handler_start]
        if "format_principle_message" not in detail_formatter_source:
            issues.append("menu principle cards use a formatter that can drift from daily principle cards")

    dry_setup_phrases = (
        "Setup complete!",
        "Настройка завершена!",
        "Sozlash yakunlandi!",
        "Баптау аяқталды!",
    )
    for phrase in dry_setup_phrases:
        if phrase in handlers_source:
            issues.append(f"setup completion still contains dry phrase: {phrase!r}")
    setup_markers = (
        "The other principles are not paused",
        "Остальные принципы не выключаются",
        "Boshqa tamoyillar to'xtamaydi",
        "Қалған қағидалар тоқтамайды",
    )
    for marker in setup_markers:
        if marker not in handlers_source:
            issues.append(f"setup completion is missing living-practice marker: {marker!r}")
    for stale_fragment in ("not implemented", "placeholder"):
        if stale_fragment in handlers_source.lower():
            issues.append(f"handlers still expose stale implementation wording: {stale_fragment!r}")
    bot_sources = "\n".join(path.read_text(encoding="utf-8-sig") for path in (ROOT / "bot").glob("*.py"))
    if re.search(r"parse_mode=[\"']Markdown[\"']", bot_sources):
        issues.append("bot still sends messages with Markdown parse mode")
    utils_source = (ROOT / "bot" / "utils.py").read_text(encoding="utf-8-sig")
    if "_point_area_practice_hint" not in utils_source:
        issues.append("meridian point formatter does not add body-area practice cues")
    if "Смягчите живот и таз" not in utils_source or "Lengthen the spine" not in utils_source:
        issues.append("meridian point body-area cues are missing abdomen or spine guidance")
    principle_image_start = utils_source.find("def get_principle_image_path")
    principle_image_end = utils_source.find("def has_principle_image")
    if principle_image_start != -1 and principle_image_end != -1:
        principle_image_source = utils_source[principle_image_start:principle_image_end]
        for extension in (".jpg", ".png", ".gif"):
            if extension not in principle_image_source:
                issues.append(f"principle image lookup does not support {extension}")

    settings_keyboard_start = handlers_source.find("def _create_settings_menu_keyboard")
    principles_keyboard_start = handlers_source.find("def _create_principles_menu_keyboard")
    if settings_keyboard_start != -1 and principles_keyboard_start != -1:
        settings_keyboard_source = handlers_source[settings_keyboard_start:principles_keyboard_start]
        if "principles_enabled" not in settings_keyboard_source or "meridians_enabled" not in settings_keyboard_source:
            issues.append("settings keyboard does not adapt time buttons to active practice modes")

    points_page_start = handlers_source.find("def _format_meridian_points_page_text")
    menu_handler_start = handlers_source.find("async def _handle_menu")
    if points_page_start != -1 and menu_handler_start != -1:
        points_page_source = handlers_source[points_page_start:menu_handler_start]
        for marker in ("current focus", "текущим фокусом"):
            if marker not in points_page_source:
                issues.append(f"meridian points page text is missing manual-focus marker: {marker!r}")

    return issues


def audit_rendered_html() -> list[str]:
    """Catch mojibake in the actual browser simulator output."""
    html = build_html()
    issues: list[str] = []
    visible_mojibake = (
        "рџ",
        "Рџ",
        "Рњ",
        "Р”",
        "Рљ",
        "СЃ",
        "С€",
        "ТЇ",
        "Т›",
        "У™",
        "В·",
    )
    for fragment in visible_mojibake:
        if fragment in html:
            issues.append(f"rendered simulator HTML contains mojibake fragment: {fragment!r}")
    if "???" in html:
        issues.append("rendered simulator HTML contains question-mark damaged text")
    if 'value="setupComplete"' not in html or "renderSetupComplete" not in html:
        issues.append("browser simulator is missing setup-complete scenario")
    for scenario_value in ("chooseMeridian", "allPoints", "noviceMeridians", "noviceFirstPoint"):
        if f'value="{scenario_value}"' not in html:
            issues.append(f"browser simulator is missing {scenario_value} scenario")
        if f"scenario === '{scenario_value}'" not in html:
            issues.append(f"browser simulator scenario {scenario_value} has no quick-open handler")
    if "function resetState()" not in html:
        issues.append("browser simulator scenarios do not reset shared state before opening")
    if "function currentMeridianName()" not in html or "if (!state.currentMeridianId) return '-'" not in html:
        issues.append("browser simulator state panel shows a fallback meridian when no current focus is selected")
    if "Смягчите живот и таз" not in html or "Soften the belly and pelvis" not in html:
        issues.append("browser simulator point cards do not include body-area practice cues")
    if "const timeRow = []" not in html or "state.principlesEnabled" not in html or "state.meridiansEnabled" not in html:
        issues.append("browser simulator settings screen is not mode-aware")
    return issues


def build_html() -> str:
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
    .bubble {{ background: var(--paper); border-radius: 18px; padding: 18px 20px; box-shadow: 0 1px 2px rgba(0,0,0,.16); overflow: visible; }}
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
    .ok {{ color: #246b37; font-weight: 650; }}
    .warn {{ color: #8a5a00; font-weight: 650; }}
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
          <option value="timezone">Time zone step</option>
          <option value="time">Reminder time step</option>
          <option value="skipDays">Quiet days step</option>
          <option value="setupComplete">Setup complete</option>
          <option value="noviceMeridians">Novice: before meridian start</option>
          <option value="noviceFirstPoint">Novice: first meridian point</option>
          <option value="main">Main menu</option>
          <option value="meridians">Meridians section</option>
          <option value="measurements">TCM measurements</option>
          <option value="pointHelp">Point search help</option>
          <option value="meridianPath">Meridian study path</option>
          <option value="chooseMeridian">Choose meridian</option>
          <option value="currentPoint">Current meridian point</option>
          <option value="allPoints">All meridian points</option>
          <option value="principles">Yama/Niyama section</option>
          <option value="modes">My Path</option>
          <option value="about">About bot</option>
          <option value="settings">Settings</option>
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
        <b>Quality status</b>
        <div id="localizationStatus" class="coverage"></div>
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
    const localizationStatusBox = document.getElementById('localizationStatus');

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

    function resetState() {{
      state.principlesEnabled = true;
      state.meridiansEnabled = false;
      state.learningMode = null;
      state.currentMeridianId = 'conception_vessel';
      state.currentPointIndex = -1;
      state.currentPointsPage = 0;
      state.completed = [];
    }}

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
    function currentMeridianName() {{
      if (!state.currentMeridianId) return '-';
      const item = payload.meridians.find((candidate) => candidate.id === state.currentMeridianId);
      return item ? item.names[state.language] : '-';
    }}
    function meridianImageUrl(item) {{ return item && item.overviewImage ? `../images/meridians/${{encodeURIComponent(item.overviewImage)}}` : null; }}
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
        <div>meridian: <b>${{currentMeridianName()}}</b></div>
        <div>point: <b>${{state.currentPointIndex + 1 || 'intro'}}</b></div>
      `;
    }}

    function renderCoverage() {{
      coverageBox.innerHTML = payload.meridians.map((item) => `
        <div class="bar"><span>${{item.names[state.language]}}</span><b>${{item.pointsCount}}</b></div>
      `).join('');
      const openLocationTasks = payload.languages
        .map((language) => [language, payload.translationCoverage[language]])
        .filter(([, item]) => item.source || item.pending);
      localizationStatusBox.innerHTML = openLocationTasks.length
        ? openLocationTasks.map(([language, item]) => `
            <div class="task">
              <span class="warn">${{language.toUpperCase()}} needs location review</span>
              <small>${{item.source + item.pending}} point descriptions still need editorial cleanup before release.</small>
            </div>
          `).join('')
        : '<div class="ok">All meridian point locations are ready in the four app languages.</div>';
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
        [{{ label: '\\u{{1F1F7}}\\u{{1F1FA}} \\u041C\\u043E\\u0441\\u043A\\u0432\\u0430 +3', action: () => setScreen('time') }}, {{ label: '\\u{{1F1FA}}\\u{{1F1FF}} \\u0422\\u0430\\u0448\\u043A\\u0435\\u043D\\u0442 +5', action: () => setScreen('time') }}],
        [{{ label: '\\u{{1F1F0}}\\u{{1F1FF}} \\u0410\\u043B\\u043C\\u0430\\u0442\\u044B +5', action: () => setScreen('time') }}, {{ label: '\\u{{1F30D}} UTC +0', action: () => setScreen('time') }}],
      ]);
    }}

    function renderTime() {{
      const key = state.principlesEnabled && state.meridiansEnabled
        ? 'time_step_both'
        : state.meridiansEnabled ? 'time_step_meridians' : 'time_step_principles';
      show('Time', fmt(t(key)), [
        [{{ label: '08:00', action: () => setScreen(state.principlesEnabled ? 'skipDays' : 'setupComplete') }}, {{ label: '20:00', action: () => setScreen(state.principlesEnabled ? 'skipDays' : 'setupComplete') }}],
      ]);
    }}

    function renderSkipDays() {{
      const note = state.language === 'en'
        ? 'No days selected - messages will be sent daily'
        : state.language === 'ru'
          ? '\\u0414\\u043D\\u0438 \\u043D\\u0435 \\u0432\\u044B\\u0431\\u0440\\u0430\\u043D\\u044B - \\u0441\\u043E\\u043E\\u0431\\u0449\\u0435\\u043D\\u0438\\u044F \\u0431\\u0443\\u0434\\u0443\\u0442 \\u043E\\u0442\\u043F\\u0440\\u0430\\u0432\\u043B\\u044F\\u0442\\u044C\\u0441\\u044F \\u0435\\u0436\\u0435\\u0434\\u043D\\u0435\\u0432\\u043D\\u043E'
          : state.language === 'uz'
            ? 'Kunlar tanlanmagan - xabarlar har kuni yuboriladi'
            : '\\u041A\\u04AF\\u043D\\u0434\\u0435\\u0440 \\u0442\\u0430\\u04A3\\u0434\\u0430\\u043B\\u043C\\u0430\\u0493\\u0430\\u043D - \\u0445\\u0430\\u0431\\u0430\\u0440\\u043B\\u0430\\u0440 \\u043A\\u04AF\\u043D \\u0441\\u0430\\u0439\\u044B\\u043D \\u0436\\u0456\\u0431\\u0435\\u0440\\u0456\\u043B\\u0435\\u0434\\u0456';
      const dayNames = {{
        en: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
        ru: ['\\u041F\\u043E\\u043D\\u0435\\u0434\\u0435\\u043B\\u044C\\u043D\\u0438\\u043A', '\\u0412\\u0442\\u043E\\u0440\\u043D\\u0438\\u043A', '\\u0421\\u0440\\u0435\\u0434\\u0430', '\\u0427\\u0435\\u0442\\u0432\\u0435\\u0440\\u0433', '\\u041F\\u044F\\u0442\\u043D\\u0438\\u0446\\u0430', '\\u0421\\u0443\\u0431\\u0431\\u043E\\u0442\\u0430', '\\u0412\\u043E\\u0441\\u043A\\u0440\\u0435\\u0441\\u0435\\u043D\\u044C\\u0435'],
        uz: ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba'],
        kz: ['\\u0414\\u04AF\\u0439\\u0441\\u0435\\u043D\\u0431\\u0456', '\\u0421\\u0435\\u0439\\u0441\\u0435\\u043D\\u0431\\u0456', '\\u0421\\u04D9\\u0440\\u0441\\u0435\\u043D\\u0431\\u0456', '\\u0411\\u0435\\u0439\\u0441\\u0435\\u043D\\u0431\\u0456', '\\u0416\\u04B1\\u043C\\u0430', '\\u0421\\u0435\\u043D\\u0431\\u0456', '\\u0416\\u0435\\u043A\\u0441\\u0435\\u043D\\u0431\\u0456'],
      }}[state.language] || [];
      const shortDay = (name) => name.length > 8 ? `${{name.slice(0, 7)}}.` : name;
      const buttons = [];
      for (let i = 0; i < dayNames.length; i += 2) {{
        buttons.push(dayNames.slice(i, i + 2).map((name) => ({{ label: `📅 ${{shortDay(name)}}`, action: () => setScreen('setupComplete') }})));
      }}
      const noSkip = {{
        en: '🎯 No Skip Days',
        ru: '\\u{{1F3AF}} \\u041D\\u0435 \\u043F\\u0440\\u043E\\u043F\\u0443\\u0441\\u043A\\u0430\\u0442\\u044C',
        uz: "\\u{{1F3AF}} Kunlarni o'tkazmaslik",
        kz: '\\u{{1F3AF}} \\u041A\\u04AF\\u043D\\u0434\\u0435\\u0440\\u0434\\u0456 \\u04E9\\u0442\\u043A\\u0456\\u0437\\u0431\\u0435\\u0443',
      }}[state.language] || '🎯 No Skip Days';
      const weekends = {{
        en: '📅 Weekends Only',
        ru: '\\u{{1F4C5}} \\u0422\\u043E\\u043B\\u044C\\u043A\\u043E \\u0432\\u044B\\u0445\\u043E\\u0434\\u043D\\u044B\\u0435',
        uz: '\\u{{1F4C5}} Faqat dam olish kunlari',
        kz: '\\u{{1F4C5}} \\u0422\\u0435\\u043A \\u0434\\u0435\\u043C\\u0430\\u043B\\u044B\\u0441 \\u043A\\u04AF\\u043D\\u0434\\u0435\\u0440\\u0456',
      }}[state.language] || '📅 Weekends Only';
      buttons.push([{{ label: noSkip, action: () => setScreen('setupComplete') }}]);
      buttons.push([{{ label: weekends, action: () => setScreen('setupComplete') }}]);
      buttons.push([{{ label: t('continue_setup'), action: () => setScreen('setupComplete') }}]);
      show('Skip days', `${{fmt(t('skip_days_step'))}}<br><br><b>${{note}}</b>`, buttons);
    }}

    function renderSetupComplete() {{
      const labels = {{
        en: {{
          done: '🎉 <b>Your practice rhythm is ready.</b>',
          settings: '📋 <b>What is active now:</b>',
          mode: '🧭 Practice:',
          principles: 'Yama/Niyama',
          meridians: 'Meridians',
          both: 'Yama/Niyama + Meridians',
          timezone: '🌍 Time zone:',
          time: '🕐 Time:',
          principleTime: '🕐 Yama/Niyama time:',
          meridianTime: '☯️ Meridian time:',
          skip: '📅 Quiet days:',
          nextPrinciples: "The bot will bring you back to one principle each day. The other principles are not paused; this is simply the day's point of attention.",
          nextMeridians: 'The bot will return you to the current meridian focus. You move through points only when you press the buttons, so the pace stays yours.',
          nextBoth: 'The bot will support both layers: daily ethical focus and meridian observation. Keep the practice gentle, regular, and honest.',
          hint: 'Open /menu whenever you want to explore the lists, change the rhythm, or continue meridian practice.',
        }},
        ru: {{
          done: '🎉 <b>Ритм практики настроен.</b>',
          settings: '📋 <b>Что сейчас активно:</b>',
          mode: '🧭 Практика:',
          principles: 'Яма/Нияма',
          meridians: 'Меридианы',
          both: 'Яма/Нияма + Меридианы',
          timezone: '🌍 Часовой пояс:',
          time: '🕐 Время:',
          principleTime: '🕐 Время Ямы/Ниямы:',
          meridianTime: '☯️ Время меридианов:',
          skip: '📅 Дни тишины:',
          nextPrinciples: 'Бот будет каждый день возвращать вас к одному принципу. Остальные принципы не выключаются: это просто акцент дня для внимания.',
          nextMeridians: 'Бот будет возвращать вас к текущему фокусу меридиана. По точкам вы двигаетесь только кнопками, поэтому темп остаётся вашим.',
          nextBoth: 'Бот будет поддерживать оба слоя: ежедневный нравственный фокус и наблюдение меридианов. Держите практику мягкой, регулярной и честной.',
          hint: 'Открывайте /menu, когда захотите посмотреть списки, изменить ритм или продолжить практику меридианов.',
        }},
        uz: {{
          done: '🎉 <b>Amaliyot ritmingiz tayyor.</b>',
          settings: '📋 <b>Hozir nimalar faol:</b>',
          mode: '🧭 Amaliyot:',
          principles: 'Yama/Niyama',
          meridians: 'Meridianlar',
          both: 'Yama/Niyama + Meridianlar',
          timezone: '🌍 Vaqt mintaqasi:',
          time: '🕐 Vaqt:',
          principleTime: '🕐 Yama/Niyama vaqti:',
          meridianTime: '☯️ Meridian vaqti:',
          skip: '📅 Sokin kunlar:',
          nextPrinciples: "Bot har kuni sizni bitta tamoyilga qaytaradi. Boshqa tamoyillar to'xtamaydi; bu faqat kunning diqqat nuqtasi.",
          nextMeridians: "Bot sizni joriy meridian fokusiga qaytaradi. Nuqtalar bo'ylab faqat tugmalar orqali o'tasiz, shuning uchun sur'at sizniki bo'lib qoladi.",
          nextBoth: "Bot ikkala qatlamni qo'llab-quvvatlaydi: kundalik axloqiy fokus va meridianlarni kuzatish. Amaliyot yumshoq, muntazam va halol bo'lsin.",
          hint: "/menu ni ochib, ro'yxatlarni ko'rishingiz, ritmni o'zgartirishingiz yoki meridian amaliyotini davom ettirishingiz mumkin.",
        }},
        kz: {{
          done: '🎉 <b>Тәжірибе ырғағы дайын.</b>',
          settings: '📋 <b>Қазір не белсенді:</b>',
          mode: '🧭 Тәжірибе:',
          principles: 'Яма/Нияма',
          meridians: 'Меридиандар',
          both: 'Яма/Нияма + Меридиандар',
          timezone: '🌍 Уақыт белдеуі:',
          time: '🕐 Уақыт:',
          principleTime: '🕐 Яма/Нияма уақыты:',
          meridianTime: '☯️ Меридиан уақыты:',
          skip: '📅 Тыныш күндер:',
          nextPrinciples: 'Бот күн сайын сізді бір қағидаға қайтарады. Қалған қағидалар тоқтамайды; бұл тек күннің зейін нүктесі.',
          nextMeridians: 'Бот сізді ағымдағы меридиан фокусына қайтарады. Нүктелер бойынша тек батырмалармен өтесіз, сондықтан қарқын өзіңізде қалады.',
          nextBoth: 'Бот екі қабатты да қолдайды: күнделікті этикалық фокус және меридиандарды бақылау. Тәжірибе жұмсақ, тұрақты және шынайы болсын.',
          hint: '/menu ашып, тізімдерді көре аласыз, ырғақты өзгерте аласыз немесе меридиан тәжірибесін жалғастыра аласыз.',
        }},
      }}[state.language];
      const mode = state.principlesEnabled && state.meridiansEnabled
        ? labels.both
        : state.meridiansEnabled ? labels.meridians : labels.principles;
      const next = state.principlesEnabled && state.meridiansEnabled
        ? labels.nextBoth
        : state.meridiansEnabled ? labels.nextMeridians : labels.nextPrinciples;
      const rows = [
        labels.done,
        '',
        labels.settings,
        `${{labels.mode}} ${{mode}}`,
        `${{labels.timezone}} <code>Europe/Moscow</code>`,
      ];
      if (state.principlesEnabled && state.meridiansEnabled) {{
        rows.push(`${{labels.principleTime}} <code>08:00</code>`, `${{labels.meridianTime}} <code>08:00</code>`, `${{labels.skip}} -`);
      }} else if (state.principlesEnabled) {{
        rows.push(`${{labels.time}} <code>08:00</code>`, `${{labels.skip}} -`);
      }} else {{
        rows.push(`${{labels.meridianTime}} <code>08:00</code>`, `${{labels.skip}} -`);
      }}
      rows.push('', next, '', labels.hint);
      show('Setup complete', rows.join('<br>'), [[{{ label: t('back_to_menu'), action: () => setScreen('main') }}]]);
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
      const buttons = [];
      if (state.meridiansEnabled && state.currentMeridianId) buttons.push([{{ label: t('current_meridian'), action: () => setScreen('currentMeridian') }}]);
      buttons.push(
        [{{ label: t('meridian_change_path'), action: () => setScreen('meridianPath') }}],
        [{{ label: t('meridian_measurements'), action: () => setScreen('measurements') }}],
        [{{ label: t('back_to_menu'), action: () => setScreen('main') }}],
      );
      show('Meridians', fmt(t('meridians_menu')), [
        ...buttons
      ]);
    }}

    function renderMeridianPath() {{
      show('Path', fmt(t('meridian_mode_menu')), [
        [{{ label: t('meridian_guided_path'), action: () => {{ state.meridiansEnabled = true; state.learningMode = 'guided'; state.currentMeridianId = firstReadyMeridian().id; setScreen('currentMeridian'); }} }}],
        [{{ label: t('meridian_free_choice'), action: () => {{ state.meridiansEnabled = true; state.learningMode = 'free'; setScreen('chooseMeridian'); }} }}],
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
          [{{ label: t('all_points'), action: () => {{ state.currentPointsPage = 0; setScreen('allPoints'); }}, disabled: item.pointsCount === 0 }}, {{ label: t('meridian_point_help'), action: () => setScreen('pointHelp') }}],
          [{{ label: t('meridian_back'), action: () => setScreen('meridians') }}],
        ]
        : [
          [
            ...(state.currentPointIndex > 0 ? [{{ label: t('prev_point'), action: prevPoint, disabled: item.pointsCount === 0 }}] : []),
            ...(state.currentPointIndex < item.pointsCount - 1 ? [{{ label: t('next_point'), action: nextPoint, disabled: item.pointsCount === 0 }}] : []),
          ],
          [{{ label: t('all_points'), action: () => {{ state.currentPointsPage = 0; setScreen('allPoints'); }}, disabled: item.pointsCount === 0 }}, {{ label: t('meridian_point_help'), action: () => setScreen('pointHelp') }}],
          ...(state.currentPointIndex >= item.pointsCount - 1 ? [[{{ label: t('complete_meridian'), action: completeMeridian }}]] : []),
          [{{ label: t('meridian_back'), action: () => setScreen('meridians') }}],
        ];
      show('Current focus', html, buttons, point ? pointImageUrl(point) : meridianImageUrl(item));
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
      setScreen('meridianCompleted');
    }}

    function renderMeridianCompleted() {{
      const buttons = [];
      if (state.currentMeridianId) buttons.push([{{ label: t('current_meridian'), action: () => setScreen('currentMeridian') }}]);
      buttons.push(
        [{{ label: t('meridian_change_path'), action: () => setScreen('meridianPath') }}],
        [{{ label: t('meridian_measurements'), action: () => setScreen('measurements') }}],
        [{{ label: t('meridian_back'), action: () => setScreen('meridians') }}],
      );
      show('Meridian completed', fmt(t('meridian_completed')), buttons);
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
      buttons.push([{{ label: t('back_to_current_focus'), action: () => setScreen('currentMeridian') }}]);
      const helper = {{
        en: 'Choose a point to open its location image and practice. The opened point becomes your current focus; the bot will not move further until you press the next button.',
        ru: 'Выберите точку, чтобы открыть изображение расположения и практику. Открытая точка станет текущим фокусом; бот не пойдёт дальше, пока вы сами не нажмёте следующую кнопку.',
        uz: "Joylashuv rasmi va amaliyotni ochish uchun nuqtani tanlang. Ochilgan nuqta joriy fokusga aylanadi; keyingi tugmani bosmaguningizcha bot oldinga o'tmaydi.",
        kz: 'Орналасу суреті мен тәжірибені ашу үшін нүктені таңдаңыз. Ашылған нүкте ағымдағы фокусқа айналады; келесі батырманы өзіңіз басқанша бот әрі қарай өтпейді.',
      }}[state.language] || '';
      const pageNote = totalPages > 1 ? `<br><br>${{state.language === 'ru' ? 'Страница' : state.language === 'uz' ? 'Sahifa' : state.language === 'kz' ? 'Бет' : 'Page'}} ${{state.currentPointsPage + 1}}/${{totalPages}}` : '';
      show('All points', `<b>${{t('all_points')}}</b><br><br>${{helper}}${{pageNote}}`, buttons);
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
        [{{ label: t('back_to_menu'), action: () => setScreen('main') }}],
      ]);
    }}

    function renderAllPrinciples() {{
      const buttons = payload.principles[state.language].map((item, index) => [{{ label: item.button, action: () => renderPrincipleDetail(index) }}]);
      buttons.push([{{ label: t('principles_back'), action: () => setScreen('principles') }}]);
      show('All principles', `<b>${{t('principles_all')}}</b>`, buttons);
    }}

    function renderSimple(key, title = key) {{
      show(title, fmt(t(key) || key), [[{{ label: t('back_to_menu'), action: () => setScreen('main') }}]]);
    }}

    function renderSettings() {{
      const rows = [[{{ label: t('change_modes'), action: () => setScreen('modes') }}]];
      const timeRow = [];
      if (state.principlesEnabled) {{
        timeRow.push({{ label: t('change_time'), action: () => setScreen('time') }});
      }}
      if (state.meridiansEnabled) {{
        timeRow.push({{ label: t('change_meridian_time'), action: () => setScreen('time') }});
      }}
      if (timeRow.length) {{
        rows.push(timeRow);
      }}
      rows.push(
        [{{ label: t('change_language'), action: () => setScreen('onboarding') }}, {{ label: t('change_timezone'), action: () => setScreen('timezone') }}],
        [{{ label: t('change_skip_days'), action: () => setScreen('skipDays') }}],
        [{{ label: t('back_to_menu'), action: () => setScreen('main') }}],
      );
      show('Settings', fmt(t('settings_menu')), rows);
    }}

    function render() {{
      renderCoverage();
      const routes = {{
        onboarding: renderOnboarding,
        timezone: renderTimezone,
        time: renderTime,
        setupComplete: renderSetupComplete,
        main: renderMain,
        modes: renderModes,
        meridians: renderMeridians,
        meridianPath: renderMeridianPath,
        meridianCompleted: renderMeridianCompleted,
        currentMeridian: renderCurrentMeridian,
        chooseMeridian: renderChooseMeridian,
        allPoints: renderAllPoints,
        skipDays: renderSkipDays,
        measurements: () => show('Measurements', fmt(t('meridian_measurements_text')), [[{{ label: t('meridian_point_help'), action: () => setScreen('pointHelp') }}], [{{ label: t('meridian_back'), action: () => setScreen('meridians') }}]]),
        pointHelp: () => {{
          const buttons = [];
          if (state.currentMeridianId) buttons.push([{{ label: t('current_meridian'), action: () => setScreen('currentMeridian') }}]);
          buttons.push([{{ label: t('meridian_back'), action: () => setScreen('meridians') }}]);
          show('Point help', fmt(t('meridian_point_help_text')), buttons);
        }},
        principles: renderPrinciples,
        principleDetail: () => renderPrincipleDetail(0),
        allPrinciples: renderAllPrinciples,
        about: () => renderSimple('about_text', 'About'),
        settings: renderSettings,
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
        resetState();
        state.principlesEnabled = true;
        state.meridiansEnabled = true;
        state.learningMode = 'guided';
        state.currentMeridianId = firstReadyMeridian().id;
        state.currentPointIndex = 0;
        state.screen = 'currentMeridian';
      }} else if (scenario === 'noviceMeridians') {{
        resetState();
        state.principlesEnabled = true;
        state.meridiansEnabled = false;
        state.learningMode = null;
        state.currentMeridianId = null;
        state.currentPointIndex = -1;
        state.screen = 'meridians';
      }} else if (scenario === 'noviceFirstPoint') {{
        resetState();
        state.principlesEnabled = true;
        state.meridiansEnabled = true;
        state.learningMode = 'guided';
        state.currentMeridianId = firstReadyMeridian().id;
        state.currentPointIndex = 0;
        state.screen = 'currentMeridian';
      }} else if (scenario === 'meridians') {{
        resetState();
        state.learningMode = null;
        state.currentPointIndex = -1;
        state.screen = 'meridians';
      }} else if (scenario === 'measurements') {{
        state.screen = 'measurements';
      }} else if (scenario === 'meridianPath') {{
        state.screen = 'meridianPath';
      }} else if (scenario === 'chooseMeridian') {{
        resetState();
        state.learningMode = 'free';
        state.currentMeridianId = null;
        state.currentPointIndex = -1;
        state.screen = 'chooseMeridian';
      }} else if (scenario === 'pointHelp') {{
        state.screen = 'pointHelp';
      }} else if (scenario === 'allPoints') {{
        resetState();
        state.learningMode = 'guided';
        state.currentMeridianId = 'bladder';
        state.currentPointIndex = 0;
        state.currentPointsPage = 0;
        state.screen = 'allPoints';
      }} else if (scenario === 'principles') {{
        state.screen = 'principles';
      }} else if (scenario === 'modes') {{
        state.screen = 'modes';
      }} else if (scenario === 'about') {{
        state.screen = 'about';
      }} else if (scenario === 'settings') {{
        state.screen = 'settings';
      }} else if (scenario === 'timezone') {{
        state.screen = 'timezone';
      }} else if (scenario === 'time') {{
        state.screen = 'time';
      }} else if (scenario === 'skipDays') {{
        state.screen = 'skipDays';
      }} else if (scenario === 'setupComplete') {{
        resetState();
        state.principlesEnabled = true;
        state.meridiansEnabled = true;
        state.screen = 'setupComplete';
      }} else if (scenario === 'main') {{
        resetState();
        state.screen = 'main';
      }} else {{
        resetState();
        state.screen = 'onboarding';
      }}
      render();
    }});
    render();
  </script>
</body>
</html>
"""
    return html


def render(output: Path) -> None:
    html = build_html()
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
    issues.extend(audit_rendered_html())
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
