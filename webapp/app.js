import * as THREE from 'three';
import { MeridianScene, reducedMotion } from './scene3d.js';
import { loadData, loadPoseContent, isActiveNow, activeChannelNow, hh, ASSET_VERSION } from './data.js';
import {
  CLOCK_ORDER, PALETTE, TRANSITIONS, SHORT, FLOW_SHORT, POSE_GROUP, ASANA_ORDER, MUDRA_ORDER, ARM_ORDER, normalizeCode, MIDLINE_IDS, VESSEL_IDS,
} from './channels.js';
import { makeT, normalizeLang, LANGS } from './i18n.js';

const tg = window.Telegram?.WebApp;
const params = new URLSearchParams(location.search);
const startTokens = parseStartParam(tg?.initDataUnsafe?.start_param || params.get('tgWebAppStartParam') || '');

const store = {
  get(key, def) { try { const v = localStorage.getItem(`m3d-${key}`); return v == null ? def : JSON.parse(v); } catch { return def; } },
  set(key, val) {
    try { localStorage.setItem(`m3d-${key}`, JSON.stringify(val)); } catch { /* storage blocked */ }
    try { if (tg?.isVersionAtLeast?.('6.9')) tg.CloudStorage.setItem(key, JSON.stringify(val)); } catch { /* old client */ }
  },
};

// the bot opens the map with the language its messages go out in (?lang=); a language picked in the map menu
// reloads the page with that ?lang= and lasts only until the map is closed, so every open from the bot is in its language
const LANG = normalizeLang(params.get('lang') || startTokens.l || tg?.initDataUnsafe?.user?.language_code || 'ru');
const LANG_NAMES = { ru: 'Русский', en: 'English', uz: "O'zbek", kz: 'Қазақ' };
// practice progress the bot puts into the button URL: meridian in work, point reached (0-based), finished meridians
const PROGRESS = {
  m: params.get('pm') || null,
  p: /^\d+$/.test(params.get('pi') || '') ? Number(params.get('pi')) : -1,
  done: new Set((params.get('pd') || '').split(',').filter(Boolean)),
};
const t = makeT(LANG);
const EDIT = params.get('edit') === '1';
const SPECIAL_CATS = new Set(['jing_well', 'ying_spring', 'shu_stream', 'jing_river', 'he_sea', 'yuan', 'luo', 'great_luo', 'mu', 'back_shu', 'confluent']);
const BADGE_ORDER = ['transition', 'confluent', 'great_luo', 'luo', 'jing_well', 'ying_spring', 'shu_stream', 'jing_river', 'he_sea', 'yuan', 'mu', 'back_shu', 'xi'];

function parseStartParam(sp) {
  const out = {};
  for (const tok of String(sp).split('__')) {
    const m = /^([a-z])_(.+)$/.exec(tok);
    if (m) out[m[1]] = m[2];
  }
  return out;
}

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const richText = (s) => esc(s).replace(/&lt;(\/?)(b|i)&gt;/g, '<$1$2>');

// ---------------------------------------------------------------- state

// background photos (styles.css .backdrop[data-photo]): the author's two of Kailash, the rest from Wikimedia
// Commons under CC0 / public domain (see webapp/assets/PHOTOS.md)
const SCENERY = ['k1', 'k2', 'pyramids', 'altai', 'tianshan', 'stonehenge'];

const state = {
  data: null,
  channelById: new Map(),
  level: { view: 'home' },
  overlay: null, // 'list' | 'poses'
  sheet: 'peek',
  flowAuto: store.get('flow_auto', true),
  flowSlow: store.get('flow_slow', false),
  luoOn: store.get('luo_links', true),
  // one of SCENERY (photos behind the figure) or 'off'; older builds stored a boolean
  scenery: ((v) => (v === false ? 'off' : ([...SCENERY, 'off'].includes(v) ? v : 'k1')))(store.get('scenery', 'k1')),
  special: false,
  expanded: new Set(),
  body: ({ f: 'female', m: 'male' })[params.get('body') || startTokens.b] || store.get('body', 'female'),
  pose: 'stand',
  mudra: 'open',
  posesTab: 'asanas',
  poseContent: null,
  lastTouch: performance.now(),
  autoPaused: false,
  nextShown: false,
  multiSet: new Set(),
};

let scene = null;
const $ = (id) => document.getElementById(id);
const els = {
  sheet: $('sheet'), peek: $('sheetPeek'), body: $('sheetBody'), chips: $('chips'), labels: $('labels'),
  pick: $('pickChips'), tooltip: $('tooltip'), next: $('nextChip'), toast: $('toast'), fabs: $('fabs'), shade: $('shade'),
};

