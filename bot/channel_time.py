"""Texts of the "by channel hours" meridian reminder mode (the scheduler picks the time)."""

from typing import Any

TEXTS = {
    "ru": {
        "btn_on": "🕰 По часам канала",
        "btn_off": "↩️ Вернуть своё время {time}",
        "hint": "Или нажмите «По часам канала»: напоминание будет приходить, когда активен меридиан, который вы "
                "сейчас проходите (желудок в 07:00, сердце в 11:00). Каналы, активные ночью, например лёгкие и "
                "печень, напомнят в ваше время <code>{time}</code>.",
        "hint_on": "Сейчас напоминания идут по часам канала. Если ввести время, бот вернётся к нему.",
        "on_day": "✅ Напоминания по меридианам теперь идут по часам канала. Сейчас у вас <b>{name}</b>, "
                  "напоминание придёт в {time}.",
        "on_night": "✅ Напоминания по меридианам теперь идут по часам канала. <b>{name}</b> активен ночью "
                    "({window}), поэтому напоминание придёт в ваше время {time}.",
        "on_now": "✅ Напоминания по меридианам теперь идут по часам канала. Часы канала <b>{name}</b> идут прямо "
                  "сейчас, поэтому напоминание придёт через минуту.",
        "on_none": "✅ Напоминания по меридианам теперь идут по часам канала. У канала <b>{name}</b> нет своего "
                   "часа, поэтому напоминание придёт в ваше время {time}.",
        "off": "✅ Напоминания по меридианам снова приходят в ваше время {time}.",
        "settings_auto": "по часам канала, сейчас {time}",
        "sent_today": "Сегодня напоминание уже приходило, следующее будет завтра.",
    },
    "en": {
        "btn_on": "🕰 By channel hours",
        "btn_off": "↩️ Back to my time {time}",
        "hint": "Or tap «By channel hours»: the reminder will come while the meridian you are studying is "
                "active (stomach at 07:00, heart at 11:00). Channels active at night, such as the lung and "
                "liver, will remind you at your time <code>{time}</code>.",
        "hint_on": "Reminders follow the channel hours now. Type a time and the bot returns to it.",
        "on_day": "✅ Meridian reminders now follow the channel hours. You are on <b>{name}</b>, so the "
                  "reminder comes at {time}.",
        "on_night": "✅ Meridian reminders now follow the channel hours. <b>{name}</b> is active at night "
                    "({window}), so the reminder comes at your time {time}.",
        "on_now": "✅ Meridian reminders now follow the channel hours. The hours of <b>{name}</b> are going on "
                  "right now, so the reminder comes in a minute.",
        "on_none": "✅ Meridian reminders now follow the channel hours. <b>{name}</b> has no hour of its own, so "
                   "the reminder comes at your time {time}.",
        "off": "✅ Meridian reminders come at your time {time} again.",
        "settings_auto": "by channel hours, now {time}",
        "sent_today": "Today's reminder has already come, the next one is tomorrow.",
    },
    "uz": {
        "btn_on": "🕰 Kanal soatlari bo'yicha",
        "btn_off": "↩️ O'z vaqtimga qaytish {time}",
        "hint": "Yoki «Kanal soatlari bo'yicha» tugmasini bosing: eslatma siz hozir o'rganayotgan meridian faol "
                "bo'lgan paytda keladi (oshqozon — 07:00, yurak — 11:00). Tunda faol kanallar, masalan o'pka va "
                "jigar, sizning vaqtingizda eslatadi: <code>{time}</code>.",
        "hint_on": "Hozir eslatmalar kanal soatlari bo'yicha keladi. Vaqt kiritsangiz, bot unga qaytadi.",
        "on_day": "✅ Meridian eslatmalari endi kanal soatlari bo'yicha keladi. Hozir sizda <b>{name}</b>, "
                  "eslatma vaqti: {time}.",
        "on_night": "✅ Meridian eslatmalari endi kanal soatlari bo'yicha keladi. <b>{name}</b> tunda faol "
                    "({window}), shuning uchun eslatma sizning vaqtingizda keladi: {time}.",
        "on_now": "✅ Meridian eslatmalari endi kanal soatlari bo'yicha keladi. <b>{name}</b> soatlari hozir "
                  "davom etmoqda, shuning uchun eslatma bir daqiqadan keyin keladi.",
        "on_none": "✅ Meridian eslatmalari endi kanal soatlari bo'yicha keladi. <b>{name}</b> kanalining o'z "
                   "soati yo'q, shuning uchun eslatma sizning vaqtingizda keladi: {time}.",
        "off": "✅ Meridian eslatmalari yana sizning vaqtingizda keladi: {time}.",
        "settings_auto": "kanal soatlari bo'yicha, hozir {time}",
        "sent_today": "Bugungi eslatma allaqachon kelgan, keyingisi ertaga.",
    },
    "kz": {
        "btn_on": "🕰 Арна сағаттары бойынша",
        "btn_off": "↩️ Өз уақытыма қайту {time}",
        "hint": "Немесе «Арна сағаттары бойынша» батырмасын басыңыз: еске салу сіз қазір өтіп жатқан меридиан "
                "белсенді кезде келеді (асқазан — 07:00, жүрек — 11:00). Түнде белсенді арналар, мысалы өкпе мен "
                "бауыр, сіздің уақытыңызда еске салады: <code>{time}</code>.",
        "hint_on": "Қазір еске салулар арна сағаттары бойынша келеді. Уақыт енгізсеңіз, бот соған қайтады.",
        "on_day": "✅ Меридиан еске салулары енді арна сағаттары бойынша келеді. Қазір сізде <b>{name}</b>, "
                  "еске салу уақыты: {time}.",
        "on_night": "✅ Меридиан еске салулары енді арна сағаттары бойынша келеді. <b>{name}</b> түнде белсенді "
                    "({window}), сондықтан еске салу сіздің уақытыңызда келеді: {time}.",
        "on_now": "✅ Меридиан еске салулары енді арна сағаттары бойынша келеді. <b>{name}</b> сағаттары дәл "
                  "қазір жүріп жатыр, сондықтан еске салу бір минуттан кейін келеді.",
        "on_none": "✅ Меридиан еске салулары енді арна сағаттары бойынша келеді. <b>{name}</b> арнасының өз "
                   "сағаты жоқ, сондықтан еске салу сіздің уақытыңызда келеді: {time}.",
        "off": "✅ Меридиан еске салулары қайтадан сіздің уақытыңызда келеді: {time}.",
        "settings_auto": "арна сағаттары бойынша, қазір {time}",
        "sent_today": "Бүгінгі еске салу келіп қойды, келесісі ертең.",
    },
}


def text(key: str, language: str, **kwargs: Any) -> str:
    """A text in the user's language (English when the language is unknown)."""
    template = TEXTS.get(language, TEXTS["en"]).get(key) or TEXTS["en"][key]
    return template.format(**kwargs) if kwargs else template
