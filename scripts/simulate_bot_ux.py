"""Generate an interactive local simulator for the bot's main UX flows.

The simulator is intentionally lightweight: it does not talk to Telegram and
does not import bot handlers. Instead it renders the same texts and content
data, then models the critical user journeys in a browser.
"""

from __future__ import annotations

import argparse
import ast
import json
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
        f"<b>{labels[1]}:</b> {escape(point_i18n.get('location', ''))}",
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

    const state = {{
      language: 'ru',
      screen: 'onboarding',
      principlesEnabled: true,
      meridiansEnabled: false,
      learningMode: null,
      currentMeridianId: 'conception_vessel',
      currentPointIndex: -1,
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
    function show(title, html, buttons) {{
      screenName.textContent = title;
      bubble.innerHTML = html;
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
        [{{ label: t('current_meridian'), action: () => setScreen('currentMeridian') }}, {{ label: t('select_meridian'), action: () => setScreen('chooseMeridian') }}],
        [{{ label: t('meridian_measurements'), action: () => setScreen('measurements') }}],
        [{{ label: t('meridian_change_path'), action: () => setScreen('meridianPath') }}],
        [{{ label: t('back_to_menu'), action: () => setScreen('main') }}],
      ]);
    }}

    function renderMeridianPath() {{
      show('Path', fmt(t('meridian_mode_menu')), [
        [{{ label: t('meridian_guided_path'), action: () => {{ state.learningMode = 'guided'; state.currentMeridianId = firstReadyMeridian().id; setScreen('currentMeridian'); }} }}],
        [{{ label: t('meridian_free_choice'), action: () => {{ state.learningMode = 'free'; setScreen('chooseMeridian'); }} }}],
        [{{ label: t('back_to_menu'), action: () => setScreen('main') }}],
      ]);
    }}

    function renderCurrentMeridian() {{
      const item = meridian();
      const html = state.currentPointIndex >= 0 && item.points[state.currentPointIndex]
        ? item.points[state.currentPointIndex].detail[state.language]
        : item.intro[state.language];
      show('Current focus', html, [
        [{{ label: t('prev_point'), action: prevPoint, disabled: item.pointsCount === 0 }}, {{ label: t('next_point'), action: nextPoint, disabled: item.pointsCount === 0 }}],
        [{{ label: t('all_points'), action: () => setScreen('allPoints'), disabled: item.pointsCount === 0 }}, {{ label: t('complete_meridian'), action: completeMeridian }}],
        [{{ label: t('meridian_back'), action: () => setScreen('meridians') }}],
      ]);
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
      const buttons = item.points.map((point, index) => [{{ label: `${{index + 1}}. ${{point.code}} ${{point.names[state.language]}}`, action: () => {{ state.currentPointIndex = index; setScreen('currentMeridian'); }} }}]);
      buttons.push([{{ label: t('meridian_back'), action: () => setScreen('currentMeridian') }}]);
      show('All points', `<b>${{t('all_points')}}</b>`, buttons);
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
        state.currentMeridianId = firstReadyMeridian().id;
        state.currentPointIndex = 0;
        state.screen = 'currentMeridian';
      }} else if (scenario === 'meridians') {{
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
    args = parser.parse_args()
    render(ROOT / args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