const theme = () => (tg?.colorScheme || (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
const color = (id) => PALETTE[theme()][id] || '#888';
const shortName = (id) => SHORT[LANG][id] || id;
const fullName = (id) => {
  const ch = state.channelById.get(id);
  return ch?.meta?.name || ch?.text?.name || shortName(id);
};
// English and Uzbek show the pinyin (the API gave a Palladius latinisation: GI11 "Cyuy-Chi" for Quchi,
// TCM council); Russian and Kazakh keep the Cyrillic names
const pointName = (code) => ((LANG === 'en' || LANG === 'uz') && state.data.pointNames?.[code]?.pinyin) || state.data.pointInfo.get(code)?.name || '';
// channel groups that can be highlighted all at once (chips at the start of the row)
const YIN = new Set(['lung', 'spleen', 'heart', 'kidney', 'pericardium', 'liver']);
const GROUPS = {
  regular: CLOCK_ORDER,
  yin: CLOCK_ORDER.filter((id) => YIN.has(id)),
  yang: CLOCK_ORDER.filter((id) => !YIN.has(id)),
  extra: [...MIDLINE_IDS, ...VESSEL_IDS],
};
// the yang channels run mostly over the back and the sides, the yin ones over the front
const GROUP_VIEW = { yang: 'back' };
const groupIds = (id) => (id === 'custom' ? [...state.multiSet] : (GROUPS[id] || [])).filter((c) => state.channelById.has(c));
const inCustom = () => state.level.view === 'group' && state.level.id === 'custom';

// "several": channels chosen one by one (chips or lines on the body) are highlighted together
function toggleCustom(id) {
  if (state.multiSet.has(id)) state.multiSet.delete(id);
  else state.multiSet.add(id);
  haptic();
  setLevel({ view: 'group', id: 'custom' }, { fly: false });
}

// ---------------------------------------------------------------- sheet geometry

// bottom safe area in px: Telegram's own insets or the CSS env() value (home indicator on iPhone)
let safeProbe = null;
function safeBottom() {
  if (!safeProbe) {
    safeProbe = document.createElement('div');
    safeProbe.style.cssText = 'position:fixed;left:0;bottom:0;width:1px;height:env(safe-area-inset-bottom,0px);visibility:hidden;pointer-events:none';
    document.body.appendChild(safeProbe);
  }
  const tgInset = Math.max(tg?.safeAreaInset?.bottom || 0, tg?.contentSafeAreaInset?.bottom || 0);
  return Math.max(tgInset, safeProbe.getBoundingClientRect().height || 0);
}
function peekHeight() {
  // the poses peek (tabs + body switch + cards + one line) is measured: a fixed height cut its header off
  const content = state.overlay === 'poses' ? Math.max(184, 16 + (els.peek.scrollHeight || 0)) : 96;
  return content + safeBottom();
}
function sheetVisible(s = state.sheet) {
  const h = tg?.viewportStableHeight || window.innerHeight;
  if (s === 'peek') return peekHeight();
  if (s === 'half') return Math.round(h * 0.5);
  return h - 64;
}
function viewportInsets() {
  // right: the column of round buttons (44 px + 12 px margin) covered the knees and points (council)
  const right = state.sheet === 'full' || window.innerWidth > 700 ? 0 : 56;
  return { top: 58, bottom: Math.min(sheetVisible(), Math.round(window.innerHeight * 0.5)), right };
}

function setSheet(s, { silent = false } = {}) {
  const prev = state.sheet;
  state.sheet = s;
  els.sheet.dataset.state = s;
  document.documentElement.style.setProperty('--sheet-visible', `${sheetVisible(s)}px`);
  els.shade.classList.toggle('on', s === 'full');
  els.fabs.classList.toggle('hidden', s === 'full');
  if (s === 'full') { hideNext(); pauseFlow('full'); }
  else if (prev === 'full') resumeFlow('full');
  setTimeout(() => scene?.resize(), silent ? 0 : 270);
  updateBackButton();
}

(function sheetDrag() {
  let start = null;
  const begin = (e) => {
    if (e.button > 0) return;
    if (state.sheet === 'full' && e.currentTarget === els.body && els.body.scrollTop > 0) return;
    start = { y: e.clientY, x: e.clientX, visible: sheetVisible(), t: performance.now(), moved: false, el: e.currentTarget };
  };
  const move = (e) => {
    if (!start) return;
    const dy = e.clientY - start.y;
    const dx = e.clientX - start.x;
    if (!start.moved) {
      if (Math.abs(dy) < 6 && Math.abs(dx) < 6) return;
      if (start.el === els.body && state.sheet === 'full' && dy < 0) { start = null; return; }
      if (Math.abs(dx) > Math.abs(dy) * 1.7) { start.horizontal = true; }
      start.moved = true;
      els.sheet.classList.add('dragging');
    }
    if (start.horizontal) return;
    const vis = THREE.MathUtils.clamp(start.visible - dy, peekHeight() * 0.85, (tg?.viewportStableHeight || window.innerHeight) - 64);
    document.documentElement.style.setProperty('--sheet-visible', `${vis}px`);
  };
  const end = (e) => {
    if (!start) return;
    els.sheet.classList.remove('dragging');
    const dy = e.clientY - start.y;
    const dx = e.clientX - start.x;
    const s0 = start;
    start = null;
    if (!s0.moved) return;
    if (s0.horizontal) {
      if (Math.abs(dx) > 48 && state.level.view === 'point' && s0.el !== els.body) stepPoint(dx < 0 ? 1 : -1);
      return;
    }
    const vel = dy / Math.max(1, performance.now() - s0.t);
    const vis = s0.visible - dy;
    const order = ['peek', 'half', 'full'];
    let idx = order.indexOf(state.sheet);
    if (vel < -0.5) idx = Math.min(2, idx + 1);
    else if (vel > 0.5) idx = Math.max(0, idx - 1);
    else idx = order.reduce((best, s, i) => (Math.abs(sheetVisible(s) - vis) < Math.abs(sheetVisible(order[best]) - vis) ? i : best), 0);
    setSheet(order[idx]);
  };
  for (const el of [$('sheetGrip'), els.peek, els.body]) {
    el.addEventListener('pointerdown', begin);
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
  }
  $('sheetGrip').addEventListener('click', () => setSheet(state.sheet === 'peek' ? 'half' : 'peek'));
})();

// ---------------------------------------------------------------- toast, next chip

let toastTimer = null;
function toast(text, ms = 3000) {
  els.toast.textContent = text;
  els.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { els.toast.hidden = true; }, ms);
}
function hideNext() { els.next.hidden = true; state.nextShown = false; }
function showNext(id, label) {
  if (state.sheet === 'full') return;
  els.next.innerHTML = `<span class="dot" style="background:${color(id)}"></span>${esc(label)} ›`;
  els.next.dataset.id = id;
  els.next.hidden = false;
  state.nextShown = true;
}
els.next.addEventListener('click', () => {
  const id = els.next.dataset.id;
  hideNext();
  if (state.channelById.has(id)) selectChannel(id);
});

// ---------------------------------------------------------------- scene selection

function nextChannelOf(id) {
  const tr = TRANSITIONS[id];
  return tr ? state.data.pointOwner.get(tr.to) : null;
}
function prevChannelOf(id) {
  const i = CLOCK_ORDER.indexOf(id);
  return i < 0 ? null : CLOCK_ORDER[(i + 11) % 12];
}

function luoFor(id) {
  if (!state.luoOn) return [];
  const pair = state.channelById.get(id)?.meta?.pair;
  const sel = state.level.view === 'point' ? state.level.code : null;
  return state.data.luoLinks
    .filter((l) => l.to && ((l.meridian === id) || (pair && l.meridian === pair && l.to_meridian === id)))
    .map((l) => ({ from: l.from, to: l.to, color: color(l.to_meridian), strong: sel === l.from }));
}

function crossingsFor(id) {
  const out = new Map();
  for (const [code, c] of state.data.crossings) {
    if (c.confidence && c.confidence !== 'high') continue;
    if (state.data.pointOwner.get(code) !== id) continue;
    const other = (c.meridians || []).find((m) => m !== id && (state.channelById.has(m)));
    if (other) out.set(code, color(other));
  }
  return out;
}

/** "Several" mode: flow, points and the links that show how the chosen channels work together. */
function multiSelection(ids) {
  const set = new Set(ids);
  const visible = new Set();
  const luo = [];
  const seen = new Set();
  const crossings = new Map();
  const nextOf = {};
  for (const id of ids) {
    const ch = state.channelById.get(id);
    if (!ch) continue;
    if (ch.kind === 'vessel') { for (const c of ch.path || []) visible.add(c); continue; }
    for (const c of ch.points) visible.add(c);
    const next = nextChannelOf(id);
    nextOf[id] = next;
    if (ch.link && set.has(next)) visible.add(ch.link.to);
    for (const l of luoFor(id)) {
      const k = `${l.from}>${l.to}`;
      // with several channels only the luo branches between the chosen ones
      if (seen.has(k) || (ids.length > 1 && !set.has(state.data.pointOwner.get(l.to)))) continue;
      seen.add(k);
      luo.push(l);
    }
    for (const [code, c] of crossingsFor(id)) crossings.set(code, c);
  }
  return { flowChannels: ids, visiblePoints: visible, luo, crossings, nextOf };
}
const multiMode = () => inCustom() || (state.level.view === 'point' && !!state.level.multi);

// the hand slot (state.mudra) holds either a mudra or an arm position (arms up, hands behind the head)
const isArmPos = (id = state.mudra) => id !== 'open' && ARM_ORDER.includes(id);
const isMudraOn = () => state.mudra !== 'open' && !isArmPos();
const armItem = (id = state.mudra) => state.poseContent?.arm_positions?.find((x) => x.id === id);

function mudraContacts(m) {
  if (!m || m.id === 'open') return [];
  const pts = m.contact_points || [];
  const fingerColor = (code) => color(state.data.pointOwner.get(code));
  if (m.palm === 'apart_facing' || m.id === 'hakini' || m.id === 'anjali') {
    return pts.flatMap((code) => [1, -1].map((side) => ({ codes: [code], side, color: fingerColor(code) })));
  }
  const fingerPts = pts.filter((c) => state.data.pointOwner.get(c) !== 'conception_vessel');
  return [1, -1].map((side) => ({ codes: fingerPts, side, color: fingerColor(fingerPts[0]) }));
}

function applySelection() {
  const lv = state.level;
  const d = state.data;
  const sel = { level: 'home', highlight: [], flowChannels: [] };
  if (state.overlay === 'poses' && lv.view === 'home') {
    if (isArmPos()) {
      // an arm position shows the channels it opens, like an asana (with the body pose's own ones)
      const a = armItem();
      const b = state.poseContent?.asanas?.find((x) => x.id === state.pose);
      sel.level = 'asana';
      sel.highlight = [...new Set([...(a?.emphasized_meridians || []), ...(b?.emphasized_meridians || [])])];
      sel.visiblePoints = new Set([...(a?.emphasized_points || []), ...(b?.emphasized_points || [])]);
    } else if (state.mudra !== 'open') {
      const m = state.poseContent?.mudras?.find((x) => x.id === state.mudra);
      sel.level = 'mudra';
      sel.highlight = m?.connected_meridians || [];
      sel.flowChannels = sel.highlight.filter((id) => state.channelById.has(id));
      sel.visiblePoints = new Set(m?.contact_points || []);
      sel.contacts = mudraContacts(m);
    } else if (state.pose !== 'stand') {
      const a = state.poseContent?.asanas?.find((x) => x.id === state.pose);
      sel.level = 'asana';
      sel.highlight = a?.emphasized_meridians || [];
      sel.visiblePoints = new Set(a?.emphasized_points || []);
    }
    scene.setSelection(sel);
    return;
  }
  if (lv.view === 'home') {
    const now = activeChannelNow(d.channels);
    if (now) sel.highlight = [now.id];
  } else if (lv.view === 'group') {
    sel.level = 'group';
    sel.highlight = groupIds(lv.id);
    sel.visiblePoints = new Set();
    if (lv.id === 'custom' && sel.highlight.length) Object.assign(sel, multiSelection(sel.highlight));
  } else {
    const ch = state.channelById.get(lv.id);
    if (ch.kind === 'vessel') {
      sel.level = 'vessel';
      sel.vessel = { id: ch.id, path: ch.path, confluent: ch.confluent, coupled: ch.coupled, coupledColor: ch.pairId ? color(ch.pairId) : null };
      sel.flowChannels = [ch.id];
    } else {
      sel.level = lv.view;
      sel.channel = ch.id;
      sel.pair = state.luoOn ? ch.meta?.pair : null;
      sel.flowChannels = [ch.id];
      sel.luo = luoFor(ch.id);
      sel.crossings = crossingsFor(ch.id);
      sel.nextChannel = nextChannelOf(ch.id);
      sel.special = state.special;
      const visible = new Set(ch.points);
      if (ch.link) visible.add(ch.link.to);
      sel.visiblePoints = visible;
      if (lv.multi) {
        // a point opened from "several": the other chosen channels stay lit and flowing
        const ids = [...new Set([...state.multiSet, ch.id])];
        const m = multiSelection(ids);
        sel.highlight = ids;
        sel.flowChannels = ids;
        sel.luo = m.luo;
        sel.nextOf = m.nextOf;
        for (const [k, v] of m.crossings) sel.crossings.set(k, v);
        for (const c of m.visiblePoints) visible.add(c);
      }
      if (lv.view === 'point') {
        sel.point = lv.code;
        sel.side = lv.side || 1;
        const cr = d.crossings.get(lv.code);
        if (cr) sel.fullColor = (cr.meridians || []).filter((m) => state.channelById.has(m));
      }
    }
  }
  scene.setSelection(sel);
}

// ---------------------------------------------------------------- flow control

function flowMode() {
  const lv = state.level;
  if (state.overlay === 'poses' && lv.view === 'home' && isMudraOn()) return 'comet';
  if (lv.view === 'group') return inCustom() && groupIds('custom').length ? 'comet' : null;
  if (lv.view === 'home') return null;
  const ch = state.channelById.get(lv.id);
  if (ch.kind === 'vessel') return ch.id === 'dai_mai' ? 'breath' : 'wave';
  return 'comet';
}

function startFlow({ force = false } = {}) {
  const mode = flowMode();
  if (!mode) return;
  if (!force && (!state.flowAuto || reducedMotion.matches)) { renderPeek(); return; }
  if (state.sheet === 'full' || document.hidden) return;
  state.autoPaused = false;
  scene.startFlow({ mode, slow: state.flowSlow, once: reducedMotion.matches });
  renderPeek();
}
function pauseFlow(reason) {
  if (!scene?.flowPlaying) return;
  state.autoPaused = reason;
  scene.stopFlow();
  setTimeout(renderPeek, 220);
}
function resumeFlow(reason) {
  if (state.autoPaused && (!reason || state.autoPaused === reason) && state.flowAuto) {
    state.autoPaused = false;
    startFlow();
  }
}
function toggleFlow() {
  if (scene.flowPlaying) {
    state.flowAuto = false;
    store.set('flow_auto', false);
    scene.stopFlow();
    setTimeout(renderPeek, 220);
  } else {
    state.flowAuto = true;
    store.set('flow_auto', true);
    startFlow({ force: true });
  }
  renderPeek();
}

// ---------------------------------------------------------------- navigation

function setLevel(level, { fly = true, instant = false } = {}) {
  state.level = level;
  wholeShown = false;
  state.expanded.clear();
  hideNext();
  scene.clearRuler();
  els.pick.hidden = true;
  scene.stopFlow(true);
  applySelection();
  renderChips();
  renderSheet();
  // a new channel or point starts at its top (a point opened from the end of the point list kept the
  // list's scroll and showed the bottom of its card)
  els.body.scrollTop = 0;
  updateBackButton();
  if (EDIT) renderEditbar();
  if (!fly) { setTimeout(startFlow, 150); return; }
  const onEnd = () => setTimeout(startFlow, 150);
  if (level.view === 'home' || level.view === 'group') {
    scene.setView((level.view === 'group' && GROUP_VIEW[level.id]) || 'front', { instant });
    return;
  }
  if (level.view === 'point') {
    level.side = level.side || scene.sideFacingCamera(level.code);
    scene.focusPoint(level.code, level.side, { onEnd, instant, distance: pointDistance(level.code) });
    return;
  }
  frameChannel(state.channelById.get(level.id), onEnd, instant);
}

// camera distance for a point: hands and feet close, the head farther (a head point filled the screen
// and it was unclear where on the body it was, council)
// where on the body a point lies, by its number (WHO ranges), for the search results: VG11 between the
// shoulder blades is not one to press on oneself (UX round 3). null = arm, leg, trunk front: no label
function bodyRegion(code) {
  const m = /^([A-Z]+)(\d+)$/.exec(code);
  if (!m) return null;
  const [, c, s] = m, n = Number(s);
  const inR = (lo, hi) => n >= lo && n <= hi;
  if ((c === 'P' && inR(10, 11)) || (c === 'GI' && inR(1, 5)) || (c === 'C' && inR(7, 9)) || (c === 'IG' && inR(1, 5))
    || (c === 'MC' && inR(7, 9)) || (c === 'TR' && inR(1, 4))) return 'hand';
  if ((c === 'RP' && inR(1, 5)) || (c === 'E' && inR(41, 45)) || (c === 'V' && inR(60, 67)) || (c === 'R' && inR(1, 6))
    || (c === 'F' && inR(1, 4)) || (c === 'VB' && inR(40, 44))) return 'foot';
  if ((c === 'VG' && n >= 16) || (c === 'VB' && inR(1, 20)) || (c === 'V' && inR(1, 10)) || (c === 'E' && inR(1, 9))
    || (c === 'TR' && inR(17, 23)) || (c === 'IG' && inR(17, 19)) || (c === 'GI' && inR(18, 20)) || (c === 'VC' && inR(22, 24))) return 'head';
  if ((c === 'VG' && inR(1, 15)) || (c === 'V' && (inR(11, 35) || inR(41, 54)))) return 'back';
  return null;
}

function pointDistance(code) {
  if (/^(P1[01]|GI[1-5]|C[789]|IG[1-5]|MC[789]|TR[1-4]|RP[1-5]|E4[1-5]|V6[0-7]|R[1-6]|F[1-4]|VB4[0-4])$/.test(code)) return 0.4;
  const pp = scene.pointPosition(code, 1);
  const { center, size } = scene.bodyCenter();
  if (pp && pp.p.y > center.y + size.y * 0.33) return 0.7;
  return 0.5;
}

function frameChannel(ch, onEnd, instant = false) {
  if (!ch) return;
  const dirs = { front: [0, 0.18, 1], back: [0, 0.18, -1], side: [1, 0.12, 0.2] };
  const dir = new THREE.Vector3(...(dirs[ch.view] || dirs.front));
  const box = ch.view === 'side' && ch.bilateral ? scene.channelBox(ch.id, 1) : scene.channelBox(ch.id);
  if (box.isEmpty()) { onEnd?.(); return; }
  scene.frameBox(box, dir, { onEnd, instant, minRadius: 0.15 });
}

function selectChannel(id, opts) {
  if (state.overlay === 'poses') closePoses({ refocus: false });
  searchTrail = null;
  setLevel({ view: 'channel', id }, opts);
  if (store.get('onb_points', false) === false && state.channelById.get(id)?.kind === 'regular') {
    toast(t('hint_points'));
    store.set('onb_points', true);
  }
}

function selectGroup(id) {
  if (state.level.view === 'group' && state.level.id === id) {
    if (id === 'custom') setLevel({ view: 'home' });   // the chip toggles the mode off
    return;
  }
  if (id === 'custom') {
    // start from what is on screen: the open channel, or the whole group being shown
    const lv = state.level;
    if (lv.view === 'point' && lv.multi) { /* back to the chosen set */ }
    else if (lv.view === 'channel' || lv.view === 'point') state.multiSet = new Set([lv.id]);
    else if (lv.view === 'group') state.multiSet = new Set(groupIds(lv.id));
  }
  if (state.overlay === 'poses') closePoses({ refocus: false });
  state.overlay = null;
  setLevel({ view: 'group', id });
  haptic();
}

let searchTrail = null;   // { list: codes, q, inMenu } while points found by a complaint are being looked at
const onTrail = (code) => !!searchTrail && searchTrail.list.includes(code);

function backToSearch() {
  const trail = searchTrail;
  searchTrail = null;
  if (!trail) return;
  symptom.q = trail.q;
  if (trail.inMenu) openMenu();
  else { setLevel({ view: 'home' }); setSheet('full'); }
  requestAnimationFrame(() => document.getElementById('symResults')?.scrollIntoView({ block: 'start' }));
}

function openPoint(code, side, opts) {
  const owner = state.data.pointOwner.get(code);
  if (!owner) { toast(t('point_not_found', { code })); return; }
  if (!opts?.fromSearch && !onTrail(code)) searchTrail = null;
  if (state.overlay === 'poses') closePoses({ refocus: false });
  // from the menu (search results, the practice path): leave the menu and show the point on the body (the
  // menu stayed on top and the camera flew behind it, council round 2)
  const fromMenu = state.overlay === 'list';
  if (fromMenu) state.overlay = null;
  const wasOther = state.level.view !== 'home' && state.level.id !== owner;
  setLevel({ view: 'point', id: owner, code, side, multi: multiMode() }, opts);
  if (fromMenu || state.sheet === 'full') setSheet('half');
  if (wasOther) haptic('medium'); else haptic();
}

function stepPoint(dir) {
  const lv = state.level;
  if (lv.view !== 'point') return;
  if (onTrail(lv.code)) {
    const list = searchTrail.list;
    const next = list[list.indexOf(lv.code) + dir];
    if (next) openPoint(next, undefined, { fromSearch: true });
    return;
  }
  const ch = state.channelById.get(lv.id);
  const idx = ch.points.indexOf(lv.code);
  const target = ch.points[idx + dir];
  if (target) { openPoint(target, lv.side); return; }
  if (ch.midline) return;
  if (dir > 0 && TRANSITIONS[lv.id]) openPoint(TRANSITIONS[lv.id].to);
  if (dir < 0) {
    const prev = prevChannelOf(lv.id);
    if (prev && TRANSITIONS[prev]) openPoint(TRANSITIONS[prev].from);
  }
}

function back() {
  if (!els.pick.hidden) { els.pick.hidden = true; return; }
  // the menu closes in one step (the full -> half step came first and left the menu open, council)
  if (state.overlay === 'list') { state.overlay = null; setSheet(state.level.view === 'home' ? 'peek' : 'half'); renderSheet(); return; }
  if (state.sheet === 'full') { setSheet('half'); return; }
  if (state.overlay === 'poses') { closePoses({ refocus: true }); return; }
  const lv = state.level;
  if (lv.view === 'point' && onTrail(lv.code)) { backToSearch(); return; }
  if (lv.view === 'point') { setLevel(lv.multi ? { view: 'group', id: 'custom' } : { view: 'channel', id: lv.id }); return; }
  if (lv.view === 'channel' || lv.view === 'group') { setLevel({ view: 'home' }); return; }
  tg?.close?.();
}

function updateBackButton() {
  if (!tg?.BackButton) return;
  const can = state.level.view !== 'home' || state.overlay || state.sheet === 'full' || !els.pick.hidden;
  if (can) tg.BackButton.show(); else tg.BackButton.hide();
}

function haptic(kind = 'selection') {
  try {
    if (kind === 'selection') tg?.HapticFeedback?.selectionChanged();
    else tg?.HapticFeedback?.impactOccurred(kind);
  } catch { /* outside Telegram */ }
}

// ---------------------------------------------------------------- chips

function renderChips() {
  const lv = state.level;
  const selId = lv.view !== 'home' ? lv.id : null;
  const now = activeChannelNow(state.data.channels);
  const chip = (id, extra = '') => {
    const sel = multiMode() ? state.multiSet.has(id) : selId === id;
    const c = color(id);
    const style = sel ? `background:color-mix(in srgb, ${c} 26%, var(--card));border:2px solid ${c}` : '';
    // in "my set" the chips are checkboxes: an empty ring / a tick instead of the colour dot alone
    const mark = multiMode() ? `<span class="tick" style="--chan:${c}">${sel ? '✓' : ''}</span>` : `<span class="dot" style="background:${c}"></span>`;
    const nowTag = now?.id === id ? `<span class="now-tag">${esc(t('now_badge'))}</span>` : '';
    return `<button class="chip${extra}" role="tab" data-id="${id}" aria-selected="${sel}" style="${style}">${mark}<span class="chip-label">${esc(shortName(id))}</span>${nowTag}</button>`;
  };
  const html = [];
  for (const g of ['regular', 'yin', 'yang', 'extra', 'custom']) {
    const sel = (lv.view === 'group' && lv.id === g) || (g === 'custom' && multiMode());
    const ids = groupIds(g);
    const dots = (g === 'custom' && !ids.length) ? '<span class="plus">＋</span>'
      : ids.slice(0, 4).map((id) => `<span class="dot" style="background:${color(id)}"></span>`).join('');
    html.push(`<button class="chip group" role="tab" data-group="${g}" aria-selected="${sel}"><span class="dots">${dots}</span><span class="chip-label">${esc(t(`group_${g}`))}</span></button>`);
  }
  html.push('<span class="chip-sep"></span>');
  for (const id of CLOCK_ORDER) if (state.channelById.has(id)) html.push(chip(id));
  html.push('<span class="chip-sep"></span>');
  for (const id of ['governing_vessel', 'conception_vessel']) if (state.channelById.has(id)) html.push(chip(id));
  html.push('<span class="chip-sep"></span>');
  for (const v of state.data.vessels) html.push(chip(v.id, ' vessel'));
  els.chips.innerHTML = html.join('');
  // on the start screen the row stays at its beginning (the groups); a selection is only brought into view
  // when it is off screen, so the row does not jump under the finger on every tap
  if (lv.view === 'home') { els.chips.scrollLeft = 0; return; }
  const target = lv.view === 'group' ? els.chips.querySelector(`[data-group="${lv.id}"]`) : els.chips.querySelector(`[data-id="${lv.id}"]`);
  target?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: reducedMotion.matches ? 'auto' : 'smooth' });
}

els.chips.addEventListener('click', (e) => {
  const btn = e.target.closest('.chip');
  if (!btn) return;
  if (btn.dataset.group) { selectGroup(btn.dataset.group); return; }
  const id = btn.dataset.id;
  if (multiMode()) { toggleCustom(id); return; }
  if (state.level.view !== 'home' && state.level.id === id) return;
  selectChannel(id);
});

// ---------------------------------------------------------------- cards

function playButton() {
  const playing = scene?.flowPlaying;
  return `<button class="round primary" data-act="flow" aria-label="${esc(t(playing ? 'aria_pause' : 'aria_play'))}">${playing
    ? '<svg viewBox="0 0 24 24" width="20" height="20"><path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor"/></svg>'
    : '<svg viewBox="0 0 24 24" width="20" height="20"><path d="M8 5l11 7-11 7z" fill="currentColor"/></svg>'}</button>`;
}

function factsLine(ch) {
  const m = ch.meta;
  const bits = [m.labels?.system];
  if (m.element && m.element !== 'extraordinary') bits.push(m.labels?.element);
  if (!ch.midline) bits.push(`${hh(m.active_time, 0)}–${hh(m.active_time, 1)}`);
  bits.push(t.points(ch.points.length));
  return bits.filter(Boolean).join(' · ');
}

// ---------------------------------------------------------------- practice progress (from the bot)

// Opened from the chat menu button (a fixed URL without pm/pi/pd): ask the bot with the signed initData.
// Resolves to true when the progress changed.
function fetchProgress() {
  if (params.has('pm') || params.has('pd') || !tg?.initData) return Promise.resolve(false);
  return fetch('api/progress', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ initData: tg.initData }),
  }).then((res) => (res.ok ? res.json() : {})).then((p) => {
    if (!p || (!p.pm && !p.pd)) return false;
    PROGRESS.m = p.pm || null;
    PROGRESS.p = Number.isInteger(p.pi) ? p.pi : -1;
    PROGRESS.done = new Set(Array.isArray(p.pd) ? p.pd : []);
    return true;
  }).catch(() => false);
}

