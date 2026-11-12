// Loading and shaping the map data: meridians from the bot API plus static JSON assets.

import { CLOCK_ORDER, MIDLINE_IDS, VESSEL_IDS, VIEW, TRANSITIONS } from './channels.js';

export const ASSET_VERSION = '2026-11-12-2';

async function getJson(url, optional = false) {
  try {
    const sep = url.includes('?') ? '&' : '?';
    const r = await fetch(`${url}${sep}v=${ASSET_VERSION}`, { cache: 'no-cache' });
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return await r.json();
  } catch (err) {
    if (optional) return null;
    throw err;
  }
}

export function loadPoseContent() {
  return getJson('assets/practice_poses.json', true);
}

export async function loadData(lang) {
  const [api, points3d, vessels, categories, extras, profiles] = await Promise.all([
    getJson(`api/meridians?lang=${encodeURIComponent(lang)}`),
    getJson('assets/points3d.json'),
    getJson('assets/extra_vessels.json', true),
    getJson('assets/point_categories.json', true),
    getJson(`assets/point_extras.json?lang=${encodeURIComponent(lang)}`, true),   // the server keeps only this language
    getJson('assets/meridian_profiles.json', true),
  ]);
  const data = shapeData(lang, api, points3d, vessels, categories, extras);
  // traditional profile per channel (role, five elements, balance, where to begin)
  data.profile = (id) => {
    const p = profiles?.channels?.[id];
    return p ? { start: p.start_code, ...pick(p.i18n, lang) } : null;
  };
  return data;
}

const pick = (i18n, lang) => (i18n && (i18n[lang] || i18n.en || i18n.ru)) || {};

function shapeData(lang, api, points3d, vessels, categories, extras) {
  const byId = new Map(api.meridians.map((m) => [m.id, m]));
  const pointOwner = new Map();
  const pointInfo = new Map();
  for (const m of api.meridians) {
    m.points.forEach((p, i) => {
      pointOwner.set(p.code, m.id);
      pointInfo.set(p.code, { ...p, index: i, meridian: m.id });
    });
  }
  const regular = [...CLOCK_ORDER, ...MIDLINE_IDS].filter((id) => byId.has(id)).map((id) => {
    const m = byId.get(id);
    const codes = m.points.map((p) => p.code);
    const tr = TRANSITIONS[id];
    return {
      id, kind: 'regular', midline: MIDLINE_IDS.includes(id), bilateral: !MIDLINE_IDS.includes(id),
      chains: (points3d.chains && points3d.chains[id]) || [codes],
      link: tr ? { ...tr } : null,
      points: codes, meta: m, view: VIEW[id] || 'front',
    };
  });
  const vRaw = new Map((vessels?.vessels || []).map((v) => [v.id, v]));
  const vesselList = VESSEL_IDS.filter((id) => vRaw.has(id)).map((id) => {
    const v = vRaw.get(id);
    return {
      id, kind: 'vessel', bilateral: v.bilateral !== false,
      chains: (points3d.chains && points3d.chains[id]) || [v.path],
      points: [], path: v.path, disputed: new Set(v.path_note_codes || []),
      confluent: v.confluent_point, coupled: v.coupled_point,
      text: pick(v.i18n, lang), view: VIEW[id] || 'front',
    };
  });
  // the vessel whose opening point is this vessel's coupled point is its pair
  for (const v of vesselList) v.pairId = vesselList.find((o) => o.confluent === v.coupled)?.id || null;
  const references = new Map((vessels?.references || []).map((r) => [r.id, r]));

  const cat = categories || {};
  return {
    lang,
    channels: regular,
    vessels: vesselList,
    references,
    byId,
    pointOwner,
    pointInfo,
    coords: points3d.points,
    via: points3d.via || {},
    categories: cat,
    catText: (key) => pick(cat.categories?.[key]?.i18n, lang),
    pointCats: cat.points || {},
    luoLinks: (cat.luo_links || []),
    crossings: new Map((cat.crossings || []).map((c) => [c.point, c])),
    muOf: cat.mu_of || {},
    backShuOf: cat.back_shu_of || {},
    confluentOf: cat.confluent_of || {},
    extras: extras?.points || {},
    extraText: (code) => pick(extras?.points?.[code]?.i18n, lang),
  };
}

export function parseRange(range) {
  const m = /^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/.exec(range || '');
  if (!m) return null;
  return [Number(m[1]) * 60 + Number(m[2]), Number(m[3]) * 60 + Number(m[4])];
}

export function isActiveNow(range, now = new Date()) {
  const r = parseRange(range);
  if (!r) return false;
  const minutes = now.getHours() * 60 + now.getMinutes();
  return r[0] < r[1] ? minutes >= r[0] && minutes < r[1] : minutes >= r[0] || minutes < r[1];
}

export function activeChannelNow(channels, now = new Date()) {
  return channels.find((c) => !c.midline && isActiveNow(c.meta?.active_time, now)) || null;
}

export function hh(range, idx) {
  const r = parseRange(range);
  if (!r) return '';
  return String(Math.floor(r[idx] / 60)).padStart(2, '0');
}
