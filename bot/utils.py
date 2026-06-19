"""Utility functions for yoga bot."""

import json
import random
import os
import re
from html import escape, unescape
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import pytz
import aiofiles


class PrinciplesManager:
    """Manager for Yama/Niyama principle content."""
    
    def __init__(self, principles_file: str = "bot/principles.json"):
        self.principles_file = principles_file
        self._principles: List[Dict[str, Any]] = []
    
    async def load_principles(self) -> None:
        """Load principles from JSON file."""
        try:
            async with aiofiles.open(self.principles_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                self._principles = json.loads(content)
        except Exception as e:
            print(f"Error loading principles: {e}")
            self._principles = {"en": [], "ru": []}
    
    def get_principle_by_id(self, principle_id: int) -> Optional[Dict[str, Any]]:
        """Get principle by ID."""
        for principle in self._principles:
            if principle["id"] == principle_id:
                return principle
        return None
    
    def get_random_principle(self, language: str = "en", excluded_ids: List[int] = None) -> Optional[Dict[str, Any]]:
        """Get completely random principle for specified language."""
        if not self._principles:
            return None
        
        # Get principles for specified language
        lang_principles = self._principles.get(language, self._principles.get("en", []))
        if not lang_principles:
            return None
        
        return random.choice(lang_principles)
    
    def get_all_principles(self, language: str = "en") -> List[Dict[str, Any]]:
        """Get all principles for specified language."""
        if not self._principles:
            return []
        
        return self._principles.get(language, self._principles.get("en", [])).copy()
    
    async def add_principle(self, principle: Dict[str, Any]) -> bool:
        """Add new principle."""
        # Get max ID and increment.
        max_id = max([p["id"] for p in self._principles], default=0)
        principle["id"] = max_id + 1
        
        self._principles.append(principle)
        
        # Save to file.
        try:
            async with aiofiles.open(self.principles_file, 'w', encoding='utf-8') as f:
                content = json.dumps(self._principles, ensure_ascii=False, indent=2)
                await f.write(content)
            return True
        except Exception:
            # Remove from memory if saving failed.
            self._principles.remove(principle)
            return False


class MeridiansManager:
    """Manager for Chinese meridians study content."""

    RECOMMENDED_PATH = [
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
    ]

    def __init__(self, meridians_file: str = "bot/meridians.json"):
        self.meridians_file = meridians_file
        self._meridians: Dict[str, Any] = {"meridians": []}

    async def load_meridians(self) -> None:
        """Load meridians from JSON file."""
        try:
            async with aiofiles.open(self.meridians_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                self._meridians = json.loads(content)
        except Exception as e:
            print(f"Error loading meridians: {e}")
            self._meridians = {"meridians": []}

    def get_all_meridians(self) -> List[Dict[str, Any]]:
        """Get all meridians."""
        return self._meridians.get("meridians", []).copy()

    def get_available_meridians(self) -> List[Dict[str, Any]]:
        """Get meridians that have point content ready for practice."""
        return [
            meridian
            for meridian in self.get_all_meridians()
            if meridian.get("points")
        ]

    def get_recommended_path_meridians(self) -> List[Dict[str, Any]]:
        """Get available meridians in the product's recommended study order."""
        by_id = {meridian.get("id"): meridian for meridian in self.get_all_meridians()}
        ordered = [
            by_id[meridian_id]
            for meridian_id in self.RECOMMENDED_PATH
            if by_id.get(meridian_id) and by_id[meridian_id].get("points")
        ]
        extra_ready = [
            meridian
            for meridian in self.get_available_meridians()
            if meridian.get("id") not in self.RECOMMENDED_PATH
        ]
        return ordered + extra_ready

    def get_meridian_by_id(self, meridian_id: str) -> Optional[Dict[str, Any]]:
        """Get meridian by ID."""
        for meridian in self._meridians.get("meridians", []):
            if meridian.get("id") == meridian_id:
                return meridian
        return None

    def get_first_meridian(self) -> Optional[Dict[str, Any]]:
        """Get the first meridian in the recommended path."""
        meridians = self.get_recommended_path_meridians() or self.get_all_meridians()
        return meridians[0] if meridians else None

    def get_next_meridian(self, current_meridian_id: Optional[str], completed_ids: List[str] = None) -> Optional[Dict[str, Any]]:
        """Get the next meridian after the current one, preferring incomplete meridians."""
        meridians = self.get_recommended_path_meridians() or self.get_all_meridians()
        if not meridians:
            return None

        completed_ids = completed_ids or []
        if not current_meridian_id:
            for meridian in meridians:
                if meridian.get("id") not in completed_ids:
                    return meridian
            return meridians[0]

        current_index = next((idx for idx, item in enumerate(meridians) if item.get("id") == current_meridian_id), -1)
        for offset in range(1, len(meridians) + 1):
            candidate = meridians[(current_index + offset) % len(meridians)]
            if candidate.get("id") not in completed_ids:
                return candidate
        return meridians[(current_index + 1) % len(meridians)] if current_index >= 0 else meridians[0]


def format_principle_message(principle: Dict[str, Any], language: str = "en", max_length: int = 1024) -> str:
    """Format a daily Yama/Niyama focus as an HTML caption-safe message."""
    labels = {
        "en": ("Part", "Today's focus", "Practice"),
        "ru": ("Часть", "Фокус дня", "Практика"),
        "uz": ("Qismi", "Bugungi fokus", "Amaliyot"),
        "kz": ("Бөлігі", "Бүгінгі фокус", "Тәжірибе"),
    }.get(language, ("Part", "Today's focus", "Practice"))
    groups = {
        "en": ("Yama", "Niyama"),
        "ru": ("Яма", "Нияма"),
        "uz": ("Yama", "Niyama"),
        "kz": ("Яма", "Нияма"),
    }.get(language, ("Yama", "Niyama"))
    reminders = {
        "en": "Keep this principle especially visible today. The rest are not paused; we are simply giving one of them more attention.",
        "ru": "Сегодня держите этот принцип особенно близко. Остальные не выключаются; мы просто даём одному из них больше внимания.",
        "uz": "Bugun shu tamoyilni ayniqsa yaqin tuting. Qolganlari to'xtamaydi; biz faqat bittasiga ko'proq e'tibor beramiz.",
        "kz": "Бүгін осы қағиданы ерекше жақын ұстаңыз. Қалғандары тоқтамайды; біз тек біреуіне көбірек назар береміз.",
    }.get(language)

    principle_id = int(principle.get("id", 0) or 0)
    group = groups[0] if principle_id <= 5 else groups[1]
    emoji = principle.get("emoji", "🧘")
    name = principle.get("name", "")
    short_desc = principle.get("short_description", "")
    description = principle.get("description", "")
    practice_tip = principle.get("practice_tip", "")

    def shorten(value: str, limit: int) -> str:
        if limit <= 0:
            return ""
        if len(value) <= limit:
            return value
        if limit <= 3:
            return value[:limit]
        candidate = value[:limit - 3].rstrip()
        sentence_end = max(candidate.rfind("."), candidate.rfind("!"), candidate.rfind("?"))
        if sentence_end >= max(40, int(limit * 0.45)):
            candidate = candidate[:sentence_end + 1]
            return candidate
        return candidate.rstrip(",;:") + "..."

    def build(desc: str, practice: str) -> str:
        parts = [
            f"<b>{escape(name)}</b> {escape(emoji)}".strip(),
            f"<b>{escape(labels[0])}:</b> {escape(group)}",
        ]
        if short_desc:
            parts.append(escape(short_desc))
        if reminders:
            parts.append(f"<b>{escape(labels[1])}:</b> {escape(reminders)}")
        if desc:
            parts.append(escape(desc))
        if practice:
            parts.append(f"💡 <b>{escape(labels[2])}:</b> <i>{escape(practice)}</i>")
        return "\n\n".join(part for part in parts if part)

    text = build(description, practice_tip)
    if len(text) <= max_length:
        return text

    desc = description
    practice = practice_tip
    while len(build(desc, practice)) > max_length and len(desc) > 20:
        overflow = len(build(desc, practice)) - max_length
        desc = shorten(desc, max(20, len(desc) - overflow - 8))

    text = build(desc, practice)
    if len(text) <= max_length:
        return text

    desc = ""
    text = build(desc, practice)
    while len(text) > max_length and len(practice) > 20:
        overflow = len(text) - max_length
        practice = shorten(practice, max(20, len(practice) - overflow - 8))
        text = build(desc, practice)

    if len(text) <= max_length:
        return text
    return build("", "")


def fit_html_caption(text: str, max_length: int = 1024) -> str:
    """Fit simple Telegram HTML text into a media caption without cutting tags."""
    if len(text) <= max_length:
        return text

    def plain_text(source: str) -> str:
        return unescape(
            source.replace("<br>", "\n")
            .replace("<b>", "")
            .replace("</b>", "")
            .replace("<i>", "")
            .replace("</i>", "")
        )

    def fit_plain(source: str, budget: int) -> str:
        if budget <= 3:
            return "..."[:max(0, budget)]
        plain = plain_text(source)
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


def _localized_value(item: Dict[str, Any], language: str, key: str, default: str = "") -> str:
    """Return a localized value from a content item."""
    localized = item.get("i18n", {})
    return localized.get(language, localized.get("en", {})).get(key, default)


def _content_html(value: str) -> str:
    """Escape local content while allowing basic Telegram HTML formatting."""
    escaped = escape(value)
    for tag in ("b", "i"):
        escaped = escaped.replace(f"&lt;{tag}&gt;", f"<{tag}>")
        escaped = escaped.replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    return escaped


def _has_cyrillic(value: str) -> bool:
    """Detect Cyrillic text in a localized content field."""
    return any("А" <= char <= "я" or char in "ЁёІіЇїЄєҚқҒғҰұҮүӘәӨөҺһҢң" for char in value)


def _latinize_point_name(name: str) -> str:
    """Make Cyrillic Chinese point names readable in Latin-script locales."""
    if not name:
        return ""
    text = name.lower().replace("ё", "е")
    phrase_replacements = (
        ("чж", "zh"),
        ("цз", "z"),
        ("ш", "sh"),
        ("щ", "shch"),
        ("ч", "ch"),
        ("ю", "yu"),
        ("я", "ya"),
        ("й", "y"),
        ("х", "h"),
        ("э", "e"),
    )
    for source, target in phrase_replacements:
        text = text.replace(source, target)
    letters = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
        "ж": "zh", "з": "z", "и": "i", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "u", "ф": "f", "ц": "c", "ы": "y", "ь": "", "ъ": "",
    }
    latin = "".join(letters.get(char, char) for char in text)
    parts = re.split(r"([-\s])", latin)
    return "".join(part.capitalize() if part and part not in {"-", " "} else part for part in parts)


def localized_point_name(point: Dict[str, Any], language: str) -> str:
    """Return a point name only when it fits the visible interface language."""
    name = _localized_value(point, language, "name", "")
    if language in {"en", "uz"} and _has_cyrillic(name):
        return _latinize_point_name(name)
    return name


def _localized_location(point: Dict[str, Any], language: str) -> str:
    """Return point location, making unfinished translations explicit."""
    location = _localized_value(point, language, "location")
    if language in {"ru", "kz"} or not location:
        return location

    prefixes = (
        "Source location:",
        "Manbadagi joylashuv:",
        "Дереккөздегі орналасуы:",
    )
    source_location = location
    for prefix in prefixes:
        if source_location.startswith(prefix):
            source_location = source_location[len(prefix):].strip()
            break
    else:
        if not _has_cyrillic(location):
            return location

    if source_location.lower().startswith("pending source refinement"):
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
    return f"{labels.get(language, 'Original source location (RU)')}: {source_location}"


def format_meridian_intro(meridian: Dict[str, Any], language: str = "en") -> str:
    """Format meridian overview for the user."""
    name = escape(_localized_value(meridian, language, "name", meridian.get("id", "Meridian")))
    description = _content_html(_localized_value(meridian, language, "description"))
    active_time = meridian.get("active_time", "-")
    passive_time = meridian.get("passive_time", "-")
    points = meridian.get("points", [])
    direction = _content_html(_localized_value(meridian, language, "direction"))
    practice = _content_html(_localized_value(meridian, language, "intro_practice"))

    labels = {
        "en": ("Active", "Passive", "Points", "Direction", "Practice"),
        "ru": ("Активен", "Пассивен", "Точек", "Ход", "Практика"),
        "uz": ("Faol", "Passiv", "Nuqtalar", "Yo'nalish", "Amaliyot"),
        "kz": ("Белсенді", "Пассивті", "Нүктелер", "Бағыты", "Тәжірибе"),
    }.get(language, ("Active", "Passive", "Points", "Direction", "Practice"))

    message = f"<b>{name}</b>\n\n"
    if description:
        message += f"{description}\n\n"
    message += f"<b>{escape(labels[0])}:</b> {escape(str(active_time))}\n"
    message += f"<b>{escape(labels[1])}:</b> {escape(str(passive_time))}\n"
    message += f"<b>{escape(labels[2])}:</b> {len(points)}\n"
    if direction:
        message += f"<b>{escape(labels[3])}:</b> {direction}\n"
    if practice:
        message += f"\n<i>{escape(labels[4])}:</i> {practice}"
    return message


def _short_point_area(location: str, limit: int = 96) -> str:
    """Create a compact body-area phrase from a point location."""
    if not location:
        return ""
    area = re.split(r"(?<!\d)\.(?!\d)|;", location.strip(), maxsplit=1)[0]
    if len(area) <= limit:
        return area
    return area[:limit].rsplit(" ", 1)[0].rstrip(",") + "..."


def _compact_point_location(location: str, limit: int = 260) -> str:
    """Keep very long anatomical locations readable inside Telegram captions."""
    if len(location) <= limit:
        return location
    return location[:limit].rsplit(" ", 1)[0].rstrip(",") + "..."


def _clean_point_location(location: str) -> str:
    """Remove source-editorial tails from point locations before showing them."""
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


def _point_observation_prompt(
    point: Dict[str, Any],
    point_index: int,
    language: str,
    point_title: str,
    location: str,
) -> str:
    """Build a point-specific observation prompt so cards do not feel generic."""
    if language == "ru":
        if point_index == 0:
            return "Что первым откликается здесь: тепло, давление, пульсация, пустота или сопротивление внимания?"
        return (
            "Удерживая предыдущие точки, что меняется здесь: линия становится яснее, "
            "теплее, плотнее или где-то обрывается?"
        )
    if language == "uz":
        if point_index == 0:
            return "Bu yerda birinchi nima javob beradi: iliqlik, bosim, pulsatsiya, bo'shliq yoki diqqatga qarshilik?"
        return (
            "Oldingi nuqtalarni ushlab turib, bu yerda nima o'zgaradi: chiziq "
            "aniqroq, iliqroq, zichroq bo'ladimi yoki qayerdadir uziladimi?"
        )
    if language == "kz":
        if point_index == 0:
            return "Бұл жерде алдымен не жауап береді: жылу, қысым, соғу, бос кеңістік немесе зейінге қарсылық па?"
        return (
            "Алдыңғы нүктелерді ұстап тұрып, бұл жерде не өзгереді: сызық "
            "анығырақ, жылырақ, тығызырақ бола ма, әлде бір жерде үзіле ме?"
        )
    if point_index == 0:
        return "What responds first here: warmth, pressure, pulsation, emptiness, or resistance to attention?"
    return (
        "While holding the previous points, what changes here: does the line become "
        "clearer, warmer, denser, or does it break somewhere?"
    )


def _point_sequence_practice_hint(point_index: int, points_count: int, language: str) -> str:
    """Guide the user through the meridian as a growing line, not isolated dots."""
    is_first = point_index <= 0
    is_last = points_count > 0 and point_index >= points_count - 1
    late = points_count > 0 and point_index >= max(1, int(points_count * 0.7))

    if language == "ru":
        if is_first:
            return (
                "Начните только с этой точки. Найдите её по изображению, касанию, дыханию "
                "и спокойному вниманию. Если ощущение слабое, считайте точку пока закрытой "
                "для практики: побудьте дольше, мягко помассируйте область и представляйте "
                "дыхание через точку, пока вниманию не станет легче удерживаться здесь."
            )
        if is_last:
            return (
                "Сначала соберите ощущение всех уже пройденных точек. Затем добавьте последнюю "
                "точку и почувствуйте, замыкается ли меридиан в одну линию или где-то ещё просит внимания."
            )
        if late:
            return (
                "Вернитесь вниманием к началу меридиана и проведите линию до этой точки. "
                "Не спешите: если участок теряется, задержитесь на нём, мягко коснитесь и снова соедините с предыдущими точками."
            )
        return (
            "Сначала вспомните уже изученные точки. Удерживая их фоном, добавьте эту точку "
            "и посмотрите, становится ли линия меридиана яснее, теплее или где-то обрывается."
        )

    if language == "uz":
        if is_first:
            return (
                "Faqat shu nuqtadan boshlang. Uni rasm, teginish, nafas va sokin diqqat orqali toping. "
                "Agar sezgi kuchsiz bo'lsa, nuqtani amaliyot uchun hali ochilmagan deb qabul qiling: "
                "uzoqroq turing, sohani yengil massaj qiling va diqqat bu yerda osonroq turmaguncha "
                "nuqta orqali nafas olayotganingizni tasavvur qiling."
            )
        if is_last:
            return (
                "Avval o'tilgan barcha nuqtalar sezgisini yig'ing. Keyin oxirgi nuqtani qo'shib, "
                "meridian bitta chiziqqa yopiladimi yoki qayerdir yana e'tibor so'raydimi, sezing."
            )
        if late:
            return (
                "Diqqatni meridian boshiga qaytaring va chiziqni shu nuqtagacha olib boring. "
                "Shoshilmang: agar biror qism yo'qolsa, unda qoling, yengil teging va oldingi nuqtalar bilan yana ulang."
            )
        return (
            "Avval o'rganilgan nuqtalarni eslang. Ularni fon sifatida ushlab, bu nuqtani qo'shing "
            "va meridian chizig'i aniqroq, iliqroq bo'ladimi yoki qayerdadir uziladimi, kuzating."
        )

    if language == "kz":
        if is_first:
            return (
                "Тек осы нүктеден бастаңыз. Оны сурет, жанасу, тыныс және тыныш зейін арқылы табыңыз. "
                "Егер сезім әлсіз болса, нүктені тәжірибе үшін әзірге ашылмаған деп қабылдаңыз: "
                "ұзағырақ болыңыз, аймақты жеңіл уқалаңыз және зейін бұл жерде жеңілірек орныққанша "
                "нүкте арқылы тыныстап жатқаныңызды елестетіңіз."
            )
        if is_last:
            return (
                "Алдымен өткен барлық нүктелердің сезімін жинаңыз. Содан кейін соңғы нүктені қосып, "
                "меридиан бір сызыққа тұтаса ма, әлде бір жері әлі назар сұрай ма, байқаңыз."
            )
        if late:
            return (
                "Зейінді меридианның басына қайтарып, сызықты осы нүктеге дейін алып келіңіз. "
                "Асықпаңыз: бір бөлігі жоғалса, сонда кідіріп, жеңіл тиіп, алдыңғы нүктелермен қайта қосыңыз."
            )
        return (
            "Алдымен бұрын зерттелген нүктелерді еске түсіріңіз. Оларды фон ретінде ұстап, осы нүктені қосыңыз "
            "және меридиан сызығы анығырақ, жылырақ бола ма, әлде бір жерде үзіле ме, байқаңыз."
        )

    if is_first:
        return (
            "Start with this point only. Find it with the image, touch, breath, and quiet attention. "
            "If the sensation is weak, treat the point as not yet open for practice: stay longer, "
            "gently massage the area, and imagine breathing through the point until attention can rest here more easily."
        )
    if is_last:
        return (
            "First gather the feeling of all points you have already passed. Then add the last point and notice "
            "whether the meridian closes into one line or still asks for attention somewhere."
        )
    if late:
        return (
            "Return attention to the beginning of the meridian and trace the line up to this point. "
            "Do not hurry: if a segment disappears, stay with it, touch it gently, and reconnect it with the previous points."
        )
    return (
        "Recall the points you have already studied. Keep them in the background, add this point, "
        "and notice whether the meridian line becomes clearer, warmer, or breaks somewhere."
    )


def _point_area_practice_hint(location: str, language: str) -> str:
    """Return a short body-area cue so point practice does not feel mechanical."""
    normalized = (location or "").lower()
    cues = {
        "ru": (
            (("пуп", "живот", "лобков", "промежност", "анус", "половых", "мошон"), "Смягчите живот и таз; пусть дыхание не толкает ощущение, а будто освобождает для него место."),
            (("позвон", "крестц", "копчик", "спин", "затыл"), "Выпрямитесь без напряжения и почувствуйте, как точка включается в заднюю срединную линию."),
            (("горл", "шеи", "шее", "шейн", "шею", "подбород", "губ", "носа", "носу", "носов", "лицо", "лица", "лицев", "лоб", "тем", "голов"), "Расслабьте лицо, язык и горло; иногда точка откликается только после этого."),
            (("грудной", "грудная", "грудной клет", "ребр", "ребер", "межреб", "ключиц", "соска", "соски"), "Дайте грудной клетке чуть больше пространства; наблюдайте, меняется ли глубина дыхания."),
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


def _point_setup_practice_hint(source_location: str, language: str) -> str:
    """Recover useful positioning hints from source-style location tails."""
    normalized = (source_location or "").lower()
    rules = (
        (("mouth open", "og'iz ochiq", "открытым ртом", "ауыз ашық"), {
            "ru": "Для уточнения точки мягко приоткройте рот и ищите углубление без напряжения челюсти.",
            "en": "To refine the point, softly open the mouth and look for the hollow without tensing the jaw.",
            "uz": "Nuqtani aniqlash uchun og'izni yumshoq oching va jag'ni zo'riqtirmasdan chuqurchani qidiring.",
            "kz": "Нүктені нақтылау үшін ауызды жұмсақ ашып, жақты қыспай ойықты іздеңіз.",
        }),
        (("arm raised", "qo'l yuqoriga", "рука подня", "поднятой рукой", "қол жоғары"), {
            "ru": "Если точка находится на боковой линии груди, мягко поднимите руку, чтобы зона раскрылась.",
            "en": "If the point is on the side of the chest, raise the arm gently so the area opens.",
            "uz": "Nuqta ko'krak yon chizig'ida bo'lsa, qo'lni yumshoq ko'taring, shunda soha ochiladi.",
            "kz": "Нүкте кеуденің бүйір сызығында болса, аймақ ашылуы үшін қолды жұмсақ көтеріңіз.",
        }),
        (("palm facing upward", "kaft yuqoriga", "ладонь вверх", "ладонью вверх", "алақан жоғары"), {
            "ru": "Поверните ладонь вверх и отпустите локоть; так внутренняя линия руки читается яснее.",
            "en": "Turn the palm upward and release the elbow; the inner arm line becomes easier to read.",
            "uz": "Kaftni yuqoriga qarating va tirsakni bo'shating; qo'lning ichki chizig'i aniqroq seziladi.",
            "kz": "Алақанды жоғары қаратып, шынтақты босатыңыз; қолдың ішкі сызығы анық сезіледі.",
        }),
        (("knee bent", "knee slightly bent", "tizza bukilgan", "колено согну", "согнутым колен", "тізе бүг"), {
            "ru": "Слегка согните колено, если так точка находится яснее; не удерживайте ногу силой.",
            "en": "Bend the knee slightly if the point becomes clearer; do not hold the leg with force.",
            "uz": "Nuqta aniqroq topilsa, tizzani biroz buking; oyoqni kuch bilan ushlab turmang.",
            "kz": "Нүкте анығырақ табылса, тізені сәл бүгіңіз; аяқты күшпен ұстамаңыз.",
        }),
        (("lies on the abdomen", "qorni bilan yot", "на животе", "етпетінен"), {
            "ru": "Для задней линии можно лечь на живот и дать спине спокойно опуститься в опору.",
            "en": "For the back line, you may lie face down and let the back settle into support.",
            "uz": "Orqa chiziq uchun qorin bilan yotib, bel va orqani tayanchga qo'yib yuborish mumkin.",
            "kz": "Артқы сызық үшін етпетінен жатып, арқаны тірекке жайлап босатуға болады.",
        }),
        (("lies on the side", "yonboshlab", "на боку", "бүйір"), {
            "ru": "Если точка на тазобедренной или боковой линии, найдите её лёжа на боку, без сжатия таза.",
            "en": "If the point is on the hip or side line, find it lying on the side without gripping the pelvis.",
            "uz": "Nuqta son yoki yon chiziqda bo'lsa, uni yonboshlab yotib, tosni siqmasdan toping.",
            "kz": "Нүкте жамбас не бүйір сызығында болса, оны бүйірлеп жатып, жамбасты қыспай табыңыз.",
        }),
        (("palm on the chest", "kaftni ko'krakka", "ладонь к груди", "алақанды кеудеге"), {
            "ru": "Если помогает, положите ладонь к груди: так край кости и углубление становятся заметнее.",
            "en": "If helpful, place the palm toward the chest; the bony edge and hollow become easier to notice.",
            "uz": "Agar yordam bersa, kaftni ko'krakka qo'ying; suyak cheti va chuqurcha sezilarliroq bo'ladi.",
            "kz": "Көмектессе, алақанды кеудеге қойыңыз; сүйек жиегі мен ойық айқынырақ сезіледі.",
        }),
    )
    for markers, translations in rules:
        if any(marker in normalized for marker in markers):
            return translations.get(language, "")
    return ""


def _point_stage_practice_hint(point_index: int, points_count: int, language: str) -> str:
    """Return a short cue for the user's place inside the meridian sequence."""
    if points_count <= 0 or point_index < points_count - 1:
        return ""
    return {
        "ru": "После этого пройдите вниманием весь канал от первой точки до последней и отметьте, где линия стала цельной, а где ещё просит внимания.",
        "en": "After that, pass through the whole channel from the first point to the last and notice where the line feels whole or still asks for attention.",
        "uz": "Shundan keyin butun kanalni birinchi nuqtadan oxirgisigacha diqqat bilan bosib o'ting va chiziq qayerda yaxlit, qayerda yana e'tibor so'rashini kuzating.",
        "kz": "Содан кейін бүкіл арнаны бірінші нүктеден соңғысына дейін зейінмен өтіп, сызық қай жерде тұтас, қай жерде әлі назар сұрайтынын байқаңыз.",
    }.get(language, "")


def format_meridian_point(meridian: Dict[str, Any], point_index: int, language: str = "en") -> str:
    """Format a meridian point for meditation practice."""
    points = meridian.get("points", [])
    if point_index < 0 or point_index >= len(points):
        return format_meridian_intro(meridian, language)

    point = points[point_index]
    meridian_name = escape(_localized_value(meridian, language, "name", meridian.get("id", "Meridian")))
    point_name = escape(localized_point_name(point, language))
    source_location = _localized_location(point, language)
    raw_location = _clean_point_location(source_location)
    compact_location = _compact_point_location(raw_location)
    location = escape(compact_location)

    area_hint = _point_area_practice_hint(compact_location, language)
    base_instruction = _point_sequence_practice_hint(point_index, len(points), language)
    practice_parts = [base_instruction]
    if area_hint:
        practice_parts.append(area_hint)
    setup_hint = _point_setup_practice_hint(source_location, language)
    if setup_hint:
        practice_parts.append(setup_hint)
    stage_hint = _point_stage_practice_hint(point_index, len(points), language)
    if stage_hint:
        practice_parts.append(stage_hint)
    practice_note = escape(" ".join(practice_parts))

    labels = {
        "en": ("Point", "Location", "Focus", "Observe"),
        "ru": ("Точка", "Расположение", "Концентрация", "Наблюдение"),
        "uz": ("Nuqta", "Joylashuv", "Diqqat", "Kuzatish"),
        "kz": ("Нүкте", "Орналасуы", "Зейін", "Бақылау"),
    }.get(language, ("Point", "Location", "Focus", "Observe"))

    point_title = " ".join(part for part in (escape(str(point.get("code", ""))), point_name) if part)
    raw_point_title = " ".join(part for part in (str(point.get("code", "")).strip(), localized_point_name(point, language)) if part)
    question = escape(_point_observation_prompt(point, point_index, language, raw_point_title, raw_location))
    message = f"<b>{meridian_name}</b>\n"
    message += f"<b>{escape(labels[0])} {point_index + 1}/{len(points)}:</b> {point_title}\n\n"
    if location:
        message += f"<b>{escape(labels[1])}:</b> {location}\n\n"
    message += f"<b>{escape(labels[2])}:</b> {practice_note}\n\n"
    if question:
        with_question = message + f"<i>{escape(labels[3])}:</i> {question}"
        if len(with_question) <= 1024:
            message = with_question
    return message


def get_meridian_image_path(meridian_id: str, point_code: Optional[str] = None) -> Optional[str]:
    """Get image path for a meridian or a meridian point."""
    current_dir = Path(__file__).parent.parent
    filenames = []
    if point_code:
        filenames.extend([
            f"{meridian_id}_{point_code}.jpg",
            f"{meridian_id}_{point_code}.png",
            f"{meridian_id}_{point_code}.gif",
        ])
    else:
        filenames.extend([f"{meridian_id}.jpg", f"{meridian_id}.png", f"{meridian_id}.gif"])

    base_paths = [
        current_dir / "images" / "meridians",
        Path("images") / "meridians",
        Path("/app/images/meridians"),
    ]
    for base_path in base_paths:
        for filename in filenames:
            image_path = base_path / filename
            if image_path.exists():
                return str(image_path)
    return None


def is_valid_timezone(timezone_str: str) -> bool:
    """Check if timezone string is valid."""
    try:
        pytz.timezone(timezone_str)
        return True
    except pytz.exceptions.UnknownTimeZoneError:
        return False


def is_valid_time_format(time_str: str) -> bool:
    """Check if time string is in HH:MM format."""
    try:
        datetime.strptime(time_str, "%H:%M")
        return True
    except ValueError:
        return False


def get_user_local_time(user_timezone: str, target_time: str) -> datetime:
    """Get next occurrence of target time in user's timezone."""
    try:
        tz = pytz.timezone(user_timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        tz = pytz.UTC
    
    # Parse target time.
    target_hour, target_minute = map(int, target_time.split(":"))
    
    # Get current time in user's timezone.
    now = datetime.now(tz)
    
    # Create target datetime for today.
    target_dt = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # If target time already passed today, schedule for tomorrow.
    if target_dt <= now:
        target_dt += timedelta(days=1)
    
    return target_dt


def should_skip_today(skip_days: List[int], target_datetime: datetime) -> bool:
    """Check if should skip sending today based on user's skip days."""
    # Monday = 0, Sunday = 6.
    weekday = target_datetime.weekday()
    return weekday in skip_days


def get_next_send_time(user_timezone: str, target_time: str, skip_days: List[int]) -> datetime:
    """Get next valid send time considering skip days."""
    target_dt = get_user_local_time(user_timezone, target_time)
    
    # Keep checking future days until we find one that's not skipped.
    while should_skip_today(skip_days, target_dt):
        target_dt += timedelta(days=1)
    
    return target_dt


def validate_skip_days(skip_days: List[int]) -> bool:
    """Validate skip days list."""
    if not isinstance(skip_days, list):
        return False
    
    for day in skip_days:
        if not isinstance(day, int) or day < 0 or day > 6:
            return False
    
    return True


class HealthCheck:
    """Health check utilities."""
    
    def __init__(self):
        self.start_time = datetime.now(timezone.utc)
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status."""
        uptime = datetime.now(timezone.utc) - self.start_time
        
        return {
            "status": "healthy",
            "uptime_seconds": int(uptime.total_seconds()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0"
        }


def get_prometheus_metrics() -> str:
    """Get Prometheus metrics format."""
    # Basic metrics for now.
    now = datetime.now(timezone.utc)
    uptime = now - now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    metrics = [
        "# HELP yoga_bot_uptime_seconds Bot uptime in seconds",
        "# TYPE yoga_bot_uptime_seconds counter",
        f"yoga_bot_uptime_seconds {int(uptime.total_seconds())}",
        "",
        "# HELP yoga_bot_info Bot information",
        "# TYPE yoga_bot_info gauge",
        'yoga_bot_info{version="1.0.0"} 1'
    ]
    
    return "\n".join(metrics)


def get_principle_image_path(principle_id: int) -> Optional[str]:
    """Get image path for principle by ID."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Get the directory where this file is located
    current_dir = Path(__file__).parent.parent
    
    base_paths = [
        current_dir / "images",
        Path("images"),
        Path("../images"),
        Path("/app/images"),
    ]
    checked_paths = []
    for base_path in base_paths:
        for extension in (".jpg", ".png", ".gif"):
            image_path = base_path / f"{principle_id}{extension}"
            checked_paths.append(str(image_path))
            logger.debug(f"Checking image path: {image_path}")
            if image_path.exists():
                logger.info(f"Found image for principle {principle_id}: {image_path}")
                return str(image_path)

    logger.warning(f"No image found for principle {principle_id}. Checked paths: {checked_paths}")
    return None


def has_principle_image(principle_id: int) -> bool:
    """Check if principle has an associated image."""
    return get_principle_image_path(principle_id) is not None