const pathChannel = () => (PROGRESS.m && state.channelById.get(PROGRESS.m)) || null;
function pathPoint() {
  const ch = pathChannel();
  return ch && PROGRESS.p >= 0 ? ch.points[PROGRESS.p] || null : null;
}
function pointPassed(ch, code) {
  if (PROGRESS.done.has(ch.id)) return true;
  return PROGRESS.m === ch.id && PROGRESS.p >= 0 && ch.points.indexOf(code) <= PROGRESS.p;
}
function pathBadge(id) {
  if (PROGRESS.done.has(id)) return `<span class="path-badge done" title="${esc(t('path_done'))}">✓</span>`;
  if (PROGRESS.m === id) return `<span class="path-badge">${esc(t('path_in_work'))}</span>`;
  return '';
}
function pathSection() {
  const ch = pathChannel();
  const done = [...PROGRESS.done].filter((id) => state.channelById.has(id));
  if (!ch && !done.length) return '';
  const cur = pathPoint();
  const work = ch ? `<button class="row-btn tall" ${cur ? `data-goto="${cur}"` : `data-chan="${ch.id}"`}><span class="dot big" style="background:${color(ch.id)}"></span>
    <span class="name"><span class="row-title">${esc(fullName(ch.id))}</span><span class="row-sub">${esc(cur ? t('path_point', { i: PROGRESS.p + 1, n: ch.points.length, code: cur }) : t('path_intro'))}</span></span><span class="chev">›</span></button>` : '';
  const doneHtml = done.length ? `<p class="text muted small-gap">${esc(t('path_done_list'))}</p><div class="tags">${done.map((id) => `<button class="tag button chip-like" data-chan="${id}"><span class="dot" style="background:${color(id)}"></span>${esc(shortName(id))} ✓</button>`).join('')}</div>` : '';
  return `<div class="section"><h3>${esc(t('path_title'))}</h3>${work ? `<div class="rows">${work}</div>` : ''}${doneHtml}</div>`;
}

// ---------------------------------------------------------------- search by how one feels (point indications)

const SYM_GROUPS = ['sleep_mood', 'head_face', 'eyes', 'ent', 'breathing', 'chest_heart', 'digestion', 'back', 'arms', 'legs', 'urogenital', 'cycle', 'cold', 'fatigue', 'skin', 'swelling'];
const symptom = { q: '', g: null, more: false };
// how people type a complaint vs how the indications are written: "болит плечо" found nothing because the
// texts say "боль в плече". Small words are dropped, verb and case forms map to the stem the texts use.
const SYM_STOP = new Set(['в', 'во', 'на', 'и', 'у', 'с', 'со', 'при', 'от', 'по', 'к', 'мне', 'меня', 'очень', 'сильно', 'часто',
  'не', 'плохо', 'постоянно', 'бывает', 'есть',
  'the', 'of', 'in', 'my', 'a', 'an', 'and', 'with', 'i', 'have', 'va', 'bilan', 'men', 'мен', 'және']);
const SYM_SYN = [
  // "боль", "боли", "болезнь", not "большой палец"
  [/^(болит|болят|болело|болела|болели|болеть|больно|боли|болью|болей|боль)$/, /бол(ь(?!ш)|и|е[зй]|ям|ях)/],
  // the shoulder and the top of the shoulder, not the forearm ("предплечье")
  [/^голов/, 'голов'], [/^плеч/, /(^|[^а-я])(над)?плеч/], [/^спин/, 'спин'], [/^поясниц/, 'поясниц'], [/^ше[яиюе]$/, /(^|[^а-я])ше[йияюе]/],
  [/^живот/, 'живот'], [/^желуд/, 'желуд'], [/^горл/, 'горл'], [/^кашл|^кашел/, 'каш'], [/^насморк/, 'насморк'],
  // the texts say "понос", "утомляемость", "боль в половине головы": "диаре", "устал", "мигрень" found nothing
  // (TCM council round 3)
  [/^тошн/, 'тошн'], [/^запор/, 'запор'], [/^понос|^диаре/, 'понос'], [/^бессон|^сплю$|^спится$|^уснуть$|^засып/, 'бессон'],
  [/^тревог|^тревожн/, 'трев'], [/^давлен|^давит/, /(^|[^а-я])давлен/], [/^устал|^усталост|^утомл/, /устал|утомля/],
  [/^мигрен/, /мигрен|половин\w* голов/],
  [/^отек/, /(^|[^а-я])отек/], [/^ауру|^ауыр/, /(^|[^а-яәіңғүұқөһ])ауы?р/],
  [/^колен/, 'колен'], [/^зуб/, 'зуб'], [/^глаз/, 'глаз'], [/^ух[оаеу]$|^уши|^ушей/, /(^|[^а-я])(ух[оаеу]|уш[иаеу])/],
  [/^aches?$|^aching$|^hurts?$|^painful$|^pains?$|^sore$/, 'pain'], [/^headaches?$/, 'headache'],
];
function symStem(w) {
  for (const [re, s] of SYM_SYN) if (re.test(w)) return s;
  // Kazakh and Uzbek suffixes are long: compare the first 4-5 letters
  if (LANG === 'kz' || LANG === 'uz') return w.length > 5 ? w.slice(0, 5) : w;
  // crude stem so "бессонница" also finds "бессонницы", "головная боль" finds "головные боли"
  return w.length > 5 ? w.slice(0, -2) : w.length > 3 ? w.slice(0, -1) : w;
}

// The points textbooks reach for first (project codes). Results were in channel order: "головная боль"
// listed VG4 (a lower-back point) fifth of 93 and left VB20, GI4, F3 far below (council round 3).
const KEY_POINTS_A = new Set(['GI4', 'E36', 'RP6', 'MC6', 'C7', 'F3', 'VB20', 'VG20', 'R3', 'P7']);
const KEY_POINTS_B = new Set(['P1', 'P5', 'P9', 'P11', 'GI11', 'GI20', 'E25', 'E40', 'E44', 'RP4', 'RP9', 'RP10', 'C5',
  'IG3', 'V10', 'V13', 'V15', 'V17', 'V18', 'V20', 'V23', 'V40', 'V60', 'V62', 'R1', 'R6', 'R7', 'MC7', 'MC8', 'TR5',
  'TR17', 'VB21', 'VB30', 'VB34', 'VB39', 'VB41', 'F2', 'F14', 'VG14', 'VG16', 'VG24', 'VG26', 'VC4', 'VC6', 'VC12', 'VC17', 'VC22']);

// Frequent complaints -> the classic points in textbook order (assets/key_points.json, TCM council round 3),
// fetched on the first search; until it arrives the scores below order the results alone
let keyComplaints = null;
function loadKeyComplaints() {
  if (keyComplaints) return;
  keyComplaints = [];
  fetch(`assets/key_points.json?v=${ASSET_VERSION}`).then((r) => (r.ok ? r.json() : null)).then((j) => {
    keyComplaints = Array.isArray(j?.complaints) ? j.complaints : [];
    refreshSymptomResults();
  }).catch(() => {});
}
function complaintOf(raw) {
  if (!raw || !keyComplaints?.length) return null;
  let best = null;
  for (const c of keyComplaints) {
    for (const m of c.match?.[LANG] || c.match?.en || []) {
      // the longest matching phrase wins ("боль в груди" over "боль")
      if (m && raw.includes(m) && (!best || m.length > best.len)) best = { c, len: m.length };
    }
  }
  return best?.c || null;
}

function symptomMatches() {
  const d = state.data;
  // typographic apostrophes as typed on phones (’ ‘ ʻ ʼ `) count as the ASCII one the Uzbek texts use
  const raw = symptom.q.trim().toLowerCase().replace(/ё/g, 'е').replace(/[’‘ʻʼ`´]/g, "'").replace(/[.,;:!?()«»"]/g, ' ');
  const words = raw.split(/\s+/).filter((w) => w && !SYM_STOP.has(w)).map(symStem);
  if (!words.length && !symptom.g) return [];
  loadKeyComplaints();
  const complaint = symptom.g ? null : complaintOf(raw);
  symptom.complaint = complaint;
  const lead = new Map((complaint?.points || []).map((code, i) => [code, i]));
  // a query about pregnancy shows no point marked "not in pregnancy" (TCM council round 3)
  const pregnant = complaint?.pregnancy || /беремен|pregnan|жүкті|homilador/.test(raw);
  const out = [];
  for (const code of d.pointOwner.keys()) {
    if (pregnant && (d.extras[code]?.caution || []).includes('pregnancy')) continue;
    const ind = d.extraText(code).indications;
    if (!Array.isArray(ind)) continue;
    const hits = [];
    for (const grp of ind) {
      if (symptom.g && grp.g !== symptom.g) continue;
      for (const item of grp.items || []) {
        const low = item.toLowerCase().replace(/ё/g, 'е').replace(/[’‘ʻʼ`´]/g, "'");
        if (words.every((w) => (typeof w === 'string' ? low.includes(w) : w.test(low)))) hits.push(item);
      }
    }
    if (!hits.length && !lead.has(code)) continue;
    // the complaint in the point's own summary or main functions: it is what the point is for, not one of
    // twenty listed indications
    const tx = d.extraText(code);
    const head = [tx.why || '', ...(Array.isArray(tx.functions) ? tx.functions : [])].join(' ').toLowerCase().replace(/ё/g, 'е');
    const inHead = words.length && words.every((w) => (typeof w === 'string' ? head.includes(w) : w.test(head)));
    let score = Math.min(hits.length, 3) + (inHead ? 3 : 0) + (KEY_POINTS_A.has(code) ? 3 : KEY_POINTS_B.has(code) ? 1.5 : 0);
    if (lead.has(code)) score = 100 - lead.get(code);
    // a lead point whose texts word the complaint differently still shows why it is listed
    out.push({ code, hits: hits.length ? hits : [symptom.q.trim()], score });
  }
  out.sort((a, b) => b.score - a.score);
  return out;
}

function symptomResultsHtml() {
  const res = symptomMatches();
  if (!symptom.q.trim() && !symptom.g) return `<p class="text muted">${esc(t('sym_hint'))}</p>`;
  if (!res.length) return `<p class="text muted">${esc(t('sym_none'))}</p>`;
  const shown = symptom.more ? res : res.slice(0, 12);
  const rows = shown.map(({ code, hits }) => {
    const owner = state.data.pointOwner.get(code);
    // a point with a caution (pregnancy, an artery, the eye...) is marked here too, not only in its card
    const warn = (state.data.extras[code]?.caution || []).length ? `<span class="warn" title="${esc(t('sym_warn_title'))}">⚠</span>` : '';
    return `<button class="row-btn" data-goto="${code}"><span class="code">${esc(dispCode(code))}</span><span class="name"><span>${esc(pointName(code))}${warn}</span><span class="row-sub">${bodyRegion(code) ? `<b class="region">${esc(t(`region_${bodyRegion(code)}`))}</b> · ` : ''}${esc(hits.slice(0, 3).join(', '))}</span></span><span class="dot" style="background:${color(owner)}"></span></button>`;
  }).join('');
  // a query that may mean pregnancy (no periods) or blood / retained urine gets its own line: the search
  // offered exactly the points not used in pregnancy for "нет месячных" (TCM council round 2)
  const q = symptom.q.toLowerCase();
  const preg = symptom.g === 'cycle' || symptom.complaint?.pregnancy || /месячн|менстру|беремен|задерж|period|menstru|pregnan|hayz|homilador|етеккір|жүкті/.test(q);
  const blood = /кров|задержк\w* моч|не могу помочит|blood|bleed|retention|qon|siydik tutil|қан|зәр ұста/.test(q);
  const extra = (preg ? `<p class="caution sym-flags">${esc(t('sym_pregnancy'))}</p>` : '') + (blood ? `<p class="caution sym-flags">${esc(t('sym_blood'))}</p>` : '');
  // a complaint that can be an emergency (chest pain...) puts the warning first and in full weight
  const flag = `<p class="caution sym-flags${symptom.complaint?.red_flag ? ' strong' : ''}">${esc(t('sym_red_flags'))}</p>`;
  // the complaint's own warning ("одышка в покое, синие губы — сразу скорая"); written in Russian only
  const note = LANG === 'ru' && symptom.complaint?.note ? `<p class="caution sym-flags${symptom.complaint.red_flag ? ' strong' : ''}">${esc(symptom.complaint.note)}</p>` : '';
  return `${symptom.complaint?.red_flag ? flag + note + extra : note + extra + flag}
    <p class="text muted small-gap">${esc(t('sym_found', { n: res.length }))}</p><div class="rows">${rows}</div>
    ${res.length > shown.length ? `<button class="more" data-act="symmore">${esc(t('more_n', { n: res.length - shown.length }))}</button>` : ''}
    <p class="note">${esc(t('ind_note'))}</p>`;
}

function symptomSection() {
  const pills = SYM_GROUPS.map((g) => `<button data-symg="${g}" aria-pressed="${symptom.g === g}" aria-selected="${symptom.g === g}">${esc(t(`ind_${g}`))}</button>`).join('');
  // the results right under the field: below the 16 topic buttons they were off screen while typing with
  // the keyboard open (council round 2)
  return `<div class="section sym"><h3 id="symTitle">${esc(t('sym_title'))}</h3>
    <input class="sym-input" id="symInput" type="search" enterkeyhint="search" autocomplete="off" aria-labelledby="symTitle" placeholder="${esc(t('sym_placeholder'))}" value="${esc(symptom.q)}">
    <div id="symResults">${symptomResultsHtml()}</div>
    <div class="scenery-opts sym-groups">${pills}</div></div>`;
}

function refreshSymptomResults() {
  const box = document.getElementById('symResults');
  if (box) box.innerHTML = symptomResultsHtml();
}

// the WHO code beside the European one (IG19 · SI19): readers of English and international books know
// only the WHO codes (council)
function whoCode(code) {
  const who = state.data.pointInfo.get(code)?.who;
  return who ? String(who).replace(/\s+/g, '') : '';
}
// the code shown in lists, labels and buttons: WHO in English (readers know only LI11, not GI11),
// the French/Russian code otherwise; both appear together only in the point card header
function dispCode(code) {
  return (LANG === 'en' && whoCode(code)) || code;
}
// in English the WHO code comes first (LI11 · GI11): English books use only it
function codePair(code) {
  const w = whoCode(code);
  if (!w || w === code) return `<span class="code">${esc(code)}</span>`;
  const [a, b] = LANG === 'en' ? [w, code] : [code, w];
  return `<span class="code">${esc(a)}</span> <span class="code who">· ${esc(b)}</span>`;
}

