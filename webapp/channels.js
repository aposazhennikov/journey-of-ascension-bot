// Constants for the 20 channels: order, colours for both themes, camera view, transitions,
// short names and flow direction (council spec, sections 3.1, 7.2, 7.3).

export const CLOCK_ORDER = [
  'lung', 'large_intestine', 'stomach', 'spleen', 'heart', 'small_intestine',
  'bladder', 'kidney', 'pericardium', 'triple_burner', 'gallbladder', 'liver',
];
export const MIDLINE_IDS = ['governing_vessel', 'conception_vessel'];
export const VESSEL_IDS = ['chong_mai', 'dai_mai', 'yin_wei_mai', 'yang_wei_mai', 'yin_qiao_mai', 'yang_qiao_mai'];
export const ALL_IDS = [...CLOCK_ORDER, ...MIDLINE_IDS, ...VESSEL_IDS];

export const PALETTE = {
  light: {
    lung: '#46546a', large_intestine: '#7c8ea6', stomach: '#e3ac00', spleen: '#b97a00',
    heart: '#c21f32', small_intestine: '#e0552b', bladder: '#2f7be0', kidney: '#1f3a9a',
    // gallbladder yellow-green, liver deep green: the paired wood channels must not look the same
    pericardium: '#a3236e', triple_burner: '#e0609a', gallbladder: '#8aae12', liver: '#1e6b45',
    governing_vessel: '#5b34b8', conception_vessel: '#9a5fd6',
    // the eight extraordinary vessels must stay apart from each other when shown together
    chong_mai: '#0d8f8c', dai_mai: '#8a6a2f', yin_wei_mai: '#6d7a12', yang_wei_mai: '#0099c4',
    yin_qiao_mai: '#c0397a', yang_qiao_mai: '#d9781c',
  },
  dark: {
    lung: '#f2f5f8', large_intestine: '#b9c6d6', stomach: '#ffd84a', spleen: '#f0a830',
    heart: '#ff5a5f', small_intestine: '#ff8a50', bladder: '#5cc0ff', kidney: '#6f8cff',
    pericardium: '#f05aa8', triple_burner: '#ff9ac6', gallbladder: '#9be05a', liver: '#3fbf7f',
    governing_vessel: '#b08cff', conception_vessel: '#e0a8ff',
    chong_mai: '#3fe0d0', dai_mai: '#e0c070', yin_wei_mai: '#c8d850', yang_wei_mai: '#4fd2ff',
    yin_qiao_mai: '#ff6fae', yang_qiao_mai: '#ffad5a',
  },
};

export const BODY_TONE = { light: '#d6cabe', dark: '#4e4844' };

export const VIEW = {
  lung: 'front', large_intestine: 'side', stomach: 'front', spleen: 'front', heart: 'front',
  small_intestine: 'side', bladder: 'back', kidney: 'front', pericardium: 'front', triple_burner: 'side',
  gallbladder: 'side', liver: 'front', governing_vessel: 'back', conception_vessel: 'front',
  chong_mai: 'front', dai_mai: 'side', yin_wei_mai: 'front', yang_wei_mai: 'side', yin_qiao_mai: 'front', yang_qiao_mai: 'side',
};

// Exit point of a channel and entry point of the next one in the daily cycle.
export const TRANSITIONS = {
  lung: { from: 'P7', to: 'GI1' }, large_intestine: { from: 'GI20', to: 'E1' }, stomach: { from: 'E42', to: 'RP1' },
  spleen: { from: 'RP21', to: 'C1', internal: true }, heart: { from: 'C9', to: 'IG1' }, small_intestine: { from: 'IG18', to: 'V1' },
  bladder: { from: 'V67', to: 'R1' }, kidney: { from: 'R22', to: 'MC1', internal: true }, pericardium: { from: 'MC8', to: 'TR1' },
  triple_burner: { from: 'TR23', to: 'VB1' }, gallbladder: { from: 'VB41', to: 'F1' }, liver: { from: 'F14', to: 'P1', internal: true },
};

