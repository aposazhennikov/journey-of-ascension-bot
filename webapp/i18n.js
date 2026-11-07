// UI strings (council spec, section 7.1). uz in Latin script, kz in Cyrillic.

const S = {
  app_title: ['Карта меридианов', 'Meridian map', 'Meridianlar xaritasi', 'Меридиандар картасы'],
  loading: ['Загружаю модель…', 'Loading the model…', 'Model yuklanmoqda…', 'Модель жүктелуде…'],
  slow_net: ['Медленное соединение…', 'Slow connection…', 'Aloqa sekin…', 'Байланыс баяу…'],
  load_error: ['Не удалось загрузить карту.', 'Could not load the map.', "Xaritani yuklab bo'lmadi.", 'Картаны жүктеу мүмкін болмады.'],
  retry: ['Повторить', 'Retry', 'Qayta urinish', 'Қайталау'],
  no_webgl: ['На этом устройстве 3D недоступно. Списки и карточки работают.', '3D is not available on this device. Lists and cards still work.', "Bu qurilmada 3D ishlamaydi. Ro'yxatlar va kartalar ishlaydi.", 'Бұл құрылғыда 3D қолжетімсіз. Тізімдер мен карталар жұмыс істейді.'],
  restoring: ['Восстанавливаю изображение…', 'Restoring the view…', 'Tasvir tiklanmoqda…', 'Кескін қалпына келтірілуде…'],
  hint_gesture: ['Крутите пальцем, сводите два пальца, чтобы приблизить', 'Drag to rotate, pinch to zoom', "Aylantirish uchun suring, yaqinlashtirish uchun ikki barmoqni yoying", 'Айналдыру үшін сүйреңіз, жақындату үшін екі саусақты жайыңыз'],
  hint_points: ['Коснитесь точки или листайте ‹ ›', 'Tap a point or use ‹ ›', "Nuqtaga teging yoki ‹ › bilan o'ting", 'Нүктеге басыңыз немесе ‹ › арқылы ауысыңыз'],
  point_not_found: ['Точка {code} не найдена', 'Point {code} not found', '{code} nuqtasi topilmadi', '{code} нүктесі табылмады'],
  aria_menu: ['Все каналы', 'All channels', 'Barcha kanallar', 'Барлық арналар'],
  aria_turn: ['Повернуть', 'Turn around', 'Burish', 'Бұру'],
  aria_fit: ['Показать целиком', 'Fit to screen', "To'liq ko'rsatish", 'Толық көрсету'],
  aria_pose: ['Поза и тело', 'Pose and body', 'Holat va tana', 'Қалып және дене'],
  aria_play: ['Показать движение', 'Play the flow', "Oqimni ko'rsatish", 'Ағынды көрсету'],
  aria_pause: ['Пауза', 'Pause', 'Pauza', 'Кідірту'],
  aria_prev: ['Предыдущая точка', 'Previous point', 'Oldingi nuqta', 'Алдыңғы нүкте'],
  aria_next: ['Следующая точка', 'Next point', 'Keyingi nuqta', 'Келесі нүкте'],
  now_active: ['Сейчас активен', 'Active now', 'Hozir faol', 'Қазір белсенді'],
  until: ['до {time}', 'until {time}', '{time} gacha', '{time} дейін'],
  pick_channel: ['Выберите меридиан', 'Choose a meridian', 'Meridianni tanlang', 'Меридианды таңдаңыз'],
  sec_main: ['Двенадцать меридианов по суточным часам', 'Twelve meridians by the daily clock', "Kunlik soat bo'yicha o'n ikki meridian", 'Тәуліктік сағат бойынша он екі меридиан'],
  sec_mid: ['Срединные каналы', 'Midline channels', "O'rta chiziq kanallari", 'Орта сызық арналары'],
  sec_vessels: ['Чудесные сосуды', 'Extraordinary vessels', "G'aroyib tomirlar", 'Ғажайып тамырлар'],
  outside_clock: ['вне суточного круга', 'outside the daily clock', 'kunlik doiradan tashqarida', 'тәуліктік шеңберден тыс'],
  opening_point: ['Точка открытия {code}', 'Opening point {code}', 'Ochilish nuqtasi {code}', 'Ашылу нүктесі {code}'],
  disclaimer: ['Это практика самонаблюдения. Она не заменяет врача, диагностику или лечение.', 'This is a self-observation practice. It does not replace a doctor, diagnosis, or treatment.', "Bu o'zini kuzatish amaliyoti. U shifokor, tashxis yoki davolanish o'rnini bosmaydi.", 'Бұл өзін-өзі бақылау тәжірибесі. Ол дәрігерді, диагнозды немесе емді алмастырмайды.'],
  about_title: ['О карте', 'About the map', 'Xarita haqida', 'Карта туралы'],
  about_text: ['Точки на модели расставлены приблизительно. Ищите место по описанию и по ощущению под пальцами. Направление потока показано по традиционному описанию каналов.', 'Points on the model are placed approximately. Find the spot by its description and by what you feel under your fingers. The flow direction follows the traditional description of the channels.', "Modeldagi nuqtalar taxminan joylashtirilgan. Joyni tavsif va barmoq ostidagi sezgi orqali toping. Oqim yo'nalishi kanallarning an'anaviy tavsifi bo'yicha ko'rsatilgan.", 'Модельдегі нүктелер шамамен қойылған. Орынды сипаттама мен саусақ астындағы сезім арқылы табыңыз. Ағын бағыты арналардың дәстүрлі сипаттамасы бойынша көрсетілген.'],
  now_badge: ['сейчас', 'now', 'hozir', 'қазір'],
  hours: ['Активность {a} · спад {p}', 'Active {a} · low {p}', 'Faollik {a} · pasayish {p}', 'Белсенділік {a} · бәсеңдеу {p}'],
  flow_label: ['Поток', 'Flow', 'Oqim', 'Ағын'],
  pair: ['пара', 'pair', 'juft', 'жұп'],
  tag_hand: ['Рука', 'Arm', "Qo'l", 'Қол'],
  tag_foot: ['Нога', 'Leg', 'Oyoq', 'Аяқ'],
  tag_midline: ['Срединный', 'Midline', "O'rta chiziq", 'Орта сызық'],
  hint_yin: ['Иньские каналы идут по внутренней стороне конечностей и по передней поверхности туловища.', 'Yin channels run along the inner side of the limbs and the front of the torso.', "Yin kanallari qo'l-oyoqlarning ichki tomoni va tananing old yuzasi bo'ylab o'tadi.", 'Инь арналары аяқ-қолдың ішкі жағымен және дененің алдыңғы бетімен өтеді.'],
  hint_yang: ['Янские каналы идут по наружной стороне конечностей, по спине и по бокам.', 'Yang channels run along the outer side of the limbs, the back and the sides.', "Yang kanallari qo'l-oyoqlarning tashqi tomoni, orqa va yonlar bo'ylab o'tadi.", 'Ян арналары аяқ-қолдың сыртқы жағымен, арқа мен бүйірлер бойымен өтеді.'],
  hint_element: ['По традиции каждая пара каналов относится к одной из пяти стихий. Цвет линии на карте показывает стихию.', 'Traditionally each pair of channels belongs to one of the five elements. The line colour shows the element.', "An'anaga ko'ra har bir kanal jufti besh unsurdan biriga tegishli. Chiziq rangi unsurni ko'rsatadi.", 'Дәстүр бойынша әр арна жұбы бес стихияның біріне жатады. Сызықтың түсі стихияны көрсетеді.'],
  hint_hand: ['Канал начинается или заканчивается на пальцах руки.', 'The channel starts or ends at the fingers.', "Kanal qo'l barmoqlarida boshlanadi yoki tugaydi.", 'Арна қол саусақтарында басталады немесе аяқталады.'],
  hint_foot: ['Канал начинается или заканчивается на пальцах стопы.', 'The channel starts or ends at the toes.', 'Kanal oyoq barmoqlarida boshlanadi yoki tugaydi.', 'Арна аяқ саусақтарында басталады немесе аяқталады.'],
  hint_midline: ['Канал идёт по срединной линии тела, точки на нём непарные.', 'The channel runs along the midline of the body; its points are single.', "Kanal tananing o'rta chizig'i bo'ylab o'tadi, nuqtalari juftsiz.", 'Арна дененің орта сызығымен өтеді, нүктелері жұпсыз.'],
  hint_hours: ['По традиционным китайским часам каждый канал два часа в сутки наиболее активен, а через 12 часов находится в спаде.', 'By the traditional Chinese clock each channel is most active for two hours a day and at its lowest twelve hours later.', "An'anaviy xitoy soati bo'yicha har bir kanal sutkada ikki soat eng faol bo'ladi, 12 soatdan keyin esa pasayadi.", 'Дәстүрлі қытай сағаты бойынша әр арна тәулігіне екі сағат ең белсенді болады, ал 12 сағаттан кейін бәсеңдейді.'],
  luo_toggle: ['Связи ло', 'Luo links', "Lo bog'lanishlari", 'Ло байланыстары'],
  slow_toggle: ['Медленнее', 'Slower', 'Sekinroq', 'Баяуырақ'],
  practice_title: ['Короткая практика', 'Short practice', 'Qisqa amaliyot', 'Қысқа тәжірибе'],
  more: ['ещё', 'more', 'yana', 'тағы'],
  less: ['свернуть', 'less', "yig'ish", 'жию'],
  description_title: ['Описание', 'Description', 'Tavsif', 'Сипаттама'],
  level_label: ['Уровень', 'Level', 'Daraja', 'Деңгей'],
  points_title: ['Точки', 'Points', 'Nuqtalar', 'Нүктелер'],
  filter_all: ['Все', 'All', 'Hammasi', 'Барлығы'],
  filter_special: ['Особые', 'Key points', 'Muhim', 'Ерекше'],
  next_channel: ['Дальше: {name}', 'Next: {name}', 'Keyingisi: {name}', 'Келесі: {name}'],
  transition: ['Переход → {code}', 'Transition → {code}', "O'tish → {code}", 'Ауысу → {code}'],
  internal_link: ['внутренняя связь', 'internal link', "ichki bog'lanish", 'ішкі байланыс'],
  start_of: ['начало канала', 'start of the channel', 'kanal boshi', 'арнаның басы'],
  end_of: ['конец канала', 'end of the channel', 'kanal oxiri', 'арнаның соңы'],
  point_of: ['{i} из {n}', '{i} of {n}', '{i} / {n}', '{i} / {n}'],
  bilateral: ['с двух сторон', 'on both sides', 'ikki tomonda', 'екі жақта'],
  midline: ['на срединной линии', 'on the midline', "o'rta chiziqda", 'орта сызықта'],
  not_on_model: ['на модели пока не отмечена', 'not yet marked on the model', 'modelda hali belgilanmagan', 'модельде әлі белгіленбеген'],
  meaning: ['Буквально: {text}', 'Literally: {text}', "So'zma-so'z: {text}", 'Сөзбе-сөз: {text}'],
  location_title: ['Где находится', 'Location', 'Joylashuvi', 'Орналасуы'],
  find_title: ['Как найти', 'How to find it', 'Qanday topish mumkin', 'Қалай табуға болады'],
  caution_pregnancy: ['Во время беременности здесь только внимание, без надавливания.', 'During pregnancy, only attention here, no pressure.', "Homiladorlik paytida bu yerga faqat diqqat qarating, bosmang.", 'Жүктілік кезінде мұнда тек зейін, баспаңыз.'],
  caution_artery: ['Если под пальцем пульс, сместитесь и не давите.', 'If you feel a pulse under the finger, move aside and do not press.', "Barmoq ostida tomir urishi sezilsa, biroz suring va bosmang.", 'Саусақ астында тамыр соғысы сезілсе, сәл жылжып, баспаңыз.'],
  caution_eye: ['Касайтесь только края глазницы, на глаз не давите.', 'Touch only the rim of the eye socket, never press on the eye.', "Faqat ko'z kosasi chetiga teging, ko'zni bosmang.", 'Тек көз ұясының жиегін ұстаңыз, көзді баспаңыз.'],
  caution_neck: ['На шее касайтесь мягко, без сильного давления.', 'On the neck, touch gently, without strong pressure.', "Bo'yinda yumshoq teging, qattiq bosmang.", 'Мойында жұмсақ ұстаңыз, қатты баспаңыз.'],
  crossings_title: ['Здесь сходятся', 'Channels meeting here', 'Bu yerda uchrashadi', 'Мұнда тоғысады'],
  some_sources: ['по части источников', 'in some sources', 'ayrim manbalarda', 'кейбір дереккөздерде'],
  observe_title: ['Вопрос для наблюдения', 'Question to observe', 'Kuzatish uchun savol', 'Бақылауға арналған сұрақ'],
  other_names: ['Другие названия', 'Other names', 'Boshqa nomlari', 'Басқа атаулары'],
  who_code: ['Код ВОЗ', 'WHO code', 'JSST kodi', 'ДДСҰ коды'],
  source: ['Источник', 'Source', 'Manba', 'Дереккөз'],
  source_line: ['Расположение: eledia.ru, shiyanbin.ru; категории: Deadman, 2007', 'Location: eledia.ru, shiyanbin.ru; categories: Deadman, 2007', 'Joylashuv: eledia.ru, shiyanbin.ru; toifalar: Deadman, 2007', 'Орналасуы: eledia.ru, shiyanbin.ru; санаттар: Deadman, 2007'],
  luo_to: ['Ветвь ло к каналу: {name}', 'Luo branch to: {name}', "Lo tarmog'i: {name}", 'Ло тармағы: {name}'],
  show_branch: ['Показать ветвь', 'Show the branch', "Tarmoqni ko'rsatish", 'Тармақты көрсету'],
  key_of: ['Ключ сосуда {vessel} · пара {couple}', 'Key point of {vessel} · paired with {couple}', '{vessel} kalit nuqtasi · jufti {couple}', '{vessel} кілт нүктесі · жұбы {couple}'],
  vessel_kind: ['Чудесный сосуд', 'Extraordinary vessel', "G'aroyib tomir", 'Ғажайып тамыр'],
  opening_title: ['Точка открытия', 'Opening point', 'Ochilish nuqtasi', 'Ашылу нүктесі'],
  pair_with: ['Пара: {name}', 'Pair: {name}', 'Jufti: {name}', 'Жұбы: {name}'],
  no_own_points: ['Своих точек нет: сосуд проходит через точки других каналов.', 'It has no points of its own and runs through points of other channels.', "O'z nuqtalari yo'q: tomir boshqa kanallar nuqtalari orqali o'tadi.", 'Өз нүктелері жоқ: тамыр басқа арналардың нүктелері арқылы өтеді.'],
  course_title: ['Ход сосуда', 'Course', "Yo'nalishi", 'Жолы'],
  route_points: ['Точки маршрута', 'Route points', "Yo'nalish nuqtalari", 'Бағыт нүктелері'],
  practice: ['Практика', 'Practice', 'Amaliyot', 'Тәжірибе'],
  poses_title: ['Поза и тело', 'Pose and body', 'Holat va tana', 'Қалып және дене'],
  tab_asanas: ['Асаны', 'Asanas', 'Asanalar', 'Асаналар'],
  tab_mudras: ['Мудры', 'Mudras', 'Mudralar', 'Мудралар'],
  body_f: ['Ж', 'F', 'A', 'Ә'],
  body_m: ['М', 'M', 'E', 'Е'],
  body_f_aria: ['Женское тело', 'Female body', 'Ayol tanasi', 'Әйел денесі'],
  body_m_aria: ['Мужское тело', 'Male body', 'Erkak tanasi', 'Ер денесі'],
  how_title: ['Как выполнить', 'How to do it', 'Qanday bajariladi', 'Қалай орындалады'],
  focus_channels: ['Внимание в этой позе', 'Attention in this pose', 'Bu holatda diqqat', 'Бұл қалыпта зейін'],
  connects: ['Соединяет', 'Connects', "Bog'laydi", 'Байланыстырады'],
  mudra_seated: ['Мудры показываются в сидячей позе', 'Mudras are shown in a seated pose', "Mudralar o'tirgan holatda ko'rsatiladi", 'Мудралар отырған қалыпта көрсетіледі'],
  mudra_note: ['Соответствие пальцев и каналов принято в современной практике, в классических текстах китайской медицины его нет.', 'The finger-to-channel correspondence comes from modern practice and is not found in classical Chinese medicine texts.', "Barmoqlar va kanallar mosligi zamonaviy amaliyotda qabul qilingan, mumtoz xitoy tibbiyoti matnlarida u yo'q.", 'Саусақтар мен арналардың сәйкестігі қазіргі тәжірибеде қабылданған, классикалық қытай медицинасы мәтіндерінде ол жоқ.'],
  poses_loading: ['Загружаю позы…', 'Loading poses…', 'Holatlar yuklanmoqda…', 'Қалыптар жүктелуде…'],
  poses_unavailable: ['Позы пока недоступны', 'Poses are not available yet', "Holatlar hozircha mavjud emas", 'Қалыптар әзірге қолжетімсіз'],
  edit_idle: ['Разметка: выберите точку.', 'Markup: pick a point.', 'Belgilash: nuqtani tanlang.', 'Белгілеу: нүктені таңдаңыз.'],
  edit_target: ['Разметка: {code}. Коснитесь тела.', 'Markup: {code}. Tap the body.', 'Belgilash: {code}. Tanaga teging.', 'Белгілеу: {code}. Денеге басыңыз.'],
  edit_saved: ['Точка {code} сохранена в браузере.', 'Point {code} saved in this browser.', '{code} nuqtasi brauzerda saqlandi.', '{code} нүктесі браузерде сақталды.'],
  edit_export: ['Экспорт JSON', 'Export JSON', 'Export JSON', 'Export JSON'],
  edit_reset: ['Сбросить правки', 'Reset edits', 'Tuzatishlarni bekor qilish', 'Түзетулерді тастау'],
  edit_copied: ['JSON скопирован.', 'JSON copied.', 'JSON nusxalandi.', 'JSON көшірілді.'],
};

const LANGS = ['ru', 'en', 'uz', 'kz'];
const PLURAL_POINTS = {
  ru: { one: '{n} точка', few: '{n} точки', many: '{n} точек', other: '{n} точки' },
  en: { one: '{n} point', other: '{n} points' },
  uz: { other: '{n} nuqta' },
  kz: { other: '{n} нүкте' },
};

export function normalizeLang(code) {
  const c = String(code || '').toLowerCase().slice(0, 2);
  if (c === 'kk') return 'kz';
  return LANGS.includes(c) ? c : 'ru';
}

export function makeT(lang) {
  const i = Math.max(0, LANGS.indexOf(lang));
  const t = (key, vars = {}) => {
    const row = S[key];
    const s = row ? (row[i] ?? row[0]) : key;
    return s.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? vars[k] : ''));
  };
  t.points = (n) => {
    const forms = PLURAL_POINTS[lang] || PLURAL_POINTS.ru;
    let rule = 'other';
    try { rule = new Intl.PluralRules(lang === 'kz' ? 'kk' : lang).select(n); } catch { /* old engine */ }
    return (forms[rule] || forms.other).replace('{n}', n);
  };
  return t;
}