function renderPeek() {
  if (!state.data) return;
  const lv = state.level;
  const d = state.data;
  if (state.overlay === 'poses') { renderPosesPeek(); return; }
  // the menu opened over a channel kept that channel's card on top, so it read as its profile (council)
  if (state.overlay === 'list') {
    els.sheet.style.removeProperty('--chan');
    els.peek.innerHTML = `<div class="peek-row"><div class="peek-main"><div class="peek-title">${esc(t('menu_title'))}</div></div>
      <button class="round" data-act="closemenu" aria-label="${esc(t('close'))}">✕</button></div>`;
    return;
  }
  if (lv.view === 'home' && pathChannel()) {
    // opened from the bot mid-practice: the first thing shown is where the person stopped
    const ch = pathChannel();
    const cur = pathPoint();
    const now = activeChannelNow(d.channels);
    const sub = [cur ? t('path_point', { i: PROGRESS.p + 1, n: ch.points.length, code: cur }) : t('path_intro'),
      now ? `${t('now_active')}: ${shortName(now.id)}` : ''].filter(Boolean).join(' · ');
    els.sheet.style.setProperty('--chan', color(ch.id));
    els.peek.innerHTML = `<button class="peek-row peek-button" ${cur ? `data-goto="${cur}"` : `data-chan="${ch.id}"`}><span class="dot big" style="background:${color(ch.id)}"></span>
      <span class="peek-main"><span class="peek-title">${esc(t('path_title'))} · ${esc(shortName(ch.id))}</span>
      <span class="peek-sub">${esc(sub)}</span></span><span class="chev">›</span></button>`;
    return;
  }
  if (lv.view === 'home') {
    const now = activeChannelNow(d.channels);
    els.sheet.style.removeProperty('--chan');
    els.peek.innerHTML = now
      ? `<button class="peek-row peek-button" data-chan="${now.id}"><span class="dot big" style="background:${color(now.id)}"></span>
          <span class="peek-main"><span class="peek-title">${esc(t('now_active'))} · ${esc(shortName(now.id))}</span>
          <span class="peek-sub">${esc(t('by_clock'))} · ${esc(t('until', { time: `${hh(now.meta.active_time, 1)}:00` }))}</span></span><span class="chev">›</span></button>`
      : `<div class="peek-row"><span class="peek-title">${esc(t('pick_channel'))}</span></div>`;
    return;
  }
  if (lv.view === 'group') {
    els.sheet.style.removeProperty('--chan');
    const dots = groupIds(lv.id).map((id) => `<span class="dot" style="background:${color(id)}"></span>`).join('');
    const n = groupIds(lv.id).length;
    const sub = lv.id !== 'custom' ? t(`group_${lv.id}_sub`) : (n ? t('group_custom_sub', { n }) : t('group_custom_sub_empty'));
    els.peek.innerHTML = `<div class="peek-row"><div class="peek-main">
      <div class="peek-title">${esc(t(`group_${lv.id}_title`))}</div>
      <div class="peek-sub group-dots">${dots}<span>${esc(sub)}</span></div></div>${lv.id === 'custom' && n ? playButton() : ''}</div>`;
    return;
  }
  const ch = state.channelById.get(lv.id);
  els.sheet.style.setProperty('--chan', color(ch.id));
  if (lv.view === 'point') {
    const idx = ch.points.indexOf(lv.code);
    const trail = onTrail(lv.code) ? searchTrail : null;
    const ti = trail ? trail.list.indexOf(lv.code) : -1;
    const hasPrev = trail ? ti > 0 : idx > 0 || (!ch.midline && prevChannelOf(ch.id));
    const hasNext = trail ? ti < trail.list.length - 1 : idx < ch.points.length - 1 || (!ch.midline && TRANSITIONS[ch.id]);
    // found by a complaint: the line under the title leads back to the results and counts in them
    const sub = trail
      ? `<button class="link" data-act="tosearch">← ${esc(t('to_results', { q: trail.q.trim() }))}</button> · ${ti + 1}/${trail.list.length}`
      : `<button class="link" data-chan="${ch.id}">${esc(shortName(ch.id))}</button> · ${idx + 1}/${ch.points.length}`;
    els.peek.innerHTML = `<div class="peek-row">
      <button class="round" data-act="prev" ${hasPrev ? '' : 'disabled'} aria-label="${esc(t('aria_prev'))}">‹</button>
      <div class="peek-main">
        <div class="peek-title">${codePair(lv.code)} <span class="ellipsis">${esc(pointName(lv.code))}</span></div>
        <div class="peek-sub">${sub}</div>
      </div>
      <button class="round" data-act="next" ${hasNext ? '' : 'disabled'} aria-label="${esc(t('aria_next'))}">›</button></div>`;
    return;
  }
  if (ch.kind === 'vessel') {
    els.peek.innerHTML = `<div class="peek-row"><span class="vessel-icon" style="color:${color(ch.id)}">∴</span><div class="peek-main">
      <div class="peek-title">${esc(shortName(ch.id))}</div>
      <div class="peek-sub">${esc(t('vessel_kind'))} · ${esc(t('opening_point', { code: ch.confluent }))}</div></div>${playButton()}</div>`;
    return;
  }
  const now = !ch.midline && isActiveNow(ch.meta.active_time) ? `<span class="now-badge">${esc(t('now_badge'))}</span>` : '';
  els.peek.innerHTML = `<div class="peek-row"><span class="dot big" style="background:${color(ch.id)}"></span><div class="peek-main">
    <div class="peek-title two-lines">${esc(ch.meta.name)}</div>
    <div class="peek-sub">${esc(factsLine(ch))}${now}</div></div>${playButton()}</div>`;
}

function renderSheet() {
  renderPeek();
  if (!state.data) return;
  if (state.overlay === 'poses') { els.body.innerHTML = posesBody(); return; }
  const lv = state.level;
  if (lv.view === 'home' || state.overlay === 'list') { els.body.innerHTML = homeBody(); return; }
  if (lv.view === 'group') { els.body.innerHTML = groupBody(lv.id); return; }
  const ch = state.channelById.get(lv.id);
  if (lv.view === 'point') els.body.innerHTML = pointBody(ch, lv.code);
  else if (ch.kind === 'vessel') els.body.innerHTML = vesselBody(ch);
  else els.body.innerHTML = channelBody(ch);
}

function homeBody() {
  const d = state.data;
  const now = activeChannelNow(d.channels);
  const start = now ? CLOCK_ORDER.indexOf(now.id) : 0;
  const order = CLOCK_ORDER.map((_, i) => CLOCK_ORDER[(start + i) % 12]).filter((id) => state.channelById.has(id));
  const row = (id, sub, badge = '') => `<button class="row-btn tall" data-chan="${id}"><span class="dot big" style="background:${color(id)}"></span>
    <span class="name"><span class="row-title">${esc(fullName(id))}</span><span class="row-sub">${esc(sub)}</span></span>${pathBadge(id)}${badge}</button>`;
  const regRows = order.map((id) => {
    const ch = state.channelById.get(id);
    const m = ch.meta;
    const sub = [m.labels?.system, m.labels?.element, `${hh(m.active_time, 0)}–${hh(m.active_time, 1)}`].filter(Boolean).join(' · ');
    return row(id, sub, now?.id === id ? `<span class="now-badge" style="--chan:${color(id)}">${esc(t('now_badge'))}</span>` : '');
  }).join('');
  const midRows = ['governing_vessel', 'conception_vessel'].filter((id) => state.channelById.has(id))
    .map((id) => row(id, `${t('outside_clock')} · ${t.points(state.channelById.get(id).points.length)}`)).join('');
  const vesRows = d.vessels.map((v) => `<button class="row-btn tall" data-chan="${v.id}"><span class="vessel-icon" style="color:${color(v.id)}">∴</span>
    <span class="name"><span class="row-title">${esc(v.text.name || shortName(v.id))}</span><span class="row-sub">${esc(t('opening_point', { code: v.confluent }))}</span></span></button>`).join('');
  const about = state.expanded.has('about');
  // first run: what this is and three ways in (a new person saw a figure, chips and four unlabelled buttons
  // and did not know where to start, council)
  const intro = state.introSession && state.overlay !== 'list' ? `<div class="section intro"><p class="text lead">${esc(t('intro_text'))}</p><div class="rows">
    <button class="row-btn" data-act="introposes"><span class="name"><span class="row-title">${esc(t('intro_poses'))}</span></span><span class="chev">›</span></button>
  </div></div>` : '';
  // search and the practice path first, the settings last (the language and photo rows stood on top, the
  // search in the middle, council)
  return `${intro}${pathSection()}
    ${symptomSection()}
    ${state.overlay === 'list' && !state.expanded.has('allch') ? `<div class="section"><button class="row-btn ind-head" data-toggle="allch" aria-expanded="false"><span class="name"><span class="row-title">${esc(t('all_channels_row'))}</span><span class="row-sub">${esc(t('all_channels_sub'))}</span></span><span class="chev">›</span></button></div>` : `
    <div class="section"><h3>${esc(t('sec_main'))}</h3><div class="rows">${regRows}</div></div>
    <div class="section"><h3>${esc(t('sec_mid'))}</h3><div class="rows">${midRows}</div></div>
    <div class="section"><h3>${esc(t('sec_vessels'))}</h3><div class="rows">${vesRows}</div></div>`}
    <div class="section prefs" id="prefs"><h3>${esc(t('settings_title'))}</h3>${langRowHtml()}${sceneryRowHtml()}
      <div class="toggle-row"><span id="lbl-luo">${esc(t('luo_toggle'))}</span><button class="switch" role="switch" data-act="luo" aria-checked="${state.luoOn}" aria-labelledby="lbl-luo"></button></div>
      <div class="toggle-row"><span id="lbl-slow">${esc(t('slow_toggle'))}</span><button class="switch" role="switch" data-act="slow" aria-checked="${state.flowSlow}" aria-labelledby="lbl-slow"></button></div></div>
    <p class="note">${esc(t('disclaimer'))}</p>
    <button class="row-btn" data-toggle="about"><span class="name">${esc(t('about_title'))}</span><span class="chev">${about ? '⌄' : '›'}</span></button>
    ${about ? `<p class="text">${esc(t('about_text'))}</p>` : ''}`;
}

/** List of the group's channels (it doubles as the colour legend); a tap opens the channel. */
function groupBody(id) {
  const ids = groupIds(id);
  const custom = id === 'custom';
  const rows = ids.map((cid) => {
    const ch = state.channelById.get(cid);
    const v = state.data.vessels.find((x) => x.id === cid);
    const sub = v ? t('opening_point', { code: v.confluent })
      : ch.midline ? `${t('outside_clock')} · ${t.points(ch.points.length)}`
        : [ch.meta?.labels?.system, `${hh(ch.meta.active_time, 0)}–${hh(ch.meta.active_time, 1)}`].filter(Boolean).join(' · ');
    const row = `<button class="row-btn tall" data-chan="${cid}"><span class="dot big" style="background:${color(cid)}"></span>
      <span class="name"><span class="row-title">${esc(v?.text?.name || fullName(cid))}</span><span class="row-sub">${esc(sub)}</span></span><span class="chev">›</span></button>`;
    if (!custom || v || !ch.points?.length) return row;
    // "several": the points of every chosen channel, a tap opens the point card and keeps the set
    const key = `pts:${cid}`;
    const open = state.expanded.has(key);
    const list = open ? `<div class="pt-grid">${ch.points.map((c) => `<button class="pt-chip" data-point="${c}" style="--chan:${color(cid)}" title="${esc(pointName(c))}">${esc(c)}</button>`).join('')}</div>` : '';
    return `${row}<button class="row-btn sub-row" data-toggle="${key}"><span class="name">${esc(t.points(ch.points.length))}</span><span class="chev">${open ? '⌄' : '›'}</span></button>${list}`;
  }).join('');
  return `${custom && ids.length > 1 ? relationsBody(ids) : ''}<div class="section"><div class="rows">${rows}</div></div>`;
}

/** How the chosen channels work together: energy passing on, yin-yang pairs with luo branches, shared points. */
function relationsBody(ids) {
  const set = new Set(ids);
  const d = state.data;
  const out = [];
  const name = (id) => esc(shortName(id));
  for (const id of ids) {
    const tr = TRANSITIONS[id];
    const next = nextChannelOf(id);
    if (tr && set.has(next)) {
      out.push(`<button class="row-btn" data-act="showluo" data-from="${tr.from}" data-to="${tr.to}"><span class="name">${name(id)} → ${name(next)}<span class="row-sub">${esc(t('rel_flow'))}: ${esc(tr.from)} → ${esc(tr.to)}</span></span><span class="chev">›</span></button>`);
    }
  }
  const pairsSeen = new Set();
  for (const id of ids) {
    const pair = state.channelById.get(id)?.meta?.pair;
    if (!pair || !set.has(pair) || pairsSeen.has(pair)) continue;
    pairsSeen.add(id);
    const branches = d.luoLinks.filter((l) => l.to && ((l.meridian === id && l.to_meridian === pair) || (l.meridian === pair && l.to_meridian === id)))
      .map((l) => `${l.from} → ${l.to}`).join(', ');
    const first = d.luoLinks.find((l) => l.to && l.meridian === id && l.to_meridian === pair);
    out.push(`<button class="row-btn"${first ? ` data-act="showluo" data-from="${first.from}" data-to="${first.to}"` : ''}><span class="name">${name(id)} ⇄ ${name(pair)}<span class="row-sub">${esc(t('rel_pair'))}${branches ? `: ${esc(branches)}` : ''}</span></span><span class="chev">›</span></button>`);
  }
  const shared = [];
  for (const [code, c] of d.crossings) {
    if (c.confidence && c.confidence !== 'high') continue;
    const ms = (c.meridians || []).filter((m) => set.has(m));
    if (ms.length >= 2) shared.push(code);
  }
  if (shared.length) {
    out.push(`<div class="row-btn static"><span class="name"><span class="row-sub">${esc(t('rel_cross'))}</span></span></div>
      <div class="pt-grid">${shared.map((c) => `<button class="pt-chip" data-point="${c}" style="--chan:${color(d.pointOwner.get(c))}" title="${esc(pointName(c))}">${esc(c)}</button>`).join('')}</div>`);
  }
  return `<div class="section"><h3>${esc(t('rel_title'))}</h3>${out.length ? `<div class="rows">${out.join('')}</div>` : `<p class="text muted">${esc(t('rel_none'))}</p>`}</div>`;
}

function clampText(key, text) {
  if (!text) return '';
  const open = state.expanded.has(key);
  return `<p class="text${open ? '' : ' clamp2'}">${richText(text)}</p>${text.length > 120 ? `<button class="more" data-toggle="${key}">${esc(t(open ? 'less' : 'more'))}</button>` : ''}`;
}

function channelBody(ch) {
  const m = ch.meta;
  const tags = [];
  if (m.system) tags.push(['yin_yang', m.labels.system, m.system === 'yin' ? 'hint_yin' : 'hint_yang']);
  if (m.element && m.element !== 'extraordinary') tags.push(['element', m.labels.element, 'hint_element']);
  if (ch.midline) tags.push(['limb', t('tag_midline'), 'hint_midline']);
  else tags.push(['limb', m.level?.startsWith('hand') ? t('tag_hand') : t('tag_foot'), m.level?.startsWith('hand') ? 'hint_hand' : 'hint_foot']);
  const openTag = [...state.expanded].find((k) => k.startsWith('tag:'));
  const tagHtml = tags.map(([k, label, hint]) => `<button class="tag button" data-toggle="tag:${hint}" aria-expanded="${openTag === `tag:${hint}`}">${esc(label)}</button>`).join('');
  const explain = openTag ? `<p class="tag-explain">${esc(t(openTag.slice(4)))}</p>` : '';
  let neighbours = '';
  if (!ch.midline) {
    const prev = prevChannelOf(ch.id);
    const next = CLOCK_ORDER[(CLOCK_ORDER.indexOf(ch.id) + 1) % 12];
    const nb = (id, dir) => `<button data-chan="${id}"><span class="dot" style="background:${color(id)}"></span>${dir < 0 ? '‹ ' : ''}${esc(shortName(id))}${dir > 0 ? ' ›' : ''}${id === m.pair ? `<span class="mini-badge">${esc(t('pair'))}</span>` : ''}</button>`;
    neighbours = `<div class="neighbours">${nb(prev, -1)}${nb(next, 1)}</div>`;
  } else {
    const ref = state.data.references.get(ch.id);
    if (ref) neighbours = `<button class="row-btn" data-goto="${ref.confluent_point}"><span class="name">${esc(t('outside_clock'))} · ${esc(t('opening_point', { code: ref.confluent_point }))}</span><span class="chev">›</span></button>`;
  }
  const hours = ch.midline ? '' : `<div class="hours-row"><span>${esc(t('hours', { a: `${hh(m.active_time, 0)}–${hh(m.active_time, 1)}`, p: `${hh(m.passive_time, 0)}–${hh(m.passive_time, 1)}` }))}</span><button class="info" data-toggle="hours" aria-label="${esc(t('aria_hours'))}">i</button></div>${state.expanded.has('hours') ? `<p class="tag-explain">${esc(t('hint_hours'))}</p>` : ''}`;
  const rows = ch.points.filter((code) => !state.special || isSpecial(ch, code)).map((code) => pointRow(ch, code)).join('');
  let path = '';
  if (PROGRESS.done.has(ch.id)) path = `<p class="path-line done">✓ ${esc(t('path_done_channel'))}</p>`;
  else if (PROGRESS.m === ch.id) {
    const cur = pathPoint();
    path = `<button class="row-btn path-line" ${cur ? `data-goto="${cur}"` : ''}><span class="name"><span class="row-title">${esc(t('path_title'))}</span>
      <span class="row-sub">${esc(cur ? t('path_point', { i: PROGRESS.p + 1, n: ch.points.length, code: cur }) : t('path_intro'))}</span></span>${cur ? `<span class="chev">${esc(t('path_continue'))} ›</span>` : ''}</button>`;
  }
  // practice first, theory folded (council: the profile opened with seven correspondences and hid the
  // practice under them); where to begin is a plain button, the switches live in the menu settings
  const pr = state.data.profile(ch.id);
  const start = pr?.start && state.data.pointOwner.has(pr.start)
    ? `<div class="rows"><button class="row-btn start-btn" data-goto="${pr.start}"><span class="name"><span class="row-title">${esc(t('start_with', { name: pointName(pr.start), code: dispCode(pr.start) }))}${(state.data.extras[pr.start]?.caution || []).length ? `<span class="warn" title="${esc(t('sym_warn_title'))}">⚠</span>` : ''}</span>${pr.start_why ? `<span class="row-sub">${esc(pr.start_why)}</span>` : ''}</span><span class="chev">›</span></button></div>` : '';
  const tradOpen = state.expanded.has('trad');
  const trad = (pr?.organ || m.description) ? `<div class="section"><button class="row-btn ind-head" data-toggle="trad" aria-expanded="${tradOpen}"><span class="name"><span class="row-title">${esc(t('profile_title'))}</span><span class="row-sub">${esc(t('trad_sub'))}</span></span><span class="chev">${tradOpen ? '⌄' : '›'}</span></button>
    ${tradOpen ? `${profileSection(ch.id, { bare: true })}${m.description ? `<h3>${esc(t('description_title'))}</h3><p class="text">${richText(m.description)}</p>` : ''}${m.labels?.level ? `<p class="text muted">${esc(t('level_label'))}: ${esc(m.labels.level)}</p>` : ''}` : ''}</div>` : '';
  return `<div class="tags">${tagHtml}</div>${explain}
    ${path}
    ${pr?.organ ? `<p class="text lead">${esc(pr.organ)}</p>` : ''}
    ${start}
    ${m.intro_practice ? `<div class="section"><h3>${esc(t('practice_title'))}</h3><p class="text">${richText(m.intro_practice)}</p></div>` : ''}
    <p class="text flow-line">${esc(t('flow_label'))}: ${esc(FLOW_SHORT[LANG][ch.id] || m.direction || '')}</p>
    ${hours}
    ${neighbours}
    <div class="section">
      <div class="toggle-row"><h3 class="inline">${esc(t('points_title'))} · ${esc(t.points(ch.points.length))}</h3>
        <div class="seg seg-small"><button data-filter="all" aria-selected="${!state.special}">${esc(t('filter_all'))}</button><button data-filter="special" aria-selected="${state.special}">${esc(t('filter_special'))}</button></div></div>
      <p class="note legend">${esc(t('marks_legend'))}</p>
      <div class="rows">${rows}</div>
    </div>
    ${trad}`;
}