export const PREFIX = {
  lung: 'P', large_intestine: 'GI', stomach: 'E', spleen: 'RP', heart: 'C', small_intestine: 'IG', bladder: 'V',
  kidney: 'R', pericardium: 'MC', triple_burner: 'TR', gallbladder: 'VB', liver: 'F', governing_vessel: 'VG', conception_vessel: 'VC',
};
export const WHO = {
  P: 'LU', GI: 'LI', E: 'ST', RP: 'SP', C: 'HT', IG: 'SI', V: 'BL', R: 'KI', MC: 'PC', TR: 'TE', VB: 'GB', F: 'LR', VG: 'GV', VC: 'CV',
};

export const SHORT = {
  ru: { lung: 'Лёгкие', large_intestine: 'Толстая кишка', stomach: 'Желудок', spleen: 'Селезёнка', heart: 'Сердце', small_intestine: 'Тонкая кишка', bladder: 'Мочевой пузырь', kidney: 'Почки', pericardium: 'Перикард', triple_burner: 'Три обогревателя', gallbladder: 'Желчный пузырь', liver: 'Печень', governing_vessel: 'Ду-май', conception_vessel: 'Жэнь-май', chong_mai: 'Чун-май', dai_mai: 'Дай-май', yin_wei_mai: 'Инь-вэй', yang_wei_mai: 'Ян-вэй', yin_qiao_mai: 'Инь-цяо', yang_qiao_mai: 'Ян-цяо' },
  en: { lung: 'Lung', large_intestine: 'Large Intestine', stomach: 'Stomach', spleen: 'Spleen', heart: 'Heart', small_intestine: 'Small Intestine', bladder: 'Bladder', kidney: 'Kidney', pericardium: 'Pericardium', triple_burner: 'Triple Burner', gallbladder: 'Gallbladder', liver: 'Liver', governing_vessel: 'Du Mai', conception_vessel: 'Ren Mai', chong_mai: 'Chong Mai', dai_mai: 'Dai Mai', yin_wei_mai: 'Yin Wei', yang_wei_mai: 'Yang Wei', yin_qiao_mai: 'Yin Qiao', yang_qiao_mai: 'Yang Qiao' },
  uz: { lung: "O'pka", large_intestine: "Yo'g'on ichak", stomach: 'Oshqozon', spleen: 'Taloq', heart: 'Yurak', small_intestine: 'Ingichka ichak', bladder: 'Siydik pufagi', kidney: 'Buyrak', pericardium: 'Perikard', triple_burner: 'Uch isitkich', gallbladder: "O't pufagi", liver: 'Jigar', governing_vessel: 'Du-may', conception_vessel: 'Ren-may', chong_mai: 'Chun-may', dai_mai: 'Day-may', yin_wei_mai: 'In-vey', yang_wei_mai: 'Yan-vey', yin_qiao_mai: 'In-tsyao', yang_qiao_mai: 'Yan-tsyao' },
  kz: { lung: 'Өкпе', large_intestine: 'Тоқ ішек', stomach: 'Асқазан', spleen: 'Көкбауыр', heart: 'Жүрек', small_intestine: 'Ащы ішек', bladder: 'Қуық', kidney: 'Бүйрек', pericardium: 'Перикард', triple_burner: 'Үш жылытқыш', gallbladder: 'Өт қабы', liver: 'Бауыр', governing_vessel: 'Ду-май', conception_vessel: 'Жэнь-май', chong_mai: 'Чун-май', dai_mai: 'Дай-май', yin_wei_mai: 'Инь-вэй', yang_wei_mai: 'Ян-вэй', yin_qiao_mai: 'Инь-цяо', yang_qiao_mai: 'Ян-цяо' },
};

