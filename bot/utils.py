"""Utility functions for yoga bot."""

import json
import random
import os
from html import escape
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import pytz
import aiofiles


class PrinciplesManager:
    """Manager for yoga principles."""
    
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
        "en": "We do not leave the other principles behind. Today this one becomes the main lens through which you watch thoughts, words, and actions.",
        "ru": "Остальные принципы не откладываются в сторону. Сегодня этот принцип просто становится главным фокусом, через который вы наблюдаете мысли, речь и поступки.",
        "uz": "Boshqa tamoyillar chetga surilmaydi. Bugun shu tamoyil fikr, so'z va harakatlarni kuzatish uchun asosiy fokus bo'ladi.",
        "kz": "Қалған қағидалар шетте қалмайды. Бүгін осы қағида ойды, сөзді және әрекетті бақылауға арналған негізгі фокус болады.",
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
        return value[:limit - 3].rstrip() + "..."

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


def _localized_location(point: Dict[str, Any], language: str) -> str:
    """Return point location, making unfinished translations explicit."""
    location = _localized_value(point, language, "location")
    if language == "ru" or not location:
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


def format_meridian_point(meridian: Dict[str, Any], point_index: int, language: str = "en") -> str:
    """Format a meridian point for meditation practice."""
    points = meridian.get("points", [])
    if point_index < 0 or point_index >= len(points):
        return format_meridian_intro(meridian, language)

    point = points[point_index]
    meridian_name = escape(_localized_value(meridian, language, "name", meridian.get("id", "Meridian")))
    point_name = escape(_localized_value(point, language, "name", point.get("code", "Point")))
    location = escape(_localized_location(point, language))
    instruction = escape(_localized_value(point, language, "meditation_instruction"))
    question = escape(_localized_value(point, language, "observation_question"))

    practice_notes = {
        "en": (
            "Begin with the first point: find it through body sensation, breath, and attention. "
            "If the sensation is weak, treat the point as not yet open: give it more time, gently massage it, "
            "and imagine breathing through it until concentration becomes steady and easy.",
            "First recall the points you have already studied. Without losing them, add the current point and connect it with the previous ones as one line of attention. "
            "If it is hard to feel, treat it as not yet open: gently massage it, breathe through it with attention, and stay longer until the sensation becomes stable."
        ),
        "ru": (
            "Начните с первой точки: найдите её через ощущение тела, дыхание и внимание. "
            "Если ощущение слабое, считайте точку пока закрытой: уделите ей больше времени, мягко помассируйте её "
            "и представляйте вдох и выдох через неё, пока концентрация не станет лёгкой и устойчивой.",
            "Сначала вспомните и удерживайте ощущение уже пройденных точек. Не отпуская их, добавьте текущую точку и соедините её с предыдущими в одну линию внимания. "
            "Если точка не ощущается, считайте её пока закрытой: мягко помассируйте её, дышите через неё вниманием и оставайтесь дольше, пока ощущение не станет устойчивым."
        ),
        "uz": (
            "Birinchi nuqtadan boshlang: uni tana sezgisi, nafas va diqqat orqali toping. "
            "Agar sezgi kuchsiz bo'lsa, nuqtani hali ochilmagan deb qabul qiling: unga ko'proq vaqt bering, yengil massaj qiling "
            "va diqqat barqaror bo'lguncha shu nuqta orqali nafas olayotganingizni tasavvur qiling.",
            "Avval oldin o'rganilgan nuqtalarni eslang va sezib turing. Ularni yo'qotmasdan, hozirgi nuqtani qo'shing va oldingilari bilan bitta diqqat chizig'iga ulang. "
            "Agar nuqta sezilmasa, uni hali ochilmagan deb qabul qiling: yengil massaj qiling, diqqat bilan shu nuqta orqali nafas oling va sezgi barqaror bo'lguncha turing."
        ),
        "kz": (
            "Бірінші нүктеден бастаңыз: оны дене сезімі, тыныс және зейін арқылы табыңыз. "
            "Егер сезім әлсіз болса, нүктені әзірге ашылмаған деп қабылдаңыз: оған көбірек уақыт бөліңіз, жеңіл уқалаңыз "
            "және шоғырлану тұрақталғанша осы нүкте арқылы дем алып-шығаруды елестетіңіз.",
            "Алдымен бұрын өткен нүктелердің сезімін еске түсіріп, ұстап тұрыңыз. Оларды жібермей, қазіргі нүктені қосып, алдыңғыларымен бір зейін сызығына біріктіріңіз. "
            "Егер нүкте сезілмесе, оны әзірге ашылмаған деп қабылдаңыз: жеңіл уқалаңыз, зейінмен сол нүкте арқылы тыныстаңыз және сезім тұрақталғанша ұзағырақ болыңыз."
        ),
    }
    first_note, next_note = practice_notes.get(language, practice_notes["en"])
    practice_note = escape(first_note if point_index == 0 else next_note)

    labels = {
        "en": ("Point", "Location", "Focus", "Observe"),
        "ru": ("Точка", "Расположение", "Концентрация", "Наблюдение"),
        "uz": ("Nuqta", "Joylashuv", "Diqqat", "Kuzatish"),
        "kz": ("Нүкте", "Орналасуы", "Зейін", "Бақылау"),
    }.get(language, ("Point", "Location", "Focus", "Observe"))

    message = f"<b>{meridian_name}</b>\n"
    message += f"<b>{escape(labels[0])} {point_index + 1}/{len(points)}:</b> {escape(str(point.get('code', '')))} {point_name}\n\n"
    if location:
        message += f"<b>{escape(labels[1])}:</b> {location}\n\n"
    if instruction:
        message += f"<b>{escape(labels[2])}:</b> {instruction}\n\n"
    message += f"{practice_note}\n\n"
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
    
    # Try different possible locations for images
    possible_paths = [
        current_dir / "images" / f"{principle_id}.jpg",  # From project root
        Path("images") / f"{principle_id}.jpg",  # Relative to current dir
        Path("../images") / f"{principle_id}.jpg",  # One level up
        Path(f"./images/{principle_id}.jpg"),  # Current directory
        Path(f"/app/images/{principle_id}.jpg"),  # Docker absolute path
    ]
    
    for image_path in possible_paths:
        logger.debug(f"Checking image path: {image_path}")
        if image_path.exists():
            logger.info(f"Found image for principle {principle_id}: {image_path}")
            return str(image_path)
    
    logger.warning(f"No image found for principle {principle_id}. Checked paths: {[str(p) for p in possible_paths]}")
    return None


def has_principle_image(principle_id: int) -> bool:
    """Check if principle has an associated image."""
    return get_principle_image_path(principle_id) is not None 