function fmtCun(n) {
  const num = String(n).replace('.', LANG === 'en' ? '.' : ',');
  if (LANG === 'ru') return `${num} ${n === 1 ? 'цунь' : n < 5 ? 'цуня' : 'цуней'}`;
  if (LANG === 'uz') return `${num} sun`;
  if (LANG === 'kz') return `${num} цунь`;
  return `${num} cun`;
}

function showRuler(from, to, cun) {
  const r = scene.showRuler(from, to, cun, state.level.side || 1);
  if (!r) return;
  scene.frameBox(r.box, r.normal.clone().add(new THREE.Vector3(0, 0.15, 0)), { minRadius: 0.07 });
  toast(t('ruler_toast', { n: fmtCun(cun), code: from }));
  haptic('light');
}

/** Traditional profile of a channel: role, five-element correspondences, balance / imbalance, where to begin. */
function profileSection(id, { bare = false } = {}) {
  const pr = state.data.profile(id);
  if (!pr || !pr.organ) return '';
  if (bare) {
    // inside the folded "In the tradition" row of a channel: no heading, no repeated lead or start button
    const c = pr.correspondences || {};
    const corr = ['element', 'emotion', 'season', 'taste', 'color', 'sense', 'tissue'].filter((k) => c[k])
      .map((k) => `<dt>${esc(t(`corr_${k}`))}</dt><dd>${esc(c[k])}</dd>`).join('');
    const imb = Array.isArray(pr.imbalance) ? pr.imbalance : [];
    return `${corr ? `<dl class="ind corr">${corr}</dl>` : ''}
      ${pr.balance ? `<p class="text"><b>${esc(t('balance_title'))}:</b> ${esc(pr.balance)}</p>` : ''}
      ${imb.length ? `<h3>${esc(t('imbalance_title'))}</h3><ul class="bullets">${imb.map((x) => `<li>${esc(x)}</li>`).join('')}</ul><p class="note">${esc(t('imbalance_note'))}</p>` : ''}`;
  }
  const c = pr.correspondences || {};
  const corr = ['element', 'emotion', 'season', 'taste', 'color', 'sense', 'tissue'].filter((k) => c[k])
    .map((k) => `<dt>${esc(t(`corr_${k}`))}</dt><dd>${esc(c[k])}</dd>`).join('');
  const open = state.expanded.has('imbalance');
  const imb = Array.isArray(pr.imbalance) ? pr.imbalance : [];
  const start = pr.start && state.data.pointOwner.has(pr.start)
    ? `<button class="row-btn" data-goto="${pr.start}"><span class="name"><span class="row-sub">${esc(t('start_title'))}</span><span class="code">${esc(pr.start)}</span> ${esc(pointName(pr.start))}${pr.start_why ? `<span class="row-sub">${esc(pr.start_why)}</span>` : ''}</span><span class="chev">›</span></button>` : '';
  return `<div class="section profile"><h3>${esc(t('profile_title'))}</h3>
    <p class="text">${esc(pr.organ)}</p>
    ${corr ? `<dl class="ind corr">${corr}</dl>` : ''}
    ${pr.balance ? `<p class="text"><b>${esc(t('balance_title'))}:</b> ${esc(pr.balance)}</p>` : ''}
    ${imb.length ? `<button class="row-btn ind-head" data-toggle="imbalance" aria-expanded="${open}"><span class="name"><span class="row-title">${esc(t('imbalance_title'))}</span></span><span class="chev">${open ? '⌄' : '›'}</span></button>
      ${open ? `<ul class="bullets">${imb.map((x) => `<li>${esc(x)}</li>`).join('')}</ul><p class="note">${esc(t('imbalance_note'))}</p>` : ''}` : ''}
    ${start ? `<div class="rows">${start}</div>` : ''}</div>`;
}

function isSpecial(ch, code) {
  if (ch.points[0] === code || ch.points[ch.points.length - 1] === code) return true;
  if (TRANSITIONS[ch.id]?.from === code) return true;
  return (state.data.pointCats[code] || []).some((k) => SPECIAL_CATS.has(k));
}

function pointRow(ch, code) {
  const cats = state.data.pointCats[code] || [];
  const marks = [];
  if (cats.includes('luo') || cats.includes('great_luo')) marks.push('<span class="mk">◆</span>');
  if (cats.includes('confluent')) marks.push('<span class="mk">■</span>');
  const cr = state.data.crossings.get(code);
  if (cr && (cr.meridians || []).length > 1) marks.push('<span class="mk">◎</span>');
  const has = !!state.data.coords[code];
  if (pathPoint() === code) marks.unshift(`<span class="mk here" title="${esc(t('path_here_short'))}">●</span>`);
  else if (pointPassed(ch, code)) marks.unshift(`<span class="mk passed" title="${esc(t('path_done'))}">✓</span>`);
  return `<button class="row-btn${has ? '' : ' missing'}" data-point="${code}"><span class="code">${esc(dispCode(code))}</span>
    <span class="name">${esc(pointName(code))}${has ? '' : `<span class="row-sub">${esc(t('not_on_model'))}</span>`}</span><span class="marks">${marks.join('')}</span></button>`;
}

function badgeLabel(key, code) {
  if (key === 'transition') {
    const tr = Object.entries(TRANSITIONS).find(([, v]) => v.from === code);
    return t('transition', { code: tr?.[1].to || '' });
  }
  const tx = state.data.catText(key);
  let label = tx?.name || key;
  if (key === 'mu' && state.data.muOf[code]) label += ` · ${shortName(state.data.muOf[code])}`;
  if (key === 'back_shu' && state.data.backShuOf[code] && SHORT[LANG][state.data.backShuOf[code]]) label += ` · ${shortName(state.data.backShuOf[code])}`;
  return label;
}

