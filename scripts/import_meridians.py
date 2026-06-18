import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MERIDIANS_FILE = ROOT / "bot" / "meridians.json"
IMAGE_DIR = ROOT / "images" / "meridians"
HEADERS = {"User-Agent": "Mozilla/5.0 Journey of Ascension content importer"}


LANG_META = {
    "en": {
        "focus": "Rest attention on this point for 3-5 minutes. Notice warmth, pressure, pulsation, emptiness, thoughts, or images without forcing a result.",
        "question": "What changes when attention rests here: sensation, breath, mood, thought flow, or inner imagery?",
        "source_location": "Source location",
        "source_note": "Classical note",
    },
    "ru": {
        "focus": "Удерживайте внимание на этой точке 3-5 минут. Наблюдайте тепло, давление, пульсацию, пустоту, мысли или образы без усилия получить результат.",
        "question": "Что меняется, когда внимание находится здесь: ощущение, дыхание, настроение, поток мыслей или внутренние образы?",
        "source_location": "Расположение",
        "source_note": "Классическое примечание",
    },
    "uz": {
        "focus": "Diqqatni ushbu nuqtada 3-5 daqiqa ushlab turing. Iliqlik, bosim, pulsatsiya, bo'shliq, fikrlar yoki obrazlarni majburlamasdan kuzating.",
        "question": "Diqqat shu yerda turganda nima o'zgaradi: sezgi, nafas, kayfiyat, fikr oqimi yoki ichki obrazlar?",
        "source_location": "Manbadagi joylashuv",
        "source_note": "Klassik izoh",
    },
    "kz": {
        "focus": "Зейінді осы нүктеде 3-5 минут ұстаңыз. Жылуды, қысымды, соғуды, бос кеңістікті, ойларды немесе бейнелерді күш салмай бақылаңыз.",
        "question": "Зейін осында тұрғанда не өзгереді: сезім, тыныс, көңіл күй, ой ағымы немесе ішкі бейнелер?",
        "source_location": "Дереккөздегі орналасуы",
        "source_note": "Классикалық түсіндірме",
    },
}


MERIDIANS = [
    {
        "id": "governing_vessel",
        "category_id": 29,
        "source_url": "https://shiyanbin.ru/zadnesredinnyj-meridian-vg/",
        "active_time": "-",
        "passive_time": "-",
        "names": {
            "en": "Governing Vessel",
            "ru": "Заднесрединный меридиан",
            "uz": "Orqa o'rta meridian",
            "kz": "Артқы орта меридиан",
        },
        "direction": {
            "en": "Along the posterior midline: from the perineum upward through the spine, neck, head, and face.",
            "ru": "По задней срединной линии: от промежности вверх через позвоночник, шею, голову и лицо.",
            "uz": "Orqa o'rta chiziq bo'ylab: oraliq sohasidan umurtqa, bo'yin, bosh va yuz orqali yuqoriga.",
            "kz": "Артқы орта сызық бойымен: аралық аймағынан омыртқа, мойын, бас және бет арқылы жоғары.",
        },
        "intro": {
            "en": "The Governing Vessel is used here as a map for observing the back midline and the vertical axis of attention.",
            "ru": "Заднесрединный меридиан здесь используется как карта наблюдения задней срединной линии и вертикальной оси внимания.",
            "uz": "Orqa o'rta meridian bu yerda orqa o'rta chiziq va diqqatning vertikal o'qini kuzatish xaritasi sifatida ishlatiladi.",
            "kz": "Артқы орта меридиан бұл жерде артқы орта сызықты және зейіннің тік осін бақылау картасы ретінде қолданылады.",
        },
        "practice": {
            "en": "Sit upright, relax the jaw and spine, and let attention rise slowly along the back midline without strain.",
            "ru": "Сядьте ровно, расслабьте челюсть и позвоночник, затем мягко ведите внимание вверх по задней срединной линии без напряжения.",
            "uz": "Tik o'tiring, jag' va umurtqani bo'shating, keyin diqqatni orqa o'rta chiziq bo'ylab zo'riqmasdan yuqoriga olib boring.",
            "kz": "Тік отырыңыз, жақ пен омыртқаны босатыңыз, содан кейін зейінді артқы орта сызық бойымен күш салмай жоғары жүргізіңіз.",
        },
    },
    {
        "id": "conception_vessel",
        "category_id": 30,
        "source_url": "https://shiyanbin.ru/perednesredinnyj-meridian-vs/",
        "active_time": "-",
        "passive_time": "-",
        "names": {
            "en": "Conception Vessel",
            "ru": "Переднесрединный меридиан",
            "uz": "Old o'rta meridian",
            "kz": "Алдыңғы орта меридиан",
        },
        "direction": {
            "en": "Along the anterior midline: from the perineum upward through the abdomen, chest, throat, and face.",
            "ru": "По передней срединной линии: от промежности вверх через живот, грудь, горло и лицо.",
            "uz": "Old o'rta chiziq bo'ylab: oraliq sohasidan qorin, ko'krak, tomoq va yuz orqali yuqoriga.",
            "kz": "Алдыңғы орта сызық бойымен: аралық аймағынан іш, кеуде, тамақ және бет арқылы жоғары.",
        },
        "intro": {
            "en": "The Conception Vessel is used here as a map for observing the front midline, breath, abdomen, chest, and throat.",
            "ru": "Переднесрединный меридиан здесь используется как карта наблюдения передней срединной линии, дыхания, живота, груди и горла.",
            "uz": "Old o'rta meridian bu yerda old o'rta chiziq, nafas, qorin, ko'krak va tomoqni kuzatish xaritasi sifatida ishlatiladi.",
            "kz": "Алдыңғы орта меридиан бұл жерде алдыңғы орта сызықты, тынысты, ішті, кеудені және тамақты бақылау картасы ретінде қолданылады.",
        },
        "practice": {
            "en": "Sit calmly, soften the abdomen and chest, and let attention move along the front midline with natural breathing.",
            "ru": "Сядьте спокойно, смягчите живот и грудь, затем ведите внимание по передней срединной линии вместе с естественным дыханием.",
            "uz": "Sokin o'tiring, qorin va ko'krakni yumshating, keyin diqqatni tabiiy nafas bilan old o'rta chiziq bo'ylab olib boring.",
            "kz": "Тыныш отырыңыз, іш пен кеудені жұмсартыңыз, содан кейін зейінді табиғи тыныспен алдыңғы орта сызық бойымен жүргізіңіз.",
        },
    },
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=35) as response:
        return response.read().decode("utf-8", errors="replace")