export const FLOW_SHORT = {
  ru: { lung: 'грудь → большой палец', large_intestine: 'указательный палец → нос', stomach: 'под глазом → второй палец стопы', spleen: 'большой палец стопы → бок груди', heart: 'подмышка → мизинец', small_intestine: 'мизинец → ухо', bladder: 'угол глаза → мизинец стопы', kidney: 'подошва → под ключицей', pericardium: 'грудь у соска → средний палец', triple_burner: 'безымянный палец → бровь', gallbladder: 'наружный угол глаза → четвёртый палец стопы', liver: 'большой палец стопы → под соском', governing_vessel: 'копчик → верхняя губа', conception_vessel: 'промежность → подбородок' },
  en: { lung: 'chest → thumb', large_intestine: 'index finger → nose', stomach: 'below the eye → second toe', spleen: 'big toe → side of the chest', heart: 'armpit → little finger', small_intestine: 'little finger → ear', bladder: 'inner eye corner → little toe', kidney: 'sole → below the collarbone', pericardium: 'chest by the nipple → middle finger', triple_burner: 'ring finger → eyebrow', gallbladder: 'outer eye corner → fourth toe', liver: 'big toe → below the nipple', governing_vessel: 'tailbone → upper lip', conception_vessel: 'perineum → chin' },
  uz: { lung: "ko'krak → bosh barmoq", large_intestine: "ko'rsatkich barmoq → burun", stomach: "ko'z osti → oyoqning ikkinchi barmog'i", spleen: "oyoq bosh barmog'i → ko'krak yoni", heart: "qo'ltiq → jimjiloq", small_intestine: "jimjiloq → quloq", bladder: "ko'zning ichki burchagi → oyoq jimjilog'i", kidney: "oyoq tagi → o'mrov osti", pericardium: "ko'krak uchi yoni → o'rta barmoq", triple_burner: 'nomsiz barmoq → qosh', gallbladder: "ko'zning tashqi burchagi → oyoqning to'rtinchi barmog'i", liver: "oyoq bosh barmog'i → ko'krak uchi osti", governing_vessel: "dumg'aza → yuqori lab", conception_vessel: 'oraliq → iyak' },
  kz: { lung: 'кеуде → бас бармақ', large_intestine: 'сұқ саусақ → мұрын', stomach: 'көз асты → аяқтың екінші саусағы', spleen: 'аяқтың бас бармағы → кеуде бүйірі', heart: 'қолтық → шынашақ', small_intestine: 'шынашақ → құлақ', bladder: 'көздің ішкі бұрышы → аяқтың шынашағы', kidney: 'табан → бұғана асты', pericardium: 'емшек жаны → ортаңғы саусақ', triple_burner: 'атсыз саусақ → қас', gallbladder: 'көздің сыртқы бұрышы → аяқтың төртінші саусағы', liver: 'аяқтың бас бармағы → емшек асты', governing_vessel: 'құйымшақ → үстіңгі ерін', conception_vessel: 'аралық → иек' },
};

// Pose groups for transitions (spec 5.3).
export const POSE_GROUP = {
  stand: 'standing', tadasana: 'standing', vrikshasana: 'standing',
  dandasana: 'seated', sukhasana: 'seated', ardha_padmasana: 'seated', padmasana: 'seated',
  vajrasana: 'kneeling',
};
export const ASANA_ORDER = ['stand', 'tadasana', 'vrikshasana', 'dandasana', 'sukhasana', 'ardha_padmasana', 'padmasana', 'vajrasana'];
export const MUDRA_ORDER = ['open', 'gyan', 'prithvi', 'shuni', 'vyana', 'apana', 'hakini', 'anjali'];

/** Normalize a point code from any notation: P7, LU7, lu 7, Cyrillic look-alikes. */
export function normalizeCode(raw) {
  if (!raw) return '';
  let s = String(raw).trim().toUpperCase().replace(/\s+/g, '');
  s = s.replace(/[РСЕВТ]/g, (ch) => ({ Р: 'P', С: 'C', Е: 'E', В: 'B', Т: 'T' }[ch]));
  const m = /^([A-Z]+)\.?(\d+)$/.exec(s);
  if (!m) return s;
  const [, pre, num] = m;
  if (Object.values(PREFIX).includes(pre)) return `${pre}${num}`;
  const fromWho = Object.entries(WHO).find(([, w]) => w === pre);
  if (fromWho) return `${fromWho[0]}${num}`;
  return s;
}