function pointBody(ch, code) {
  const d = state.data;
  const info = d.pointInfo.get(code);
  const ex = d.extraText(code);
  const extra = d.extras[code] || {};
  const cats = (d.pointCats[code] || []).filter((k) => BADGE_ORDER.includes(k));
  const keys = [];
  if (TRANSITIONS[ch.id]?.from === code) keys.push('transition');
  for (const k of BADGE_ORDER) if (cats.includes(k)) keys.push(k);
  const showAll = state.expanded.has('badges');
  const shown = showAll ? keys : keys.slice(0, 2);
  const openBadge = [...state.expanded].find((k) => k.startsWith('badge:'))?.slice(6);
  const badges = shown.map((k) => `<button class="tag button" data-toggle="badge:${k}" aria-expanded="${openBadge === k}">${esc(badgeLabel(k, code))}</button>`).join('')
    + (!showAll && keys.length > 2 ? `<button class="tag button" data-toggle="badges">+${keys.length - 2}</button>` : '');
  let explain = '';
  if (openBadge) {
    let text = openBadge === 'transition' ? t('next_channel', { name: shortName(nextChannelOf(ch.id)) }) : d.catText(openBadge)?.short || '';
    let actions = '';
    if (openBadge === 'luo' || openBadge === 'great_luo') {
      const l = d.luoLinks.find((x) => x.from === code);
      if (l?.to_meridian) actions = `<button class="link" data-chan="${l.to_meridian}">${esc(t('luo_to', { name: shortName(l.to_meridian) }))}</button>`;
      if (l?.to) actions += ` · <button class="link" data-act="showluo" data-from="${code}" data-to="${l.to}">${esc(t('show_branch'))}</button>`;
    }
    if (openBadge === 'confluent') {
      const v = d.vessels.find((x) => x.confluent === code);
      if (v) actions = `<button class="link" data-chan="${v.id}">${esc(t('key_of', { vessel: shortName(v.id), couple: v.pairId ? shortName(v.pairId) : '' }))}</button>`;
    }
    if (openBadge === 'transition') actions = `<button class="link" data-chan="${nextChannelOf(ch.id)}">${esc(shortName(nextChannelOf(ch.id)))} ›</button>`;
    explain = `<div class="tag-explain">${esc(text)}${actions ? `<div class="explain-actions">${actions}</div>` : ''}</div>`;
  }
  const cautions = (extra.caution || []).map((k) => `<p class="caution">⚠ ${esc(t(`caution_${k}`))}</p>`).join('');
  const cr = d.crossings.get(code);
  const meets = cr ? (cr.meridians || []).filter((m) => state.channelById.has(m)) : [];
  const meetChips = meets.length > 1 ? `<div class="section"><h3>${esc(t('crossings_title'))}${cr.confidence === 'medium' ? ` · <span class="muted">${esc(t('some_sources'))}</span>` : ''}</h3>
    <div class="tags">${meets.map((m) => `<button class="tag button chip-like" data-chan="${m}"><span class="dot" style="background:${color(m)}"></span>${esc(shortName(m))}</button>`).join('')}</div></div>` : '';
  const other = ex.other_names?.length ? `<div class="section"><h3>${esc(t('other_names'))}</h3><p class="text">${esc(ex.other_names.join(', '))}</p></div>` : '';
  // what the point is for (traditional view): a lead line, 2 functions shown, indications folded
  const fns = Array.isArray(ex.functions) ? ex.functions : [];
  const fnOpen = state.expanded.has('fns');
  const fnHtml = fns.length ? `<div class="section"><h3>${esc(t('functions_title'))}</h3><ul class="bullets">${(fnOpen ? fns : fns.slice(0, 2)).map((f) => `<li>${esc(f)}</li>`).join('')}</ul>
    ${fns.length > 2 ? `<button class="more" data-toggle="fns">${esc(fnOpen ? t('less') : t('more_n', { n: fns.length - 2 }))}</button>` : ''}</div>` : '';
  const ind = Array.isArray(ex.indications) ? ex.indications : [];
  const indOpen = state.expanded.has('ind');
  const indHtml = ind.length ? `<div class="section"><button class="row-btn ind-head" data-toggle="ind" aria-expanded="${indOpen}">
      <span class="name"><span class="row-title">${esc(t('indications_title'))}</span><span class="row-sub">${esc(ind.map((g) => t(`ind_${g.g}`)).join(' · '))}</span></span><span class="chev">${indOpen ? '⌄' : '›'}</span></button>
    ${indOpen ? `<dl class="ind">${ind.map((g) => `<dt>${esc(t(`ind_${g.g}`))}</dt><dd>${esc(g.items.join(', '))}</dd>`).join('')}</dl>` : ''}
    <p class="note">${esc(t('ind_note'))}</p></div>` : '';
  // a luo point: say right away where its connecting branch goes (the owner looked for it on the body)
  const luo = (cats.includes('luo') || cats.includes('great_luo')) ? d.luoLinks.find((x) => x.from === code) : null;
  const luoRow = luo?.to_meridian ? `<p class="luo-row"><span class="dot" style="background:${color(luo.to_meridian)}"></span>
    <button class="link" data-chan="${luo.to_meridian}">${esc(t('luo_to', { name: shortName(luo.to_meridian) }))}</button>${luo.to ? ` · <button class="link" data-act="showluo" data-from="${code}" data-to="${luo.to}">${esc(t('show_branch'))}</button>` : ''}</p>` : '';
  const crossNote = (code === 'GI19' || code === 'GI20') ? `<p class="text meaning">${esc(t('li_cross'))}</p>` : '';
  const here = pathPoint() === code ? `<p class="path-here">● ${esc(t('path_here'))}</p>` : '';
  // how to find it on one's own body: position, numbered steps, an optional cun ruler from a reference point
  const steps = Array.isArray(ex.find_steps) ? ex.find_steps : [];
  const find = extra.find || {};
  const rulerOk = find.ref && find.cun > 0 && d.coords[find.ref] && d.coords[code];
  const findHtml = steps.length || ex.finding_hint || info?.setup ? `<div class="section find"><h3>${esc(t('find_title'))}</h3>
    ${ex.find_pose ? `<p class="text muted">${esc(ex.find_pose)}</p>` : ''}
    ${steps.length ? `<ol class="steps">${steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>` : ''}
    ${ex.finding_hint ? `<p class="text tip">${esc(ex.finding_hint)}</p>` : (!steps.length && info?.setup ? `<p class="text">${esc(info.setup)}</p>` : '')}
    ${rulerOk ? `<button class="tag button chip-like ruler-btn" data-act="ruler" data-from="${find.ref}" data-to="${code}" data-cun="${find.cun}">📏 ${esc(t('ruler_show', { n: fmtCun(find.cun), code: find.ref }))}</button>` : ''}
    ${rulerOk || /цун|cun|\bsun\b/i.test(steps.join(' ') + (ex.finding_hint || '')) ? `<p class="note">${esc(t('cun_note'))}</p>` : ''}</div>` : '';
  const nm = d.pointNames?.[code];
  const hanzi = nm?.hanzi ? `<p class="text muted hanzi"><span lang="zh">${esc(nm.hanzi)}</span> · ${esc(nm.pinyin_tone || nm.pinyin || '')}</p>` : '';
  // what the point is comes first; the caution sits with "where it is" (it opened the card before the
  // point was even named, council round 2)
  return `${here}${hanzi}
    ${ex.why ? `<p class="text lead">${esc(ex.why)}</p>` : ''}
    ${luoRow}${crossNote}
    ${ex.name_meaning ? `<p class="text meaning">${esc(t('meaning', { text: ex.name_meaning }))}</p>` : ''}
    ${keys.length ? `<div class="tags">${badges}</div>${explain}` : ''}
    ${info?.location ? `<div class="section"><h3>${esc(t('location_title'))}</h3>${cautions}<p class="text big">${esc(info.location.charAt(0).toUpperCase() + info.location.slice(1))}</p></div>` : cautions}
    ${findHtml}
    ${fnHtml}
    ${indHtml}
    ${meetChips}
    ${other}
    <p class="note">${esc(t('source'))}: ${esc(t('source_line'))}</p>`;
}

function vesselBody(v) {
  const d = state.data;
  const tx = v.text;
  const rows = v.path.map((code) => {
    const owner = d.pointOwner.get(code);
    return `<button class="row-btn" data-goto="${code}"><span class="code">${esc(dispCode(code))}</span><span class="name">${esc(pointName(code))}<span class="row-sub">${esc(shortName(owner))}${v.disputed.has(code) ? ` · ${esc(t('some_sources'))}` : ''}</span></span><span class="dot" style="background:${color(owner)}"></span></button>`;
  }).join('');
  return `${tx.short ? `<p class="text">${esc(tx.short)}</p>` : ''}
    <button class="row-btn" data-goto="${v.confluent}"><span class="name"><span class="row-sub">${esc(t('opening_title'))}</span>${esc(v.confluent)} ${esc(pointName(v.confluent))} · ${esc(shortName(d.pointOwner.get(v.confluent)))}</span><span class="chev">›</span></button>
    ${v.pairId ? `<button class="row-btn" data-chan="${v.pairId}"><span class="name">${esc(t('pair_with', { name: shortName(v.pairId) }))} · ${esc(v.coupled)}</span><span class="chev">›</span></button>` : ''}
    <p class="text muted">${esc(t('no_own_points'))}</p>
    ${profileSection(v.id)}
    ${tx.practice ? `<div class="section"><h3>${esc(t('practice'))}</h3>${clampText('vpractice', tx.practice)}</div>` : ''}
    ${tx.course ? `<div class="section"><h3>${esc(t('course_title'))}</h3><p class="text">${richText(tx.course)}</p></div>` : ''}
    ${tx.description ? `<div class="section"><h3>${esc(t('description_title'))}</h3><p class="text">${richText(tx.description)}</p></div>` : ''}
    <div class="section"><h3>${esc(t('route_points'))}</h3><div class="rows">${rows}</div></div>`;
}

function onSheetClick(e) {
  const el = e.target.closest('button');
  if (!el || el.disabled) return;
  const ds = el.dataset;
  const lv = state.level;
  if (ds.act === 'flow') { toggleFlow(); return; }
  if (ds.act === 'prev') { stepPoint(-1); return; }
  if (ds.act === 'next') { stepPoint(1); return; }
  if (ds.act === 'closemenu') { back(); return; }
  if (el.closest('.intro')) state.introSession = false;
  if (ds.act === 'introsearch') {
    setSheet('full');
    const inp = els.body.querySelector('input[type="search"], .sym-input, input');
    inp?.scrollIntoView({ block: 'center' });
    inp?.focus();
    return;
  }
  if (ds.act === 'introposes') { openPoses(); return; }
  if (ds.symg) {
    symptom.g = symptom.g === ds.symg ? null : ds.symg;
    symptom.more = false;
    for (const b of els.body.querySelectorAll('[data-symg]')) { b.setAttribute('aria-selected', String(b.dataset.symg === symptom.g)); b.setAttribute('aria-pressed', String(b.dataset.symg === symptom.g)); }
    refreshSymptomResults();
    return;
  }
  if (ds.act === 'symmore') { symptom.more = true; refreshSymptomResults(); return; }
  if (ds.act === 'ruler') { showRuler(ds.from, ds.to, Number(ds.cun)); return; }
  if (ds.lang) {
    if (ds.lang !== LANG) {
      const url = new URL(location.href);
      url.searchParams.set('lang', ds.lang);
      // the reload keeps the open channel or point (it went back to the start screen)
      url.searchParams.delete('p');
      url.searchParams.delete('m');
      if (lv.view === 'point') url.searchParams.set('p', lv.code);
      else if (lv.view === 'channel') url.searchParams.set('m', lv.id);
      location.replace(url.toString());
    }
    return;
  }
  if (ds.scenery) { state.scenery = ds.scenery; store.set('scenery', state.scenery); applyScenery(); renderSheet(); return; }
  if (ds.act === 'luo') { state.luoOn = !state.luoOn; store.set('luo_links', state.luoOn); applySelection(); renderSheet(); return; }
  if (ds.act === 'slow') {
    state.flowSlow = !state.flowSlow;
    store.set('flow_slow', state.flowSlow);
    if (scene.flowPlaying) startFlow({ force: true });
    renderSheet();
    return;
  }
  if (ds.act === 'showluo') {
    const box = new THREE.Box3();
    for (const code of [ds.from, ds.to]) { const pp = scene.pointPosition(code, lv.side || 1); if (pp) box.expandByPoint(pp.p); }
    if (!box.isEmpty()) scene.frameBox(box, new THREE.Vector3(0.3, 0.3, 1), { minRadius: 0.06 });
    return;
  }
  if (ds.tab) { state.posesTab = ds.tab; renderSheet(); return; }
  if (ds.body) { setBody(ds.body); return; }
  if (ds.pose) { choosePose(ds.pose); return; }
  if (ds.toggle) {
    const key = ds.toggle;
    const group = key.split(':')[0];
    if (state.expanded.has(key)) state.expanded.delete(key);
    else {
      if (group === 'tag' || group === 'badge') for (const k of [...state.expanded]) if (k.startsWith(`${group}:`)) state.expanded.delete(k);
      state.expanded.add(key);
    }
    renderSheet();
    return;
  }
  if (ds.filter) { state.special = ds.filter === 'special'; applySelection(); renderSheet(); return; }
  if (ds.chan) { state.overlay = state.overlay === 'list' ? null : state.overlay; selectChannel(ds.chan); return; }
  if (ds.act === 'tosearch') { backToSearch(); return; }
  if (ds.goto) {
    // a point found by a complaint: ‹ › step through the found points and back returns to the list
    // (back led to a channel nobody had opened and the list was lost, UX council round 3)
    if (el.closest('#symResults')) {
      searchTrail = { list: symptomMatches().map((r) => r.code), q: symptom.q, inMenu: state.overlay === 'list' };
    }
    openPoint(ds.goto, undefined, { fromSearch: !!el.closest('#symResults') });
    return;
  }
  if (ds.point) openPoint(ds.point, lv.side);
}
els.peek.addEventListener('click', onSheetClick);
els.body.addEventListener('click', onSheetClick);
// typing in the symptom search updates only the results, so the field keeps focus and the keyboard stays up
els.body.addEventListener('input', (e) => {
  if (e.target.id !== 'symInput') return;
  symptom.q = e.target.value;
  symptom.more = false;
  refreshSymptomResults();
});

// ---------------------------------------------------------------- floating buttons

let facing = 'front';
// "show whole": the whole figure, also with a point open (it kept the close-up, council); pressed again
// with the whole figure in view, it goes back to the point or channel
var wholeShown = false;
$('fitBtn').addEventListener('click', () => {
  const lv = state.level;
  if (wholeShown || (lv.view === 'home' && state.overlay !== 'poses')) { wholeShown = false; $('fitBtn').setAttribute('aria-pressed', 'false'); fitCurrent(); return; }
  wholeShown = true;
  $('fitBtn').setAttribute('aria-pressed', 'true');
  scene.setView(facing);
});
function fitCurrent() {
  const lv = state.level;
  if (state.overlay === 'poses' && isMudraOn()) { frameHands(); return; }
  if (state.overlay === 'poses' && isArmPos() && lv.view === 'home') { frameArms(); return; }
  if (lv.view === 'point') scene.focusPoint(lv.code, lv.side || 1, { distance: pointDistance(lv.code) });
  else if (lv.view === 'channel') frameChannel(state.channelById.get(lv.id));
  else scene.setView(facing);
}
let turnTimer = null;
let longPressed = false;
$('turnBtn').addEventListener('pointerdown', () => {
  longPressed = false;
  turnTimer = setTimeout(() => {
    longPressed = true;
    facing = facing === 'left' ? 'right' : 'left';
    scene.setView(facing);
    haptic('light');
  }, 500);
});
$('turnBtn').addEventListener('pointerup', () => clearTimeout(turnTimer));
$('turnBtn').addEventListener('click', () => {
  if (longPressed) return;
  // with a point open: the same point on the other side of the body (turning the camera round the point
  // looked at it from inside the head, council)
  const lv = state.level;
  const owner = lv.view === 'point' ? state.channelById.get(lv.id) : null;
  if (owner && !owner.midline) {
    lv.side = -(lv.side || 1);
    scene.focusPoint(lv.code, lv.side, { distance: pointDistance(lv.code) });
    applySelection();
    haptic('light');
    // the button means "turn" elsewhere; here it changes the side, so say which one is shown (UX round 3).
    // side +1 is the body's left (+x)
    toast(t(lv.side > 0 ? 'side_left' : 'side_right'));
    return;
  }
  // a midline point (Du Mai / Ren Mai) has no other side: the whole figure from the opposite side
  // instead of orbiting the point through the body
  if (owner && owner.midline) {
    facing = facing === 'front' ? 'back' : 'front';
    wholeShown = true;
    scene.setView(facing);
    haptic('light');
    return;
  }
  facing = facing === 'front' ? 'back' : 'front';
  const tgt = scene.controls.target.clone();
  const off = scene.camera.position.clone().sub(tgt);
  off.x = -off.x;
  off.z = -off.z;
  scene.flyTo(tgt, tgt.clone().add(off));
});
$('poseBtn').addEventListener('click', () => (state.overlay === 'poses' ? closePoses({ refocus: true }) : openPoses()));
// female / male: its own button, the switch inside the poses panel was too hard to find
function renderBodyBtn() {
  const b = $('bodyBtn');
  if (!b) return;
  const male = state.body === 'male';
  // drawn like the other buttons (the ♀/♂ text glyphs were thin and font-dependent, artist round 2)
  const g = male
    ? '<circle cx="10" cy="14" r="5"/><path d="M13.6 10.4 19 5M14.5 5H19v4.5"/>'
    : '<circle cx="12" cy="9" r="5"/><path d="M12 14v7M9 18h6"/>';
  b.innerHTML = `<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${g}</g></svg>`;
  b.setAttribute('aria-label', t('body_switch_aria', { name: t(male ? 'body_m_aria' : 'body_f_aria') }));
}
$('bodyBtn').addEventListener('click', async () => {
  await ensurePoses();
  const next = state.body === 'male' ? 'female' : 'male';
  await setBody(next);
  renderBodyBtn();
  // only when it really switched (without the poses setBody returns quietly)
  if (state.body === next) toast(t(next === 'male' ? 'body_switched_m' : 'body_switched_f'));
  else toast(t('poses_unavailable'));
});
renderBodyBtn();
function openMenu() {
  if (!state.data) return;
  if (state.overlay === 'poses') closePoses({ refocus: false });
  // over the open channel or point without resetting it (setLevel cleared the open sections, the ruler
  // and stopped the flow, which did not come back, council round 2)
  state.overlay = 'list';
  hideNext();
  els.pick.hidden = true;
  renderSheet();
  els.body.scrollTop = 0;
  setSheet('full');
  updateBackButton();
}
$('menuBtn').addEventListener('click', openMenu);

// ---------------------------------------------------------------- poses

const poseSys = { mod: null, rig: null, skinner: null, segments: [], seg: 0, t0: 0, variantRest: {}, variantEyes: {}, morph: null, loading: null };

// the pose module and its data, fetched together with the body model at start (the start pose is
// a pose of the rig: arms a little out with the palms forward, not the A-pose the model is rigged in)
function prefetchPoses() {
  const json = (u) => fetch(u).then((res) => { if (!res.ok) throw new Error(`${u}: ${res.status}`); return res.json(); });
  const p = {
    mod: import('./pose.js'),
    rig: json(`assets/rig.json?v=${ASSET_VERSION}`),
    poses: json(`assets/poses.json?v=${ASSET_VERSION}`),
  };
  for (const k of Object.keys(p)) p[k].catch(() => {});   // failures surface in ensurePoses, not as unhandled
  return p;
}

// Put the figure into the current body pose at once (start: the stand pose) before the loader goes;
// without the pose data in a few seconds the rigged A-pose stays
async function applyStartPose() {
  const ready = ensurePoses().then(() => !!poseSys.skinner);
  const ok = await Promise.race([ready, new Promise((r) => setTimeout(() => r(false), 6000))]);
  if (!ok) return;
  const pos = poseSys.skinner.apply(state.pose, state.mudra, 1);
  scene.setBodyPositions(pos, eyePositions(), { normals: true });
  scene.refitBvh();
}

async function ensurePoses() {
  if (poseSys.loading) return poseSys.loading;
  poseSys.loading = (async () => {
    state.poseContent = state.poseContent || await loadPoseContent();
    try {
      const pre = poseSys.prefetch || prefetchPoses();
      poseSys.prefetch = null;
      poseSys.mod = await pre.mod;
      poseSys.rig = await poseSys.mod.loadRig(pre.rig, pre.poses);
      poseSys.skinner = poseSys.mod.createSkinner(poseSys.rig, scene.restPositions, state.body);
    } catch (err) {
      console.warn('poses unavailable', err);
      poseSys.mod = null;
    }
  })();
  return poseSys.loading;
}

// A photo behind the figure (chosen in the poses sheet). It stays when the poses sheet closes and channels
// are picked: tied to the sheet, it vanished on every channel change and had to be switched on again.
function applyScenery() {
  const on = state.scenery !== 'off';
  if (on) $('backdrop').dataset.photo = state.scenery;
  document.body.classList.toggle('scenery', on);
}

async function openPoses() {
  state.overlay = 'poses';
  applyScenery();
  $('poseBtn').setAttribute('aria-pressed', 'true');
  hideNext();
  setSheet('peek', { silent: true });
  renderSheet();
  await ensurePoses();
  renderSheet();
  applySelection();
  updateBackButton();
}

function closePoses({ refocus }) {
  state.overlay = null;
  applyScenery();
  $('poseBtn').setAttribute('aria-pressed', 'false');
  setSheet('peek', { silent: true });
  applySelection();
  renderSheet();
  updateBackButton();
  if (refocus) setLevel(state.level);
}

function poseItems(kind) {
  const c = state.poseContent;
  if (!c) return [];
  const order = kind === 'asanas' ? ASANA_ORDER : kind === 'arms' ? ARM_ORDER : MUDRA_ORDER;
  const list = (kind === 'asanas' ? c.asanas : kind === 'arms' ? c.arm_positions : c.mudras) || [];
  return order.map((id) => list.find((x) => x.id === id)).filter(Boolean);
}
const poseText = (item) => (item?.i18n?.[LANG] || item?.i18n?.en || {});

function renderPosesPeek() {
  const tab = state.posesTab;
  const items = poseItems(tab);
  const active = tab === 'asanas' ? state.pose : state.mudra;
  const cards = items.map((it) => {
    const tx = poseText(it);
    const name = (tx.name || it.id).split('(')[0].trim();
    return `<button class="pose-card" data-pose="${it.id}" aria-pressed="${it.id === active}"><span class="pose-name">${esc(name)}</span>${it.sanskrit ? `<span class="pose-sk">${esc(it.sanskrit)}</span>` : ''}</button>`;
  }).join('');
  const cur = items.find((x) => x.id === active);
  els.sheet.style.removeProperty('--chan');
  const prevScroll = els.peek.querySelector('.pose-row')?.scrollLeft || 0;
  els.peek.innerHTML = `<div class="poses-head">
      <div class="seg" role="tablist">${['asanas', 'mudras', 'arms'].map((k) => `<button role="tab" data-tab="${k}" aria-selected="${tab === k}">${esc(t(`tab_${k}`))}</button>`).join('')}</div>
    </div>
    <div class="pose-row">${cards || `<span class="muted">${esc(poseSys.loading ? t('poses_loading') : t('poses_unavailable'))}</span>`}</div>
    <div class="peek-sub pose-desc">${esc(poseText(cur).short || '')}</div>
    ${tab === 'mudras' && isMudraOn() && state.mudra !== 'hakini' && state.mudra !== 'anjali' ? `<div class="peek-sub closeup-hint">${esc(t('closeup_hint'))}</div>` : ''}`;
  // keep the row where it was and bring the chosen card into view (padmasana stayed off screen)
  const row = els.peek.querySelector('.pose-row');
  if (row) {
    row.scrollLeft = prevScroll;
    // after layout: drawn before it (a pose from a link while the sheet opens) the boxes were all zero
    requestAnimationFrame(() => row.querySelector('[aria-pressed="true"]')?.scrollIntoView({ inline: 'nearest', block: 'nearest' }));
  }
  if (state.sheet === 'peek') document.documentElement.style.setProperty('--sheet-visible', `${sheetVisible('peek')}px`);
}

function sceneryRowHtml() {
  return `<div class="scenery-row"><span class="scenery-label">${esc(t('scenery_toggle'))}</span><div class="scenery-opts" role="tablist">${[...SCENERY, 'off'].map((v) => `<button role="tab" data-scenery="${v}" aria-selected="${state.scenery === v}">${esc(t(`scenery_${v}`))}</button>`).join('')}</div></div>`;
}
function langRowHtml() {
  return `<div class="scenery-row"><span class="scenery-label">${esc(t('lang_label'))}</span><div class="scenery-opts" role="tablist">${LANGS.map((l) => `<button role="tab" data-lang="${l}" lang="${l === 'kz' ? 'kk' : l}" aria-selected="${LANG === l}">${esc(LANG_NAMES[l])}</button>`).join('')}</div></div>`;
}

function posesBody() {
  const tab = state.posesTab;
  const item = poseItems(tab).find((x) => x.id === (tab === 'asanas' ? state.pose : state.mudra));
  if (!item) return '';
  const tx = poseText(item);
  const disclaimer = state.poseContent?.disclaimer_i18n?.[LANG] || '';
  const chips = (ids) => ids.map((id) => `<button class="tag button chip-like" data-chan="${id}"><span class="dot" style="background:${color(id)}"></span>${esc(shortName(id))}</button>`).join('');
  const sceneryRow = sceneryRowHtml();
  if (tab === 'asanas' || tab === 'arms') {
    return `${sceneryRow}<h2 class="card-h">${esc(tx.name || item.id)}${item.sanskrit ? ` <span class="muted">${esc(item.sanskrit)}</span>` : ''}</h2>
      ${tx.how ? `<div class="section"><h3>${esc(t('how_title'))}</h3><p class="text">${esc(tx.how)}</p></div>` : ''}
      ${(item.emphasized_meridians || []).length ? `<div class="section"><h3>${esc(t('focus_channels'))}</h3><div class="tags">${chips(item.emphasized_meridians)}</div></div>` : ''}
      ${tx.meridians_note ? `<p class="text">${esc(tx.meridians_note)}</p>` : ''}
      ${tx.practice ? `<div class="section"><h3>${esc(t('practice'))}</h3><p class="text">${esc(tx.practice)}</p></div>` : ''}
      ${disclaimer ? `<p class="note">${esc(disclaimer)}</p>` : ''}`;
  }
  const pts = item.contact_points || [];
  const fm = state.poseContent?.finger_meridians || {};
  const pairs = [];
  if (item.id !== 'open') {
    const owners = pts.map((c) => [c, state.data.pointOwner.get(c)]).filter(([, o]) => o);
    if (item.id === 'hakini' || item.id === 'anjali') {
      for (const [c, o] of owners) pairs.push(`<span class="pair-chip"><span class="dot" style="background:${color(o)}"></span>${esc(shortName(o))} ${esc(c)} ↔ ${esc(c)}</span>`);
    } else if (owners.length) {
      const [thumb, ...rest] = owners;
      for (const [c, o] of rest) pairs.push(`<span class="pair-chip"><span class="dot" style="background:${color(thumb[1])}"></span>${esc(shortName(thumb[1]))} ${esc(thumb[0])} ↔ <span class="dot" style="background:${color(o)}"></span>${esc(shortName(o))} ${esc(c)}</span>`);
    }
  }
  void fm;
  return `${sceneryRow}<h2 class="card-h">${esc(tx.name || item.id)}${item.sanskrit ? ` <span class="muted">${esc(item.sanskrit)}</span>` : ''}</h2>
    ${pairs.length ? `<div class="section"><h3>${esc(t('connects'))}</h3><div class="pairs">${pairs.join('')}</div></div>` : ''}
    ${(item.connected_meridians || []).length ? `<div class="tags">${chips(item.connected_meridians.filter((id) => state.channelById.has(id)))}</div>` : ''}
    ${tx.meridians_note ? `<p class="text">${esc(tx.meridians_note)}</p>` : ''}
    ${tx.how ? `<div class="section"><h3>${esc(t('how_title'))}</h3><p class="text">${esc(tx.how)}</p></div>` : ''}
    ${tx.practice ? `<div class="section"><h3>${esc(t('practice'))}</h3><p class="text">${esc(tx.practice)}</p></div>` : ''}
    <p class="note">${esc(t('mudra_note'))}</p>
    ${disclaimer ? `<p class="note">${esc(disclaimer)}</p>` : ''}`;
}

function choosePose(id) {
  if (!poseSys.skinner) { toast(t('poses_unavailable')); return; }
  wholeShown = false;    // a new pose is framed afresh; "show whole" starts from it (council round 2)
  const tab = state.posesTab;
  const prevBody = state.pose;
  if (tab === 'asanas') {
    state.pose = id;
    const def = state.poseContent?.asanas?.find((a) => a.id === id);
    if (id === 'vrikshasana' && state.mudra === 'open') state.mudra = def?.defaultHand || 'open';
  } else {
    // mudras and arm positions share the hand slot; the body keeps its pose either way
    state.mudra = id;
  }
  scheduleTransition(prevBody, state.pose, state.mudra);
  haptic();
  renderSheet();
  applySelection();
}

function scheduleTransition(fromBody, toBody, hand) {
  const g0 = POSE_GROUP[fromBody];
  const g1 = POSE_GROUP[toBody];
  const segs = [];
  const handNow = hand;
  if (g0 !== g1 && (g0 === 'seated' || g1 === 'seated') && fromBody !== 'dandasana' && toBody !== 'dandasana' && !(g0 === 'standing' && g1 === 'kneeling') && !(g0 === 'kneeling' && g1 === 'standing')) {
    const first = g0 === 'standing' ? 900 : 700;
    const second = g1 === 'standing' ? 900 : 700;
    segs.push({ body: 'dandasana', hand: 'open', ms: first, ease: (k) => k * k });
    segs.push({ body: toBody, hand: handNow, ms: second, ease: (k) => 1 - (1 - k) * (1 - k) });
  } else {
    const ms = g0 === g1 ? 800 : (g0 === 'kneeling' || g1 === 'kneeling') ? 1000 : 900;
    segs.push({ body: toBody, hand: handNow, ms, ease: (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2) });
  }
  if (reducedMotion.matches) for (const s of segs) s.ms = 1;
  poseSys.segments = segs;
  poseSys.seg = 0;
  poseSys.t0 = performance.now();
  scene.stopFlow(true);
  scene.requestRender();
}

function poseFrame(now) {
  let changed = false;
  if (poseSys.morph) {
    const m = poseSys.morph;
    const k = Math.min(1, (now - m.t0) / m.ms);
    const out = poseSys.morphBuf;
    for (let i = 0; i < out.length; i++) out[i] = m.a[i] + (m.b[i] - m.a[i]) * k;
    scene.setBodyPositions(out, eyePositions(), { normals: true });
    if (k >= 1) { poseSys.morph = null; scene.refitBvh(); afterPose(); }
    return true;
  }
  if (!poseSys.segments.length || !poseSys.skinner) return changed;
  const seg = poseSys.segments[poseSys.seg];
  const k = Math.min(1, (now - poseSys.t0) / seg.ms);
  const pos = poseSys.skinner.apply(seg.body, seg.hand, seg.ease(k));
  scene.setBodyPositions(pos, eyePositions(), { normals: (Math.floor(now / 16) % 2) === 0 || k >= 1 });
  if (k >= 1) {
    poseSys.seg += 1;
    poseSys.t0 = now;
    if (poseSys.seg >= poseSys.segments.length) {
      poseSys.segments = [];
      scene.refitBvh();
      afterPose();
    }
  }
  return true;
}

function eyePositions() {
  if (!poseSys.skinner || !scene.eyeRest) return null;
  return scene.eyeRest.map((rest) => poseSys.skinner.skinRigid(rest));
}

function afterPose() {
  haptic('light');
  if (state.overlay === 'poses' && isMudraOn() && state.level.view === 'home') { frameHands(); setTimeout(startFlow, 750); return; }
  fitCurrent();
  setTimeout(startFlow, 750);
}

function frameHands() {
  const tips = ['P11', 'GI1', 'MC9', 'TR1', 'C9', 'IG1', 'MC8', 'P9'];
  const together = state.mudra === 'hakini' || state.mudra === 'anjali';
  if (!together) {
    // hands apart (on the knees, at the thighs, out to the sides): one hand close up, three-quarter view;
    // a box round both hands and the head cut the head off or made the mudra a speck (council); "show
    // whole" gives the whole figure
    // the fingertips only (the wrist and palm points made the box 24 cm wide: a far shot on a phone)
    const box = new THREE.Box3();
    for (const code of ['P11', 'GI1', 'MC9', 'TR1', 'C9', 'IG1']) { const pp = scene.pointPosition(code, 1); if (pp) box.expandByPoint(pp.p); }
    if (box.isEmpty()) return;
    box.expandByScalar(0.012);
    const c = box.getCenter(new THREE.Vector3());
    const out = new THREE.Vector3(Math.sign(c.x) || 1, 0, 0);
    const dir = new THREE.Vector3(0, 0.6, 1).addScaledVector(out, 0.5).normalize();
    scene.frameBox(box, dir, { ms: 600, minDist: 0.22, minRadius: 0.06 });
    return;
  }
  const box = new THREE.Box3();
  for (const code of tips) for (const side of [1, -1]) {
    const pp = scene.pointPosition(code, side);
    if (pp) box.expandByPoint(pp.p);
  }
  if (box.isEmpty()) return;
  // hands at the chest: the head stays in the picture
  for (const code of ['VG20', 'VC24']) { const pp = scene.pointPosition(code, 1); if (pp) box.expandByPoint(pp.p); }
  box.expandByScalar(0.06);
  // hakini reads best from the front and above (the dome and the meeting tips); anjali from the front
  const polar = THREE.MathUtils.degToRad(state.mudra === 'hakini' ? 55 : 80);
  const dir = new THREE.Vector3(0, Math.cos(polar), Math.sin(polar));
  scene.frameBox(box, dir, { ms: 600, minDist: 0.3 });
}

// an arm position is there to open the armpit and the inner arm: from the front the raised arm hides
// the armpit (UX council 2026-11-12), so the camera looks at the upper body from 35 deg to one side;
// hands behind the head open the back of the upper arm (IG9, IG10, TR14), seen from behind and aside
const ARM_VIEW_AZ = { arms_up: 35, behind_head: 140 };
function frameArms() {
  const box = new THREE.Box3();
  for (const code of armItem()?.emphasized_points || []) for (const side of [1, -1]) {
    const pp = scene.pointPosition(code, side);
    if (pp) box.expandByPoint(pp.p);
  }
  if (box.isEmpty()) { scene.setView(facing); return; }
  // and the whole figure down to the feet with a margin above the sheet (cut at the hips, then at the toes:
  // council rounds 1 and 2)
  for (const code of ['VG20', 'E41', 'V67']) { const pp = scene.pointPosition(code, 1); if (pp) box.expandByPoint(pp.p); }
  box.expandByScalar(0.12);
  const polar = THREE.MathUtils.degToRad(78), az = THREE.MathUtils.degToRad(ARM_VIEW_AZ[state.mudra] ?? 35);
  const dir = new THREE.Vector3(Math.sin(polar) * Math.sin(az), Math.cos(polar), Math.sin(polar) * Math.cos(az));
  scene.frameBox(box, dir, { ms: 600, minDist: 0.5 });
}

async function bodyPositions(variant) {
  if (poseSys.variantRest[variant]) return poseSys.variantRest[variant];
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const gltf = await new GLTFLoader().loadAsync(`assets/body_${variant}.glb?v=${ASSET_VERSION}`);
  const meshes = [];
  gltf.scene.traverse((o) => { if (o.isMesh) meshes.push(o); });
  const body = meshes.find((m) => m.geometry.attributes.position.count > 1000);
  poseSys.variantRest[variant] = Float32Array.from(body.geometry.attributes.position.array);
  // the eyes differ per body too; skinning the old body's eyes with the new head put them under the chin
  poseSys.variantEyes[variant] = meshes.filter((m) => m !== body).map((m) => Float32Array.from(m.geometry.attributes.position.array));
  return poseSys.variantRest[variant];
}

async function setBody(variant) {
  if (variant === state.body || !poseSys.mod) return;
  const restB = await bodyPositions(variant);
  const a = Float32Array.from(scene.body.geometry.attributes.position.array);
  const skB = poseSys.mod.createSkinner(poseSys.rig, restB, variant);
  const b = Float32Array.from(skB.apply(state.pose, state.mudra, 1));
  poseSys.skinner = skB;
  if (poseSys.variantEyes[variant]?.length === scene.eyes.length) scene.eyeRest = poseSys.variantEyes[variant];
  state.body = variant;
  store.set('body', variant);
  renderBodyBtn();
  poseSys.morphBuf = new Float32Array(a.length);
  poseSys.morph = { a, b, t0: performance.now(), ms: reducedMotion.matches ? 1 : 500 };
  scene.stopFlow(true);
  scene.requestRender();
  renderSheet();
  haptic('light');
}

// ---------------------------------------------------------------- canvas input

let down = null;
let lastTap = { t: 0, x: 0, y: 0 };
function bindCanvas() {
  const el = scene.renderer.domElement;
  el.addEventListener('pointerdown', (e) => {
    down = { x: e.clientX, y: e.clientY, t: performance.now() };
    els.tooltip.hidden = true;
    touched();
  });
  el.addEventListener('pointerup', (e) => {
    if (!down) return;
    const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
    const quick = performance.now() - down.t < 300;
    down = null;
    if (moved > 10 || !quick) return;
    const nowT = performance.now();
    const dbl = nowT - lastTap.t < 300 && Math.hypot(e.clientX - lastTap.x, e.clientY - lastTap.y) < 30;
    lastTap = { t: nowT, x: e.clientX, y: e.clientY };
    handleTap(e.clientX, e.clientY, dbl);
  });
  el.addEventListener('pointermove', (e) => {
    if (e.pointerType !== 'mouse' || e.buttons) return;
    const res = scene.pick(e.clientX, e.clientY, { pointsEnabled: state.level.view !== 'home' || state.overlay === 'poses' });
    if (res.type === 'point') els.tooltip.innerHTML = `<b>${esc(res.code)} ${esc(pointName(res.code))}</b><br>${esc(shortName(res.channel))}`;
    else if (res.type === 'line' || res.type === 'link') els.tooltip.innerHTML = `<b>${esc(shortName(res.type === 'link' ? nextChannelOf(res.channel) : res.channel))}</b>`;
    else { els.tooltip.hidden = true; el.style.cursor = ''; return; }
    els.tooltip.style.left = `${e.clientX}px`;
    els.tooltip.style.top = `${e.clientY}px`;
    els.tooltip.hidden = false;
    el.style.cursor = 'pointer';
  });
  el.addEventListener('pointerleave', () => { els.tooltip.hidden = true; });
}

function touched() {
  state.lastTouch = performance.now();
  scene.idle = false;
  if (store.get('onb_gesture', false) === false) { store.set('onb_gesture', true); $('gestureHint').hidden = true; }
  if (state.autoPaused === 'idle') resumeFlow('idle');
}

function handleTap(x, y, dbl) {
  els.pick.hidden = true;
  // groups show lines only, so a tap there picks a line, not a hidden point
  const pointsEnabled = (state.level.view !== 'home' && (state.level.view !== 'group' || inCustom())) || state.overlay === 'poses';
  const res = scene.pick(x, y, { pointsEnabled });
  if (EDIT && state.editTarget && res.hit) { placeEditedPoint(res.hit); return; }
  if (dbl) {
    if (res.hit) {
      const p = res.hit.point;
      const dir = scene.camera.position.clone().sub(p).normalize();
      scene.flyTo(p.clone(), p.clone().addScaledVector(dir, Math.max(0.35, scene.camera.position.distanceTo(p) / 2.5)), { ms: 450 });
    } else fitCurrent();
    return;
  }
  if (res.type === 'cluster') {
    const dist = scene.camera.position.distanceTo(scene.controls.target);
    if (dist > 0.8 && res.hit) {
      const p = res.hit.point;
      const dir = scene.camera.position.clone().sub(p).normalize();
      scene.flyTo(p.clone(), p.clone().addScaledVector(dir, scene.camera.position.distanceTo(p) / 2));
      return;
    }
    // the name under the code: "C8 / MC8" said nothing to a newcomer (UX round 3)
    els.pick.innerHTML = res.candidates.map((c) => `<button data-code="${c.code}" data-side="${c.side}">${esc(dispCode(c.code))}<small>${esc(pointName(c.code))}</small></button>`).join('');
    els.pick.style.left = `${x}px`;
    els.pick.style.top = `${y}px`;
    els.pick.hidden = false;
    updateBackButton();
    return;
  }
  if (res.type === 'point') { openPoint(res.code, res.side); return; }
  if (res.type === 'link') { const n = nextChannelOf(res.channel); if (n) selectChannel(n); return; }
  if (res.type === 'line') {
    if (multiMode()) { toggleCustom(res.channel); return; }
    if (state.level.view !== 'home' && state.level.id === res.channel) return;
    selectChannel(res.channel);
  }
}
els.pick.addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  els.pick.hidden = true;
  openPoint(b.dataset.code, Number(b.dataset.side));
});

