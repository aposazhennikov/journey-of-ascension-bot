import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MERIDIANS_FILE = ROOT / "bot" / "meridians.json"
IMAGE_DIR = ROOT / "images" / "meridians"
HEADERS = {"User-Agent": "Mozilla/5.0 Journey of Ascension content importer"}


LANG_META = {
    "en": {
        "focus": "Rest attention on this point without forcing a result. Notice warmth, pressure, pulsation, emptiness, thoughts, or images. If the sensation is weak, treat the point as not yet open: give it more attention, gently massage it, and imagine breathing in and out through it until the sensation becomes steady.",
        "question": "What changes when attention rests here: sensation, breath, mood, thought flow, or inner imagery?",
        "source_location": "Source location",
        "source_note": "Classical note",
    },
    "ru": {
        "focus": "Перенесите внимание в эту точку без усилия получить результат. Наблюдайте тепло, давление, пульсацию, пустоту, мысли или образы. Если ощущение слабое, считайте точку пока закрытой: уделите ей больше внимания, мягко помассируйте её и представляйте вдох и выдох через неё, пока ощущение не станет устойчивым.",
        "question": "Что меняется, когда внимание находится здесь: ощущение, дыхание, настроение, поток мыслей или внутренние образы?",
        "source_location": "Расположение",
        "source_note": "Классическое примечание",
    },
    "uz": {
        "focus": "Diqqatni natijani majburlamasdan shu nuqtaga olib keling. Iliqlik, bosim, pulsatsiya, bo'shliq, fikrlar yoki obrazlarni kuzating. Agar sezgi kuchsiz bo'lsa, nuqtani hali ochilmagan deb qabul qiling: unga ko'proq e'tibor bering, yengil massaj qiling va sezgi barqaror bo'lguncha shu nuqta orqali nafas olayotganingizni tasavvur qiling.",
        "question": "Diqqat shu yerda turganda nima o'zgaradi: sezgi, nafas, kayfiyat, fikr oqimi yoki ichki obrazlar?",
        "source_location": "Manbadagi joylashuv",
        "source_note": "Klassik izoh",
    },
    "kz": {
        "focus": "Нәтижені күштемей, зейінді осы нүктеге әкеліңіз. Жылуды, қысымды, соғуды, бос кеңістікті, ойларды немесе бейнелерді бақылаңыз. Егер сезім әлсіз болса, нүктені әзірге ашылмаған деп қабылдаңыз: оған көбірек зейін беріңіз, жеңіл уқалаңыз және сезім тұрақталғанша осы нүкте арқылы дем алып-шығаруды елестетіңіз.",
        "question": "Зейін осында тұрғанда не өзгереді: сезім, тыныс, көңіл күй, ой ағымы немесе ішкі бейнелер?",
        "source_location": "Дереккөздегі орналасуы",
        "source_note": "Классикалық түсіндірме",
    },
}


