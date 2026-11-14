"""Self-check "which channel to start with": 24 everyday signs, the channel with most ticks is a place to begin.

The questions live in webapp/assets/self_check.json (shared with the map): each one is an imbalance item of
meridian_profiles.json, so the texts and their four translations come from there. A tick gives its channel
2 and the related channels 1. The bot keeps nothing: the ticks travel in the callback data as a bit mask.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton

from .utils import point_caution_lines
from .webapp import WEBAPP_DIR

if TYPE_CHECKING:
    from .utils import MeridiansManager

ASSETS = WEBAPP_DIR / "assets"
PER_PAGE = 12
PER_ROW = 4
PREFIX = "meridian_check"

TEXTS = {
    "ru": {
        "menu": "🧭 С какого канала начать",
        "title": "<b>🧭 С какого канала начать</b>",
        "intro": "Отметьте всё, что было с вами в последние недели, сколько угодно. Нажимайте номера под "
                 "сообщением. По отметкам видно, какой канал откликается больше других: с него удобно начать "
                 "знакомство. Это подсказка, не диагноз.",
        "page": "<i>Часть {p} из {n}</i>",
        "next": "Дальше ›",
        "prev": "‹ Назад",
        "done": "Готово ✓",
        "picked": "Отмечено: {n}",
        "result_top": "Больше всего отметок у этого канала: <b>{name}</b>. С него удобно начать.",
        "your_signs": "Что вы отметили по этому каналу:",
        "first_point": "Первая точка: <b>{point}</b>. {why}",
        "also": "Ещё откликаются: {names}.",
        "none": "Вы ничего не отметили. Тогда начните с канала, который идёт следующим на пути: <b>{name}</b>.",
        "none_bare": "Вы ничего не отметили.",
        "note": "Это подсказка для знакомства с каналами, не диагноз. Если что-то беспокоит всерьёз или долго "
                "не проходит, обратитесь к врачу.",
        "start": "▶️ Начать с этого канала",
        "continue": "▶️ Продолжить этот канал",
        "path_kept": "🧭 Путь по порядку сохраняется: после этого канала бот перейдёт дальше, к нему: <b>{name}</b>.",
        "path_kept_last": "🧭 Путь по порядку сохраняется: это последний канал пути, который вы ещё не прошли.",
        "point_btn": "📍 Первая точка: {code}",
        "again": "↻ Пройти заново",
        "back": "↩ К меридианам",
    },
    "en": {
        "menu": "🧭 Which channel to start with",
        "title": "<b>🧭 Which channel to start with</b>",
        "intro": "Tick what has been true for you in recent weeks, as many as you like. Tap the numbers under "
                 "the message. The ticks show which channel comes up most often, a good place to begin. "
                 "This is a hint, not a diagnosis.",
        "page": "<i>Part {p} of {n}</i>",
        "next": "Next ›",
        "prev": "‹ Back",
        "done": "Done ✓",
        "picked": "Ticked: {n}",
        "result_top": "Most of your ticks fall on this channel: <b>{name}</b>. It is a good place to begin.",
        "your_signs": "What you ticked for this channel:",
        "first_point": "First point: <b>{point}</b>. {why}",
        "also": "Also standing out: {names}.",
        "none": "Nothing is ticked. Then begin with the channel next on the path: <b>{name}</b>.",
        "none_bare": "Nothing is ticked.",
        "note": "This is a hint for getting to know the channels, not a diagnosis. If something worries you "
                "seriously or does not go away, see a doctor.",
        "start": "▶️ Start with this channel",
        "continue": "▶️ Continue this channel",
        "path_kept": "🧭 Your step-by-step path stays on: after this channel the bot moves on to <b>{name}</b>.",
        "path_kept_last": "🧭 Your step-by-step path stays on: this is the last channel of the path you have not done yet.",
        "point_btn": "📍 First point: {code}",
        "again": "↻ Take it again",
        "back": "↩ To meridians",
    },
    "uz": {
        "menu": "🧭 Qaysi kanaldan boshlash",
        "title": "<b>🧭 Qaysi kanaldan boshlash</b>",
        "intro": "So'nggi haftalarda sizga xos bo'lganlarini belgilang, xohlagancha. Xabar ostidagi raqamlarni "
                 "bosing. Belgilar qaysi kanal boshqalardan ko'proq javob berishini ko'rsatadi: tanishuvni "
                 "undan boshlash qulay. Bu maslahat, tashxis emas.",
        "page": "<i>{n} qismdan {p}-qism</i>",
        "next": "Keyingi ›",
        "prev": "‹ Orqaga",
        "done": "Tayyor ✓",
        "picked": "Belgilangan: {n}",
        "result_top": "Belgilaringizning ko'pi shu kanalga to'g'ri keldi: <b>{name}</b>. Undan boshlash qulay.",
        "your_signs": "U bo'yicha belgilaringiz:",
        "first_point": "Birinchi nuqta: <b>{point}</b>. {why}",
        "also": "Yana javob beradi: {names}.",
        "none": "Hech narsa belgilanmadi. Unda yo'l tartibidagi kanaldan boshlang: <b>{name}</b>.",
        "none_bare": "Hech narsa belgilanmadi.",
        "note": "Bu kanallar bilan tanishish uchun maslahat, tashxis emas. Biror narsa jiddiy bezovta qilsa "
                "yoki uzoq o'tmasa, shifokorga murojaat qiling.",
        "start": "▶️ Shu kanaldan boshlash",
        "continue": "▶️ Shu kanalni davom ettirish",
        "path_kept": "🧭 Tartibli yo'l saqlanadi: shu kanaldan keyin bot <b>{name}</b> kanaliga o'tadi.",
        "path_kept_last": "🧭 Tartibli yo'l saqlanadi: bu yo'lning siz hali o'tmagan oxirgi kanali.",
        "point_btn": "📍 Birinchi nuqta: {code}",
        "again": "↻ Qaytadan o'tish",
        "back": "↩ Meridianlarga",
    },
    "kz": {
        "menu": "🧭 Қай арнадан бастау керек",
        "title": "<b>🧭 Қай арнадан бастау керек</b>",
        "intro": "Соңғы апталарда сізге тән болғанын белгілеңіз, қалағаныңызша. Хабар астындағы нөмірлерді "
                 "басыңыз. Белгілер қай арна басқаларынан көбірек жауап беретінін көрсетеді: танысуды содан "
                 "бастаған ыңғайлы. Бұл кеңес, диагноз емес.",
        "page": "<i>{n} бөліктің {p}-бөлігі</i>",
        "next": "Әрі қарай ›",
        "prev": "‹ Артқа",
        "done": "Дайын ✓",
        "picked": "Белгіленді: {n}",
        "result_top": "Белгілеріңіздің көбі мына арнаға түсті: <b>{name}</b>. Содан бастаған ыңғайлы.",
        "your_signs": "Ол бойынша белгілеріңіз:",
        "first_point": "Бірінші нүкте: <b>{point}</b>. {why}",
        "also": "Тағы жауап береді: {names}.",
        "none": "Ештеңе белгіленбеді. Онда жол ретіндегі арнадан бастаңыз: <b>{name}</b>.",
        "none_bare": "Ештеңе белгіленбеді.",
        "note": "Бұл арналармен танысуға арналған кеңес, диагноз емес. Бірдеңе қатты мазаласа немесе ұзақ "
                "басылмаса, дәрігерге қаралыңыз.",
        "start": "▶️ Осы арнадан бастау",
        "continue": "▶️ Осы арнаны жалғастыру",
        "path_kept": "🧭 Ретімен жүретін жол сақталады: осы арнадан кейін бот <b>{name}</b> арнасына өтеді.",
        "path_kept_last": "🧭 Ретімен жүретін жол сақталады: бұл жолдың сіз әлі өтпеген соңғы арнасы.",
        "point_btn": "📍 Бірінші нүкте: {code}",
        "again": "↻ Қайта өту",
        "back": "↩ Меридиандарға",
    },
}


def text(key: str, language: str, **kw: Any) -> str:
    value = TEXTS.get(language, TEXTS["en"]).get(key) or TEXTS["en"][key]
    return value.format(**kw) if kw else value


def _load(name: str) -> Dict[str, Any]:
    try:
        return json.loads((ASSETS / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_CACHE: Dict[str, Any] = {}


def _data() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if "check" not in _CACHE:
        _CACHE["check"] = _load("self_check.json")
        _CACHE["profiles"] = _load("meridian_profiles.json").get("channels", {})
    return _CACHE["check"], _CACHE["profiles"]


def _profile_text(profiles: Dict[str, Any], channel: str, language: str) -> Dict[str, Any]:
    i18n = (profiles.get(channel) or {}).get("i18n") or {}
    return i18n.get(language) or i18n.get("en") or i18n.get("ru") or {}


def questions(language: str) -> List[Dict[str, Any]]:
    """[{ch, also, text}] in the order of self_check.json; items whose text is missing are left out."""
    check, profiles = _data()
    out = []
    for q in check.get("questions", []):
        items = _profile_text(profiles, q.get("ch"), language).get("imbalance") or []
        i = q.get("i", -1)
        if 0 <= i < len(items):
            out.append({"ch": q["ch"], "also": list(q.get("also") or []), "text": items[i]})
    return out


def picked_indices(mask: int, total: int) -> List[int]:
    return [i for i in range(total) if mask >> i & 1]


def score(mask: int, qs: List[Dict[str, Any]]) -> List[Tuple[str, int, int, List[int]]]:
    """Channels with ticks, best first: (channel, score, own ticks, own question indices).

    Ties go to more own ticks, then to the channel asked about first."""
    check, _ = _data()
    own_w, also_w = int(check.get("own", 2)), int(check.get("also_weight", 1))
    table: Dict[str, List[Any]] = {}
    first: Dict[str, int] = {}
    for i, q in enumerate(qs):
        first.setdefault(q["ch"], i)
        if not mask >> i & 1:
            continue
        row = table.setdefault(q["ch"], [0, 0, []])
        row[0] += own_w
        row[1] += 1
        row[2].append(i)
        for other in q["also"]:
            table.setdefault(other, [0, 0, []])[0] += also_w
    ranked = sorted(table.items(), key=lambda kv: (-kv[1][0], -kv[1][1], first.get(kv[0], 99)))
    return [(ch, s, n, idx) for ch, (s, n, idx) in ranked if s > 0]


def start_info(channel: str, language: str) -> Tuple[Optional[str], str]:
    """(map code of the point to begin with, why it is a good start) from meridian_profiles.json."""
    _, profiles = _data()
    p = profiles.get(channel) or {}
    return p.get("start_code"), _profile_text(profiles, channel, language).get("start_why", "")


# ---------------------------------------------------------------- bot screens

def pages(total: int) -> int:
    return max(1, (total + PER_PAGE - 1) // PER_PAGE)


def page_screen(page: int, mask: int, language: str) -> Tuple[str, List[List[InlineKeyboardButton]]]:
    qs = questions(language)
    n_pages = pages(len(qs))
    page = min(max(page, 0), n_pages - 1)
    lo, hi = page * PER_PAGE, min(len(qs), (page + 1) * PER_PAGE)
    lines = [text("title", language), "", text("intro", language), "", text("page", language, p=page + 1, n=n_pages), ""]
    for i in range(lo, hi):
        mark = "✅ " if mask >> i & 1 else ""
        lines.append(f"{mark}<b>{i + 1}.</b> {qs[i]['text']}")
    picked = len(picked_indices(mask, len(qs)))
    if picked:
        lines += ["", text("picked", language, n=picked)]
    rows: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for i in range(lo, hi):
        label = f"✅ {i + 1}" if mask >> i & 1 else str(i + 1)
        row.append(InlineKeyboardButton(label, callback_data=f"{PREFIX}t:{page}:{mask}:{i}"))
        if len(row) == PER_ROW:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text("prev", language), callback_data=f"{PREFIX}p:{page - 1}:{mask}"))
    if page < n_pages - 1:
        nav.append(InlineKeyboardButton(text("next", language), callback_data=f"{PREFIX}p:{page + 1}:{mask}"))
    else:
        nav.append(InlineKeyboardButton(text("done", language), callback_data=f"{PREFIX}r:{mask}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text("back", language), callback_data="meridian_main")])
    return "\n".join(lines), rows


def parse_callback(data: str) -> Optional[Tuple[str, int, int, int]]:
    """("start" | "toggle" | "page" | "result", page, mask, question index) of a self-check button."""
    if not data.startswith(PREFIX):
        return None
    head, _, rest = data[len(PREFIX):].partition(":")
    parts = rest.split(":") if rest else []
    try:
        nums = [int(x) for x in parts]
    except ValueError:
        return None
    if any(x < 0 or x >= 1 << 30 for x in nums):
        return None
    if head == "" and not nums:
        return "start", 0, 0, -1
    if head == "t" and len(nums) == 3 and nums[2] < len(_data()[0].get("questions", [])):
        return "toggle", nums[0], nums[1] ^ (1 << nums[2]), nums[2]
    if head == "p" and len(nums) == 2:
        return "page", nums[0], nums[1], -1
    if head == "r" and len(nums) == 1:
        return "result", 0, nums[0], -1
    return None


def result_screen(
    mask: int,
    language: str,
    meridians_manager: "MeridiansManager",
    point_lookup: Dict[str, Tuple[str, int, Dict[str, Any]]],
    point_title: Callable[[Dict[str, Any], str], str],
    channel_name: Callable[[str, str], str],
    fallback_channel: Optional[str],
    current_channel: Optional[str] = None,
) -> Tuple[str, List[List[InlineKeyboardButton]], Optional[str]]:
    """Text, buttons and the suggested channel id of the result."""
    qs = questions(language)
    mask &= (1 << len(qs)) - 1
    # a channel reached only through "also" never comes first (the map does the same)
    ranked = [r for r in score(mask, qs) if r[2] and meridians_manager.get_meridian_by_id(r[0])]
    lines = [text("title", language), ""]
    if ranked:
        top, _, _, own_idx = ranked[0]
        lines.append(text("result_top", language, name=channel_name(top, language)))
        if own_idx:
            lines += ["", text("your_signs", language)] + [f"• {qs[i]['text']}" for i in own_idx]
    else:
        top = fallback_channel
        lines.append(text("none", language, name=channel_name(top, language)) if top else text("none_bare", language))
    rows: List[List[InlineKeyboardButton]] = []
    if top:
        code, why = start_info(top, language)
        hit = point_lookup.get(code or "")
        if hit and hit[0] == top:
            lines += ["", text("first_point", language, point=point_title(hit[2], language), why=why).strip()]
            # the same caution lines as the point card (GI4 is not pressed in pregnancy)
            lines += [f"⚠️ {line}" for line in point_caution_lines(code or "", language)]
        others = [channel_name(ch, language) for ch, s, n, _ in ranked[1:3] if n]
        if others:
            lines += ["", text("also", language, names=", ".join(others))]
        key = "continue" if current_channel == top else "start"
        rows.append([InlineKeyboardButton(text(key, language), callback_data="meridian_current" if key == "continue" else f"meridian_select:{top}")])
        if hit and hit[0] == top:
            rows.append([InlineKeyboardButton(
                text("point_btn", language, code=hit[2].get("code") or code), callback_data=f"meridian_point:{top}:{hit[1]}"
            )])
    lines += ["", f"<i>{text('note', language)}</i>"]
    rows.append([InlineKeyboardButton(text("again", language), callback_data=PREFIX)])
    rows.append([InlineKeyboardButton(text("back", language), callback_data="meridian_main")])
    return "\n".join(lines), rows, top