// ---------------------------------------------------------------- labels

const labelPool = [];
function label(i) {
  while (labelPool.length <= i) {
    const el = document.createElement('div');
    el.className = 'plabel';
    els.labels.appendChild(el);
    labelPool.push(el);
  }
  return labelPool[i];
}

function updateLabels() {
  if (!state.data) return;
  const items = [];
  const lv = state.level;
  if (state.overlay === 'poses' && lv.view === 'home' && isMudraOn()) {
    const m = state.poseContent?.mudras?.find((x) => x.id === state.mudra);
    const groups = mudraContacts(m);
    // hakini/anjali: each code touches its twin, so one label per code on the side facing the camera
    // (two per code with a cap of 6 left TR1, C9 and IG1 unlabelled)
    const paired = groups.length > 0 && groups.every((g) => g.codes.length === 1);
    const seen = new Set();
    for (const g of groups) {
      if (paired) {
        if (seen.has(g.codes[0])) continue;
        seen.add(g.codes[0]);
        items.push({ code: g.codes[0], side: null, text: dispCode(g.codes[0]), main: false, grazing: true });
        // below the point, not over the fingers that touch (the label hid the mudra's contact, council)
      } else items.push({ code: g.codes[0], side: g.side, text: g.codes.map(dispCode).join(' · '), main: false, below: true });
    }
  } else if (state.overlay === 'poses' && lv.view === 'home' && isArmPos()) {
    // the points the arm position opens (armpit, side of the chest), on the side facing the camera
    for (const code of armItem()?.emphasized_points || []) items.push({ code, side: null, text: dispCode(code), main: false });
  } else if (lv.view === 'point') {
    const ch = state.channelById.get(lv.id);
    const idx = ch.points.indexOf(lv.code);
    items.push({ code: lv.code, side: lv.side || 1, text: `${dispCode(lv.code)} · ${pointName(lv.code)}`, main: true });
    for (const c of [ch.points[idx - 1], ch.points[idx + 1]]) if (c) items.push({ code: c, side: lv.side || 1, text: dispCode(c) });
    // the end of the luo branch is labelled with the channel it joins
    const luo = state.luoOn ? state.data.luoLinks.find((x) => x.from === lv.code && x.to && x.to_meridian) : null;
    if (luo) items.push({ code: luo.to, side: lv.side || 1, text: `→ ${shortName(luo.to_meridian)} · ${dispCode(luo.to)}` });
  } else if (lv.view === 'channel') {
    const ch = state.channelById.get(lv.id);
    if (ch.kind === 'vessel') {
      for (const c of [ch.confluent, ch.coupled]) if (c) items.push({ code: c, side: null, text: dispCode(c) });
    } else {
      items.push({ code: ch.points[0], side: null, text: dispCode(ch.points[0]) });
      items.push({ code: ch.points[ch.points.length - 1], side: null, text: dispCode(ch.points[ch.points.length - 1]) });
    }
  }
  let used = 0;
  const placed = [];
  for (const it of items) {
    let pp = null;
    if (it.side == null) {
      const s = scene.sideFacingCamera(it.code);
      pp = scene.pointPosition(it.code, s);
    } else pp = scene.pointPosition(it.code, it.side);
    if (!pp) continue;
    // fingertips pressed together face each other, edge-on to the camera: shown when nothing hides them
    if (it.grazing ? !(scene.isVisible(pp.p, pp.n, -0.35) && scene.unoccluded(pp.p)) : !scene.isVisible(pp.p, pp.n)) continue;
    const [sx, sy, sz] = scene.toScreen(pp.p);
    if (sz > 1 || sx < 0 || sx > window.innerWidth || sy < 0 || sy > window.innerHeight - sheetVisible()) continue;
    // not under the column of round buttons on the right
    if (!it.main && sx > window.innerWidth - 64 && state.sheet !== 'full') continue;
    // points closer than a label's height share one label (C9 and IG1 sit on the same little fingertip);
    // three or more read "IG9 +2" instead of a stack of codes over the arm (artist of the council)
    // (a label is ~22 px tall: at 18 px IG9 and VB22 still touched in the hands-behind-head view, artist round 3)
    const near = placed.find((q) => Math.abs(q.sx - sx) < 46 && Math.abs(q.sy - sy) < 23);
    if (near) {
      if (!it.main) {
        near.extra += 1;
        near.el.textContent = near.extra === 1 ? `${near.first} · ${it.text}` : `${near.first} +${near.extra}`;
        continue;
      }
    }
    const el = label(used++);
    placed.push({ sx, sy, el, first: it.text, extra: 0 });
    el.textContent = it.text;
    el.className = `plabel${it.main ? ' main' : ''}${sy < 110 || it.below ? ' below' : ''}`;
    el.style.transform = `translate(${Math.round(sx)}px, ${Math.round(sy)}px)`;
    el.hidden = false;
  }
  for (let i = used; i < labelPool.length; i++) labelPool[i].hidden = true;
}