MERIDIANS = [
    {
        "id": "lung",
        "category_id": 17,
        "source_url": "https://shiyanbin.ru/meridian-legkih-p/",
        "active_time": "03:00-05:00",
        "passive_time": "15:00-17:00",
        "names": {
            "en": "Lung Meridian",
            "ru": "Меридиан лёгких",
            "uz": "O'pka meridiani",
            "kz": "Өкпе меридианы",
        },
        "direction": {
            "en": "From the upper chest along the inner side of the arm toward the thumb.",
            "ru": "От верхней части груди по внутренней стороне руки к большому пальцу.",
            "uz": "Ko'krakning yuqori qismidan qo'lning ichki tomoni bo'ylab bosh barmoqqa.",
            "kz": "Кеуденің жоғарғы бөлігінен қолдың ішкі жағымен бас бармаққа қарай.",
        },
        "intro": {
            "en": "The Lung Meridian is used here as a map for observing breath, the chest, the inner line of the arm, and the quality of receiving and releasing.",
            "ru": "Меридиан лёгких здесь используется как карта наблюдения дыхания, грудной клетки, внутренней линии руки и способности принимать и отпускать.",
            "uz": "O'pka meridiani bu yerda nafas, ko'krak, qo'lning ichki chizig'i hamda qabul qilish va qo'yib yuborish sifatini kuzatish xaritasi sifatida ishlatiladi.",
            "kz": "Өкпе меридианы бұл жерде тынысты, кеудені, қолдың ішкі сызығын және қабылдау мен босату сапасын бақылау картасы ретінде қолданылады.",
        },
        "practice": {
            "en": "Sit calmly, soften the chest and shoulders, then follow the channel from the chest through the inner arm to the thumb together with natural breathing.",
            "ru": "Сядьте спокойно, смягчите грудь и плечи, затем ведите внимание от груди по внутренней стороне руки к большому пальцу вместе с естественным дыханием.",
            "uz": "Sokin o'tiring, ko'krak va yelkalarni yumshating, keyin diqqatni tabiiy nafas bilan ko'krakdan qo'lning ichki tomoni bo'ylab bosh barmoqqa olib boring.",
            "kz": "Тыныш отырыңыз, кеуде мен иықты жұмсартыңыз, содан кейін зейінді табиғи тыныспен кеудеден қолдың ішкі жағымен бас бармаққа қарай жүргізіңіз.",
        },
    },
    {
        "id": "large_intestine",
        "category_id": 18,
        "source_url": "https://shiyanbin.ru/meridian-tolstoj-kishki-gi/",
        "active_time": "05:00-07:00",
        "passive_time": "17:00-19:00",
        "names": {
            "en": "Large Intestine Meridian",
            "ru": "Меридиан толстой кишки",
            "uz": "Yo'g'on ichak meridiani",
            "kz": "Тоқ ішек меридианы",
        },
        "direction": {
            "en": "From the index finger along the outer side of the arm through the shoulder and neck to the face.",
            "ru": "От указательного пальца по наружной стороне руки через плечо и шею к лицу.",
            "uz": "Ko'rsatkich barmoqdan qo'lning tashqi tomoni bo'ylab yelka va bo'yin orqali yuzga.",
            "kz": "Сұқ саусақтан қолдың сыртқы жағымен иық пен мойын арқылы бетке қарай.",
        },
        "intro": {
            "en": "The Large Intestine Meridian is used here as a map for observing the outer line of the arm, the shoulder, neck, face, and the inner skill of releasing what is no longer needed.",
            "ru": "Меридиан толстой кишки здесь используется как карта наблюдения наружной линии руки, плеча, шеи, лица и внутреннего навыка отпускать то, что уже не нужно.",
            "uz": "Yo'g'on ichak meridiani bu yerda qo'lning tashqi chizig'i, yelka, bo'yin, yuz va endi kerak bo'lmagan narsani qo'yib yuborish ko'nikmasini kuzatish xaritasi sifatida ishlatiladi.",
            "kz": "Тоқ ішек меридианы бұл жерде қолдың сыртқы сызығын, иықты, мойынды, бетті және енді қажет емес нәрсені босату дағдысын бақылау картасы ретінде қолданылады.",
        },
        "practice": {
            "en": "Relax the hand, jaw, and shoulders. Let attention travel from the index finger along the outer arm toward the face, noticing where the line feels clear and where it feels silent.",
            "ru": "Расслабьте кисть, челюсть и плечи. Ведите внимание от указательного пальца по наружной стороне руки к лицу, замечая, где линия ощущается ясно, а где будто молчит.",
            "uz": "Kaft, jag' va yelkalarni bo'shating. Diqqatni ko'rsatkich barmoqdan qo'lning tashqi tomoni bo'ylab yuzga olib boring, qayerda chiziq aniq, qayerda esa jimdek ekanini kuzating.",
            "kz": "Қолды, жақты және иықты босатыңыз. Зейінді сұқ саусақтан қолдың сыртқы жағымен бетке қарай жүргізіп, сызық қай жерде анық, қай жерде үнсіз сияқты екенін байқаңыз.",
        },
    },
    {
        "id": "stomach",
        "category_id": 19,
        "source_url": "https://shiyanbin.ru/meridian-zheludka-e/",
        "active_time": "07:00-09:00",
        "passive_time": "19:00-21:00",
        "names": {
            "en": "Stomach Meridian",
            "ru": "Меридиан желудка",
            "uz": "Oshqozon meridiani",
            "kz": "Асқазан меридианы",
        },
        "direction": {
            "en": "From the face downward through the neck, chest, abdomen, front of the leg, and foot.",
            "ru": "От лица вниз через шею, грудь, живот, переднюю поверхность ноги и стопу.",
            "uz": "Yuzdan pastga bo'yin, ko'krak, qorin, oyoqning old yuzasi va panja orqali.",
            "kz": "Беттен төмен қарай мойын, кеуде, іш, аяқтың алдыңғы беті және табан арқылы.",
        },
        "intro": {
            "en": "The Stomach Meridian is used here as a map for observing nourishment, grounding, the front of the body, the legs, and the ability to receive life without inner haste.",
            "ru": "Меридиан желудка здесь используется как карта наблюдения питания, опоры, передней линии тела, ног и способности принимать жизнь без внутренней спешки.",
            "uz": "Oshqozon meridiani bu yerda oziqlanish, tayanch, tananing old chizig'i, oyoqlar va hayotni ichki shoshilmasdan qabul qilish qobiliyatini kuzatish xaritasi sifatida ishlatiladi.",
            "kz": "Асқазан меридианы бұл жерде қоректенуді, тіректі, дененің алдыңғы сызығын, аяқтарды және өмірді ішкі асығыстықсыз қабылдау қабілетін бақылау картасы ретінде қолданылады.",
        },
        "practice": {
            "en": "Soften the face, jaw, abdomen, and thighs. Let attention descend from the face through the front of the body and legs, noticing where the channel feels full, tense, empty, or silent.",
            "ru": "Смягчите лицо, челюсть, живот и бёдра. Ведите внимание от лица вниз по передней стороне тела и ног, замечая, где канал ощущается наполненным, напряжённым, пустым или молчащим.",
            "uz": "Yuz, jag', qorin va sonlarni yumshating. Diqqatni yuzdan tananing old tomoni va oyoqlar bo'ylab pastga olib boring, kanal qayerda to'la, tarang, bo'sh yoki jimdek sezilishini kuzating.",
            "kz": "Бетті, жақты, ішті және санды жұмсартыңыз. Зейінді беттен дененің алдыңғы жағы мен аяқтар бойымен төмен жүргізіп, арна қай жерде толық, қысылған, бос немесе үнсіз сияқты екенін байқаңыз.",
        },
    },
    {
        "id": "spleen",
        "category_id": 20,
        "source_url": "https://shiyanbin.ru/meridian-selezenki-rp/",
        "active_time": "09:00-11:00",
        "passive_time": "21:00-23:00",
        "names": {
            "en": "Spleen Meridian",
            "ru": "Меридиан селезёнки",
            "uz": "Taloq meridiani",
            "kz": "Көкбауыр меридианы",
        },
        "direction": {
            "en": "From the big toe along the inner side of the foot and leg, then upward through the abdomen and chest.",
            "ru": "От большого пальца стопы по внутренней стороне стопы и ноги, затем вверх через живот и грудь.",
            "uz": "Oyoq bosh barmog'idan panja va oyoqning ichki tomoni bo'ylab, keyin qorin va ko'krak orqali yuqoriga.",
            "kz": "Аяқтың бас бармағынан табан мен аяқтың ішкі жағымен, содан кейін іш пен кеуде арқылы жоғары.",
        },
        "intro": {
            "en": "The Spleen Meridian is used here as a map for observing assimilation, inner steadiness, the medial line of the leg, and how the body distributes strength after receiving nourishment.",
            "ru": "Меридиан селезёнки здесь используется как карта наблюдения усвоения, внутренней устойчивости, медиальной линии ноги и того, как тело распределяет силы после получения питания.",
            "uz": "Taloq meridiani bu yerda o'zlashtirish, ichki barqarorlik, oyoqning ichki chizig'i va tana oziqlanishdan keyin kuchni qanday taqsimlashini kuzatish xaritasi sifatida ishlatiladi.",
            "kz": "Көкбауыр меридианы бұл жерде сіңіруді, ішкі тұрақтылықты, аяқтың ішкі сызығын және дене қоректенуден кейін күшті қалай бөлетінін бақылау картасы ретінде қолданылады.",
        },
        "practice": {
            "en": "Relax the feet, knees, abdomen, and chest. Let attention rise from the big toe along the inner leg toward the abdomen and chest, noticing where the channel feels stable, heavy, warm, or unclear.",
            "ru": "Расслабьте стопы, колени, живот и грудь. Ведите внимание от большого пальца стопы по внутренней стороне ноги к животу и груди, замечая, где канал ощущается устойчивым, тяжёлым, тёплым или неясным.",
            "uz": "Panja, tizza, qorin va ko'krakni bo'shating. Diqqatni oyoq bosh barmog'idan oyoqning ichki tomoni bo'ylab qorin va ko'krakka olib boring, kanal qayerda barqaror, og'ir, iliq yoki noaniq sezilishini kuzating.",
            "kz": "Табанды, тізені, ішті және кеудені босатыңыз. Зейінді аяқтың бас бармағынан аяқтың ішкі жағымен іш пен кеудеге қарай жүргізіп, арна қай жерде тұрақты, ауыр, жылы немесе анық емес екенін байқаңыз.",
        },
    },
    {
        "id": "heart",
        "category_id": 21,
        "source_url": "https://shiyanbin.ru/meridian-serdtsa-s/",
        "active_time": "11:00-13:00",
        "passive_time": "23:00-01:00",
        "names": {
            "en": "Heart Meridian",
            "ru": "Меридиан сердца",
            "uz": "Yurak meridiani",
            "kz": "Жүрек меридианы",
        },
        "direction": {
            "en": "From the chest and axilla along the inner side of the arm toward the little finger.",
            "ru": "От груди и подмышечной области по внутренней стороне руки к мизинцу.",
            "uz": "Ko'krak va qo'ltiq sohasidan qo'lning ichki tomoni bo'ylab jimjiloq barmoqqa.",
            "kz": "Кеуде мен қолтық аймағынан қолдың ішкі жағымен шынашаққа қарай.",
        },
        "intro": {
            "en": "The Heart Meridian is used here as a map for observing the chest, inner arm, clarity of attention, emotional heat, and the quiet center from which action becomes cleaner.",
            "ru": "Меридиан сердца здесь используется как карта наблюдения груди, внутренней линии руки, ясности внимания, эмоционального жара и тихого центра, из которого действие становится чище.",
            "uz": "Yurak meridiani bu yerda ko'krak, qo'lning ichki chizig'i, diqqat ravshanligi, hissiy issiqlik va harakatni tiniqlashtiradigan sokin markazni kuzatish xaritasi sifatida ishlatiladi.",
            "kz": "Жүрек меридианы бұл жерде кеудені, қолдың ішкі сызығын, зейіннің айқындығын, эмоциялық қызуды және әрекетті тазарақ ететін тыныш орталықты бақылау картасы ретінде қолданылады.",
        },
        "practice": {
            "en": "Soften the chest, armpit, elbow, wrist, and little finger. Let attention move along the inner arm without dramatizing emotion: just notice heat, tightness, tenderness, or quietness.",
            "ru": "Смягчите грудь, подмышку, локоть, запястье и мизинец. Ведите внимание по внутренней стороне руки без драматизации эмоций: просто замечайте жар, сжатие, чувствительность или тишину.",
            "uz": "Ko'krak, qo'ltiq, tirsak, bilak va jimjiloqni yumshating. Hissiyotni kuchaytirmasdan diqqatni qo'lning ichki tomoni bo'ylab olib boring: faqat issiqlik, siqilish, noziklik yoki sokinlikni kuzating.",
            "kz": "Кеудені, қолтықты, шынтақты, білекті және шынашақты жұмсартыңыз. Эмоцияны ұлғайтпай, зейінді қолдың ішкі жағымен жүргізіңіз: жылуды, қысылуды, нәзіктікті немесе тыныштықты ғана байқаңыз.",
        },
    },
    {
        "id": "small_intestine",
        "category_id": 22,
        "source_url": "https://shiyanbin.ru/meridian-tonkoj-kishki-ig/",
        "active_time": "13:00-15:00",
        "passive_time": "01:00-03:00",
        "names": {
            "en": "Small Intestine Meridian",
            "ru": "Меридиан тонкого кишечника",
            "uz": "Ingichka ichak meridiani",
            "kz": "Ащы ішек меридианы",
        },
        "direction": {
            "en": "From the little finger along the outer side of the arm through the shoulder blade, neck, cheek, and ear.",
            "ru": "От мизинца по наружной стороне руки через лопатку, шею, щёку и область уха.",
            "uz": "Jimjiloqdan qo'lning tashqi tomoni bo'ylab kurak, bo'yin, yonoq va quloq sohasiga.",
            "kz": "Шынашақтан қолдың сыртқы жағымен жауырын, мойын, бет және құлақ аймағына қарай.",
        },
        "intro": {
            "en": "The Small Intestine Meridian is used here as a map for observing how the body separates clear from unclear: tension in the arm, shoulder blade, neck, jaw, and the ability to digest impressions without carrying everything inside.",
            "ru": "Меридиан тонкого кишечника здесь используется как карта наблюдения того, как тело отделяет ясное от неясного: напряжение руки, лопатки, шеи, челюсти и способность переваривать впечатления, не таща всё внутрь себя.",
            "uz": "Ingichka ichak meridiani bu yerda tana ravshanni noaniqdan qanday ajratishini kuzatish xaritasi sifatida ishlatiladi: qo'l, kurak, bo'yin, jag' tarangligi va taassurotlarni ichda ortiqcha ko'tarmasdan hazm qilish qobiliyati.",
            "kz": "Ащы ішек меридианы бұл жерде дененің айқынды айқын еместен қалай ажырататынын бақылау картасы ретінде қолданылады: қол, жауырын, мойын, жақ кернеуі және әсерлерді іште артық көтермей қорыту қабілеті.",
        },
        "practice": {
            "en": "Relax the little finger, wrist, elbow, shoulder blade, neck, and jaw. Let attention move from the little finger toward the ear, noticing where the line feels sharp, hot, blocked, or unexpectedly clear.",
            "ru": "Расслабьте мизинец, запястье, локоть, лопатку, шею и челюсть. Ведите внимание от мизинца к уху, замечая, где линия ощущается резкой, горячей, закрытой или неожиданно ясной.",
            "uz": "Jimjiloq, bilak, tirsak, kurak, bo'yin va jag'ni bo'shating. Diqqatni jimjiloqdan quloqqa qarab olib boring, chiziq qayerda o'tkir, issiq, yopiq yoki kutilmaganda ravshan sezilishini kuzating.",
            "kz": "Шынашақты, білекті, шынтақты, жауырынды, мойынды және жақты босатыңыз. Зейінді шынашақтан құлаққа қарай жүргізіп, сызықтың қай жерде өткір, ыстық, жабық немесе күтпегендей айқын сезілетінін байқаңыз.",
        },
    },
    {
        "id": "bladder",
        "category_id": 23,
        "source_url": "https://shiyanbin.ru/meridian-mochevogo-puzyrya-v/",
        "active_time": "15:00-17:00",
        "passive_time": "03:00-05:00",
        "names": {
            "en": "Bladder Meridian",
            "ru": "Меридиан мочевого пузыря",
            "uz": "Siydik pufagi meridiani",
            "kz": "Қуық меридианы",
        },
        "direction": {
            "en": "From the inner corner of the eye over the head, down the back and posterior legs toward the little toe.",
            "ru": "От внутреннего угла глаза через голову, спину и заднюю поверхность ног к мизинцу стопы.",
            "uz": "Ko'zning ichki burchagidan bosh, orqa va oyoqlarning orqa tomoni bo'ylab oyoq jimjilog'iga.",
            "kz": "Көздің ішкі бұрышынан бас, арқа және аяқтың артқы бетімен аяқтың шынашағына қарай.",
        },
        "intro": {
            "en": "The Bladder Meridian is used here as a map for observing the whole back line: eyes, head, spine, sacrum, back of the legs, and the body's relationship with effort, fear, rest, and release.",
            "ru": "Меридиан мочевого пузыря здесь используется как карта наблюдения всей задней линии тела: глаза, голова, позвоночник, крестец, задняя поверхность ног и то, как тело связано с усилием, страхом, отдыхом и отпусканием.",
            "uz": "Siydik pufagi meridiani bu yerda tananing butun orqa chizig'ini kuzatish xaritasi sifatida ishlatiladi: ko'zlar, bosh, umurtqa, dumg'aza, oyoqlarning orqa tomoni hamda tananing kuch, qo'rquv, dam olish va qo'yib yuborish bilan aloqasi.",
            "kz": "Қуық меридианы бұл жерде дененің бүкіл артқы сызығын бақылау картасы ретінде қолданылады: көздер, бас, омыртқа, сегізкөз, аяқтың артқы беті және дененің күш салумен, қорқынышпен, демалыспен әрі босатумен байланысы.",
        },
        "practice": {
            "en": "Let the back of the body soften from the eyes and head down through the spine, sacrum, calves, and feet. Notice where the line feels guarded, tired, cold, tense, or suddenly spacious.",
            "ru": "Позвольте задней линии тела смягчиться от глаз и головы вниз через позвоночник, крестец, икры и стопы. Замечайте, где линия ощущается защищённой, уставшей, холодной, напряжённой или неожиданно просторной.",
            "uz": "Tananing orqa chizig'i ko'z va boshdan umurtqa, dumg'aza, boldir va panjalargacha yumshashiga ruxsat bering. Chiziq qayerda himoyalangan, charchagan, sovuq, tarang yoki kutilmaganda keng sezilishini kuzating.",
            "kz": "Дененің артқы сызығы көз бен бастан омыртқа, сегізкөз, балтыр және табанға дейін жұмсарсын. Сызықтың қай жерде қорғанған, шаршаған, суық, керілген немесе күтпегендей кең сезілетінін байқаңыз.",
        },
    },
    {
        "id": "kidney",
        "category_id": 24,
        "source_url": "https://shiyanbin.ru/meridian-pochek-r/",
        "active_time": "17:00-19:00",
        "passive_time": "05:00-07:00",
        "names": {
            "en": "Kidney Meridian",
            "ru": "Меридиан почек",
            "uz": "Buyrak meridiani",
            "kz": "Бүйрек меридианы",
        },
        "direction": {
            "en": "From the sole of the foot up the inner leg through the abdomen and chest toward the root of the tongue.",
            "ru": "От подошвы стопы вверх по внутренней стороне ноги через живот и грудь к корню языка.",
            "uz": "Oyoq kaftidan oyoqning ichki tomoni bo'ylab qorin va ko'krak orqali til ildiziga.",
            "kz": "Табаннан аяқтың ішкі жағымен іш пен кеуде арқылы тіл түбіне қарай.",
        },
        "intro": {
            "en": "The Kidney Meridian is used here as a map for observing deep resource: feet, inner legs, pelvis, lower back, breath depth, fear, will, and the quiet strength that is not loud but steady.",
            "ru": "Меридиан почек здесь используется как карта наблюдения глубинного ресурса: стопы, внутренняя линия ног, таз, поясница, глубина дыхания, страх, воля и тихая сила, которая не шумит, но держит.",
            "uz": "Buyrak meridiani bu yerda chuqur resursni kuzatish xaritasi sifatida ishlatiladi: panjalar, oyoqlarning ichki chizig'i, chanoq, bel, nafas chuqurligi, qo'rquv, iroda va baland ovoz qilmaydigan, ammo ushlab turadigan sokin kuch.",
            "kz": "Бүйрек меридианы бұл жерде терең ресурсты бақылау картасы ретінде қолданылады: табандар, аяқтың ішкі сызығы, жамбас, бел, тыныстың тереңдігі, қорқыныш, ерік және айқайламайтын, бірақ ұстап тұратын тыныш күш.",
        },
        "practice": {
            "en": "Begin at the soles and let attention rise slowly along the inner legs toward the pelvis, abdomen, and chest. Notice where the body feels empty, cold, deep, grounded, or quietly alive.",
            "ru": "Начните с подошв и медленно ведите внимание по внутренней стороне ног к тазу, животу и груди. Замечайте, где тело ощущается пустым, холодным, глубоким, заземлённым или тихо живым.",
            "uz": "Panjalardan boshlang va diqqatni oyoqlarning ichki tomoni bo'ylab chanoq, qorin va ko'krakka sekin olib boring. Tana qayerda bo'sh, sovuq, chuqur, tayanchli yoki sokin tirik sezilishini kuzating.",
            "kz": "Табаннан бастап, зейінді аяқтың ішкі жағымен жамбасқа, ішке және кеудеге қарай баяу жүргізіңіз. Дененің қай жерде бос, суық, терең, орнықты немесе тыныш тірі сезілетінін байқаңыз.",
        },
    },
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
        code = normalize_point_code(f"{match.group(1).upper()}{match.group(2)}".replace(".", ""))
        name = match.group(3).strip()
        alt_code = match.group(4).strip() if match.group(4) else ""
        result.append((urllib.parse.urljoin("https://www.eledia.ru/", href), code, name, alt_code))
    return result


def fetch_category_pages(category_url: str, max_pages: int = 8) -> list[str]:
    """Fetch category listing pages, including Eledia pagination like /publ/23-2."""
    pages = []
    for page_num in range(1, max_pages + 1):
        page_url = category_url if page_num == 1 else f"{category_url}-{page_num}"
        try:
            page_html = fetch(page_url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and page_num > 1:
                break
            raise
        entries = point_entries(page_html)
        if page_num > 1 and not entries:
            break
        pages.append(page_html)
        time.sleep(0.15)
    return pages


def normalize_point_code(code: str) -> str:
    """Normalize visually similar Cyrillic channel letters to Latin codes."""
    translation = str.maketrans({
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "У": "Y",
        "Х": "X",
    })
    return code.translate(translation)


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
    category_html = "\n".join(fetch_category_pages(category_url))
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