def strip_tags(value: str) -> str:
    value = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"</p\s*>", "\n", value, flags=re.I)
    value = re.sub(r"</div\s*>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value).replace("\xa0", " ")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    return re.sub(r"\n\s*\n+", "\n", value).strip()


def clean_text(value: str, max_len: int = 520) -> str:
    value = re.sub(r"\s+", " ", strip_tags(value)).strip(" -–—;,.")
    if len(value) <= max_len:
        return value
    cut = value[:max_len]
    for sep in [". ", "; ", ", "]:
        pos = cut.rfind(sep)
        if pos > 160:
            return cut[: pos + 1].strip()
    return cut.strip() + "..."


def section_after(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        pattern = rf"<b>\s*{re.escape(label)}\s*:?\s*</b>([\s\S]*?)(?=<b>|<div class=\"youtube|<iframe|</td>)"
        match = re.search(pattern, text, flags=re.I)
        if match:
            return clean_text(match.group(1), 760)
    return ""


def point_entries(category_html: str) -> list[tuple[str, str]]:
    entries = re.findall(r'<div class="eTitle"[^>]*>\s*<a href="([^"]+)">([^<]+)</a>', category_html, flags=re.I)
    result = []
    for href, title in entries:
        title = clean_text(title, 140)
        match = re.match(r"^([A-ZА-Я]{1,3})\s*(\d+)\s+(.+?)(?:\s*\(([^)]+)\))?$", title, flags=re.I)
        if not match:
            continue
        code = f"{match.group(1).upper()}{match.group(2)}".replace(".", "")
        name = match.group(3).strip()
        alt_code = match.group(4).strip() if match.group(4) else ""
        result.append((urllib.parse.urljoin("https://www.eledia.ru/", href), code, name, alt_code))
    return result


def get_image_url(point_html: str) -> str | None:
    body_match = re.search(r'<td class="eText"[\s\S]*?</td>', point_html, flags=re.I)
    body = body_match.group(0) if body_match else point_html
    candidates = re.findall(r'<a[^>]+href="([^"]+\.(?:jpg|jpeg|png|gif))"[^>]*>\s*<img', body, flags=re.I)
    candidates += re.findall(r'<img[^>]+src="([^"]+\.(?:jpg|jpeg|png|gif))"', body, flags=re.I)
    candidates += re.findall(r'"(https://(?:www\.)?eledia\.ru/[^"]+\.(?:jpg|jpeg|png|gif))"', point_html, flags=re.I)
    for src in candidates:
        low = src.lower()
        if any(skip in low for skip in ["avatar", "icon", "counter", "watch", "thumb", "logo"]):
            continue
        return urllib.parse.urljoin("https://www.eledia.ru/", src)
    return None


def kiberis_image_url(code: str) -> str | None:
    try:
        search_html = fetch(f"https://kiberis.ru/?s={urllib.parse.quote(code)}")
        match = re.search(r'href="(\?p=\d+&a=\d+)"', search_html)
        if not match:
            return None
        point_html = fetch(urllib.parse.urljoin("https://kiberis.ru/", match.group(1)))
        image = re.search(r'contentUrl"?\s*[:=]\s*"([^"]+\.(?:jpg|png|gif))"', point_html, flags=re.I)
        if image:
            return urllib.parse.urljoin("https://kiberis.ru/", image.group(1))
    except Exception:
        return None
    return None


def download_image(url: str | None, filename: str) -> str | None:
    if not url:
        return None
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower() or ".jpg"
    target = IMAGE_DIR / f"{filename}{ext}"
    if target.exists() and target.stat().st_size > 0:
        return target.name
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=35) as response:
            data = response.read()
        if data and len(data) > 500:
            target.write_bytes(data)
            return target.name
    except Exception as exc:
        print(f"image failed {url}: {exc}")
    return None


def make_point_i18n(ru_name: str, classification: str, name_note: str, location: str) -> dict:
    result = {}
    for lang, meta in LANG_META.items():
        meaning = " ".join(part for part in [classification, name_note] if part)
        if lang == "ru":
            result[lang] = {
                "name": ru_name,
                "location": location or "Расположение будет уточнено после сверки источников.",
                "meaning": meaning,
                "meditation_instruction": meta["focus"],
                "observation_question": meta["question"],
            }
        else:
            result[lang] = {
                "name": ru_name,
                "location": f"{meta['source_location']}: {location}" if location else f"{meta['source_location']}: pending source refinement.",
                "meaning": f"{meta['source_note']}: {meaning}" if meaning else "",
                "meditation_instruction": meta["focus"],
                "observation_question": meta["question"],
            }
    return result


def build_meridian(meta: dict) -> dict:
    category_url = f"https://www.eledia.ru/publ/{meta['category_id']}"
    print(f"fetch {meta['id']} from {category_url}", flush=True)
    category_html = fetch(category_url)
    time.sleep(0.2)
    shiyanbin_html = fetch(meta["source_url"])
    time.sleep(0.2)

    intro_ru_source = first_meaningful_paragraph(shiyanbin_html)
    points = []
    for point_url, code, ru_name, alt_code in point_entries(category_html):
        try:
            point_html = fetch(point_url)
            time.sleep(0.08)
        except Exception as exc:
            print(f"point failed {point_url}: {exc}")
            point_html = ""
        classification = section_after(point_html, ("Классификация",))
        name_note = section_after(point_html, ("Название",))
        location = section_after(point_html, ("Локализация", "Расположение"))
        image_url = get_image_url(point_html) or kiberis_image_url(code)
        image_name = download_image(image_url, f"{meta['id']}_{code}")
        points.append(
            {
                "code": code,
                "alt_code": alt_code,
                "source_url": point_url,
                "image": image_name,
                "i18n": make_point_i18n(ru_name, classification, name_note, location),
            }
        )

    i18n = {}
    for lang in ("en", "ru", "uz", "kz"):
        description = meta["intro"][lang]
        if lang == "ru" and intro_ru_source:
            description = f"{description} {intro_ru_source}"
        i18n[lang] = {
            "name": meta["names"][lang],
            "description": description,
            "direction": meta["direction"][lang],
            "intro_practice": meta["practice"][lang],
        }

    print(f"  points: {len(points)}", flush=True)
    return {
        "id": meta["id"],
        "active_time": meta["active_time"],
        "passive_time": meta["passive_time"],
        "source_url": meta["source_url"],
        "points_source_url": category_url,
        "i18n": i18n,
        "points": points,
    }


def first_meaningful_paragraph(text: str) -> str:
    body_match = re.search(r"<h1[^>]*>[\s\S]*?</h1>([\s\S]*?)(?:<h2|</article>|</main>)", text, flags=re.I)
    body = body_match.group(1) if body_match else text
    paragraphs = [clean_text(p, 420) for p in re.findall(r"<p[^>]*>([\s\S]*?)</p>", body, flags=re.I)]
    paragraphs = [p for p in paragraphs if len(p) > 70 and "cookie" not in p.lower()]
    return paragraphs[0] if paragraphs else ""


def merge_meridians(new_items: list[dict]) -> None:
    if MERIDIANS_FILE.exists():
        data = json.loads(MERIDIANS_FILE.read_text(encoding="utf-8"))
    else:
        data = {"meridians": []}

    by_id = {item["id"]: item for item in data.get("meridians", [])}
    for item in new_items:
        by_id[item["id"]] = item

    existing_order = [item["id"] for item in data.get("meridians", []) if item["id"] in by_id]
    for item in new_items:
        if item["id"] not in existing_order:
            existing_order.append(item["id"])
    merged = [by_id[item_id] for item_id in existing_order]
    MERIDIANS_FILE.write_text(json.dumps({"meridians": merged}, ensure_ascii=False, indent=2), encoding="utf-8")


def import_meridians(selected_ids: set[str] | None = None) -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    selected = [item for item in MERIDIANS if selected_ids is None or item["id"] in selected_ids]
    if not selected:
        allowed = ", ".join(item["id"] for item in MERIDIANS)
        raise SystemExit(f"No matching meridians. Allowed: {allowed}")
    merge_meridians([build_meridian(item) for item in selected])
    print(f"done {len(selected)} meridians")


if __name__ == "__main__":
    ids = set(sys.argv[1:]) or None
    import_meridians(ids)