// ---------------------------------------------------------------- markup mode

const EDITS_KEY = 'meridian3d-edits-v2';
state.editTarget = null;
function renderEditbar() {
  if (!EDIT) return;
  state.editTarget = state.level.view === 'point' ? state.level.code : null;
  $('editbar').hidden = false;
  $('editText').textContent = state.editTarget ? t('edit_target', { code: state.editTarget }) : t('edit_idle');
}
function placeEditedPoint(hit) {
  const code = state.editTarget;
  const side = hit.point.x < 0 ? -1 : 1;
  const n = hit.face.normal.clone();
  const att = scene.skin.attach(hit.point, hit.faceIndex);
  const entry = { p: [hit.point.x * side, hit.point.y, hit.point.z].map((x) => +x.toFixed(4)), n: [n.x * side, n.y, n.z].map((x) => +x.toFixed(3)) };
  if (side === 1) { entry.tri = att.tri; entry.bary = att.bary.map((x) => +x.toFixed(5)); }
  const edits = store.get(EDITS_KEY, {});
  edits[code] = entry;
  store.set(EDITS_KEY, edits);
  state.data.coords[code] = entry;
  scene.buildChannels([...state.data.channels, ...state.data.vessels], state.data.coords, state.data.via);
  applyPointMeta();
  applySelection();
  $('editText').textContent = t('edit_saved', { code });
}
if (EDIT) {
  $('editExport').textContent = t('edit_export');
  $('editReset').textContent = t('edit_reset');
  $('editExport').addEventListener('click', async () => {
    const out = $('editOutput');
    out.value = JSON.stringify({ version: 2, status: 'draft', points: state.data.coords, via: state.data.via }, null, 1);
    out.hidden = false;
    try { await navigator.clipboard.writeText(out.value); $('editText').textContent = t('edit_copied'); } catch { out.select(); }
  });
  $('editReset').addEventListener('click', () => { store.set(EDITS_KEY, {}); location.reload(); });
}

// ---------------------------------------------------------------- boot

function applyPointMeta() {
  scene.setPointMeta((code, chId) => {
    const cats = state.data.pointCats[code] || [];
    const ch = state.channelById.get(chId);
    return {
      shape: cats.includes('confluent') ? 2 : (cats.includes('luo') || cats.includes('great_luo')) ? 1 : 0,
      special: ch ? isSpecial(ch, code) : false,
    };
  });
}

function applyTheme() {
  document.documentElement.dataset.theme = theme();
  if (!scene) return;
  scene.setTheme(theme());
  if (state.data) { renderChips(); renderSheet(); applySelection(); }
}

function setLoading(text, { error = false, progress = null } = {}) {
  $('loadingText').textContent = text;
  $('spinner').hidden = error;
  $('retryBtn').hidden = !error;
  if (progress != null) $('progressBar').style.transform = `scaleX(${progress})`;
}

function webglAvailable() {
  try {
    const c = document.createElement('canvas');
    return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')));
  } catch { return false; }
}

function deepLink() {
  const d = state.data;
  const pRaw = params.get('p') || startTokens.p;
  const mRaw = params.get('m') || startTokens.m || params.get('v');
  if (pRaw) {
    const code = normalizeCode(pRaw);
    if (d.pointOwner.has(code)) { openPoint(code, undefined, { instant: true }); setSheet('half'); return true; }
    toast(t('point_not_found', { code: pRaw }));
    return false;
  }
  if (mRaw) {
    let id = mRaw.toLowerCase();
    if (!state.channelById.has(id)) {
      const code = normalizeCode(`${mRaw}1`).replace(/1$/, '');
      id = [...state.channelById.values()].find((c) => c.points[0]?.replace(/\d+$/, '') === code)?.id;
    }
    if (id && state.channelById.has(id)) { selectChannel(id, { instant: true }); return true; }
  }
  return false;
}

let booting = false;
async function boot() {
  if (booting) return;
  booting = true;
  document.documentElement.lang = LANG === 'kz' ? 'kk' : LANG;
  document.title = t('app_title');
  document.documentElement.dataset.theme = theme();
  $('retryBtn').textContent = t('retry');
  for (const [id, key] of [['menuBtn', 'aria_menu'], ['turnBtn', 'aria_turn'], ['fitBtn', 'aria_fit'], ['poseBtn', 'aria_pose']]) $(id).setAttribute('aria-label', t(key));
  setLoading(t('loading'));
  if (tg) {
    tg.ready();
    tg.expand();
    try { if (tg.isVersionAtLeast?.('7.7')) tg.disableVerticalSwipes(); } catch { /* old client */ }
    try { tg.setHeaderColor?.('bg_color'); } catch { /* old client */ }
    tg.BackButton?.onClick(back);
    try { if (tg.isVersionAtLeast?.('7.0')) { tg.SettingsButton.show(); tg.SettingsButton.onClick(() => { openMenu(); document.getElementById('prefs')?.scrollIntoView({ block: 'start' }); }); } } catch { /* old client */ }
    tg.onEvent?.('themeChanged', applyTheme);
    tg.onEvent?.('viewportChanged', () => { setSheet(state.sheet, { silent: true }); scene?.resize(); });
    tg.onEvent?.('activated', () => { if (scene) scene.paused = false; resumeFlow('hidden'); });
    tg.onEvent?.('deactivated', () => { if (scene) scene.paused = true; pauseFlow('hidden'); });
  }
  if (!webglAvailable()) {
    setLoading(t('no_webgl'), { error: true });
    $('retryBtn').hidden = true;
    booting = false;
    return;
  }
  const slow = setTimeout(() => setLoading(t('slow_net')), 8000);
  const fail = setTimeout(() => setLoading(t('load_error'), { error: true }), 25000);
  try {
    if (!scene) {
      scene = new MeridianScene($('stage'), { theme: theme(), getViewport: viewportInsets });
      scene.onFrame = (now) => {
        const posed = poseFrame(now);
        if (scene.flowPlaying && performance.now() - state.lastTouch > 60000) { scene.idle = true; pauseFlow('idle'); }
        return posed;
      };
      scene.onRendered = updateLabels;
      scene.onUserMove = () => { touched(); els.pick.hidden = true; };
      scene.onFlowPass = (n) => {
        if (n !== 1) return;
        const lv = state.level;
        if (lv.view === 'home') return;
        const ch = state.channelById.get(lv.id);
        if (ch.kind === 'vessel') { if (ch.pairId) showNext(ch.pairId, t('pair_with', { name: shortName(ch.pairId) })); return; }
        const n2 = nextChannelOf(ch.id);
        if (n2) showNext(n2, t('next_channel', { name: shortName(n2) }));
      };
      scene.onContextLost = () => setLoading(t('restoring'));
      scene.onContextRestored = () => $('loading').classList.add('hidden');
    }
    const bodyUrl = `assets/body_${state.body}.glb?v=${ASSET_VERSION}`;
    if (!poseSys.mod && !poseSys.loading) poseSys.prefetch = prefetchPoses();
    const progressReady = fetchProgress();
    const [data] = await Promise.all([
      loadData(LANG),
      scene.loadBody(bodyUrl, (ev) => { if (ev.total) setLoading(t('loading'), { progress: ev.loaded / ev.total }); })
        .catch(() => scene.loadBody(`assets/body.glb?v=${ASSET_VERSION}`)),
    ]);
    state.data = data;
    if (EDIT) Object.assign(data.coords, store.get(EDITS_KEY, {}));
    for (const c of [...data.channels, ...data.vessels]) state.channelById.set(c.id, c);
    scene.buildChannels([...data.channels, ...data.vessels], data.coords, data.via);
    applyPointMeta();
    await applyStartPose();
    // the progress usually arrives with the data; a slow answer redraws the home sheet when it comes
    const progressLate = await Promise.race([progressReady.then(() => false), new Promise((r) => setTimeout(() => r(true), 1500))]);
    if (progressLate) progressReady.then((changed) => { if (!changed) return; renderChips(); if (state.level.view === 'home' && !state.overlay) renderSheet(); });
    setSheet('peek', { silent: true });
    scene.resize();
    bindCanvas();
    renderChips();
    applyScenery();      // the chosen photo shows from the start, not only once the poses sheet opens
    if (!deepLink()) {
      applySelection(); renderSheet(); scene.setView('front', { instant: true });
      // the first visit opens the sheet halfway on the three ways in
      // shown once: remembered at once, not only after a tap inside it (whoever just turned the figure got
      // the half-open sheet on every start, council round 2)
      if (!store.get('onb_intro', false) && !pathChannel()) {
        store.set('onb_intro', true);
        state.introSession = true;
        renderSheet();
        setSheet('half', { silent: true });
        // reframe once the camera offset follows the taller sheet (the head went off the top)
        setTimeout(() => scene.setView('front', { instant: true }), 40);
      }
    }
    if (EDIT) renderEditbar();
    try { await scene.renderer.compileAsync(scene.scene, scene.camera); } catch { /* optional */ }
    clearTimeout(slow);
    clearTimeout(fail);
    $('loading').classList.add('hidden');
    if (!store.get('onb_gesture', false) && !params.get('p') && !params.get('m')) {
      $('gestureHint').hidden = false;
      // shown for a few seconds, not until the first touch (it stood over the body, council)
      setTimeout(() => $('gestureHint').classList.add('fade'), 4500);
      setTimeout(() => { $('gestureHint').hidden = true; $('gestureHint').classList.remove('fade'); }, 5200);
    }
    $('gestureHint').textContent = t('hint_gesture');
    const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 3000));
    idle(() => ensurePoses().then(async () => {
      const pose = params.get('pose') || startTokens.a;
      const mudra = params.get('mudra') || startTokens.u;
      if ((pose || mudra) && poseSys.skinner) {
        await openPoses();
        if (pose) { state.posesTab = 'asanas'; choosePose(pose); }
        if (mudra) { state.posesTab = isArmPos(mudra) ? 'arms' : 'mudras'; choosePose(mudra); }
      }
    }));
    if (params.get('debug') === '1') window.__map = { THREE, scene, state, openPoint, selectChannel, setBody, choosePose, poseSys };
  } catch (err) {
    console.error(err);
    clearTimeout(slow);
    clearTimeout(fail);
    setLoading(t('load_error'), { error: true });
  } finally {
    booting = false;
  }
}

$('retryBtn').addEventListener('click', () => { $('loading').classList.remove('hidden'); boot(); });
document.addEventListener('visibilitychange', () => {
  if (!scene) return;
  scene.paused = document.hidden;
  if (document.hidden) pauseFlow('hidden'); else resumeFlow('hidden');
});
window.addEventListener('resize', () => setSheet(state.sheet, { silent: true }));

boot();
