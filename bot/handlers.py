"""Command handlers for yoga bot."""

import asyncio
import logging
import re
from html import escape
from typing import List, Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaAnimation
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from telegram.error import BadRequest

from .storage import JsonStorage, User, Feedback
from .scheduler import YogaScheduler
from .utils import (
    PrinciplesManager, 
    MeridiansManager,
    is_valid_timezone, 
    is_valid_time_format, 
    validate_skip_days,
    format_principle_message,
    format_meridian_intro,
    format_meridian_point,
    get_principle_image_path,
    get_meridian_image_path
)


logger = logging.getLogger(__name__)

MERIDIAN_POINTS_PAGE_SIZE = 10


# Multilingual texts
TEXTS = {
    "en": {
        "welcome": (
            "🕊️ **Welcome to Yoga Principles Bot!**\n\n"
            "🎯 **What I do:**\n"
            "Every day I send you one of the 10 fundamental yoga principles (yamas and niyamas) "
            "at your preferred time with full description and practical tips.\n\n"
            "🌟 **Who will find this useful:**\n"
            "• Yoga practitioners of any level\n"
            "• Those who want to develop mindfulness\n"
            "• People striving for spiritual growth\n"
            "• Anyone interested in yoga philosophy\n\n"
            "🔄 **How it works:**\n"
            "• Principles are chosen randomly for each user\n"
            "• Repetitions are possible — this is normal and helpful!\n"
            "• Each principle is a daily lesson\n"
            "• You can skip certain days of the week\n\n"
            "Let's start with choosing your preferred language:"
        ),
        "language_chosen": "✅ Language set to English!",
        "timezone_step": (
            "📍 **Step 1/3: Time Zone**\n"
                "Choose your time zone:"
        ),
        "timezone_custom": "⌨️ Enter manually",
        "timezone_saved": "✅ Time zone saved!",
        "time_step": (
            "⏰ **Step 2/3: Send Time**\n"
            "Please specify time in HH:MM format (e.g., 08:00, 20:30)\n\n"
            "Morning time is recommended for better perception of principles."
        ),
        "time_saved": "✅ Send time saved!",
        "skip_days_step": (
            "📅 **Step 3/3: Days to Skip (optional)**\n"
            "Specify weekdays when you DON'T want to receive messages.\n\n"
            "Format: day numbers separated by commas (0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun)\n"
            "Examples:\n"
            "• `5,6` - skip weekends\n"
            "• `0,2,4` - skip Mon, Wed, Fri\n"
            "• `-` or just Enter - don't skip days"
        ),
        "setup_complete": (
            "🎉 **Setup Complete!**\n\n"
            "📋 **Your Settings:**\n"
            "🕐 Time: {time}\n"
            "🌍 Time Zone: {timezone}\n"
            "📅 Skip Days: {skip_days}\n\n"
            "✨ Your first yoga principle will be sent at the next scheduled time!\n\n"
            "Use /test to get a test message."
        ),
        "already_subscribed": (
            "🧘 You're already subscribed to daily yoga principles!\n\n"
            "Use /settings to change settings or /stop to stop the bot."
        ),
        "unsubscribed": (
            "The bot has been stopped. Reminders will no longer be sent.\n\n"
            "Use /start if you want to return."
        ),
        "not_subscribed": "You were not subscribed to the newsletter.",
        "current_settings": (
            "⚙️ **Your Current Settings:**\n\n"
            "🌐 Language: {user_language}\n"
            "🕐 Send Time: `{time}`\n"
            "🌍 Time Zone: `{timezone}`\n"
            "📅 Skip Days: {skip_days}\n\n"
            "To change settings, use /start for new setup."
        ),
        "not_subscribed_test": "You're not subscribed to the newsletter. Use /start to subscribe.",
        "test_failed": "Failed to send test message.",
        "invalid_timezone": "❌ Invalid time zone format. Please try again.\n\nExamples: Europe/Moscow, Asia/Tashkent, UTC",
        "invalid_time": "❌ Invalid time format. Use HH:MM format (e.g., 08:00)",
        "invalid_skip_days": "❌ Invalid days format. Use numbers from 0 to 6 separated by commas.",
        "setup_error": "❌ Error saving settings. Please try again.",
        "error": "An error occurred. Please try again.",
        "choose_language": "Please choose your language:",
        "english": "🇺🇸 English",
        "russian": "🇷🇺 Русский",
        "menu": "📋 **Main Menu**",
        "menu_settings": "⚙️ Settings",
        "menu_test": "🧪 Test Message",
        "sending_test": "🧪 Sending test message...",
        "menu_about": "ℹ️ About Bot",
        "menu_feedback": "💌 Feedback & Ideas",
        "menu_stop": "⏹ Stop bot",
        "settings_menu": "⚙️ **Settings Menu**\n\nWhat would you like to change?",
        "change_language": "🌐 Change Language",
        "change_time": "⏰ Change Send Time",
        "change_timezone": "🌍 Change Time Zone",
        "change_skip_days": "📅 Change Skip Days",
        "back_to_menu": "🔙 Back to Menu",
        "skip_days_improved": (
            "📅 **Days to Skip (optional)**\n\n"
            "You can:\n"
            "• Enter day numbers: `5,6` (skip weekends)\n"
            "• Enter day numbers: `0,2,4` (skip Mon, Wed, Fri)\n"
            "• Type anything else to not skip any days\n\n"
            "Examples: 'no skip', 'don't skip', '-', or just press Enter"
        ),
        "no_skip_days": "✅ No days will be skipped",
        "about_text": (
            "🕊️ **Yama/Niyama Training Bot**\n\n"
            "This bot helps you practice yoga principles (Yama and Niyama) daily. "
            "Each day you receive one principle that becomes your focus of attention for the entire day.\n\n"
            "🌟 **Features:**\n"
            "• Principles are chosen randomly - everyone has their own path!\n"
            "• Repetitions help better understand the principles\n"
            "• Practice the principle throughout the day\n"
            "• Develop mindfulness in everyday life\n\n"
            "⚙️ **Capabilities:**\n"
            "🔹 **Random selection** of principle for each user\n"
            "🔹 **Two languages:** English and Russian\n"
            "🔹 **Flexible settings** for receiving time\n"
            "🔹 **Skip days** when you need to rest\n\n"
            "Created with ❤️ for your spiritual growth. Let's change for the better together!"
        ),
        "feedback_prompt": (
            "💌 **Share Your Feedback & Ideas**\n\n"
            "Your opinion and suggestions matter! Please share:\n"
            "• How do you like the bot?\n"
            "• What features would you like to see?\n"
            "• Any suggestions for improvement?\n"
            "• Issues you've encountered\n"
            "• Ideas for new principles or content\n\n"
            "Just write your message below:"
        ),
        "feedback_sent": "✅ Thank you for your feedback! Your message has been sent to the developers.",
        "feedback_too_long": "❌ Message too long. Please keep it under 1000 characters.",
        "feedback_rate_limit": "⏰ Please wait before sending another feedback. You can send feedback once every 10 minutes.",
        "feedback_error": "❌ Error saving your feedback. Please try again later."
    },
    "ru": {
        "welcome": (
            "🕊️ **Добро пожаловать в бот принципов йоги!**\n\n"
            "🎯 **Что я делаю:**\n"
            "Каждый день отправляю вам один из 10 основных принципов йоги (ямы и ниямы) "
            "в удобное для вас время.\n\n"
            "🌟 **Для кого это будет полезно:**\n"
            "• Практикующим йогу любого уровня\n"
            "• Тем, кто хочет развивать осознанность\n"
            "• Людям, которые стремятся к Развитию\n"
            "• Всем, кто интересуется философией йоги\n\n"
            "🔄 **Как это работает:**\n"
            "• Принципы выбираются случайно для каждого пользователя\n"
            "• Повторения возможны — это нормально и полезно - укаждого своя судьба!\n"
            "• Каждый принцип — это урок на день, мы стараемся придерживаться этого принципа на протяжении всего дня, во всех аспектах жизни\n"
            "• Вы можете пропускать определённые дни недели\n\n"
            "Начнём с выбора предпочитаемого языка:"
        ),
        "language_chosen": "✅ Язык установлен: Русский!",
        "timezone_step": (
            "📍 **Шаг 1/3: Часовой пояс**\n"
            "Выберите ваш часовой пояс:"
        ),
        "timezone_custom": "⌨️ Ввести вручную",
        "timezone_saved": "✅ Часовой пояс сохранён!",
        "time_step": (
            "⏰ **Шаг 2/3: Время отправки**\n"
            "Укажите время в формате ЧЧ:ММ (например: 08:00, 20:30)\n\n"
            "Рекомендуется утреннее время для лучшего восприятия принципов."
        ),
        "time_saved": "✅ Время отправки сохранено!",
        "skip_days_step": (
            "📅 **Шаг 3/3: Дни для пропуска (необязательно)**\n"
            "Укажите дни недели, в которые НЕ нужно присылать сообщения.\n\n"
            "Формат: номера дней через запятую (0=Пн, 1=Вт, 2=Ср, 3=Чт, 4=Пт, 5=Сб, 6=Вс)\n"
            "Примеры:\n"
            "• `5,6` - пропустить выходные\n"
            "• `0,2,4` - пропустить пн, ср, пт\n"
            "• `-` или просто Enter - не пропускать дни"
        ),
        "setup_complete": (
            "🎉 **Настройка завершена!**\n\n"
            "📋 **Ваши настройки:**\n"
            "🕐 Время: {time}\n"
            "🌍 Часовой пояс: {timezone}\n"
            "📅 Пропускать: {skip_days}\n\n"
            "✨ Первый принцип йоги будет отправлен в ближайшее запланированное время!\n\n"
            "Используйте /test для получения тестового сообщения."
        ),
        "already_subscribed": (
            "🧘 Вы уже подписаны на ежедневные принципы йоги!\n\n"
            "Используйте /settings для изменения настроек или /stop, чтобы остановить бота."
        ),
        "unsubscribed": (
            "Бот остановлен. Напоминания больше не будут приходить.\n\n"
            "Если захотите вернуться, используйте /start."
        ),
        "not_subscribed": "Вы не были подписаны на рассылку.",
        "current_settings": (
            "⚙️ **Ваши текущие настройки:**\n\n"
            "🌐 Язык: {user_language}\n"
            "🕐 Время отправки: `{time}`\n"
            "🌍 Часовой пояс: `{timezone}`\n"
            "📅 Пропускать дни: {skip_days}\n\n"
            "Чтобы изменить настройки, используйте /start для новой настройки."
        ),
        "not_subscribed_test": "Вы не подписаны на рассылку. Используйте /start для подписки.",
        "test_failed": "Не удалось отправить тестовое сообщение.",
        "invalid_timezone": "❌ Неверный формат часового пояса. Попробуйте еще раз.\n\nПримеры: Europe/Moscow, Asia/Tashkent, UTC",
        "invalid_time": "❌ Неверный формат времени. Используйте формат ЧЧ:ММ (например: 08:00)",
        "invalid_skip_days": "❌ Неверный формат дней. Используйте числа от 0 до 6 через запятую.",
        "setup_error": "❌ Ошибка при сохранении настроек. Попробуйте еще раз.",
        "error": "Произошла ошибка. Попробуйте еще раз.",
        "choose_language": "Пожалуйста, выберите ваш язык:",
        "english": "🇺🇸 English",
        "russian": "🇷🇺 Русский",
        "menu": "📋 **Главное меню**",
        "menu_settings": "⚙️ Настройки",
        "menu_test": "🧪 Тестовое сообщение",
        "sending_test": "🧪 Отправляю тестовое сообщение...",
        "menu_about": "ℹ️ О боте",
        "menu_feedback": "💌 Отзывы и идеи",
        "menu_stop": "⏹ Остановить бота",
        "settings_menu": "⚙️ **Меню настроек**\n\nЧто вы хотите изменить?",
        "change_language": "🌐 Изменить язык",
        "change_time": "⏰ Изменить время отправки",
        "change_timezone": "🌍 Изменить часовой пояс",
        "change_skip_days": "📅 Изменить дни пропуска",
        "back_to_menu": "🔙 Назад в меню",
        "skip_days_improved": (
            "📅 **Дни для пропуска (необязательно)**\n\n"
            "Вы можете:\n"
            "• Ввести номера дней: `5,6` (пропустить выходные)\n"
            "• Ввести номера дней: `0,2,4` (пропустить пн, ср, пт)\n"
            "• Написать что угодно другое, чтобы не пропускать дни\n\n"
            "Примеры: 'не пропускать', 'нет', '-', или просто нажмите Enter"
        ),
        "no_skip_days": "✅ Дни не будут пропускаться",
        "about_text": (
            "🕊️ **Бот для тренировки Ямы/Ниямы**\n\n"
            "Этот бот помогает вам ежедневно практиковать принципы йоги (Яма и Нияма). "
            "Каждый день вы получаете один принцип, который становится вашим фокусом внимания на весь день.\n\n"
            "🌟 **Особенности:**\n"
            "• Принципы выбираются случайно - у каждого своя судьба!\n"
            "• Повторения принципов помогают лучше их усвоить\n"
            "• Практикуем принцип в течение всего дня\n"
            "• Развиваем осознанность в повседневной жизни\n\n"
            "⚙️ **Возможности:**\n"
            "🔹 **Случайный выбор** принципа для каждого\n"
            "🔹 **Два языка:** русский и английский\n"
            "🔹 **Гибкие настройки** времени получения\n"
            "🔹 **Пропуск дней** когда нужно отдохнуть\n\n"
            "Создано с ❤️ для вашего духовного развития. Давайте меняться к лучшему вместе!"
        ),
        "feedback_prompt": (
            "💌 **Поделитесь отзывом и идеями**\n\n"
            "Ваше мнение и предложения очень важны! Поделитесь:\n"
            "• Как вам бот?\n"
            "• Какие функции хотели бы видеть?\n"
            "• Есть предложения по улучшению?\n"
            "• Нашли какие-то проблемы?\n"
            "• Идеи для новых принципов или контента\n\n"
            "Просто напишите ваше сообщение ниже:"
        ),
        "feedback_sent": "✅ Спасибо за ваш отзыв! Ваше сообщение отправлено разработчикам.",
        "feedback_too_long": "❌ Сообщение слишком длинное. Пожалуйста, сократите его до 1000 символов.",
        "feedback_rate_limit": "⏰ Пожалуйста, подождите перед отправкой другого отзыва. Вы можете отправить отзыв один раз каждые 10 минут.",
        "feedback_error": "❌ Ошибка при сохранении вашего отзыва. Пожалуйста, попробуйте позже."
    },
    "uz": {
        "welcome": (
            "🕊️ **Yoga tamoyillari botiga xush kelibsiz!**\n\n"
            "🎯 **Men nima qilaman:**\n"
            "Har kuni sizga 10 ta asosiy yoga tamoyilidan birini (yamalar va niyamalar) "
            "siz uchun qulay vaqtda yuboran.\n\n"
            "🌟 **Bu kimlar uchun foydali:**\n"
            "• Har qanday darajadagi yoga amaliyotchilari\n"
            "• Onglilikni rivojlantirmoqchi bo'lganlar\n"
            "• Ruhiy o'sishga intiluvchi odamlar\n"
            "• Yoga falsafasiga qiziquvchi barcha kishilar\n\n"
            "🔄 **Bu qanday ishlaydi:**\n"
            "• Tamoyillar har bir foydalanuvchi uchun tasodifiy tanlanadi\n"
            "• Takrorlashlar mumkin — bu normal va foydali!\n"
            "• Har bir tamoyil — kunlik darsdir\n"
            "• Siz haftaning ma'lum kunlarini o'tkazib yuborishingiz mumkin\n\n"
            "Keling, kerakli tilni tanlashdan boshlaylik:"
        ),
        "language_chosen": "✅ Til o'zbekchaga o'rnatildi!",
        "timezone_step": (
            "📍 **1/3-qadam: Vaqt mintaqasi**\n"
            "Vaqt mintaqangizni tanlang:"
        ),
        "timezone_custom": "⌨️ Qo'lda kiriting",
        "timezone_saved": "✅ Vaqt mintaqasi saqlandi!",
        "time_step": (
            "⏰ **2/3-qadam: Yuborish vaqti**\n"
            "Vaqtni SS:DD formatida ko'rsating (masalan: 08:00, 20:30)\n\n"
            "Tamoyillarni yaxshiroq qabul qilish uchun ertalabki vaqt tavsiya etiladi."
        ),
        "time_saved": "✅ Yuborish vaqti saqlandi!",
        "skip_days_step": (
            "📅 **3/3-qadam: O'tkazib yuborish kunlari (ixtiyoriy)**\n"
            "Xabar yuborilmasligi kerak bo'lgan hafta kunlarini ko'rsating.\n\n"
            "Format: vergul bilan ajratilgan kunlar raqamlari (0=Du, 1=Se, 2=Ch, 3=Pa, 4=Ju, 5=Sh, 6=Ya)\n"
            "Misollar:\n"
            "• `5,6` - dam olish kunlarini o'tkazib yuborish\n"
            "• `0,2,4` - Du, Ch, Ju kunlarini o'tkazib yuborish\n"
            "• `-` yoki oddiy Enter - kunlarni o'tkazib yubormaslik"
        ),
        "skip_days_saved": "✅ O'tkazib yuborish kunlari saqlandi!",
        "setup_complete": (
            "🎉 **Sozlash yakunlandi!**\n\n"
            "📋 **Sizning sozlamalaringiz:**\n"
            "🕐 Vaqt: {time}\n"
            "🌍 Vaqt mintaqasi: {timezone}\n"
            "📅 O'tkazib yuborish kunlari: {skip_days}\n\n"
            "✨ Birinchi yoga tamoyili keyingi rejalashtirilgan vaqtda yuboriladi!\n\n"
            "/test dan test xabarini olish uchun foydalaning."
        ),
        "already_subscribed": "Siz allaqachon obuna bo'lgansiz. Sozlamalarni o'zgartirish uchun /settings dan foydalaning.",
        "unsubscribed": "Bot to'xtatildi. Eslatmalar endi yuborilmaydi.\n\nQaytmoqchi bo'lsangiz, /start dan foydalaning.",
        "not_subscribed": "Siz yangiliklar ro'yxatiga obuna bo'lmagan edingiz.",
        "current_settings": (
            "⚙️ **Sizning joriy sozlamalaringiz:**\n\n"
            "🌐 Til: {user_language}\n"
            "🕐 Yuborish vaqti: `{time}`\n"
            "🌍 Vaqt mintaqasi: `{timezone}`\n"
            "📅 O'tkazib yuborish kunlari: {skip_days}\n\n"
            "Sozlamalarni o'zgartirish uchun yangi sozlash uchun /start dan foydalaning."
        ),
        "not_subscribed_test": "Siz yangiliklar ro'yxatiga obuna bo'lmagansiz. Obuna bo'lish uchun /start dan foydalaning.",
        "test_failed": "Test xabarini yuborishda xatolik yuz berdi.",
        "invalid_timezone": "❌ Noto'g'ri vaqt mintaqasi formati. Iltimos, qayta urinib ko'ring.\n\nMisollar: Asia/Tashkent, Europe/Moscow, UTC",
        "invalid_time": "❌ Noto'g'ri vaqt formati. SS:DD formatidan foydalaning (masalan, 08:00)",
        "invalid_skip_days": "❌ Noto'g'ri kunlar formati. Vergul bilan ajratilgan 0 dan 6 gacha raqamlardan foydalaning.",
        "setup_error": "❌ Sozlamalarni saqlashda xatolik. Iltimos, qayta urinib ko'ring.",
        "error": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.",
        "choose_language": "Iltimos, tilingizni tanlang:",
        "english": "🇺🇸 English",
        "russian": "🇷🇺 Русский",
        "uzbek": "🇺🇿 O'zbek",
        "menu": "📋 **Asosiy menyu**",
        "menu_settings": "⚙️ Sozlamalar",
        "menu_test": "🧪 Test xabari",
        "sending_test": "🧪 Test xabarini yubormoqdaman...",
        "menu_about": "ℹ️ Bot haqida",
        "menu_feedback": "💌 Fikr va takliflar",
        "menu_stop": "⏹ Botni to'xtatish",
        "settings_menu": "⚙️ **Sozlamalar menyusi**\n\nNimani o'zgartirmoqchisiz?",
        "change_language": "🌐 Tilni o'zgartirish",
        "change_time": "⏰ Yuborish vaqtini o'zgartirish",
        "change_timezone": "🌍 Vaqt mintaqasini o'zgartirish",
        "change_skip_days": "📅 O'tkazib yuborish kunlarini o'zgartirish",
        "back_to_menu": "🔙 Menyuga qaytish",
        "about_text": (
            "🕊️ **Yoga tamoyillari boti haqida**\n\n"
            "Bu bot sizga har kuni yoga tamoyillaridan birini yuboradi.\n\n"
            "🎯 **Maqsad:** Yoga tamoyillarini kundalik hayotingizga kiritishga yordam berish\n\n"
            "📖 **Tamoyillar:**\n"
            "• 5 ta Yama (ijtimoiy tartib tamoyillari)\n"
            "• 5 ta Niyama (shaxsiy tartib tamoyillari)\n\n"
            "💝 **Bepul va ochiq manba**\n\n"
            "🌟 Har bir tamoyil sizning ruhiy o'sishingiz uchun kichik qadamdir!"
        ),
        "feedback_request": (
            "💌 **Fikr va takliflaringiz**\n\n"
            "Botni yaxshilash uchun fikrlaringizni yuboring:\n"
            "• Qanday xususiyatlar qo'shilsin?\n"
            "• Nimani o'zgartirish kerak?\n"
            "• Umumiy taassurotlaringiz\n\n"
            "Xabaringizni yozing:"
        ),
        "feedback_received": "✅ Rahmat! Sizning fikringiz qabul qilindi va ko'rib chiqiladi.",
        "feedback_too_long": "❌ Xabar juda uzun. Iltimos, uni 1000 belgigacha qisqartiring.",
        "feedback_rate_limit": "⏰ Iltimos, boshqa fikr yuborishdan oldin kuting. Har 10 daqiqada bir marta fikr yuborishingiz mumkin.",
        "feedback_error": "❌ Fikringizni saqlashda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring."
    },
    "kz": {
        "welcome": (
            "🕊️ **Йога принциптері ботына қош келдіңіз!**\n\n"
            "🎯 **Мен не істеймін:**\n"
            "Күн сайын сізге 10 негізгі йога принциптерінің бірін (ямалар мен ниямалар) "
            "сізге ыңғайлы уақытта жіберемін.\n\n"
            "🌟 **Бұл кімдерге пайдалы:**\n"
            "• Кез келген деңгейдегі йога практиктері\n"
            "• Саналылықты дамытқысы келетіндер\n"
            "• Рухани өсуге ұмтылушылар\n"
            "• Йога философиясына қызығушылық танытушылар\n\n"
            "🔄 **Бұл қалай жұмыс істейді:**\n"
            "• Принциптер әрбір пайдаланушы үшін кездейсоқ таңдалады\n"
            "• Қайталаулар мүмкін — бұл қалыпты және пайдалы!\n"
            "• Әрбір принцип — күнделікті сабақ\n"
            "• Сіз аптаның белгілі күндерін өткізіп жіберуіңізге болады\n\n"
            "Келіңіз, қажетті тілді таңдаудан бастайық:"
        ),
        "language_chosen": "✅ Тіл қазақшаға орнатылды!",
        "timezone_step": (
            "📍 **1/3-қадам: Уақыт белдеуі**\n"
            "Уақыт белдеуіңізді таңдаңыз:"
        ),
        "timezone_custom": "⌨️ Қолмен енгізу",
        "timezone_saved": "✅ Уақыт белдеуі сақталды!",
        "time_step": (
            "⏰ **2/3-қадам: Жіберу уақыты**\n"
            "Уақытты СС:ДД форматында көрсетіңіз (мысалы: 08:00, 20:30)\n\n"
            "Принциптерді жақсырақ қабылдау үшін таңертеңгілік уақыт ұсынылады."
        ),
        "time_saved": "✅ Жіберу уақыты сақталды!",
        "skip_days_step": (
            "📅 **3/3-қадам: Өткізіп жіберу күндері (қосымша)**\n"
            "Хабар жіберілмеу керек болатын апта күндерін көрсетіңіз.\n\n"
            "Формат: үтірмен бөлінген күндер сандары (0=Дс, 1=Сс, 2=Ср, 3=Бс, 4=Жм, 5=Сб, 6=Жк)\n"
            "Мысалдар:\n"
            "• `5,6` - демалыс күндерін өткізіп жіберу\n"
            "• `0,2,4` - Дс, Ср, Жм күндерін өткізіп жіберу\n"
            "• `-` немесе жай Enter - күндерді өткізіп жібермеу"
        ),
        "skip_days_saved": "✅ Өткізіп жіберу күндері сақталды!",
        "setup_complete": (
            "🎉 **Баптау аяқталды!**\n\n"
            "📋 **Сіздің баптауларыңыз:**\n"
            "🕐 Уақыт: {time}\n"
            "🌍 Уақыт белдеуі: {timezone}\n"
            "📅 Өткізіп жіберу күндері: {skip_days}\n\n"
            "✨ Алғашқы йога принципі келесі жоспарланған уақытта жіберіледі!\n\n"
            "/test арқылы тест хабарын алу үшін пайдаланыңыз."
        ),
        "already_subscribed": "Сіз қазірдің өзінде жазылғансыз. Баптауларды өзгерту үшін /settings пайдаланыңыз.",
        "unsubscribed": "Бот тоқтатылды. Еске салулар енді жіберілмейді.\n\nҚайта оралғыңыз келсе, /start қолданыңыз.",
        "not_subscribed": "Сіз жаңалықтар тізіміне жазылмағансыз.",
        "current_settings": (
            "⚙️ **Сіздің ағымдағы баптауларыңыз:**\n\n"
            "🌐 Тіл: {user_language}\n"
            "🕐 Жіберу уақыты: `{time}`\n"
            "🌍 Уақыт белдеуі: `{timezone}`\n"
            "📅 Өткізіп жіберу күндері: {skip_days}\n\n"
            "Баптауларды өзгерту үшін жаңа баптау үшін /start пайдаланыңыз."
        ),
        "not_subscribed_test": "Сіз жаңалықтар тізіміне жазылмағансыз. Жазылу үшін /start пайдаланыңыз.",
        "test_failed": "Тест хабарын жіберуде қате орын алды.",
        "invalid_timezone": "❌ Дұрыс емес уақыт белдеуі форматы. Қайтадан көріңіз.\n\nМысалдар: Asia/Almaty, Europe/Moscow, UTC",
        "invalid_time": "❌ Дұрыс емес уақыт форматы. СС:ДД форматын пайдаланыңыз (мысалы, 08:00)",
        "invalid_skip_days": "❌ Дұрыс емес күндер форматы. Үтірмен бөлінген 0 мен 6 арасындағы сандарды пайдаланыңыз.",
        "setup_error": "❌ Баптауларды сақтауда қате. Қайтадан көріңіз.",
        "error": "Қате орын алды. Қайтадан көріңіз.",
        "choose_language": "Тіліңізді таңдаңыз:",
        "english": "🇺🇸 English",
        "russian": "🇷🇺 Русский",
        "uzbek": "🇺🇿 O'zbek",
        "kazakh": "🇰🇿 Қазақша",
        "menu": "📋 **Негізгі мәзір**",
        "menu_settings": "⚙️ Баптаулар",
        "menu_test": "🧪 Тест хабар",
        "sending_test": "🧪 Тест хабарын жіберуде...",
        "menu_about": "ℹ️ Бот туралы",
        "menu_feedback": "💌 Пікірлер мен ұсыныстар",
        "menu_stop": "⏹ Ботты тоқтату",
        "settings_menu": "⚙️ **Баптаулар мәзірі**\n\nНені өзгерткіңіз келеді?",
        "change_language": "🌐 Тілді өзгерту",
        "change_time": "⏰ Жіберу уақытын өзгерту",
        "change_timezone": "🌍 Уақыт белдеуін өзгерту",
        "change_skip_days": "📅 Өткізіп жіберу күндерін өзгерту",
        "back_to_menu": "🔙 Мәзірге қайту",
        "about_text": (
            "🕊️ **Йога принциптері боты туралы**\n\n"
            "Бұл бот сізге күн сайын йога принциптерінің бірін жібереді.\n\n"
            "🎯 **Мақсаты:** Йога принциптерін күнделікті өміріңізге енгізуге көмектесу\n\n"
            "📖 **Принциптер:**\n"
            "• 5 Яма (әлеуметтік тәртіп принциптері)\n"
            "• 5 Нияма (жеке тәртіп принциптері)\n\n"
            "💝 **Тегін және ашық көз**\n\n"
            "🌟 Әрбір принцип сіздің рухани өсуіңіз үшін кішкентай қадам!"
        ),
        "feedback_request": (
            "💌 **Пікірлер мен ұсыныстарыңыз**\n\n"
            "Ботты жақсарту үшін пікірлеріңізді жіберіңіз:\n"
            "• Қандай мүмкіндіктер қосылсын?\n"
            "• Нені өзгерту керек?\n"
            "• Жалпы әсерлеріңіз\n\n"
            "Хабарыңызды жазыңыз:"
        ),
        "feedback_received": "✅ Рахмет! Сіздің пікіріңіз қабылданды және қаралады.",
        "feedback_too_long": "❌ Хабар тым ұзын. Оны 1000 таңбаға дейін қысқартыңыз.",
        "feedback_rate_limit": "⏰ Басқа пікір жібермес бұрын күтіңіз. Әр 10 минутта бір рет пікір жібере аласыз.",
        "feedback_error": "❌ Пікіріңізді сақтауда қате орын алды. Кейінірек көріңіз."
    }
}

# Admin texts (always in English, no Markdown to avoid parsing errors)
ADMIN_TEXTS = {
    "next_principle": "📋 Random principle for user {user_id}:\n\n{principle}\n\n💡 Principles are chosen randomly for each user",
    "no_principles": "No available principles for user {user_id}.",
    "add_usage": "Usage: /add <principle text>",
    "add_empty": "Principle text cannot be empty.",
    "add_success": "✅ Principle '{name}' successfully added!",
    "add_error": "❌ Error adding principle.",
    "stats": (
        "📊 Bot Statistics:\n\n"
        "👥 Total users: {total_users}\n"
        "✅ Active: {active_users}\n"
        "📨 Messages sent: {total_messages_sent}\n\n"
        "⏰ Scheduler:\n"
        "🔄 Scheduled jobs: {total_jobs}\n"
        "🎯 Jobs created: {jobs_created}\n"
        "🚀 Status: {status}"
    ),
    "broadcast_usage": "Usage: /broadcast <message>",
    "broadcast_empty": "Message text cannot be empty.",
    "broadcast_start": "📢 Starting broadcast to {count} users...",
    "broadcast_result": (
        "📢 Broadcast Results:\n\n"
        "✅ Sent: {sent}\n"
        "❌ Errors: {failed}\n"
        "👥 Total: {total}"
    ),
    "feedback_stats": (
        "💌 Feedback Statistics:\n\n"
        "📝 Total feedback: {total_feedback}\n"
        "📏 Average length: {average_length} chars\n"
        "💾 File size: {file_size_mb} MB\n\n"
        "🌐 By Language:\n{by_language}\n\n"
        "Use /feedback_list to see recent feedback"
    ),
    "feedback_list_header": "💌 Recent Feedback ({count} items):\n\n",
    "feedback_item": (
        "#{id} | {timestamp}\n"
        "👤 User: {chat_id} (@{username})\n"
        "🌐 Lang: {language} | 📏 {length} chars\n"
        "💬 {message}\n"
        "─────────────────\n"
    ),
    "no_feedback": "No feedback received yet.",
    "feedback_list_usage": "Usage: /feedback_list [limit] (default: 10, max: 50)",
    "admin_help": (
        "🔧 Admin Commands:\n\n"
        "📊 Statistics:\n"
        "• stats - Bot usage statistics\n"
        "• feedback_stats - Feedback statistics\n"
        "• feedback_list [limit] - View recent feedback\n\n"
        "📨 Messages:\n"
        "• next - Show random principle for user\n"
        "• broadcast <message> - Send message to all users\n\n"
        "🛠️ Management:\n"
        "• add <text> - Add new principle (not implemented)\n\n"
        "All commands are admin-only and require proper permissions."
    )
}

TEXTS_UPDATE = {
    "en": {
        "welcome": (
            "🕊️ **Welcome to Journey of Ascension!**\n\n"
            "Yama and Niyama are the ethical foundation of inner practice. "
            "Meridians are the next step: learning to feel attention, body, and energy through direct observation.\n\n"
            "Let's start with choosing your preferred language:"
        ),
        "onboarding_intro": (
            "<b>Journey of Ascension</b>\n\n"
            "Inner practice begins with a simple observation: we have attention, strength, and energy, and every day we either gather them or scatter them.\n\n"
            "<b>Yama and Niyama</b> help stop leaking energy through conflict, self-harm, dishonesty, excess, and unconscious habits. Each daily principle is not a one-day rule, but a focus that slowly becomes part of life.\n\n"
            "<b>Meridians</b> are a practical map of the body and Qi flow. You learn to feel points, notice closed areas, and gently bring attention, breath, and circulation back there.\n\n"
            "What would you like to study?"
        ),
        "initial_mode_question": "What would you like to study?",
        "timezone_step_principles": (
            "📍 <b>Step 1/3: Time Zone</b>\n\n"
            "Choose your time zone so the bot can send <b>Yama/Niyama</b> reminders at the correct local time for you."
        ),
        "timezone_step_meridians": (
            "📍 <b>Step 1/3: Time Zone</b>\n\n"
            "Choose your time zone so the bot can send <b>meridian</b> study reminders at the correct local time for you."
        ),
        "timezone_step_both": (
            "📍 <b>Step 1/3: Time Zone</b>\n\n"
            "Choose your time zone so the bot can send <b>Yama/Niyama</b> and <b>meridian</b> reminders at the correct local time for you."
        ),
        "time_step_principles": (
            "⏰ <b>Step 2/3: Reminder Time</b>\n\n"
            "Choose the time when the bot should send your daily <b>Yama/Niyama</b> principle.\n\n"
            "Format: HH:MM, for example 08:00 or 20:30."
        ),
        "time_step_meridians": (
            "⏰ <b>Step 2/3: Reminder Time</b>\n\n"
            "Choose the time when the bot should send your daily <b>meridian</b> focus.\n\n"
            "Format: HH:MM, for example 08:00 or 20:30."
        ),
        "time_step_both": (
            "⏰ <b>Step 2/3: Reminder Time</b>\n\n"
            "Choose the time when the bot should send your daily <b>Yama/Niyama</b> principle and <b>meridian</b> focus.\n\n"
            "Format: HH:MM, for example 08:00 or 20:30."
        ),
        "continue_setup": "Continue",
        "menu": "📋 **Journey of Ascension**",
        "menu_principles": "🧘🏻✨ Yama/Niyama",
        "menu_meridians": "☯️ Meridians",
        "menu_modes": "🧭 My Path",
        "menu_stop": "⏹ Stop bot",
        "principles_menu": (
            "🕊️ <b>Yama/Niyama</b>\n\n"
            "Yama and Niyama are the basic moral and ethical disciplines of yoga. They form the foundation for self-discipline, spiritual growth, and harmonious relations with the world.\n\n"
            "They are the first two limbs of classical eight-limbed yoga.\n\n"
            "<b>Yama</b> is how we relate to the outer world: non-violence, truthfulness, non-stealing, moderation, and non-possessiveness.\n\n"
            "<b>Niyama</b> is how we work with ourselves: purity, contentment, discipline, self-study, and surrender of the fruits of action.\n\n"
            "Open a random principle for contemplation or view the full list."
        ),
        "principles_random": "Random principle",
        "principles_all": "All principles",
        "principles_empty": "Principles are not available yet.",
        "change_modes": "🧭 My Path",
        "change_meridian_time": "☯️ Meridian Time",
        "mode_menu": (
            "🧭 <b>My Path</b>\n\n"
            "Choose what the bot should help you return to every day.\n\n"
            "<b>Yama/Niyama</b> is the foundation: less inner noise, fewer energy leaks, more honesty in action.\n\n"
            "<b>Meridians</b> are the body layer: points, channels, Qi flow, and the skill of feeling areas that were previously silent.\n\n"
            "You can begin with one direction or keep both active together."
        ),
        "mode_principles_only": "Yama/Niyama foundation",
        "mode_meridians_only": "Meridian study",
        "mode_both": "Both directions",
        "mode_saved": "✅ <b>Your path has been updated.</b>",
        "meridian_time_step": "☯️ <b>Meridian Reminder Time</b>\n\nEnter time in HH:MM format, for example 20:00.",
        "meridian_time_saved": "✅ Meridian reminder time saved.",
        "meridian_mode_menu": (
            "☯️ <b>How would you like to study meridians?</b>\n\n"
            "<b>Guided path</b> means the bot leads you through the meridians in a recommended order. You complete one channel, then move to the next.\n\n"
            "<b>Free study</b> means you choose any meridian yourself and explore it in your own order.\n\n"
            "Both options keep your progress and daily reminders."
        ),
        "meridian_guided_path": "🧭 Guided path",
        "meridian_free_choice": "👐 Free study",
        "meridian_change_path": "🧭 Study path",
        "meridian_guided_saved": "✅ <b>Guided path selected.</b>\n\nThe bot will lead you through the meridians step by step.",
        "meridian_free_saved": "✅ <b>Free study selected.</b>\n\nChoose any meridian you want to explore.",
        "meridian_measurements": "📏 How to measure cun",
        "meridian_back": "🔙 Back to meridians",
        "coming_soon": "soon",
        "meridian_measurements_text": (
            "📏 <b>Measurement System in TCM</b>\n\n"
            "Acupuncture point locations are often described in <b>cun</b>. A cun is not a fixed centimeter value: it is a body-relative unit measured on the person being studied.\n\n"
            "<b>1 cun:</b> the width of the thumb at the interphalangeal joint.\n\n"
            "<b>1.5 cun:</b> the width of the index and middle fingers together.\n\n"
            "<b>2 cun:</b> the width of three fingers together: index, middle, and ring finger.\n\n"
            "<b>3 cun:</b> the width of four fingers together, from index to little finger.\n\n"
            "<b>5 cun:</b> measure 3 cun and add about 2 cun, or divide the anatomical segment into equal parts if the source gives a proportional distance.\n\n"
            "Use cun as an orientation tool, then refine the point by touch: local sensitivity, a small hollow, warmth, pressure, or a clear response to attention."
        ),
        "meridians_menu": (
            "☯️ <b>Meridians</b>\n\n"
            "<b>Why study meridians?</b>\n\n"
            "Meridians are a map for learning how attention lives in the body. In Traditional Chinese Medicine they are described as channels through which Qi moves.\n\n"
            "Here we study them through practice: open one point, find it on the image, touch the area gently if needed, and listen for warmth, pressure, pulsation, emptiness, resistance, or a clear inner response.\n\n"
            "<b>If a point is hard to feel</b>, do not force it. Treat it as an area that needs more attention: soften the body, breathe through the point, and stay with it until the sensation becomes steadier.\n\n"
            "<b>How to move:</b> keep the points you have already felt in awareness, then add the next one. Gradually the separate points become one living line.\n\n"
            "This does not replace medical diagnosis or treatment. It is a practice of awareness, prevention, and inner discipline.\n\n"
            "Choose what you want to do now: continue practice, choose a study path, or open the TCM measurement guide for cun distances."
        ),
        "choose_meridian": "☯️ <b>Choose a meridian:</b>",
        "current_meridian": "Continue practice",
        "meridian_start_points": "Start with point 1",
        "all_points": "All points",
        "next_point": "Next point",
        "prev_point": "Previous point",
        "complete_meridian": "Complete meridian",
        "select_meridian": "Choose meridian",
        "no_points": "I could not open the points for this meridian right now. Please return to the meridian list or try again later.",
        "meridian_completed": "✅ <b>Meridian completed</b>\n\nChoose the next channel when you are ready.",
        "about_text": (
            "🕊️ <b>Journey of Ascension</b>\n\n"
            "This bot is meant to be a quiet support for real practice, not a collection of inspiring phrases.\n\n"
            "Every day it helps you return to one concrete focus: a Yama/Niyama principle or a meridian point. The aim is simple: notice where energy is spent unconsciously, stop wasting it, and learn to direct attention with more care.\n\n"
            "<b>Yama/Niyama</b> works with behaviour, speech, thoughts, discipline, and honesty with yourself.\n\n"
            "<b>Meridians</b> work with the body: channels, points, Qi flow, closed areas, breath, touch, and attention.\n\n"
            "Small repetitions matter. They turn an idea into something you can actually live."
        ),
        "feature_announcement": (
            "☯️ <b>New in Journey of Ascension: meridian practice</b>\n\n"
            "You can now study Chinese meridians inside the bot: choose a channel, open each point with its image, and move through the practice at your own pace.\n\n"
            "The daily reminder does not rush you forward. It simply brings you back to the current focus so attention can become steadier.\n\n"
            "Open /menu and choose <b>Meridians</b>."
        ),
        "already_subscribed": "🕊️ You are already subscribed to Journey of Ascension.\n\nUse /menu to choose practices or /settings to change reminders.",
        "unsubscribed": "The bot has been stopped. Reminders will no longer be sent.\n\nUse /start if you want to return.",
        "stop_feedback_prompt": "If you want, you can send one message and tell why you decided to stop using the bot. This is optional.",
        "stop_feedback_thanks": "Thank you, I will pass on your feedback.\n\nUse /start if you want to return.",
        "not_subscribed_test": "You're not subscribed yet. Use /start to begin.",
        "setup_complete": (
            "🎉 **Setup Complete!**\n\n"
            "📋 **Your Settings:**\n"
            "🕐 Time: {time}\n"
            "🌍 Time Zone: {timezone}\n"
            "📅 Skip Days: {skip_days}\n\n"
            "You can open /menu at any time to change your practice mode or explore meridians."
        )
    },
    "ru": {
        "welcome": (
            "🕊️ **Добро пожаловать в Journey of Ascension!**\n\n"
            "Яма и Нияма остаются нравственным фундаментом внутренней практики. "
            "Меридианы — следующая ступень: учиться чувствовать внимание, тело и энергию через прямое наблюдение.\n\n"
            "Начнём с выбора языка:"
        ),
        "onboarding_intro": (
            "<b>Journey of Ascension</b>\n\n"
            "Внутренняя практика начинается с простого наблюдения: у нас есть внимание, сила и энергия. Каждый день мы либо собираем их, либо рассеиваем.\n\n"
            "<b>Яма и Нияма</b> помогают перестать сливать энергию через конфликты, вред себе, нечестность, избыточность и привычки, которые мы обычно не замечаем. Ежедневный принцип — это не правило на один день, а фокус, который постепенно встраивается в жизнь.\n\n"
            "<b>Меридианы</b> — практическая карта тела и течения Ци. Вы учитесь чувствовать точки, замечать закрытые зоны и мягко возвращать туда внимание, дыхание и циркуляцию.\n\n"
            "Что вы хотели бы изучать?"
        ),
        "initial_mode_question": "Что вы хотели бы изучать?",
        "timezone_step_principles": (
            "📍 <b>Шаг 1/3: Часовой пояс</b>\n\n"
            "Выберите ваш часовой пояс, чтобы бот присылал напоминания по <b>Яме и Нияме</b> в правильное для вас местное время."
        ),
        "timezone_step_meridians": (
            "📍 <b>Шаг 1/3: Часовой пояс</b>\n\n"
            "Выберите ваш часовой пояс, чтобы бот присылал материалы и напоминания по <b>меридианам</b> в правильное для вас местное время."
        ),
        "timezone_step_both": (
            "📍 <b>Шаг 1/3: Часовой пояс</b>\n\n"
            "Выберите ваш часовой пояс, чтобы бот присылал напоминания по <b>Яме/Нияме</b> и материалы по <b>меридианам</b> в правильное для вас местное время."
        ),
        "time_step_principles": (
            "⏰ <b>Шаг 2/3: Время отправки</b>\n\n"
            "Укажите время, когда бот будет присылать ежедневный принцип <b>Ямы/Ниямы</b>.\n\n"
            "Формат: ЧЧ:ММ, например 08:00 или 20:30."
        ),
        "time_step_meridians": (
            "⏰ <b>Шаг 2/3: Время отправки</b>\n\n"
            "Укажите время, когда бот будет присылать ежедневный фокус по <b>меридианам</b>.\n\n"
            "Формат: ЧЧ:ММ, например 08:00 или 20:30."
        ),
        "time_step_both": (
            "⏰ <b>Шаг 2/3: Время отправки</b>\n\n"
            "Укажите время, когда бот будет присылать ежедневный принцип <b>Ямы/Ниямы</b> и фокус по <b>меридианам</b>.\n\n"
            "Формат: ЧЧ:ММ, например 08:00 или 20:30."
        ),
        "continue_setup": "Продолжить",
        "menu": "📋 **Journey of Ascension**",
        "menu_principles": "🧘🏻✨ Яма/Нияма",
        "menu_meridians": "☯️ Меридианы",
        "menu_modes": "🧭 Мой путь",
        "menu_stop": "⏹ Остановить бота",
        "principles_menu": (
            "🕊️ <b>Яма/Нияма</b>\n\n"
            "Яма и Нияма — это базовые морально-этические правила и ступени в йоге. Они формируют фундамент для самодисциплины, духовного развития и гармоничных отношений с миром.\n\n"
            "Они образуют первые две ступени классической восьмиступенчатой йоги.\n\n"
            "<b>Яма</b> — принципы взаимодействия с окружающим миром: ненасилие, правдивость, неворовство, умеренность и нестяжательство.\n\n"
            "<b>Нияма</b> — принципы работы над собой: чистота, удовлетворённость, дисциплина, самоизучение и посвящение плодов практики высшему.\n\n"
            "Можно открыть случайный принцип для размышления или посмотреть весь список."
        ),
        "principles_random": "Случайный принцип",
        "principles_all": "Все принципы",
        "principles_empty": "Принципы пока недоступны.",
        "change_modes": "🧭 Мой путь",
        "change_meridian_time": "☯️ Время меридианов",
        "mode_menu": (
            "🧭 <b>Мой путь</b>\n\n"
            "Выберите, к чему бот будет помогать возвращаться каждый день.\n\n"
            "<b>Яма/Нияма</b> — фундамент: меньше внутреннего шума, меньше утечек энергии, больше честности в поступках.\n\n"
            "<b>Меридианы</b> — телесный слой: точки, каналы, течение Ци и навык чувствовать зоны, которые раньше были как будто выключены.\n\n"
            "Можно начать с одного направления или оставить активными оба."
        ),
        "mode_principles_only": "Фундамент Ямы/Ниямы",
        "mode_meridians_only": "Изучение меридианов",
        "mode_both": "Оба направления",
        "mode_saved": "✅ <b>Ваш путь обновлён.</b>",
        "meridian_time_step": "☯️ <b>Время напоминания по меридианам</b>\n\nВведите время в формате ЧЧ:ММ, например 20:00.",
        "meridian_time_saved": "✅ Время напоминаний по меридианам сохранено.",
        "meridian_mode_menu": (
            "☯️ <b>Как вы хотите изучать меридианы?</b>\n\n"
            "<b>Идти по нашему пути</b> — бот ведёт вас по меридианам в рекомендованном порядке. Вы завершаете один канал и переходите к следующему.\n\n"
            "<b>Изучать самостоятельно</b> — вы сами выбираете любой меридиан и двигаетесь в своём порядке.\n\n"
            "В обоих вариантах сохраняется прогресс и работают ежедневные напоминания."
        ),
        "meridian_guided_path": "🧭 Идти по нашему пути",
        "meridian_free_choice": "👐 Изучать самостоятельно",
        "meridian_change_path": "🧭 Путь изучения",
        "meridian_guided_saved": "✅ <b>Выбран наш путь.</b>\n\nБот будет вести вас по меридианам шаг за шагом.",
        "meridian_free_saved": "✅ <b>Выбрано самостоятельное изучение.</b>\n\nВыберите любой меридиан, который хотите исследовать.",
        "meridian_measurements": "📏 Как мерить в цунях",
        "meridian_back": "🔙 К меридианам",
        "coming_soon": "скоро",
        "meridian_measurements_text": (
            "📏 <b>Система измерений в ТКМ</b>\n\n"
            "Расположение акупунктурных точек часто описывается в <b>цунях</b>. Цунь — это не фиксированное число сантиметров, а относительная мера тела конкретного человека.\n\n"
            "<b>1 цунь:</b> ширина большого пальца в области межфалангового сустава.\n\n"
            "<b>1,5 цуня:</b> ширина двух пальцев вместе — указательного и среднего.\n\n"
            "<b>2 цуня:</b> ширина трёх пальцев вместе — указательного, среднего и безымянного.\n\n"
            "<b>3 цуня:</b> ширина четырёх сомкнутых пальцев — от указательного до мизинца.\n\n"
            "<b>5 цуней:</b> можно отмерить 3 цуня и добавить около 2 цуней, либо разделить нужный анатомический участок на равные части, если источник даёт пропорциональное расстояние.\n\n"
            "Используйте цуни как ориентир, а затем уточняйте точку через тело: локальная чувствительность, небольшое углубление, тепло, давление или ясный отклик на внимание."
        ),
        "meridians_menu": (
            "☯️ <b>Меридианы</b>\n\n"
            "<b>Зачем изучать меридианы?</b>\n\n"
            "Меридианы — это карта, через которую можно учиться чувствовать, как внимание живёт в теле. В традиционной китайской медицине они описываются как каналы, по которым движется Ци.\n\n"
            "Здесь мы изучаем их не как сухую теорию, а через практику: открываем точку, смотрим её расположение на изображении, при необходимости мягко касаемся области и слушаем отклик — тепло, давление, пульсацию, пустоту, сопротивление или ясное ощущение.\n\n"
            "<b>Если точка не ощущается</b>, не нужно давить силой. Считайте её зоной, которой пока нужно больше внимания: расслабьте тело, подышите через точку и оставайтесь с ней, пока ощущение не станет устойчивее.\n\n"
            "<b>Как двигаться:</b> удерживайте уже найденные точки вниманием и добавляйте следующую. Постепенно отдельные точки начинают собираться в живую линию меридиана.\n\n"
            "Эта практика не заменяет медицинскую диагностику и лечение. Это инструмент осознанности, профилактики и внутренней дисциплины.\n\n"
            "Выберите, что сделать сейчас: продолжить практику, выбрать путь изучения или открыть справку по системе измерений в ТКМ для расстояний в цунях."
        ),
        "choose_meridian": "☯️ <b>Выберите меридиан:</b>",
        "current_meridian": "Продолжить практику",
        "meridian_start_points": "Начать с первой точки",
        "all_points": "Все точки",
        "next_point": "Следующая точка",
        "prev_point": "Предыдущая точка",
        "complete_meridian": "Завершить меридиан",
        "select_meridian": "Выбрать меридиан",
        "no_points": "Сейчас не удалось открыть точки этого меридиана. Вернитесь к списку меридианов или попробуйте позже.",
        "meridian_completed": "✅ <b>Меридиан завершён</b>\n\nВыберите следующий канал, когда будете готовы.",
        "about_text": (
            "🕊️ <b>Journey of Ascension</b>\n\n"
            "Этот бот задуман как спокойная опора для реальной практики, а не как набор вдохновляющих фраз.\n\n"
            "Каждый день он возвращает к одному конкретному фокусу: принципу Ямы/Ниямы или точке меридиана. Задача простая: замечать, где энергия уходит бессознательно, переставать её растрачивать и учиться направлять внимание бережнее.\n\n"
            "<b>Яма/Нияма</b> работает с поведением, речью, мыслями, дисциплиной и честностью перед собой.\n\n"
            "<b>Меридианы</b> работают через тело: каналы, точки, течение Ци, закрытые зоны, дыхание, касание и внимание.\n\n"
            "Маленькие повторения важны. Они превращают идею в то, чем действительно можно жить."
        ),
        "feature_announcement": (
            "☯️ <b>Новое в Journey of Ascension: практика меридианов</b>\n\n"
            "Теперь внутри бота можно изучать китайские меридианы: выбирать канал, открывать каждую точку с изображением и двигаться по практике в своём темпе.\n\n"
            "Ежедневное напоминание не торопит вас дальше. Оно просто возвращает к текущему фокусу, чтобы внимание становилось устойчивее.\n\n"
            "Откройте /menu и выберите <b>Меридианы</b>."
        ),
        "already_subscribed": "🕊️ Вы уже подписаны на Journey of Ascension.\n\nИспользуйте /menu для выбора практик или /settings для настройки напоминаний.",
        "unsubscribed": "Бот остановлен. Напоминания больше не будут приходить.\n\nЕсли захотите вернуться, используйте /start.",
        "stop_feedback_prompt": "Если хотите, можете одним сообщением написать, почему решили остановить бота. Это необязательно.",
        "stop_feedback_thanks": "Спасибо, я передам обратную связь.\n\nЕсли захотите вернуться, используйте /start.",
        "not_subscribed_test": "Вы пока не подписаны. Используйте /start, чтобы начать.",
        "setup_complete": (
            "🎉 **Настройка завершена!**\n\n"
            "📋 **Ваши настройки:**\n"
            "🕐 Время: {time}\n"
            "🌍 Часовой пояс: {timezone}\n"
            "📅 Пропускать: {skip_days}\n\n"
            "В любой момент можно открыть /menu, изменить режим практики или перейти к изучению меридианов."
        )
    },
    "uz": {
        "welcome": (
            "🕊️ **Journey of Ascension botiga xush kelibsiz!**\n\n"
            "Yama va Niyama ichki amaliyotning axloqiy poydevori bo'lib qoladi. "
            "Meridianlar keyingi bosqich: diqqat, tana va energiyani bevosita kuzatish orqali sezishni o'rganish.\n\n"
            "Avval tilni tanlaymiz:"
        ),
        "onboarding_intro": (
            "<b>Journey of Ascension</b>\n\n"
            "Ichki amaliyot oddiy kuzatuvdan boshlanadi: bizda diqqat, kuch va energiya bor. Har kuni biz ularni yo yig'amiz, yo tarqatib yuboramiz.\n\n"
            "<b>Yama va Niyama</b> energiyani mojaro, o'ziga zarar, nohalollik, ortiqchalik va ko'pincha sezilmaydigan odatlar orqali yo'qotishni kamaytiradi. Kundalik tamoyil bir kunlik qoida emas, balki hayotga asta-sekin kirib boradigan fokusdir.\n\n"
            "<b>Meridianlar</b> tana va Qi oqimining amaliy xaritasi. Siz nuqtalarni sezishni, yopiq joylarni payqashni va u yerga diqqat, nafas hamda aylanishni muloyim qaytarishni o'rganasiz.\n\n"
            "Nimani o'rganmoqchisiz?"
        ),
        "initial_mode_question": "Nimani o'rganmoqchisiz?",
        "timezone_step_principles": (
            "📍 <b>1/3-qadam: Vaqt mintaqasi</b>\n\n"
            "Bot <b>Yama/Niyama</b> eslatmalarini sizning mahalliy vaqtingiz bo'yicha yuborishi uchun vaqt mintaqangizni tanlang."
        ),
        "timezone_step_meridians": (
            "📍 <b>1/3-qadam: Vaqt mintaqasi</b>\n\n"
            "Bot <b>meridianlar</b> bo'yicha material va eslatmalarni sizning mahalliy vaqtingiz bo'yicha yuborishi uchun vaqt mintaqangizni tanlang."
        ),
        "timezone_step_both": (
            "📍 <b>1/3-qadam: Vaqt mintaqasi</b>\n\n"
            "Bot <b>Yama/Niyama</b> va <b>meridianlar</b> bo'yicha eslatmalarni sizning mahalliy vaqtingiz bo'yicha yuborishi uchun vaqt mintaqangizni tanlang."
        ),
        "time_step_principles": (
            "⏰ <b>2/3-qadam: Yuborish vaqti</b>\n\n"
            "Bot kundalik <b>Yama/Niyama</b> tamoyilini qachon yuborishini tanlang.\n\n"
            "Format: HH:MM, masalan 08:00 yoki 20:30."
        ),
        "time_step_meridians": (
            "⏰ <b>2/3-qadam: Yuborish vaqti</b>\n\n"
            "Bot kundalik <b>meridian</b> fokusini qachon yuborishini tanlang.\n\n"
            "Format: HH:MM, masalan 08:00 yoki 20:30."
        ),
        "time_step_both": (
            "⏰ <b>2/3-qadam: Yuborish vaqti</b>\n\n"
            "Bot kundalik <b>Yama/Niyama</b> tamoyili va <b>meridian</b> fokusini qachon yuborishini tanlang.\n\n"
            "Format: HH:MM, masalan 08:00 yoki 20:30."
        ),
        "continue_setup": "Davom etish",
        "menu": "📋 **Journey of Ascension**",
        "menu_principles": "🧘🏻✨ Yama/Niyama",
        "menu_meridians": "☯️ Meridianlar",
        "menu_modes": "🧭 Mening yo'lim",
        "menu_stop": "⏹ Botni to'xtatish",
        "principles_menu": (
            "🕊️ <b>Yama/Niyama</b>\n\n"
            "Yama va Niyama yogadagi asosiy axloqiy qoidalar va bosqichlardir. Ular o'zini tarbiyalash, ruhiy rivojlanish va dunyo bilan uyg'un munosabatlar uchun poydevor yaratadi.\n\n"
            "Ular klassik sakkiz bosqichli yoganing birinchi ikki pog'onasidir.\n\n"
            "<b>Yama</b> tashqi dunyo bilan munosabat tamoyillari: zarar yetkazmaslik, rostgo'ylik, o'g'irlamaslik, mo'tadillik va ortiqcha egalik qilmaslik.\n\n"
            "<b>Niyama</b> o'z ustida ishlash tamoyillari: poklik, qanoat, intizom, o'zini o'rganish va amaliyot mevasini oliy maqsadga bag'ishlash.\n\n"
            "Tafakkur uchun tasodifiy tamoyilni ochish yoki to'liq ro'yxatni ko'rish mumkin."
        ),
        "principles_random": "Tasodifiy tamoyil",
        "principles_all": "Barcha tamoyillar",
        "principles_empty": "Tamoyillar hozircha mavjud emas.",
        "change_modes": "🧭 Mening yo'lim",
        "change_meridian_time": "☯️ Meridian vaqti",
        "mode_menu": (
            "🧭 <b>Mening yo'lim</b>\n\n"
            "Bot har kuni nimaga qaytishingizga yordam berishini tanlang.\n\n"
            "<b>Yama/Niyama</b> poydevor: ichki shovqin kamroq, energiya yo'qotish kamroq, harakatlarda ko'proq halollik.\n\n"
            "<b>Meridianlar</b> tana qatlami: nuqtalar, kanallar, Qi oqimi va avval sezilmagan joylarni his qilish ko'nikmasi.\n\n"
            "Bitta yo'nalishdan boshlashingiz yoki ikkalasini ham faol qoldirishingiz mumkin."
        ),
        "mode_principles_only": "Yama/Niyama poydevori",
        "mode_meridians_only": "Meridianlarni o'rganish",
        "mode_both": "Ikkala yo'nalish",
        "mode_saved": "✅ <b>Yo'lingiz yangilandi.</b>",
        "meridian_time_step": "☯️ <b>Meridian eslatma vaqti</b>\n\nVaqtni HH:MM formatida kiriting, masalan 20:00.",
        "meridian_time_saved": "✅ Meridian eslatma vaqti saqlandi.",
        "meridian_mode_menu": (
            "☯️ <b>Meridianlarni qanday o'rganmoqchisiz?</b>\n\n"
            "<b>Yo'l bo'yicha</b> — bot meridianlar bo'ylab tavsiya etilgan tartibda olib boradi. Bir kanalni yakunlab, keyingisiga o'tasiz.\n\n"
            "<b>Mustaqil o'rganish</b> — istalgan meridianni o'zingiz tanlab, o'z tartibingizda o'rganasiz.\n\n"
            "Ikkala variantda ham progress va kundalik eslatmalar saqlanadi."
        ),
        "meridian_guided_path": "🧭 Yo'l bo'yicha",
        "meridian_free_choice": "👐 Mustaqil o'rganish",
        "meridian_change_path": "🧭 O'rganish yo'li",
        "meridian_guided_saved": "✅ <b>Yo'l bo'yicha o'rganish tanlandi.</b>\n\nBot sizni meridianlar bo'ylab bosqichma-bosqich olib boradi.",
        "meridian_free_saved": "✅ <b>Mustaqil o'rganish tanlandi.</b>\n\nO'rganmoqchi bo'lgan meridianni tanlang.",
        "meridian_measurements": "📏 Cunni qanday o'lchash",
        "meridian_back": "🔙 Meridianlarga qaytish",
        "coming_soon": "tez orada",
        "meridian_measurements_text": (
            "📏 <b>TKMdagi o'lchov tizimi</b>\n\n"
            "Akupunktura nuqtalari ko'pincha <b>cun</b> orqali tasvirlanadi. Cun aniq santimetr emas: u o'rganilayotgan odam tanasiga nisbatan olinadigan o'lchovdir.\n\n"
            "<b>1 cun:</b> bosh barmoqning bo'g'im sohasidagi kengligi.\n\n"
            "<b>1,5 cun:</b> ikki barmoq kengligi: ko'rsatkich va o'rta barmoq.\n\n"
            "<b>2 cun:</b> uch barmoq kengligi: ko'rsatkich, o'rta va nomsiz barmoq.\n\n"
            "<b>3 cun:</b> to'rt barmoq kengligi: ko'rsatkichdan kichik barmoqqacha.\n\n"
            "<b>5 cun:</b> 3 cun o'lchab, taxminan 2 cun qo'shing yoki manbada proporsional masofa berilgan bo'lsa, anatomik qismni teng bo'laklarga ajrating.\n\n"
            "Cunni yo'nalish sifatida ishlating, keyin nuqtani tana orqali aniqlang: mahalliy sezgirlik, kichik chuqurcha, iliqlik, bosim yoki diqqatga aniq javob."
        ),
        "meridians_menu": (
            "☯️ <b>Meridianlar</b>\n\n"
            "<b>Meridianlarni nima uchun o'rganamiz?</b>\n\n"
            "Meridianlar diqqat tanada qanday yashashini sezishga yordam beradigan xaritadir. An'anaviy xitoy tibbiyotida ular Qi harakatlanadigan kanallar sifatida tasvirlanadi.\n\n"
            "Bu yerda biz ularni quruq nazariya sifatida emas, amaliyot orqali o'rganamiz: nuqtani ochasiz, rasmda joylashuvini ko'rasiz, kerak bo'lsa joyini yengil ushlaysiz va javobni tinglaysiz — iliqlik, bosim, pulsatsiya, bo'shliq, qarshilik yoki aniq sezgi.\n\n"
            "<b>Agar nuqta sezilmasa</b>, kuch bilan bosmang. Uni ko'proq e'tibor kerak bo'lgan zona deb qabul qiling: tanani yumshating, nuqta orqali nafas olayotgandek tasavvur qiling va sezgi barqarorroq bo'lguncha qoling.\n\n"
            "<b>Qanday harakatlanish kerak:</b> oldin topilgan nuqtalarni diqqatda ushlab, keyingisini qo'shing. Asta-sekin alohida nuqtalar meridianning tirik chizig'iga yig'iladi.\n\n"
            "Bu amaliyot tibbiy tashxis va davolanishni almashtirmaydi. U ongli kuzatuv, profilaktika va ichki intizom vositasidir.\n\n"
            "Hozir nima qilishni tanlang: amaliyotni davom ettirish, o'rganish yo'lini tanlash yoki cun masofalari uchun TKM o'lchovlari qo'llanmasini ochish."
        ),
        "choose_meridian": "☯️ <b>Meridianni tanlang:</b>",
        "current_meridian": "Amaliyotni davom ettirish",
        "meridian_start_points": "1-nuqtadan boshlash",
        "all_points": "Barcha nuqtalar",
        "next_point": "Keyingi nuqta",
        "prev_point": "Oldingi nuqta",
        "complete_meridian": "Meridianni yakunlash",
        "select_meridian": "Meridian tanlash",
        "no_points": "Hozir bu meridian nuqtalarini ochib bo'lmadi. Meridianlar ro'yxatiga qayting yoki keyinroq urinib ko'ring.",
        "meridian_completed": "✅ <b>Meridian yakunlandi</b>\n\nTayyor bo'lganingizda keyingi kanalni tanlang.",
        "about_text": (
            "🕊️ <b>Journey of Ascension</b>\n\n"
            "Bu bot ilhomli iboralar to'plami emas, balki haqiqiy amaliyot uchun sokin tayanch bo'lishi uchun yaratilgan.\n\n"
            "Har kuni u sizni bitta aniq fokusga qaytaradi: Yama/Niyama tamoyiliga yoki meridian nuqtasiga. Maqsad oddiy: energiya qayerda ongsiz sarflanayotganini ko'rish, uni behuda ketkazmaslik va diqqatni ehtiyotkorroq yo'naltirishni o'rganish.\n\n"
            "<b>Yama/Niyama</b> xulq, nutq, fikr, intizom va o'zingizga nisbatan halollik bilan ishlaydi.\n\n"
            "<b>Meridianlar</b> tana orqali ishlaydi: kanallar, nuqtalar, Qi oqimi, yopiq joylar, nafas, teginish va diqqat.\n\n"
            "Kichik takrorlar muhim. Ular g'oyani yashash mumkin bo'lgan odatga aylantiradi."
        ),
        "feature_announcement": (
            "☯️ <b>Journey of Ascension'da yangilik: meridian amaliyoti</b>\n\n"
            "Endi bot ichida Xitoy meridianlarini o'rganish mumkin: kanalni tanlang, har bir nuqtani rasmi bilan oching va amaliyotda o'z ritmingizda yuring.\n\n"
            "Kundalik eslatma sizni shoshiltirmaydi. U faqat joriy fokusga qaytaradi, shunda diqqat asta-sekin barqarorroq bo'ladi.\n\n"
            "/menu ni oching va <b>Meridianlar</b> bo'limini tanlang."
        ),
        "already_subscribed": "🕊️ Siz Journey of Ascension'ga allaqachon obuna bo'lgansiz.\n\nAmaliyotlarni tanlash uchun /menu yoki eslatmalarni sozlash uchun /settings dan foydalaning.",
        "unsubscribed": "Bot to'xtatildi. Eslatmalar endi yuborilmaydi.\n\nQaytmoqchi bo'lsangiz, /start dan foydalaning.",
        "stop_feedback_prompt": "Xohlasangiz, botdan foydalanishni nima uchun to'xtatganingizni bitta xabarda yozishingiz mumkin. Bu majburiy emas.",
        "stop_feedback_thanks": "Rahmat, fikringizni yetkazaman.\n\nQaytmoqchi bo'lsangiz, /start dan foydalaning.",
        "not_subscribed_test": "Siz hali obuna bo'lmagansiz. Boshlash uchun /start dan foydalaning.",
        "skip_days_improved": (
            "📅 <b>O'tkazib yuboriladigan kunlar (ixtiyoriy)</b>\n\n"
            "Xohlasangiz, bot xabar yubormaydigan hafta kunlarini tanlashingiz mumkin.\n\n"
            "Masalan: <code>5,6</code> — dam olish kunlarini o'tkazib yuborish.\n"
            "Agar har kuni xabar olishni istasangiz, hech narsa tanlamang."
        ),
        "no_skip_days": "✅ Kunlar tanlanmadi — xabarlar har kuni yuboriladi",
        "feedback_prompt": (
            "💌 <b>Fikr va takliflar</b>\n\n"
            "Botni yanada qulay, tirik va foydali qilish uchun fikringiz muhim.\n\n"
            "Nima yoqdi? Nima noqulay? Qaysi amaliyot yoki kontent yetishmayapti?\n\n"
            "Bitta xabar bilan yozishingiz mumkin."
        ),
        "feedback_sent": "✅ Rahmat. Fikringiz ishlab chiquvchilarga yuborildi.",
        "setup_complete": (
            "🎉 **Sozlash yakunlandi!**\n\n"
            "📋 **Sozlamalaringiz:**\n"
            "🕐 Vaqt: {time}\n"
            "🌍 Vaqt mintaqasi: {timezone}\n"
            "📅 O'tkazib yuborish kunlari: {skip_days}\n\n"
            "Istalgan vaqtda /menu orqali amaliyot rejimini o'zgartirish yoki meridianlarni o'rganishga o'tish mumkin."
        )
    },
    "kz": {
        "welcome": (
            "🕊️ **Journey of Ascension ботына қош келдіңіз!**\n\n"
            "Яма мен Нияма ішкі тәжірибенің адамгершілік негізі болып қалады. "
            "Меридиандар — келесі саты: зейін, дене және энергияны тікелей бақылау арқылы сезуді үйрену.\n\n"
            "Алдымен тілді таңдайық:"
        ),
        "onboarding_intro": (
            "<b>Journey of Ascension</b>\n\n"
            "Ішкі тәжірибе қарапайым байқаудан басталады: бізде зейін, күш және энергия бар. Күн сайын біз оларды не жинаймыз, не шашыратып аламыз.\n\n"
            "<b>Яма мен Нияма</b> энергияны қақтығыс, өзіне зиян, адалсыздық, артықтық және байқалмайтын әдеттер арқылы жоғалтуды азайтуға көмектеседі. Күнделікті қағида — бір күндік ереже емес, өмірге біртіндеп енетін фокус.\n\n"
            "<b>Меридиандар</b> — дене мен Ци ағымының тәжірибелік картасы. Сіз нүктелерді сезуді, жабық аймақтарды байқауды және сол жерге зейін, тыныс пен айналымды жұмсақ қайтаруды үйренесіз.\n\n"
            "Нені зерттегіңіз келеді?"
        ),
        "initial_mode_question": "Нені зерттегіңіз келеді?",
        "timezone_step_principles": (
            "📍 <b>1/3-қадам: Уақыт белдеуі</b>\n\n"
            "Бот <b>Яма/Нияма</b> еске салуларын сіздің жергілікті уақытыңызбен жіберуі үшін уақыт белдеуіңізді таңдаңыз."
        ),
        "timezone_step_meridians": (
            "📍 <b>1/3-қадам: Уақыт белдеуі</b>\n\n"
            "Бот <b>меридиандар</b> туралы материалдар мен еске салуларды сіздің жергілікті уақытыңызбен жіберуі үшін уақыт белдеуіңізді таңдаңыз."
        ),
        "timezone_step_both": (
            "📍 <b>1/3-қадам: Уақыт белдеуі</b>\n\n"
            "Бот <b>Яма/Нияма</b> және <b>меридиандар</b> бойынша еске салуларды сіздің жергілікті уақытыңызбен жіберуі үшін уақыт белдеуіңізді таңдаңыз."
        ),
        "time_step_principles": (
            "⏰ <b>2/3-қадам: Жіберу уақыты</b>\n\n"
            "Бот күнделікті <b>Яма/Нияма</b> қағидасын қашан жіберетінін таңдаңыз.\n\n"
            "Формат: HH:MM, мысалы 08:00 немесе 20:30."
        ),
        "time_step_meridians": (
            "⏰ <b>2/3-қадам: Жіберу уақыты</b>\n\n"
            "Бот күнделікті <b>меридиан</b> фокусын қашан жіберетінін таңдаңыз.\n\n"
            "Формат: HH:MM, мысалы 08:00 немесе 20:30."
        ),
        "time_step_both": (
            "⏰ <b>2/3-қадам: Жіберу уақыты</b>\n\n"
            "Бот күнделікті <b>Яма/Нияма</b> қағидасын және <b>меридиан</b> фокусын қашан жіберетінін таңдаңыз.\n\n"
            "Формат: HH:MM, мысалы 08:00 немесе 20:30."
        ),
        "continue_setup": "Жалғастыру",
        "menu": "📋 **Journey of Ascension**",
        "menu_principles": "🧘🏻✨ Яма/Нияма",
        "menu_meridians": "☯️ Меридиандар",
        "menu_modes": "🧭 Менің жолым",
        "menu_stop": "⏹ Ботты тоқтату",
        "principles_menu": (
            "🕊️ <b>Яма/Нияма</b>\n\n"
            "Яма мен Нияма — йогадағы негізгі моральдық-этикалық қағидалар мен сатылар. Олар өзін-өзі тәрбиелеуге, рухани дамуға және әлеммен үйлесімді қарым-қатынасқа негіз болады.\n\n"
            "Олар классикалық сегіз сатылы йоганың алғашқы екі сатысын құрайды.\n\n"
            "<b>Яма</b> сыртқы әлеммен қарым-қатынас қағидалары: зиян келтірмеу, шыншылдық, ұрламау, ұстамдылық және дүниеқоңыздықтан арылу.\n\n"
            "<b>Нияма</b> өзімен жұмыс істеу қағидалары: тазалық, қанағат, тәртіп, өзін-өзі зерттеу және тәжірибе жемісін жоғары мақсатқа арнау.\n\n"
            "Ойлану үшін кездейсоқ қағиданы ашуға немесе толық тізімді көруге болады."
        ),
        "principles_random": "Кездейсоқ қағида",
        "principles_all": "Барлық қағидалар",
        "principles_empty": "Қағидалар әзірге қолжетімді емес.",
        "change_modes": "🧭 Менің жолым",
        "change_meridian_time": "☯️ Меридиан уақыты",
        "mode_menu": (
            "🧭 <b>Менің жолым</b>\n\n"
            "Бот күн сайын неге қайта оралуға көмектесетінін таңдаңыз.\n\n"
            "<b>Яма/Нияма</b> — негіз: ішкі шу азаяды, энергия шығыны азаяды, әрекетте адалдық көбейеді.\n\n"
            "<b>Меридиандар</b> — дене қабаты: нүктелер, арналар, Ци ағымы және бұрын сезілмеген аймақтарды сезу дағдысы.\n\n"
            "Бір бағыттан бастауға немесе екеуін де белсенді қалдыруға болады."
        ),
        "mode_principles_only": "Яма/Нияма негізі",
        "mode_meridians_only": "Меридиандарды зерттеу",
        "mode_both": "Екі бағыт та",
        "mode_saved": "✅ <b>Жолыңыз жаңартылды.</b>",
        "meridian_time_step": "☯️ <b>Меридиан еске салу уақыты</b>\n\nУақытты HH:MM форматында енгізіңіз, мысалы 20:00.",
        "meridian_time_saved": "✅ Меридиан еске салу уақыты сақталды.",
        "meridian_mode_menu": (
            "☯️ <b>Меридиандарды қалай зерттегіңіз келеді?</b>\n\n"
            "<b>Біздің жолмен</b> — бот меридиандарды ұсынылған ретпен жүргізеді. Бір арнаны аяқтап, келесісіне өтесіз.\n\n"
            "<b>Өз бетіңізше</b> — кез келген меридианды өзіңіз таңдап, өз ретіңізбен зерттейсіз.\n\n"
            "Екі нұсқада да прогресс сақталады және күнделікті еске салулар жұмыс істейді."
        ),
        "meridian_guided_path": "🧭 Біздің жолмен",
        "meridian_free_choice": "👐 Өз бетімше",
        "meridian_change_path": "🧭 Зерттеу жолы",
        "meridian_guided_saved": "✅ <b>Біздің жол таңдалды.</b>\n\nБот сізді меридиандар арқылы кезең-кезеңімен жүргізеді.",
        "meridian_free_saved": "✅ <b>Өз бетіңізше зерттеу таңдалды.</b>\n\nЗерттегіңіз келетін меридианды таңдаңыз.",
        "meridian_measurements": "📏 Цуньді қалай өлшеу",
        "meridian_back": "🔙 Меридиандарға қайту",
        "coming_soon": "жақында",
        "meridian_measurements_text": (
            "📏 <b>ҚКМ-дегі өлшем жүйесі</b>\n\n"
            "Акупунктура нүктелерінің орналасуы жиі <b>цунь</b> арқылы сипатталады. Цунь — нақты сантиметр емес, зерттеліп отырған адамның денесіне қатысты өлшем.\n\n"
            "<b>1 цунь:</b> бас бармақтың буын тұсындағы ені.\n\n"
            "<b>1,5 цунь:</b> екі саусақтың ені: сұқ және ортаңғы саусақ.\n\n"
            "<b>2 цунь:</b> үш саусақтың ені: сұқ, ортаңғы және аты жоқ саусақ.\n\n"
            "<b>3 цунь:</b> төрт саусақтың ені: сұқ саусақтан шынашаққа дейін.\n\n"
            "<b>5 цунь:</b> 3 цунь өлшеп, шамамен 2 цунь қосыңыз немесе дереккөз пропорциялық қашықтық берсе, анатомиялық бөлікті тең бөліктерге бөліңіз.\n\n"
            "Цуньді бағдар ретінде қолданыңыз, кейін нүктені дене арқылы нақтылаңыз: жергілікті сезімталдық, шағын ойыс, жылу, қысым немесе зейінге айқын жауап."
        ),
        "meridians_menu": (
            "☯️ <b>Меридиандар</b>\n\n"
            "<b>Меридиандарды не үшін зерттейміз?</b>\n\n"
            "Меридиандар зейіннің денеде қалай өмір сүретінін сезуге көмектесетін карта. Дәстүрлі қытай медицинасында олар Ци қозғалатын арналар ретінде сипатталады.\n\n"
            "Мұнда біз оларды құрғақ теория ретінде емес, тәжірибе арқылы зерттейміз: нүктені ашасыз, суреттен орналасуын көресіз, қажет болса аймақты жеңіл ұстайсыз және жауапты тыңдайсыз — жылу, қысым, пульсация, бос кеңістік, қарсылық немесе анық сезім.\n\n"
            "<b>Егер нүкте сезілмесе</b>, күшпен басудың қажеті жоқ. Оны көбірек зейін керек аймақ деп қабылдаңыз: денені жұмсартыңыз, сол нүкте арқылы тыныстап тұрғандай елестетіңіз және сезім тұрақталғанша бірге болыңыз.\n\n"
            "<b>Қалай жылжу керек:</b> бұрын табылған нүктелерді зейінде ұстап, келесі нүктені қосыңыз. Біртіндеп бөлек нүктелер меридианның тірі сызығына жиналады.\n\n"
            "Бұл тәжірибе медициналық диагностика мен емді алмастырмайды. Ол саналылық, алдын алу және ішкі тәртіп құралы ретінде қолданылады.\n\n"
            "Қазір не істегіңіз келетінін таңдаңыз: тәжірибені жалғастыру, зерттеу жолын таңдау немесе цунь қашықтықтары үшін ТҚМ өлшемдері нұсқаулығын ашу."
        ),
        "choose_meridian": "☯️ <b>Меридианды таңдаңыз:</b>",
        "current_meridian": "Тәжірибені жалғастыру",
        "meridian_start_points": "1-нүктеден бастау",
        "all_points": "Барлық нүктелер",
        "next_point": "Келесі нүкте",
        "prev_point": "Алдыңғы нүкте",
        "complete_meridian": "Меридианды аяқтау",
        "select_meridian": "Меридиан таңдау",
        "no_points": "Қазір бұл меридианның нүктелерін ашу мүмкін болмады. Меридиандар тізіміне оралыңыз немесе кейінірек қайталап көріңіз.",
        "meridian_completed": "✅ <b>Меридиан аяқталды</b>\n\nДайын болғанда келесі арнаны таңдаңыз.",
        "about_text": (
            "🕊️ <b>Journey of Ascension</b>\n\n"
            "Бұл бот шабыт беретін сөздер жинағы емес, нақты тәжірибе үшін тыныш тірек болу үшін жасалған.\n\n"
            "Күн сайын ол сізді бір нақты фокусқа қайтарады: Яма/Нияма қағидасына немесе меридиан нүктесіне. Мақсат қарапайым: энергияның қайда бейсаналы жұмсалып жатқанын көру, оны босқа шашпау және зейінді ұқыптырақ бағыттауды үйрену.\n\n"
            "<b>Яма/Нияма</b> мінез-құлықпен, сөзбен, оймен, тәртіппен және өзіңізге адал болумен жұмыс істейді.\n\n"
            "<b>Меридиандар</b> дене арқылы жұмыс істейді: арналар, нүктелер, Ци ағымы, жабық аймақтар, тыныс, жанасу және зейін.\n\n"
            "Кішкентай қайталаулар маңызды. Олар идеяны өмірде қолдануға болатын дағдыға айналдырады."
        ),
        "feature_announcement": (
            "☯️ <b>Journey of Ascension ішіндегі жаңалық: меридиан тәжірибесі</b>\n\n"
            "Енді бот ішінде қытай меридиандарын зерттеуге болады: арнаны таңдаңыз, әр нүктені суретімен ашыңыз және тәжірибеде өз ырғағыңызбен жүріңіз.\n\n"
            "Күнделікті еске салу сізді асықтырмайды. Ол тек ағымдағы фокусқа қайтарады, сонда зейін біртіндеп тұрақтанады.\n\n"
            "/menu ашып, <b>Меридиандар</b> бөлімін таңдаңыз."
        ),
        "already_subscribed": "🕊️ Сіз Journey of Ascension-ға бұрыннан жазылғансыз.\n\nТәжірибелерді таңдау үшін /menu немесе еске салуларды өзгерту үшін /settings қолданыңыз.",
        "unsubscribed": "Бот тоқтатылды. Еске салулар енді жіберілмейді.\n\nҚайта оралғыңыз келсе, /start қолданыңыз.",
        "stop_feedback_prompt": "Қаласаңыз, ботты не үшін тоқтатқаныңызды бір хабарламамен жаза аласыз. Бұл міндетті емес.",
        "stop_feedback_thanks": "Рақмет, пікіріңізді жеткіземін.\n\nҚайта оралғыңыз келсе, /start қолданыңыз.",
        "not_subscribed_test": "Сіз әлі жазылмағансыз. Бастау үшін /start қолданыңыз.",
        "skip_days_improved": (
            "📅 <b>Өткізіп жіберілетін күндер (міндетті емес)</b>\n\n"
            "Қаласаңыз, бот хабар жібермейтін апта күндерін таңдай аласыз.\n\n"
            "Мысалы: <code>5,6</code> — демалыс күндерін өткізіп жіберу.\n"
            "Күн сайын хабар алғыңыз келсе, ештеңе таңдамаңыз."
        ),
        "no_skip_days": "✅ Күндер таңдалмады — хабарлар күн сайын жіберіледі",
        "feedback_prompt": (
            "💌 <b>Пікірлер мен ұсыныстар</b>\n\n"
            "Ботты ыңғайлы, тірі және пайдалы ету үшін сіздің пікіріңіз маңызды.\n\n"
            "Не ұнады? Не ыңғайсыз? Қандай тәжірибе немесе контент жетіспейді?\n\n"
            "Бір хабарлама ретінде жаза аласыз."
        ),
        "feedback_sent": "✅ Рақмет. Пікіріңіз әзірлеушілерге жіберілді.",
        "setup_complete": (
            "🎉 **Баптау аяқталды!**\n\n"
            "📋 **Сіздің баптауларыңыз:**\n"
            "🕐 Уақыт: {time}\n"
            "🌍 Уақыт белдеуі: {timezone}\n"
            "📅 Өткізіп жіберу күндері: {skip_days}\n\n"
            "Кез келген уақытта /menu арқылы тәжірибе режимін өзгертуге немесе меридиандарды зерттеуге өтуге болады."
        )
    }
}

for _language, _updates in TEXTS_UPDATE.items():
    TEXTS.setdefault(_language, {}).update(_updates)


class BotHandlers:
    """Handlers for bot commands."""
    
    def __init__(
        self, 
        application: Application, 
        storage: JsonStorage, 
        scheduler: YogaScheduler,
        principles_manager: PrinciplesManager,
        meridians_manager: MeridiansManager,
        admin_ids: List[int]
    ):
        self.application = application
        self.storage = storage
        self.scheduler = scheduler
        self.principles_manager = principles_manager
        self.meridians_manager = meridians_manager
        self.admin_ids = admin_ids
        self.user_states = {}  # Track user registration states.
        
        # Register handlers.
        self._register_handlers()
    
    def _register_handlers(self) -> None:
        """Register all event handlers."""
        
        # User commands.
        self.application.add_handler(CommandHandler("start", self._handle_start))
        self.application.add_handler(CommandHandler("stop", self._handle_stop))
        self.application.add_handler(CommandHandler("settings", self._handle_settings))
        self.application.add_handler(CommandHandler("test", self._handle_test))
        self.application.add_handler(CommandHandler("menu", self._handle_menu))
        
        # Admin commands.
        self.application.add_handler(CommandHandler("next", self._handle_next))
        self.application.add_handler(CommandHandler("add", self._handle_add_principle))
        self.application.add_handler(CommandHandler("stats", self._handle_stats))
        self.application.add_handler(CommandHandler("broadcast", self._handle_broadcast))
        self.application.add_handler(CommandHandler("feedback_stats", self._handle_feedback_stats))
        self.application.add_handler(CommandHandler("feedback_list", self._handle_feedback_list))
        self.application.add_handler(CommandHandler("admin", self._handle_admin))
        
        # Callback query handlers.
        self.application.add_handler(CallbackQueryHandler(self._handle_language_callback, pattern="^lang_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_intro_callback, pattern="^intro_mode_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_timezone_callback, pattern="^tz_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_skipday_callback, pattern="^skipday_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_menu_callback, pattern="^menu_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_principles_callback, pattern="^principles_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_settings_callback, pattern="^settings_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_change_callback, pattern="^change_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_mode_callback, pattern="^mode_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_meridian_callback, pattern="^meridian_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_broadcast_callback, pattern="^broadcast_"))
        
        # General message handler for registration flow.
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
    
    def _get_text(self, key: str, language: str = "en", **kwargs) -> str:
        """Get localized text."""
        return TEXTS.get(language, TEXTS["en"]).get(key, key).format(**kwargs)

    def _as_html(self, text: str) -> str:
        """Normalize legacy Markdown-bold text for HTML parse mode."""
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    def _get_admin_text(self, key: str, **kwargs) -> str:
        """Get admin text."""
        return ADMIN_TEXTS.get(key, key).format(**kwargs)

    def _get_timezone_step_text(self, language: str, user_state: Optional[Dict[str, Any]] = None) -> str:
        """Get contextual timezone prompt based on selected practice modes."""
        user_state = user_state or {}
        principles_enabled = user_state.get("principles_enabled", True)
        meridians_enabled = user_state.get("meridians_enabled", False)

        if principles_enabled and meridians_enabled:
            key = "timezone_step_both"
        elif meridians_enabled:
            key = "timezone_step_meridians"
        else:
            key = "timezone_step_principles"

        return self._get_text(key, language)

    def _get_time_step_text(self, language: str, user_state: Optional[Dict[str, Any]] = None) -> str:
        """Get contextual send-time prompt based on selected practice modes."""
        user_state = user_state or {}
        principles_enabled = user_state.get("principles_enabled", True)
        meridians_enabled = user_state.get("meridians_enabled", False)

        if principles_enabled and meridians_enabled:
            key = "time_step_both"
        elif meridians_enabled:
            key = "time_step_meridians"
        else:
            key = "time_step_principles"

        return self._get_text(key, language)

    def _format_principles_list(self, language: str) -> str:
        """Format all Yama/Niyama principles as a compact catalogue heading."""
        principles = self.principles_manager.get_all_principles(language)
        if not principles:
            return self._get_text("principles_empty", language)

        title = self._get_text("principles_all", language)
        intro = {
            "en": "Choose a principle to open the detailed description and image.",
            "ru": "Выберите принцип, чтобы открыть подробное описание и изображение.",
            "uz": "Batafsil tavsif va rasmni ochish uchun tamoyilni tanlang.",
            "kz": "Толық сипаттама мен суретті ашу үшін қағиданы таңдаңыз.",
        }.get(language, "Choose a principle to open the detailed description and image.")
        return f"🕊️ <b>{title}</b>\n\n{intro}"

    def _get_principle_group_name(self, principle_id: int, language: str) -> str:
        """Return Yama/Niyama group name for a principle."""
        yama = {
            "en": "Yama",
            "ru": "Яма",
            "uz": "Yama",
            "kz": "Яма",
        }.get(language, "Yama")
        niyama = {
            "en": "Niyama",
            "ru": "Нияма",
            "uz": "Niyama",
            "kz": "Нияма",
        }.get(language, "Niyama")
        return yama if principle_id <= 5 else niyama

    def _format_principle_detail(self, principle: Dict[str, Any], language: str, max_length: Optional[int] = None) -> str:
        """Format a selected principle with its Yama/Niyama group."""
        group = self._get_principle_group_name(int(principle.get("id", 0)), language)
        part_label = {
            "en": "Part",
            "ru": "Часть",
            "uz": "Qismi",
            "kz": "Бөлігі",
        }.get(language, "Part")
        practice_label = {
            "en": "Practice",
            "ru": "Практика",
            "uz": "Amaliyot",
            "kz": "Тәжірибе",
        }.get(language, "Practice")

        emoji = principle.get("emoji", "")
        name = principle.get("name", "")
        short_description = principle.get("short_description", "")
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
            lines = [
                f"<b>{escape(name)}</b> {escape(emoji)}".strip(),
                f"<b>{escape(part_label)}:</b> {escape(group)}",
            ]
            if short_description:
                lines.extend(["", escape(short_description)])
            if desc:
                lines.extend(["", escape(desc)])
            if practice:
                lines.extend(["", f"💡 <b>{escape(practice_label)}:</b> <i>{escape(practice)}</i>"])
            return "\n".join(lines)

        text = build(description, practice_tip)
        if not max_length or len(text) <= max_length:
            return text

        # Telegram photo captions are limited, so keep the practical exercise visible
        # and shorten the explanatory description first.
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

        text = build("", "")
        if len(text) <= max_length:
            return text

        plain = f"{name} {emoji}\n{part_label}: {group}"
        return escape(shorten(plain, max_length))
    
    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        chat_id = update.effective_chat.id
        
        try:
            # Check if user already exists.
            user = await self.storage.get_user(chat_id)
            if user and user.is_active:
                text = self._get_text("already_subscribed", user.language)
                await update.message.reply_text(text, parse_mode='Markdown')
                return
            
            # Start with language selection.
            keyboard = [
                [
                    InlineKeyboardButton(TEXTS["en"]["english"], callback_data="lang_en"),
                    InlineKeyboardButton(TEXTS["en"]["russian"], callback_data="lang_ru")
                ],
                [
                    InlineKeyboardButton(TEXTS["uz"]["uzbek"], callback_data="lang_uz"),
                    InlineKeyboardButton(TEXTS["kz"]["kazakh"], callback_data="lang_kz")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Show multilingual language selection message before we know the user's language.
            welcome_message = (
                "🕊️ <b>Journey of Ascension</b>\n\n"
                "Please choose your language.\n"
                "Пожалуйста, выберите язык.\n\n"
                "Tilni tanlang.\n"
                "Тілді таңдаңыз."
            )
            message = await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='HTML')
            await self.storage.add_bot_message(chat_id, message.message_id, "welcome")
            
        except Exception as e:
            logger.error(f"Error in start handler for user {chat_id}: {e}")
            # Try to get user language for error message
            try:
                user = await self.storage.get_user(chat_id)
                error_lang = user.language if user else "en"
            except:
                error_lang = "en"
            await update.message.reply_text(self._get_text("error", language=error_lang))
    
    async def _handle_language_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle language selection callback."""
        query = update.callback_query
        chat_id = query.message.chat.id
        language = query.data.split("_")[1]  # Extract language from callback data.
        
        try:
            await query.answer()
            logger.debug(f"User {chat_id} selected language: {language}")
            
            # Check if user already exists (changing language) or new registration
            user = await self.storage.get_user(chat_id)
            logger.debug(f"User {chat_id} exists: {user is not None}, active: {user.is_active if user else 'N/A'}")
            
            if user and user.is_active:
                # User exists - changing language
                logger.debug(f"Changing language for existing user {chat_id} from {user.language} to {language}")
                old_language = user.language
                user.language = language
                success = await self.storage.save_user(user)
                logger.debug(f"Language save success for user {chat_id}: {success}")
                
                if success:
                    # Clear any previous dialog before showing new menu
                    await self._clear_user_dialog(chat_id)
                    logger.debug(f"Cleared dialog for user {chat_id} before language change")
                    
                    confirmation = self._get_text("language_chosen", language)
                    text = self._as_html(f"{confirmation}\n\n{self._get_text('menu', language)}")
                    keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
                    logger.debug(f"Sending menu in {language} to user {chat_id}")
                    
                    message = await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')
                    if message:
                        await self.storage.add_bot_message(chat_id, message.message_id, "menu")
                        logger.debug(f"Stored menu message for user {chat_id}")
                else:
                    logger.error(f"Failed to save language change for user {chat_id}")
                    await self._edit_message_text_safe(query, self._get_text("setup_error", language))
            else:
                # New user registration
                logger.debug(f"Starting registration for new user {chat_id} in language {language}")
                self.user_states[chat_id] = {
                    "step": "intro",
                    "language": language,
                    "registration_message_id": query.message.message_id  # Save message ID for editing
                }
                
                # Send language confirmation and onboarding intro before setup.
                confirmation = self._get_text("language_chosen", language)
                intro_msg = self._get_text("onboarding_intro", language)
                combined_msg = f"{confirmation}\n\n{intro_msg}"
                keyboard = self._create_registration_modes_keyboard(language)
                
                logger.debug(f"Sending onboarding intro in {language} to user {chat_id}")
                await self._edit_message_text_safe(query, combined_msg, reply_markup=keyboard, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Error in language callback for user {chat_id}: {e}")
            await self._edit_message_text_safe(query, self._get_text("error", language))

    async def _handle_intro_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Save initial practice mode and continue to timezone selection."""
        query = update.callback_query
        chat_id = query.message.chat.id
        mode = query.data.rsplit("_", 1)[1]

        try:
            await query.answer()
            user_state = self.user_states.get(chat_id)
            if not user_state or user_state.get("step") != "intro":
                logger.debug(f"Invalid state for intro callback {chat_id}: {user_state}")
                return

            language = user_state["language"]
            user_state["principles_enabled"] = mode in ["principles", "both"]
            user_state["meridians_enabled"] = mode in ["meridians", "both"]
            user_state["step"] = "timezone"
            text = self._get_timezone_step_text(language, user_state)
            keyboard = self._create_timezone_keyboard(language)
            await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error in intro callback for user {chat_id}: {e}")
            language = self.user_states.get(chat_id, {}).get("language", "en")
            await self._edit_message_text_safe(query, self._get_text("error", language))
    
    async def _handle_timezone_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle timezone selection callback."""
        query = update.callback_query
        chat_id = query.message.chat.id
        tz_data = query.data.split("_", 1)[1]  # Extract timezone or 'custom'
        
        try:
            await query.answer()
            logger.debug(f"Timezone callback for user {chat_id}: {tz_data}")
            
            user_state = self.user_states.get(chat_id)
            if not user_state or user_state.get("step") not in ["timezone", "change_timezone"]:
                logger.debug(f"Invalid state for user {chat_id}: {user_state}")
                return
            
            language = user_state["language"]
            logger.debug(f"User {chat_id} timezone selection in language: {language}")
            message_id = user_state.get("registration_message_id")
            
            if tz_data == "custom":
                # Switch to manual input mode
                if user_state.get("step") == "change_timezone":
                    self.user_states[chat_id]["step"] = "change_timezone_manual"
                else:
                    self.user_states[chat_id]["step"] = "timezone_manual"
                    
                custom_msg = (
                    f"{self._get_text('timezone_step', language)}\n\n"
                    "Please enter your timezone in IANA format:\n\n"
                    "Examples: Europe/Moscow, Asia/Tashkent, UTC"
                )
                await self._edit_message_text_safe(query, custom_msg, parse_mode='Markdown')
            else:
                # Use selected timezone
                timezone_str = tz_data
                if is_valid_timezone(timezone_str):
                    if user_state.get("step") == "change_timezone":
                        # Handle timezone change
                        user = await self.storage.get_user(chat_id)
                        if user:
                            user.timezone = timezone_str
                            success = await self.storage.save_user(user)
                            
                            if success:
                                # Reschedule user messages with new timezone
                                await self.scheduler.schedule_user_immediately(chat_id)
                                
                                # Clean up state and show menu
                                del self.user_states[chat_id]
                                
                                text = self._as_html(f"{self._get_text('timezone_saved', language)}\n\n{self._get_text('menu', language)}")
                                keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
                                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')
                            else:
                                await self._edit_message_text_safe(query, self._get_text("setup_error", language), parse_mode='Markdown')
                    else:
                        # Handle new registration
                        self.user_states[chat_id]["timezone"] = timezone_str
                        self.user_states[chat_id]["step"] = "time"
                        
                        confirmation = self._get_text("timezone_saved", language)
                        time_msg = self._get_time_step_text(language, self.user_states[chat_id])
                        
                        combined_msg = f"{confirmation}\n\n{time_msg}"
                        
                        await self._edit_message_text_safe(query, combined_msg, parse_mode='HTML')
                else:
                    await self._edit_message_text_safe(query, self._get_text("invalid_timezone", language), parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in timezone callback for user {chat_id}: {e}")
            language = self.user_states.get(chat_id, {}).get("language", "en")
            await self._edit_message_text_safe(query, self._get_text("error", language))
    
    async def _handle_skipday_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle skip days selection callback."""
        query = update.callback_query
        chat_id = query.message.chat.id
        skipday_data = query.data.split("_", 1)[1]  # Extract day number or action
        
        try:
            await query.answer()
            logger.debug(f"Skip day callback for user {chat_id}: {skipday_data}")
            
            user_state = self.user_states.get(chat_id)
            if not user_state or user_state.get("step") not in ["skip_days", "change_skip_days"]:
                logger.debug(f"Invalid state for skipday callback {chat_id}: {user_state}")
                return
            
            language = user_state["language"]
            
            # Initialize selected days if not exists
            if "selected_skip_days" not in user_state:
                user_state["selected_skip_days"] = []
            
            selected_days = user_state["selected_skip_days"]
            
            if skipday_data == "finish":
                # Finish selection and proceed
                await self._complete_skip_days_selection(update, selected_days, language)
                
            elif skipday_data == "none":
                # Clear all selections and finish this step immediately. If no
                # days were selected already, updating the keyboard is a no-op
                # and feels broken to the user.
                user_state["selected_skip_days"] = []
                await self._complete_skip_days_selection(update, [], language)
                
            elif skipday_data == "weekends":
                # Select weekends (Saturday=5, Sunday=6)
                user_state["selected_skip_days"] = [5, 6]
                await self._update_skip_days_keyboard(query, language, [5, 6])
                
            elif skipday_data.isdigit():
                # Toggle specific day
                day = int(skipday_data)
                if day in selected_days:
                    selected_days.remove(day)
                else:
                    selected_days.append(day)
                
                user_state["selected_skip_days"] = selected_days
                await self._update_skip_days_keyboard(query, language, selected_days)
            
        except Exception as e:
            logger.error(f"Error in skipday callback for user {chat_id}: {e}")
            language = self.user_states.get(chat_id, {}).get("language", "en")
            await self._edit_message_text_safe(query, self._get_text("error", language))
    
    async def _update_skip_days_keyboard(self, query, language: str, selected_days: List[int]) -> None:
        """Update skip days keyboard with current selection."""
        text = self._get_text("skip_days_step", language)
        
        # Add current selection info
        if selected_days:
            days_display = self._format_skip_days(selected_days, language)
            if language == "en":
                text += f"\n\n🔸 **Selected days to skip:** {days_display}"
            elif language == "ru":
                text += f"\n\n🔸 **Выбранные дни для пропуска:** {days_display}"
            elif language == "uz":
                text += f"\n\n🔸 **O'tkazib yuborish uchun tanlangan kunlar:** {days_display}"
            elif language == "kz":
                text += f"\n\n🔸 **Өткізіп жіберу үшін таңдалған күндер:** {days_display}"
        else:
            if language == "en":
                text += f"\n\n🔸 **No days selected** - messages will be sent daily"
            elif language == "ru":
                text += f"\n\n🔸 **Дни не выбраны** - сообщения будут отправляться ежедневно"
            elif language == "uz":
                text += f"\n\n🔸 **Kunlar tanlanmagan** - xabarlar har kuni yuboriladi"
            elif language == "kz":
                text += f"\n\n🔸 **Күндер таңдалмаған** - хабарлар күн сайын жіберіледі"
        
        keyboard = self._create_skip_days_keyboard(language, selected_days)
        await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='Markdown')
    
    async def _complete_skip_days_selection(self, update: Update, selected_days: List[int], language: str) -> None:
        """Complete skip days selection and create user or update settings."""
        query = update.callback_query
        chat_id = query.message.chat.id
        user_state = self.user_states[chat_id]
        
        if user_state.get("step") == "change_skip_days":
            # Handle settings change
            try:
                user = await self.storage.get_user(chat_id)
                if user:
                    user.skip_day_id = selected_days
                    success = await self.storage.save_user(user)
                    
                    if success:
                        # Reschedule user messages with new skip days
                        await self.scheduler.schedule_user_immediately(chat_id)
                        
                        # Clean up state and show menu
                        del self.user_states[chat_id]
                        
                        if selected_days:
                            skip_days_display = self._format_skip_days(selected_days, language)
                            confirmation = f"✅ {skip_days_display}"
                        else:
                            if language == "en":
                                confirmation = "✅ Skip days cleared - daily messages enabled"
                            elif language == "ru":
                                confirmation = "✅ Дни пропуска очищены - включены ежедневные сообщения"
                            elif language == "uz":
                                confirmation = "✅ O'tkazib yuborish kunlari tozalandi - kundalik xabarlar yoqildi"
                            elif language == "kz":
                                confirmation = "✅ Өткізіп жіберу күндері тазаланды - күнделікті хабарлар қосылды"
                        
                        text = f"{confirmation}\n\n{self._get_text('menu', language)}"
                        keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
                        
                        await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='Markdown')
                    else:
                        await self._edit_message_text_safe(query, self._get_text("setup_error", language), parse_mode='Markdown')
                        
            except Exception as e:
                logger.error(f"Error updating skip days for user {chat_id}: {e}")
                await self._edit_message_text_safe(query, self._get_text("error", language), parse_mode='Markdown')
                
        else:
            # Handle new registration
            from bot.storage import User
            
            user = User(
                chat_id=chat_id,
                language=language,
                timezone=user_state["timezone"],
                time_for_send=user_state["time"],
                meridian_time_for_send=user_state["time"],
                skip_day_id=selected_days,
                principles_enabled=user_state.get("principles_enabled", True),
                meridians_enabled=user_state.get("meridians_enabled", False),
                is_active=True
            )
            if user.meridians_enabled and not user.current_meridian_id:
                first_meridian = self.meridians_manager.get_first_meridian()
                if first_meridian:
                    user.current_meridian_id = first_meridian["id"]
                    user.current_point_index = -1
            
            success = await self.storage.save_user(user)
            if success:
                # Schedule user messages
                await self.scheduler.schedule_user_immediately(chat_id)
                
                # Clean up state
                del self.user_states[chat_id]
                
                skip_days_display = self._format_skip_days(selected_days, language)
                
                text = self._format_setup_complete(user, language, skip_days_display)
                logger.debug(f"Setup complete text for user {chat_id} in language {language}: {text[:100]}...")
                
                # Add menu after setup completion
                text += f"\n\n{self._get_text('menu', language)}"
                keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
                logger.debug(f"Final setup message for user {chat_id} in language {language}: {text[:150]}...")
                
                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='Markdown')
                # Store the final message ID
                await self.storage.add_bot_message(chat_id, query.message.message_id, "setup_complete")
            else:
                await self._edit_message_text_safe(query, self._get_text("setup_error", language), parse_mode='Markdown')
    
    async def _handle_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stop command."""
        chat_id = update.effective_chat.id
        
        try:
            user = await self.storage.get_user(chat_id)
            language = user.language if user else "ru"  # Default to Russian
            
            # Delete user's /stop command message first
            await self._delete_message_safe(chat_id, update.message.message_id)
            
            # Clear entire dialog - try to delete recent messages aggressively
            await self._clear_entire_dialog(chat_id)
            
            success = await self.storage.deactivate_user(chat_id)
            if success:
                text = f"{self._get_text('unsubscribed', language)}\n\n{self._get_text('stop_feedback_prompt', language)}"
                self.user_states[chat_id] = {"step": "stop_feedback", "language": language}
                # Remove user from scheduler
                await self.scheduler.remove_user_jobs(chat_id)
            else:
                text = self._get_text("not_subscribed", language)
            
            # Send final message directly through bot API
            await self.application.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
                
        except Exception as e:
            logger.error(f"Error in stop handler for user {chat_id}: {e}")
            try:
                user = await self.storage.get_user(chat_id)
                error_lang = user.language if user else "ru"
                await self.application.bot.send_message(chat_id=chat_id, text=self._get_text("error", error_lang))
            except:
                await self.application.bot.send_message(chat_id=chat_id, text="Произошла ошибка.")
    
    async def _handle_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /settings command."""
        chat_id = update.effective_chat.id
        
        try:
            user = await self.storage.get_user(chat_id)
            if not user or not user.is_active:
                await update.message.reply_text(self._get_text("not_subscribed_test", language="en"))
                return
            
            language_display = {"en": "English", "ru": "Русский", "uz": "O'zbek", "kz": "Қазақша"}.get(user.language, "English")
            skip_days_display = self._format_skip_days(user.skip_day_id, user.language)
            
            text = self._get_text(
                "current_settings", 
                language=user.language,
                user_language=language_display,
                time=user.time_for_send,
                timezone=user.timezone,
                skip_days=skip_days_display
            )
            mode_text = {
                "en": f"\n🧭 Practice modes: Yama/Niyama={'on' if user.principles_enabled else 'off'}, Meridians={'on' if user.meridians_enabled else 'off'}\n🌿 Meridian time: {user.meridian_time_for_send}",
                "ru": f"\n🧭 Режимы: Яма/Нияма={'вкл' if user.principles_enabled else 'выкл'}, Меридианы={'вкл' if user.meridians_enabled else 'выкл'}\n🌿 Время меридианов: {user.meridian_time_for_send}",
                "uz": f"\n🧭 Rejimlar: Yama/Niyama={'yoqilgan' if user.principles_enabled else 'o‘chirilgan'}, Meridianlar={'yoqilgan' if user.meridians_enabled else 'o‘chirilgan'}\n🌿 Meridian vaqti: {user.meridian_time_for_send}",
                "kz": f"\n🧭 Режимдер: Яма/Нияма={'қосулы' if user.principles_enabled else 'өшірулі'}, Меридиандар={'қосулы' if user.meridians_enabled else 'өшірулі'}\n🌿 Меридиан уақыты: {user.meridian_time_for_send}"
            }.get(user.language, "")
            text += mode_text

            # Show settings menu instead of just text
            text = self._as_html(f"{text}\n\n{self._get_text('settings_menu', language=user.language)}")
            keyboard = self._create_settings_menu_keyboard(user.language)

            await update.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error in settings handler for user {chat_id}: {e}")
            # Try to get user language for error message
            try:
                user = await self.storage.get_user(chat_id)
                error_lang = user.language if user else "en"
            except:
                error_lang = "en"
            await update.message.reply_text(self._get_text("error", language=error_lang))
    
    async def _handle_test(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /test command."""
        chat_id = update.effective_chat.id

        if chat_id not in self.admin_ids:
            return
        
        try:
            user = await self.storage.get_user(chat_id)
            if not user or not user.is_active:
                lang = user.language if user else "en"
                await update.message.reply_text(self._get_text("not_subscribed_test", language=lang))
                return
            
            success = await self.scheduler.send_test_message(chat_id, user.language)
            if not success:
                text = self._get_text("test_failed", user.language)
                await update.message.reply_text(text)

        except Exception as e:
            logger.error(f"Error in test handler for user {chat_id}: {e}")
            # Try to get user language for error message
            try:
                user = await self.storage.get_user(chat_id)
                error_lang = user.language if user else "en"
            except:
                error_lang = "en"
            await update.message.reply_text(self._get_text("error", language=error_lang))
    
    # Admin handlers.
    async def _handle_next(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /next command (admin only)."""
        chat_id = update.effective_chat.id
        
        if chat_id not in self.admin_ids:
            return
        
        # Check if update has message
        if not update.message:
            logger.warning("next called without message")
            return
        
        try:
            args = context.args
            target_chat_id = int(args[0]) if args else chat_id
            
            principle = await self.scheduler.get_next_principle_for_user(target_chat_id)
            if principle:
                target_user = await self.storage.get_user(target_chat_id)
                target_language = target_user.language if target_user else "en"
                principle_text = format_principle_message(principle, target_language)
                message_text = self._get_admin_text("next_principle", user_id=target_chat_id, principle=principle_text)
                await update.message.reply_text(message_text, parse_mode='HTML')
            else:
                text = self._get_admin_text("no_principles", user_id=target_chat_id)
                await update.message.reply_text(text)
                
        except Exception as e:
            logger.error(f"Error in next handler: {e}")
            try:
                await update.message.reply_text("Error getting next principle.")
            except:
                logger.error(f"Could not send error message to {chat_id}")
    
    async def _handle_add_principle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /add command (admin only)."""
        chat_id = update.effective_chat.id
        
        if chat_id not in self.admin_ids:
            return
        
        # Check if update has message
        if not update.message:
            logger.warning("add_principle called without message")
            return
        
        try:
            if not context.args:
                await update.message.reply_text(self._get_admin_text("add_usage"))
                return
            
            principle_text = " ".join(context.args)
            if not principle_text:
                await update.message.reply_text(self._get_admin_text("add_empty"))
                return
            
            # Simple parsing for new principle.
            lines = principle_text.split('\n')
            name = lines[0] if lines else "New Principle"
            description = '\n'.join(lines[1:]) if len(lines) > 1 else principle_text
            
            new_principle = {
                "name": name,
                "emoji": "🧘",
                "short_description": name,
                "description": description,
                "practice_tip": ""
            }
            
            success = await self.principles_manager.add_principle(new_principle)
            if success:
                text = self._get_admin_text("add_success", name=name)
            else:
                text = self._get_admin_text("add_error")
            
            await update.message.reply_text(text)
                
        except Exception as e:
            logger.error(f"Error in add principle handler: {e}")
            try:
                await update.message.reply_text(self._get_admin_text("add_error"))
            except:
                logger.error(f"Could not send error message to {chat_id}")
    
    async def _handle_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stats command (admin only)."""
        chat_id = update.effective_chat.id
        
        if chat_id not in self.admin_ids:
            return
        
        # Check if update has message
        if not update.message:
            logger.warning("stats called without message")
            return
        
        try:
            # Get storage stats.
            storage_stats = await self.storage.get_stats()
            
            # Get scheduler stats.
            scheduler_stats = self.scheduler.get_scheduler_stats()
            
            status = "Running" if scheduler_stats['running'] else "Stopped"
            
            text = self._get_admin_text(
                "stats",
                total_users=storage_stats['total_users'],
                active_users=storage_stats['active_users'],
                total_messages_sent=storage_stats['total_messages_sent'],
                total_jobs=scheduler_stats['total_jobs'],
                jobs_created=scheduler_stats['jobs_created'],
                status=status
            )
            
            # Send without Markdown to avoid parsing errors
            await update.message.reply_text(text)
            
        except Exception as e:
            logger.error(f"Error in stats handler: {e}")
            try:
                await update.message.reply_text("Error getting statistics.")
            except:
                logger.error(f"Could not send error message to {chat_id}")
    
    async def _handle_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /broadcast command (admin only)."""
        chat_id = update.effective_chat.id
        
        if chat_id not in self.admin_ids:
            return
        
        # Check if update has message
        if not update.message:
            logger.warning("broadcast called without message")
            return
        
        try:
            if not context.args:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("Announce meridians feature", callback_data="broadcast_meridians_announcement")
                ]])
                await update.message.reply_text(
                    f"{self._get_admin_text('broadcast_usage')}\n\nOr choose a localized template:",
                    reply_markup=keyboard
                )
                return
            
            broadcast_text = " ".join(context.args)
            if not broadcast_text:
                await update.message.reply_text(self._get_admin_text("broadcast_empty"))
                return

            if broadcast_text in ["meridians_announcement", "announce_meridians"]:
                await update.message.reply_text(self._get_admin_text("broadcast_start", count=len(await self.storage.get_all_active_users())))
                sent_count, failed_count, total = await self._send_localized_broadcast("feature_announcement", context)
                result_text = self._get_admin_text(
                    "broadcast_result",
                    sent=sent_count,
                    failed=failed_count,
                    total=total
                )
                await update.message.reply_text(result_text)
                return
            
            # Get all active users.
            active_users = await self.storage.get_all_active_users()
            
            sent_count = 0
            failed_count = 0
            
            await update.message.reply_text(self._get_admin_text("broadcast_start", count=len(active_users)))
            
            for user in active_users:
                try:
                    # Send broadcast without Markdown to avoid parsing errors
                    await context.bot.send_message(user.chat_id, broadcast_text)
                    sent_count += 1
                except Exception:
                    failed_count += 1
            
            result_text = self._get_admin_text(
                "broadcast_result",
                sent=sent_count,
                failed=failed_count,
                total=len(active_users)
            )
            
            # Send result without Markdown to avoid parsing errors
            await update.message.reply_text(result_text)
            
        except Exception as e:
            logger.error(f"Error in broadcast handler: {e}")
            try:
                await update.message.reply_text("Error during broadcast.")
            except:
                logger.error(f"Could not send error message to {chat_id}")

    async def _send_localized_broadcast(self, text_key: str, context: ContextTypes.DEFAULT_TYPE) -> tuple:
        """Send a localized broadcast template to all active users."""
        active_users = await self.storage.get_all_active_users()
        sent_count = 0
        failed_count = 0

        for user in active_users:
            try:
                text = self._get_text(text_key, user.language)
                await context.bot.send_message(user.chat_id, text, parse_mode='HTML')
                sent_count += 1
            except Exception:
                failed_count += 1

        return sent_count, failed_count, len(active_users)
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle general messages for registration flow."""
        chat_id = update.effective_chat.id
        message_text = update.message.text
        message_id = update.message.message_id
        
        # Always delete user's message for clean dialog (with small delay for better UX)
        asyncio.create_task(self._delete_user_message_delayed(chat_id, message_id))
        
        # Check if user is in registration flow.
        if chat_id not in self.user_states:
            return
        
        try:
            user_state = self.user_states[chat_id]
            step = user_state["step"]
            language = user_state["language"]
            
            if step == "timezone" or step == "timezone_manual":
                await self._handle_timezone_input(update, message_text, language)
            elif step == "time":
                await self._handle_time_input(update, message_text, language)
            elif step == "change_timezone" or step == "change_timezone_manual":
                await self._handle_change_timezone_input(update, message_text, language)
            elif step == "change_time":
                await self._handle_change_time_input(update, message_text, language)
            elif step == "change_meridian_time":
                await self._handle_change_meridian_time_input(update, message_text, language)
            elif step == "feedback":
                await self._handle_feedback_input(update, message_text, language)
            elif step == "stop_feedback":
                await self._handle_stop_feedback_input(update, message_text, language)
                
        except Exception as e:
            logger.error(f"Error in message handler for user {chat_id}: {e}")
            language = self.user_states.get(chat_id, {}).get("language", "en")
            await update.message.reply_text(self._get_text("error", language))
    
    async def _handle_timezone_input(self, update: Update, timezone_str: str, language: str) -> None:
        """Handle timezone input during registration."""
        chat_id = update.effective_chat.id
        user_state = self.user_states[chat_id]
        message_id = user_state.get("registration_message_id")
        
        if not is_valid_timezone(timezone_str):
            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=self._get_text("invalid_timezone", language),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(self._get_text("invalid_timezone", language), parse_mode='Markdown')
            return
        
        # Save timezone and move to next step.
        self.user_states[chat_id]["timezone"] = timezone_str
        self.user_states[chat_id]["step"] = "time"
        
        confirmation = self._get_text("timezone_saved", language)
        time_msg = self._get_time_step_text(language, user_state)
        
        combined_msg = f"{confirmation}\n\n{time_msg}"
        
        if message_id:
            await self._edit_bot_message_text_safe(
                chat_id=chat_id,
                message_id=message_id,
                text=combined_msg,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(combined_msg, parse_mode='HTML')
    
    async def _handle_time_input(self, update: Update, time_str: str, language: str) -> None:
        """Handle time input during registration."""
        chat_id = update.effective_chat.id
        user_state = self.user_states[chat_id]
        message_id = user_state.get("registration_message_id")
        
        if not is_valid_time_format(time_str):
            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=self._get_text("invalid_time", language),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(self._get_text("invalid_time", language))
            return
        
        # Save time and move to next step.
        self.user_states[chat_id]["time"] = time_str

        if not user_state.get("principles_enabled", True):
            from bot.storage import User

            user = User(
                chat_id=chat_id,
                language=language,
                timezone=user_state["timezone"],
                time_for_send=time_str,
                meridian_time_for_send=time_str,
                skip_day_id=[],
                principles_enabled=False,
                meridians_enabled=user_state.get("meridians_enabled", True),
                is_active=True
            )
            if user.meridians_enabled and not user.current_meridian_id:
                first_meridian = self.meridians_manager.get_first_meridian()
                if first_meridian:
                    user.current_meridian_id = first_meridian["id"]
                    user.current_point_index = -1

            success = await self.storage.save_user(user)
            if not success:
                if message_id:
                    await self._edit_bot_message_text_safe(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=self._get_text("setup_error", language),
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(self._get_text("setup_error", language), parse_mode='Markdown')
                return

            await self.scheduler.schedule_user_immediately(chat_id)
            del self.user_states[chat_id]

            text = self._format_setup_complete(user, language, self._format_skip_days([], language))
            text += f"\n\n{self._get_text('menu', language)}"
            keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)

            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
                await self.storage.add_bot_message(chat_id, message_id, "setup_complete")
            else:
                sent = await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
                await self.storage.add_bot_message(chat_id, sent.message_id, "setup_complete")
            return

        self.user_states[chat_id]["step"] = "skip_days"
        self.user_states[chat_id]["selected_skip_days"] = []  # Initialize empty selection
        
        confirmation = self._get_text("time_saved", language)
        skip_days_msg = self._get_text("skip_days_step", language)
        
        combined_msg = f"{confirmation}\n\n{skip_days_msg}"
        
        # Add info about no days selected initially
        if language == "en":
            combined_msg += f"\n\n🔸 **No days selected** - messages will be sent daily"
        elif language == "ru":
            combined_msg += f"\n\n🔸 **Дни не выбраны** - сообщения будут отправляться ежедневно"
        elif language == "uz":
            combined_msg += f"\n\n🔸 **Kunlar tanlanmagan** - xabarlar har kuni yuboriladi"
        elif language == "kz":
            combined_msg += f"\n\n🔸 **Күндер таңдалмаған** - хабарлар күн сайын жіберіледі"
        
        keyboard = self._create_skip_days_keyboard(language, [])
        
        if message_id:
            await self._edit_bot_message_text_safe(
                chat_id=chat_id,
                message_id=message_id,
                text=combined_msg,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(combined_msg, parse_mode='Markdown')
    

    
    def _format_skip_days(self, skip_days: List[int], language: str) -> str:
        """Format skip days for display."""
        if not skip_days:
            day_none = {"ru": "Нет", "en": "None", "uz": "Yo'q", "kz": "Жоқ"}
            return day_none.get(language, "None")
        
        day_names_map = {
            "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            "ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
            "uz": ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"],
            "kz": ["Дс", "Сс", "Ср", "Бс", "Жм", "Сб", "Жк"]
        }
        
        day_names = day_names_map.get(language, day_names_map["en"])
        return ", ".join([day_names[day] for day in skip_days])

    def _format_setup_complete(self, user, language: str, skip_days_display: str) -> str:
        """Format setup summary according to the selected practice modes."""
        labels = {
            "en": {
                "done": "🎉 **Setup complete!**",
                "settings": "📋 **Your settings:**",
                "mode": "🧭 Practice:",
                "principles": "Yama/Niyama",
                "meridians": "Meridians",
                "both": "Yama/Niyama + Meridians",
                "time": "🕐 Time:",
                "principle_time": "🕐 Yama/Niyama time:",
                "meridian_time": "☯️ Meridian time:",
                "timezone": "🌍 Time zone:",
                "skip": "📅 Skip Yama/Niyama on:",
                "hint": "You can open /menu at any time to adjust your path, reminders, or meridian practice.",
            },
            "ru": {
                "done": "🎉 **Настройка завершена!**",
                "settings": "📋 **Ваши настройки:**",
                "mode": "🧭 Практика:",
                "principles": "Яма/Нияма",
                "meridians": "Меридианы",
                "both": "Яма/Нияма + Меридианы",
                "time": "🕐 Время:",
                "principle_time": "🕐 Время Ямы/Ниямы:",
                "meridian_time": "☯️ Время меридианов:",
                "timezone": "🌍 Часовой пояс:",
                "skip": "📅 Пропускать Яму/Нияму:",
                "hint": "В любой момент можно открыть /menu, изменить путь, напоминания или практику меридианов.",
            },
            "uz": {
                "done": "🎉 **Sozlash yakunlandi!**",
                "settings": "📋 **Sozlamalaringiz:**",
                "mode": "🧭 Amaliyot:",
                "principles": "Yama/Niyama",
                "meridians": "Meridianlar",
                "both": "Yama/Niyama + Meridianlar",
                "time": "🕐 Vaqt:",
                "principle_time": "🕐 Yama/Niyama vaqti:",
                "meridian_time": "☯️ Meridian vaqti:",
                "timezone": "🌍 Vaqt mintaqasi:",
                "skip": "📅 Yama/Niyamani o'tkazib yuborish:",
                "hint": "Istalgan vaqtda /menu ni ochib, yo'l, eslatmalar yoki meridian amaliyotini o'zgartirishingiz mumkin.",
            },
            "kz": {
                "done": "🎉 **Баптау аяқталды!**",
                "settings": "📋 **Баптауларыңыз:**",
                "mode": "🧭 Тәжірибе:",
                "principles": "Яма/Нияма",
                "meridians": "Меридиандар",
                "both": "Яма/Нияма + Меридиандар",
                "time": "🕐 Уақыт:",
                "principle_time": "🕐 Яма/Нияма уақыты:",
                "meridian_time": "☯️ Меридиан уақыты:",
                "timezone": "🌍 Уақыт белдеуі:",
                "skip": "📅 Яма/Нияманы өткізіп жіберу:",
                "hint": "Кез келген уақытта /menu ашып, жолды, еске салуларды немесе меридиан тәжірибесін өзгерте аласыз.",
            },
        }.get(language)

        if user.principles_enabled and user.meridians_enabled:
            mode = labels["both"]
        elif user.meridians_enabled:
            mode = labels["meridians"]
        else:
            mode = labels["principles"]

        lines = [
            labels["done"],
            "",
            labels["settings"],
            f"{labels['mode']} {mode}",
            f"{labels['timezone']} `{user.timezone}`",
        ]

        if user.principles_enabled and user.meridians_enabled:
            lines.extend([
                f"{labels['principle_time']} `{user.time_for_send}`",
                f"{labels['meridian_time']} `{user.meridian_time_for_send}`",
                f"{labels['skip']} {skip_days_display}",
            ])
        elif user.principles_enabled:
            lines.extend([
                f"{labels['time']} `{user.time_for_send}`",
                f"{labels['skip']} {skip_days_display}",
            ])
        else:
            lines.append(f"{labels['time']} `{user.meridian_time_for_send}`")

        lines.extend(["", labels["hint"]])
        return "\n".join(lines)
    
    def _create_timezone_keyboard(self, language: str, add_back_button: bool = False) -> InlineKeyboardMarkup:
        """Create timezone selection keyboard."""
        timezones = {
            "en": [
                # Популярные часовые пояса для региона
                ("🇷🇺 Moscow +3", "Europe/Moscow"),
                ("🇺🇿 Tashkent +5", "Asia/Tashkent"),
                ("🇰🇿 Almaty +5", "Asia/Almaty"),
                ("🇺🇦 Kyiv +3", "Europe/Kyiv"),
                ("🇹🇷 Istanbul +3", "Europe/Istanbul"),
                ("🇦🇿 Baku +4", "Asia/Baku"),
                ("🇦🇲 Yerevan +4", "Asia/Yerevan"),
                ("🇬🇪 Tbilisi +4", "Asia/Tbilisi"),
                ("🇰🇬 Bishkek +6", "Asia/Bishkek"),
                ("🇹🇲 Ashgabat +5", "Asia/Ashgabat"),
                ("🇲🇳 Ulaanbaatar +8", "Asia/Ulaanbaatar"),
                ("🌍 UTC +0", "UTC"),
            ],
            "ru": [
                ("🇷🇺 Москва +3", "Europe/Moscow"),
                ("🇺🇿 Ташкент +5", "Asia/Tashkent"),
                ("🇰🇿 Алматы +5", "Asia/Almaty"),
                ("🇺🇦 Киев +3", "Europe/Kyiv"),
                ("🇹🇷 Стамбул +3", "Europe/Istanbul"),
                ("🇦🇿 Баку +4", "Asia/Baku"),
                ("🇦🇲 Ереван +4", "Asia/Yerevan"),
                ("🇬🇪 Тбилиси +4", "Asia/Tbilisi"),
                ("🇰🇬 Бишкек +6", "Asia/Bishkek"),
                ("🇹🇲 Ашхабад +5", "Asia/Ashgabat"),
                ("🇲🇳 Улан-Батор +8", "Asia/Ulaanbaatar"),
                ("🌍 UTC +0", "UTC"),
            ],
            "uz": [
                ("🇺🇿 Toshkent +5", "Asia/Tashkent"),
                ("🇺🇿 Samarqand +5", "Asia/Samarkand"),
                ("🇰🇿 Almaty +5", "Asia/Almaty"),
                ("🇷🇺 Moskva +3", "Europe/Moscow"),
                ("🇹🇷 Istanbul +3", "Europe/Istanbul"),
                ("🇦🇿 Boku +4", "Asia/Baku"),
                ("🇦🇲 Yerevan +4", "Asia/Yerevan"),
                ("🇬🇪 Tbilisi +4", "Asia/Tbilisi"),
                ("🇰🇬 Bishkek +6", "Asia/Bishkek"),
                ("🇹🇲 Ashgabat +5", "Asia/Ashgabat"),
                ("🇺🇦 Kyiv +3", "Europe/Kyiv"),
                ("🌍 UTC +0", "UTC"),
            ],
            "kz": [
                ("🇰🇿 Алматы +5", "Asia/Almaty"),
                ("🇰🇿 Астана +5", "Asia/Almaty"),
                ("🇰🇿 Ақтөбе +5", "Asia/Aqtobe"),
                ("🇺🇿 Ташкент +5", "Asia/Tashkent"),
                ("🇷🇺 Мәскеу +3", "Europe/Moscow"),
                ("🇰🇬 Бішкек +6", "Asia/Bishkek"),
                ("🇹🇷 Стамбул +3", "Europe/Istanbul"),
                ("🇦🇿 Баку +4", "Asia/Baku"),
                ("🇦🇲 Ереван +4", "Asia/Yerevan"),
                ("🇬🇪 Тбилиси +4", "Asia/Tbilisi"),
                ("🇺🇦 Киев +3", "Europe/Kyiv"),
                ("🌍 UTC +0", "UTC"),
            ]
        }
        
        keyboard = []
        tz_list = timezones.get(language, timezones["en"])
        
        # Create rows of 2 buttons each for better mobile experience
        for i in range(0, len(tz_list), 2):
            row = []
            for j in range(i, min(i + 2, len(tz_list))):
                display_name, tz_code = tz_list[j]
                row.append(InlineKeyboardButton(display_name, callback_data=f"tz_{tz_code}"))
            keyboard.append(row)
        
        # Add manual input button as last row
        keyboard.append([InlineKeyboardButton(
            self._get_text("timezone_custom", language), 
            callback_data="tz_custom"
        )])
        
        # Add back button if requested
        if add_back_button:
            keyboard.append([InlineKeyboardButton(
                self._get_text("back_to_menu", language), 
                callback_data="settings_back"
            )])
        
        return InlineKeyboardMarkup(keyboard)
    
    def _create_skip_days_keyboard(self, language: str, selected_days: List[int] = None, add_back_button: bool = False) -> InlineKeyboardMarkup:
        """Create skip days selection keyboard."""
        if selected_days is None:
            selected_days = []
            
        day_names = {
            "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            "ru": ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"],
            "uz": ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"],
            "kz": ["Дүйсенбі", "Сейсенбі", "Сәрсенбі", "Бейсенбі", "Жұма", "Сенбі", "Жексенбі"]
        }
        
        days = day_names.get(language, day_names["en"])
        keyboard = []
        
        # Create buttons for each day (2 per row)
        for i in range(0, 7, 2):
            row = []
            for j in range(i, min(i + 2, 7)):
                day_idx = j
                is_selected = day_idx in selected_days
                emoji = "✅" if is_selected else "📅"
                day_name = days[day_idx]
                
                # Shorten day names for better mobile display
                if len(day_name) > 8:
                    day_name = day_name[:7] + "."
                
                button_text = f"{emoji} {day_name}"
                callback_data = f"skipday_{day_idx}"
                
                row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
            keyboard.append(row)
        
        # Add action buttons - split into two rows for better layout
        if language == "en":
            keyboard.append([InlineKeyboardButton("🎯 No Skip Days", callback_data="skipday_none")])
            keyboard.append([InlineKeyboardButton("📅 Weekends Only", callback_data="skipday_weekends")])
        elif language == "ru":
            keyboard.append([InlineKeyboardButton("🎯 Не пропускать", callback_data="skipday_none")])
            keyboard.append([InlineKeyboardButton("📅 Только выходные", callback_data="skipday_weekends")])
        elif language == "uz":
            keyboard.append([InlineKeyboardButton("🎯 Kunlarni o'tkazmaslik", callback_data="skipday_none")])
            keyboard.append([InlineKeyboardButton("📅 Faqat dam olish kunlari", callback_data="skipday_weekends")])
        elif language == "kz":
            keyboard.append([InlineKeyboardButton("🎯 Күндерді өткізбеу", callback_data="skipday_none")])
            keyboard.append([InlineKeyboardButton("📅 Тек демалыс күндері", callback_data="skipday_weekends")])
        
        # Add finish button
        finish_text = {
            "en": "✅ Continue",
            "ru": "✅ Продолжить", 
            "uz": "✅ Davom etish",
            "kz": "✅ Жалғастыру"
        }
        
        keyboard.append([InlineKeyboardButton(
            finish_text.get(language, finish_text["en"]), 
            callback_data="skipday_finish"
        )])
        
        # Add back button if requested
        if add_back_button:
            keyboard.append([InlineKeyboardButton(
                self._get_text("back_to_menu", language), 
                callback_data="settings_back"
            )])
        
        return InlineKeyboardMarkup(keyboard)
    
    def _create_main_menu_keyboard(self, language: str, is_admin: bool = False) -> InlineKeyboardMarkup:
        """Create main menu keyboard."""
        keyboard = [
            [
                InlineKeyboardButton(self._get_text("menu_principles", language), callback_data="menu_principles"),
                InlineKeyboardButton(self._get_text("menu_meridians", language), callback_data="menu_meridians")
            ],
            [
                InlineKeyboardButton(self._get_text("menu_modes", language), callback_data="menu_modes"),
                InlineKeyboardButton(self._get_text("menu_settings", language), callback_data="menu_settings")
            ],
            [
                InlineKeyboardButton(self._get_text("menu_about", language), callback_data="menu_about"),
                InlineKeyboardButton(self._get_text("menu_feedback", language), callback_data="menu_feedback")
            ],
            [
                InlineKeyboardButton(self._get_text("menu_stop", language), callback_data="menu_stop")
            ]
        ]
        if is_admin:
            keyboard.append([InlineKeyboardButton(self._get_text("menu_test", language), callback_data="menu_test")])
        return InlineKeyboardMarkup(keyboard)

    def _create_main_menu_keyboard_for_user(self, chat_id: int, language: str) -> InlineKeyboardMarkup:
        """Create main menu keyboard with admin-only actions when applicable."""
        return self._create_main_menu_keyboard(language, is_admin=chat_id in self.admin_ids)
    
    def _create_settings_menu_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create settings menu keyboard."""
        keyboard = [
            [
                InlineKeyboardButton(self._get_text("change_modes", language), callback_data="change_modes"),
                InlineKeyboardButton(self._get_text("change_meridian_time", language), callback_data="change_meridian_time")
            ],
            [
                InlineKeyboardButton(self._get_text("change_language", language), callback_data="change_language"),
                InlineKeyboardButton(self._get_text("change_time", language), callback_data="change_time")
            ],
            [
                InlineKeyboardButton(self._get_text("change_timezone", language), callback_data="change_timezone"),
                InlineKeyboardButton(self._get_text("change_skip_days", language), callback_data="change_skip_days")
            ],
            [
                InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    def _create_principles_menu_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create Yama/Niyama section keyboard."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(self._get_text("principles_random", language), callback_data="principles_random"),
                InlineKeyboardButton(self._get_text("principles_all", language), callback_data="principles_all")
            ],
            [InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")]
        ])

    def _create_principles_list_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create a clickable list of all Yama/Niyama principles."""
        principles = self.principles_manager.get_all_principles(language)
        keyboard = []
        for principle in principles:
            principle_id = int(principle.get("id", 0))
            group = self._get_principle_group_name(principle_id, language)
            emoji = principle.get("emoji", "")
            name = principle.get("name", "")
            keyboard.append([
                InlineKeyboardButton(
                    f"{group}: {emoji} {name}".strip(),
                    callback_data=f"principles_show:{principle_id}"
                )
            ])
        keyboard.append([InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="principles_back")])
        return InlineKeyboardMarkup(keyboard)

    def _create_practice_modes_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create practice mode selection keyboard."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("mode_principles_only", language), callback_data="mode_principles")],
            [InlineKeyboardButton(self._get_text("mode_meridians_only", language), callback_data="mode_meridians")],
            [InlineKeyboardButton(self._get_text("mode_both", language), callback_data="mode_both")],
            [InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")]
        ])

    def _create_registration_modes_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create initial practice mode keyboard for new-user onboarding."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("mode_meridians_only", language), callback_data="intro_mode_meridians")],
            [InlineKeyboardButton(self._get_text("mode_principles_only", language), callback_data="intro_mode_principles")],
            [InlineKeyboardButton(self._get_text("mode_both", language), callback_data="intro_mode_both")],
        ])

    def _create_meridians_menu_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create compact meridians section keyboard."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("current_meridian", language), callback_data="meridian_current")],
            [
                InlineKeyboardButton(self._get_text("meridian_change_path", language), callback_data="meridian_path"),
                InlineKeyboardButton(self._get_text("meridian_measurements", language), callback_data="meridian_measurements")
            ],
            [InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")]
        ])

    def _create_meridian_practice_keyboard(
        self,
        language: str,
        at_intro: bool = False,
        point_index: Optional[int] = None,
        points_count: Optional[int] = None
    ) -> InlineKeyboardMarkup:
        """Create navigation keyboard for an opened meridian or point."""
        if at_intro:
            return InlineKeyboardMarkup([
                [InlineKeyboardButton(self._get_text("meridian_start_points", language), callback_data="meridian_next")],
                [
                    InlineKeyboardButton(self._get_text("all_points", language), callback_data="meridian_all"),
                    InlineKeyboardButton(self._get_text("complete_meridian", language), callback_data="meridian_complete")
                ],
                [InlineKeyboardButton(self._get_text("meridian_back", language), callback_data="meridian_main")]
            ])

        navigation_row = []
        if point_index is None or point_index > 0:
            navigation_row.append(InlineKeyboardButton(self._get_text("prev_point", language), callback_data="meridian_prev"))
        if point_index is None or points_count is None or point_index < points_count - 1:
            navigation_row.append(InlineKeyboardButton(self._get_text("next_point", language), callback_data="meridian_next"))

        keyboard = []
        if navigation_row:
            keyboard.append(navigation_row)
        keyboard.extend([
            [
                InlineKeyboardButton(self._get_text("all_points", language), callback_data="meridian_all"),
                InlineKeyboardButton(self._get_text("complete_meridian", language), callback_data="meridian_complete")
            ],
            [InlineKeyboardButton(self._get_text("meridian_back", language), callback_data="meridian_main")]
        ])
        return InlineKeyboardMarkup(keyboard)

    def _create_meridian_path_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create meridian learning mode selection keyboard."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("meridian_guided_path", language), callback_data="meridian_path:guided")],
            [InlineKeyboardButton(self._get_text("meridian_free_choice", language), callback_data="meridian_path:free")],
            [InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")]
        ])

    def _create_meridian_choice_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create meridian selection keyboard."""
        meridians = self.meridians_manager.get_all_meridians()
        keyboard = []
        for index in range(0, len(meridians), 2):
            row = []
            for meridian in meridians[index:index + 2]:
                localized = meridian.get("i18n", {}).get(language, meridian.get("i18n", {}).get("en", {}))
                name = localized.get("name", meridian.get("id"))
                has_points = bool(meridian.get("points"))
                if not has_points:
                    name = f"{name} ({self._get_text('coming_soon', language)})"
                row.append(InlineKeyboardButton(
                    name,
                    callback_data=(
                        f"meridian_select:{meridian.get('id')}"
                        if has_points
                        else f"meridian_unavailable:{meridian.get('id')}"
                    )
                ))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton(self._get_text("meridian_back", language), callback_data="meridian_main")])
        return InlineKeyboardMarkup(keyboard)

    def _create_meridian_points_keyboard(self, meridian: Dict[str, Any], language: str, page: int = 0) -> InlineKeyboardMarkup:
        """Create a paginated clickable list of points for the current meridian."""
        keyboard = []
        points = meridian.get("points", [])
        total_pages = max(1, (len(points) + MERIDIAN_POINTS_PAGE_SIZE - 1) // MERIDIAN_POINTS_PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        start = page * MERIDIAN_POINTS_PAGE_SIZE
        end = min(start + MERIDIAN_POINTS_PAGE_SIZE, len(points))

        for index, point in enumerate(points[start:end], start=start):
            localized = point.get("i18n", {}).get(language, point.get("i18n", {}).get("en", {}))
            code = point.get("code", "")
            name = localized.get("name", "")
            keyboard.append([
                InlineKeyboardButton(
                    f"{index + 1}. {code} {name}".strip(),
                    callback_data=f"meridian_point:{index}"
                )
            ])
        if total_pages > 1:
            navigation = []
            if page > 0:
                navigation.append(InlineKeyboardButton("◀️ 10", callback_data=f"meridian_points_page:{page - 1}"))
            navigation.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="meridian_noop"))
            if page < total_pages - 1:
                navigation.append(InlineKeyboardButton("10 ▶️", callback_data=f"meridian_points_page:{page + 1}"))
            keyboard.append(navigation)
        keyboard.append([InlineKeyboardButton(self._get_text("meridian_back", language), callback_data="meridian_current")])
        return InlineKeyboardMarkup(keyboard)

    def _format_meridian_points_page_text(self, language: str, page: int, total_pages: int) -> str:
        """Build text for the paginated point chooser."""
        choose_point = {
            "en": "Choose a point to open its location image and practice.",
            "ru": "Выберите точку, чтобы открыть изображение расположения и практику.",
            "uz": "Joylashuv rasmi va amaliyotni ochish uchun nuqtani tanlang.",
            "kz": "Орналасу суреті мен тәжірибені ашу үшін нүктені таңдаңыз.",
        }.get(language, "Choose a point to open its location image and practice.")
        if total_pages <= 1:
            return f"<b>{self._get_text('all_points', language)}</b>\n\n{choose_point}"
        page_note = {
            "en": f"Page {page + 1}/{total_pages}.",
            "ru": f"Страница {page + 1}/{total_pages}.",
            "uz": f"Sahifa {page + 1}/{total_pages}.",
            "kz": f"Бет {page + 1}/{total_pages}.",
        }.get(language, f"Page {page + 1}/{total_pages}.")
        return f"<b>{self._get_text('all_points', language)}</b>\n\n{choose_point}\n\n{page_note}"
    
    async def _handle_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /menu command."""
        chat_id = update.effective_chat.id
        
        try:
            user = await self.storage.get_user(chat_id)
            language = user.language if user else "en"
            
            if not user or not user.is_active:
                await update.message.reply_text(self._get_text("not_subscribed_test", language))
                return

            text = self._as_html(self._get_text("menu", language))
            keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)

            await update.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error in menu handler for user {chat_id}: {e}")
            # Try to get user language for error message
            try:
                user = await self.storage.get_user(chat_id)
                error_lang = user.language if user else "en"
            except:
                error_lang = "en"
            await update.message.reply_text(self._get_text("error", language=error_lang))
    
    async def _handle_menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle main menu callback queries."""
        query = update.callback_query
        chat_id = query.message.chat.id
        action = query.data.split("_", 1)[1]  # Extract action after "menu_"
        
        try:
            await query.answer()
            
            user = await self.storage.get_user(chat_id)
            language = user.language if user else "en"
            
            if action == "settings":
                text = self._as_html(self._get_text("settings_menu", language))
                keyboard = self._create_settings_menu_keyboard(language)
                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')

            elif action == "principles":
                text = self._get_text("principles_menu", language)
                keyboard = self._create_principles_menu_keyboard(language)
                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')

            elif action == "modes":
                text = self._get_text("mode_menu", language)
                keyboard = self._create_practice_modes_keyboard(language)
                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')

            elif action == "meridians":
                if not getattr(user, "meridian_learning_mode", None):
                    text = self._get_text("meridian_mode_menu", language)
                    keyboard = self._create_meridian_path_keyboard(language)
                else:
                    text = self._get_text("meridians_menu", language)
                    keyboard = self._create_meridians_menu_keyboard(language)
                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')
                
            elif action == "test":
                await self._edit_message_text_safe(query, self._get_text("sending_test", language))
                success = await self.scheduler.send_test_message(chat_id, language)
                if success:
                    text = self._as_html(self._get_text("menu", language))
                    keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
                    await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')
                else:
                    await self._edit_message_text_safe(query, self._get_text("test_failed", language))
                    
            elif action == "about":
                text = self._get_text("about_text", language)
                keyboard = [[InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")]]
                await self._edit_message_text_safe(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
                
            elif action == "feedback":
                # Set user state to expect feedback input
                self.user_states[chat_id] = {"step": "feedback", "language": language}
                
                text = self._get_text("feedback_prompt", language)
                keyboard = [[InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")]]
                await self._edit_message_text_safe(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
                
            elif action == "stop":
                success = await self.storage.deactivate_user(chat_id)
                if success:
                    await self.scheduler.remove_user_jobs(chat_id)
                    self.user_states[chat_id] = {"step": "stop_feedback", "language": language}
                    text = self._as_html(f"{self._get_text('unsubscribed', language)}\n\n{self._get_text('stop_feedback_prompt', language)}")
                    await self._edit_message_text_safe(query, text, parse_mode='HTML')
                else:
                    await self._edit_message_text_safe(query, self._get_text("not_subscribed", language))
                    
            elif action == "main":
                text = self._as_html(self._get_text("menu", language))
                keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')
                
        except Exception as e:
            logger.error(f"Error in menu callback for user {chat_id}: {e}")
            await self._edit_message_text_safe(query, self._get_text("error", language))

    async def _handle_principles_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle Yama/Niyama section callbacks."""
        query = update.callback_query
        chat_id = query.message.chat.id
        action = query.data.split("_", 1)[1]

        try:
            await query.answer()
            user = await self.storage.get_user(chat_id)
            language = user.language if user else "en"

            if action == "random":
                principle = self.principles_manager.get_random_principle(language)
                if not principle:
                    await self._edit_message_text_safe(query, self._get_text("principles_empty", language))
                    return
                await self._show_principle_detail(query, principle, language)
                return
            elif action == "all":
                text = self._format_principles_list(language)
                keyboard = self._create_principles_list_keyboard(language)
                parse_mode = 'HTML'
            elif action.startswith("show:"):
                principle_id = int(action.split(":", 1)[1])
                principle = next(
                    (item for item in self.principles_manager.get_all_principles(language) if int(item.get("id", 0)) == principle_id),
                    None
                )
                if not principle:
                    await self._edit_message_text_safe(query, self._get_text("principles_empty", language))
                    return
                await self._show_principle_detail(query, principle, language)
                return
            else:
                text = self._get_text("principles_menu", language)
                keyboard = self._create_principles_menu_keyboard(language)
                parse_mode = 'HTML'

            await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode=parse_mode)

        except Exception as e:
            logger.error(f"Error in principles callback for user {chat_id}: {e}")
            language = "en"
            try:
                user = await self.storage.get_user(chat_id)
                language = user.language if user else "en"
            except Exception:
                pass
            await self._edit_message_text_safe(query, self._get_text("error", language))
    
    async def _handle_settings_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle settings callback queries (back to settings menu)."""
        query = update.callback_query
        chat_id = query.message.chat.id
        
        try:
            await query.answer()
            
            user = await self.storage.get_user(chat_id)
            language = user.language if user else "en"
            
            text = self._as_html(self._get_text("settings_menu", language))
            keyboard = self._create_settings_menu_keyboard(language)
            await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Error in settings callback for user {chat_id}: {e}")
            await self._edit_message_text_safe(query, self._get_text("error", language))
    
    async def _handle_change_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle change settings callback queries."""
        query = update.callback_query
        chat_id = query.message.chat.id
        setting = query.data.split("_", 1)[1]  # Extract setting after "change_"
        
        try:
            await query.answer()
            
            user = await self.storage.get_user(chat_id)
            language = user.language if user else "en"
            
            if setting == "language":
                keyboard = [
                    [
                        InlineKeyboardButton(TEXTS["en"]["english"], callback_data="lang_en"),
                        InlineKeyboardButton(TEXTS["en"]["russian"], callback_data="lang_ru")
                    ],
                    [
                        InlineKeyboardButton(TEXTS["uz"]["uzbek"], callback_data="lang_uz"),
                        InlineKeyboardButton(TEXTS["kz"]["kazakh"], callback_data="lang_kz")
                    ],
                    [
                        InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="settings_back")
                    ]
                ]
                await self._edit_message_text_safe(query, 
                    self._get_text("choose_language", language), 
                    reply_markup=InlineKeyboardMarkup(keyboard), 
                    parse_mode='Markdown'
                )

            elif setting == "modes":
                text = self._get_text("mode_menu", language)
                keyboard = self._create_practice_modes_keyboard(language)
                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')

            elif setting == "meridian_time":
                self.user_states[chat_id] = {"step": "change_meridian_time", "language": language, "settings_message_id": query.message.message_id}
                keyboard = [[InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="settings_back")]]
                await self._edit_message_text_safe(query, 
                    self._get_text("meridian_time_step", language),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                
            elif setting == "time":
                self.user_states[chat_id] = {"step": "change_time", "language": language, "settings_message_id": query.message.message_id}
                keyboard = [[InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="settings_back")]]
                await self._edit_message_text_safe(query, 
                    self._get_text("time_step", language), 
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                
            elif setting == "timezone":
                self.user_states[chat_id] = {"step": "change_timezone", "language": language, "settings_message_id": query.message.message_id}
                keyboard = self._create_timezone_keyboard(language, add_back_button=True)
                await self._edit_message_text_safe(query, 
                    self._get_text("timezone_step", language), 
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
                
            elif setting == "skip_days":
                # Get current user skip days
                current_skip_days = user.skip_day_id if user else []
                self.user_states[chat_id] = {
                    "step": "change_skip_days", 
                    "language": language, 
                    "settings_message_id": query.message.message_id,
                    "selected_skip_days": current_skip_days.copy()
                }
                
                text = self._get_text("skip_days_step", language)
                
                # Add current selection info
                if current_skip_days:
                    days_display = self._format_skip_days(current_skip_days, language)
                    if language == "en":
                        text += f"\n\n🔸 **Current selection:** {days_display}"
                    elif language == "ru":
                        text += f"\n\n🔸 **Текущий выбор:** {days_display}"
                    elif language == "uz":
                        text += f"\n\n🔸 **Joriy tanlov:** {days_display}"
                    elif language == "kz":
                        text += f"\n\n🔸 **Ағымдағы таңдау:** {days_display}"
                else:
                    if language == "en":
                        text += f"\n\n🔸 **No days selected** - messages are sent daily"
                    elif language == "ru":
                        text += f"\n\n🔸 **Дни не выбраны** - сообщения отправляются ежедневно"
                    elif language == "uz":
                        text += f"\n\n🔸 **Kunlar tanlanmagan** - xabarlar har kuni yuboriladi"
                    elif language == "kz":
                        text += f"\n\n🔸 **Күндер таңдалмаған** - хабарлар күн сайын жіберіледі"
                
                keyboard = self._create_skip_days_keyboard(language, current_skip_days, add_back_button=True)
                
                await self._edit_message_text_safe(query, 
                    text, 
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Error in change callback for user {chat_id}: {e}")
            await self._edit_message_text_safe(query, self._get_text("error", language))

    async def _handle_mode_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle practice mode selection."""
        query = update.callback_query
        chat_id = query.message.chat.id
        mode = query.data.split("_", 1)[1]

        try:
            await query.answer()
            user = await self.storage.get_user(chat_id)
            language = user.language if user else "en"
            if not user:
                await self._edit_message_text_safe(query, self._get_text("not_subscribed_test", language))
                return

            user.principles_enabled = mode in ["principles", "both"]
            user.meridians_enabled = mode in ["meridians", "both"]

            if user.meridians_enabled and not user.current_meridian_id:
                first_meridian = self.meridians_manager.get_first_meridian()
                if first_meridian:
                    user.current_meridian_id = first_meridian["id"]
                    user.current_point_index = -1

            await self.storage.save_user(user)
            await self.scheduler.schedule_user_immediately(chat_id)

            menu_text = self._get_text("menu", language).replace("**", "<b>", 1).replace("**", "</b>", 1)
            text = f"{self._get_text('mode_saved', language)}\n\n{menu_text}"
            keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
            await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error in mode callback for user {chat_id}: {e}")
            await self._edit_message_text_safe(query, self._get_text("error", "en"))

    async def _handle_meridian_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle meridian study navigation."""
        query = update.callback_query
        chat_id = query.message.chat.id
        action = query.data.split("_", 1)[1]

        try:
            await query.answer()
            user = await self.storage.get_user(chat_id)
            language = user.language if user else "en"
            if not user:
                await self._edit_message_text_safe(query, self._get_text("not_subscribed_test", language))
                return

            if action == "path":
                await self._edit_message_text_safe(
                    query,
                    self._get_text("meridian_mode_menu", language),
                    reply_markup=self._create_meridian_path_keyboard(language),
                    parse_mode='HTML'
                )
                return

            if action == "measurements":
                await self._edit_message_text_safe(
                    query,
                    self._get_text("meridian_measurements_text", language),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(self._get_text("meridian_back", language), callback_data="meridian_main")]
                    ]),
                    parse_mode='HTML'
                )
                return

            if action.startswith("path:"):
                path_mode = action.split(":", 1)[1]
                user.meridian_learning_mode = path_mode
                user.meridians_enabled = True

                if path_mode == "guided":
                    if not user.current_meridian_id:
                        next_meridian = self.meridians_manager.get_next_meridian(None, user.completed_meridians)
                        if next_meridian:
                            user.current_meridian_id = next_meridian["id"]
                            user.current_point_index = -1
                    await self.storage.save_user(user)
                    await self.scheduler.schedule_user_immediately(chat_id)
                    meridian = self.meridians_manager.get_meridian_by_id(user.current_meridian_id) if user.current_meridian_id else None
                    intro = format_meridian_intro(meridian, language) if meridian else self._get_text("meridians_menu", language)
                    text = f"{self._get_text('meridian_guided_saved', language)}\n\n{intro}"
                    await self._edit_message_text_safe(
                        query,
                        text,
                        reply_markup=self._create_meridian_practice_keyboard(language, at_intro=True),
                        parse_mode='HTML'
                    )
                    return

                user.current_meridian_id = None
                user.current_point_index = -1
                await self.storage.save_user(user)
                await self.scheduler.schedule_user_immediately(chat_id)
                text = f"{self._get_text('meridian_free_saved', language)}\n\n{self._get_text('choose_meridian', language)}"
                await self._edit_message_text_safe(
                    query,
                    text,
                    reply_markup=self._create_meridian_choice_keyboard(language),
                    parse_mode='HTML'
                )
                return

            if action == "main":
                if not getattr(user, "meridian_learning_mode", None):
                    text = self._get_text("meridian_mode_menu", language)
                    keyboard = self._create_meridian_path_keyboard(language)
                else:
                    text = self._get_text("meridians_menu", language)
                    keyboard = self._create_meridians_menu_keyboard(language)
                await self._edit_message_text_safe(query,
                    text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
                return

            if action == "choose":
                user.meridian_learning_mode = "free"
                await self.storage.save_user(user)
                await self._edit_message_text_safe(query, 
                    self._get_text("choose_meridian", language),
                    reply_markup=self._create_meridian_choice_keyboard(language),
                    parse_mode='HTML'
                )
                return

            if action.startswith("unavailable:"):
                text = f"{self._get_text('no_points', language)}\n\n{self._get_text('choose_meridian', language)}"
                await self._edit_message_text_safe(
                    query,
                    text,
                    reply_markup=self._create_meridian_choice_keyboard(language),
                    parse_mode='HTML'
                )
                return

            if action.startswith("select:"):
                meridian_id = action.split(":", 1)[1]
                meridian = self.meridians_manager.get_meridian_by_id(meridian_id)
                if not meridian:
                    await self._edit_message_text_safe(query, self._get_text("error", language))
                    return
                if not meridian.get("points"):
                    await self._edit_message_text_safe(
                        query,
                        f"{self._get_text('no_points', language)}\n\n{self._get_text('choose_meridian', language)}",
                        reply_markup=self._create_meridian_choice_keyboard(language),
                        parse_mode='HTML'
                    )
                    return
                user.meridian_learning_mode = "free"
                user.current_meridian_id = meridian_id
                user.current_point_index = -1
                user.meridians_enabled = True
                await self.storage.save_user(user)
                await self.scheduler.schedule_user_immediately(chat_id)
                text = format_meridian_intro(meridian, language)
                await self._show_meridian_card(
                    query,
                    text,
                    self._create_meridian_practice_keyboard(language, at_intro=True),
                    language,
                    meridian.get("id")
                )
                return

            meridian = self.meridians_manager.get_meridian_by_id(user.current_meridian_id) if user.current_meridian_id else None
            if not meridian:
                if getattr(user, "meridian_learning_mode", None) == "free":
                    await self._edit_message_text_safe(
                        query,
                        self._get_text("choose_meridian", language),
                        reply_markup=self._create_meridian_choice_keyboard(language),
                        parse_mode='HTML'
                    )
                    return
                meridian = self.meridians_manager.get_first_meridian()
                if not meridian:
                    await self._edit_message_text_safe(query, self._get_text("no_points", language))
                    return
                user.current_meridian_id = meridian["id"]
                user.current_point_index = -1
                await self.storage.save_user(user)

            points = meridian.get("points", [])

            if action == "noop":
                return

            if action == "current":
                text = format_meridian_point(meridian, user.current_point_index, language) if user.current_point_index >= 0 else format_meridian_intro(meridian, language)
                point_code = points[user.current_point_index].get("code") if user.current_point_index >= 0 and user.current_point_index < len(points) else None
                await self._show_meridian_card(
                    query,
                    text,
                    self._create_meridian_practice_keyboard(
                        language,
                        at_intro=user.current_point_index < 0,
                        point_index=user.current_point_index if user.current_point_index >= 0 else None,
                        points_count=len(points)
                    ),
                    language,
                    meridian.get("id"),
                    point_code
                )
                return

            if action == "all":
                if not points:
                    text = self._get_text("no_points", language)
                    keyboard = self._create_meridians_menu_keyboard(language)
                else:
                    total_pages = max(1, (len(points) + MERIDIAN_POINTS_PAGE_SIZE - 1) // MERIDIAN_POINTS_PAGE_SIZE)
                    text = self._format_meridian_points_page_text(language, 0, total_pages)
                    keyboard = self._create_meridian_points_keyboard(meridian, language, page=0)
                await self._show_meridian_card(query, text, keyboard, language)
                return

            if action.startswith("points_page:"):
                if not points:
                    await self._edit_message_text_safe(query, self._get_text("no_points", language), reply_markup=self._create_meridians_menu_keyboard(language), parse_mode='HTML')
                    return
                page = int(action.split(":", 1)[1])
                total_pages = max(1, (len(points) + MERIDIAN_POINTS_PAGE_SIZE - 1) // MERIDIAN_POINTS_PAGE_SIZE)
                page = max(0, min(page, total_pages - 1))
                text = self._format_meridian_points_page_text(language, page, total_pages)
                keyboard = self._create_meridian_points_keyboard(meridian, language, page=page)
                await self._show_meridian_card(query, text, keyboard, language)
                return

            if action.startswith("point:"):
                point_index = int(action.split(":", 1)[1])
                if point_index < 0 or point_index >= len(points):
                    await self._edit_message_text_safe(query, self._get_text("error", language))
                    return
                user.current_point_index = point_index
                await self.storage.save_user(user)
                point_code = points[point_index].get("code")
                text = format_meridian_point(meridian, point_index, language)
                await self._show_meridian_card(
                    query,
                    text,
                    self._create_meridian_practice_keyboard(language, point_index=point_index, points_count=len(points)),
                    language,
                    meridian.get("id"),
                    point_code
                )
                return

            if action in ["next", "prev"]:
                if not points:
                    await self._edit_message_text_safe(query, self._get_text("no_points", language), reply_markup=self._create_meridians_menu_keyboard(language), parse_mode='HTML')
                    return
                if action == "next":
                    user.current_point_index = min(user.current_point_index + 1, len(points) - 1)
                else:
                    user.current_point_index = max(user.current_point_index - 1, 0)
                await self.storage.save_user(user)
                text = format_meridian_point(meridian, user.current_point_index, language)
                point_code = points[user.current_point_index].get("code")
                await self._show_meridian_card(
                    query,
                    text,
                    self._create_meridian_practice_keyboard(language, point_index=user.current_point_index, points_count=len(points)),
                    language,
                    meridian.get("id"),
                    point_code
                )
                return

            if action == "complete":
                if user.current_meridian_id and user.current_meridian_id not in user.completed_meridians:
                    user.completed_meridians.append(user.current_meridian_id)

                if getattr(user, "meridian_learning_mode", None) == "guided":
                    next_meridian = self.meridians_manager.get_next_meridian(user.current_meridian_id, user.completed_meridians)
                    if next_meridian:
                        user.current_meridian_id = next_meridian["id"]
                        user.current_point_index = -1
                else:
                    user.current_meridian_id = None
                    user.current_point_index = -1

                await self.storage.save_user(user)
                text = self._get_text("meridian_completed", language)
                keyboard = self._create_meridian_practice_keyboard(language, at_intro=True) if user.current_meridian_id else self._create_meridian_choice_keyboard(language)
                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error in meridian callback for user {chat_id}: {e}")
            try:
                user = await self.storage.get_user(chat_id)
                language = user.language if user else "en"
            except Exception:
                language = "en"
            await self._edit_message_text_safe(query, self._get_text("error", language))

    async def _handle_broadcast_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle localized broadcast templates."""
        query = update.callback_query
        chat_id = query.message.chat.id
        action = query.data.split("_", 1)[1]

        if chat_id not in self.admin_ids:
            await query.answer()
            return

        try:
            await query.answer()
            if action != "meridians_announcement":
                await self._edit_message_text_safe(query, self._get_admin_text("broadcast_usage"))
                return

            sent_count, failed_count, total = await self._send_localized_broadcast("feature_announcement", context)
            result_text = self._get_admin_text("broadcast_result", sent=sent_count, failed=failed_count, total=total)
            await self._edit_message_text_safe(query, result_text)
        except Exception as e:
            logger.error(f"Error in broadcast callback for admin {chat_id}: {e}")
            await self._edit_message_text_safe(query, "Error during broadcast.")

    async def _handle_change_timezone_input(self, update: Update, timezone_str: str, language: str) -> None:
        """Handle timezone change input."""
        chat_id = update.effective_chat.id
        user_state = self.user_states[chat_id]
        message_id = user_state.get("settings_message_id")
        
        if not is_valid_timezone(timezone_str):
            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=self._get_text("invalid_timezone", language),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(self._get_text("invalid_timezone", language), parse_mode='Markdown')
            return
        
        try:
            user = await self.storage.get_user(chat_id)
            if user:
                user.timezone = timezone_str
                success = await self.storage.save_user(user)
                
                if success:
                    # Reschedule user messages with new timezone
                    await self.scheduler.schedule_user_immediately(chat_id)
                    
                    # Clean up state and show menu
                    del self.user_states[chat_id]
                    
                    text = f"{self._get_text('timezone_saved', language)}\n\n{self._get_text('menu', language)}"
                    keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
                    
                    if message_id:
                        await self._edit_bot_message_text_safe(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=text,
                            reply_markup=keyboard,
                            parse_mode='Markdown'
                        )
                    else:
                        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
                else:
                    error_text = self._get_text("setup_error", language)
                    if message_id:
                        await self._edit_bot_message_text_safe(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=error_text,
                            parse_mode='Markdown'
                        )
                    else:
                        await update.message.reply_text(error_text)
            else:
                error_text = self._get_text("not_subscribed_test", language)
                if message_id:
                    await self._edit_bot_message_text_safe(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=error_text,
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(error_text)
                
        except Exception as e:
            logger.error(f"Error changing timezone for user {chat_id}: {e}")
            error_text = self._get_text("error", language)
            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_text,
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(error_text)
    
    async def _handle_change_time_input(self, update: Update, time_str: str, language: str) -> None:
        """Handle time change input."""
        chat_id = update.effective_chat.id
        user_state = self.user_states[chat_id]
        message_id = user_state.get("settings_message_id")
        
        if not is_valid_time_format(time_str):
            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=self._get_text("invalid_time", language),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(self._get_text("invalid_time", language))
            return
        
        try:
            user = await self.storage.get_user(chat_id)
            if user:
                user.time_for_send = time_str
                success = await self.storage.save_user(user)
                
                if success:
                    # Reschedule user messages with new time
                    await self.scheduler.schedule_user_immediately(chat_id)
                    
                    # Clean up state and show menu
                    del self.user_states[chat_id]
                    
                    text = f"{self._get_text('time_saved', language)}\n\n{self._get_text('menu', language)}"
                    keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
                    
                    if message_id:
                        await self._edit_bot_message_text_safe(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=text,
                            reply_markup=keyboard,
                            parse_mode='Markdown'
                        )
                    else:
                        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
                else:
                    error_text = self._get_text("setup_error", language)
                    if message_id:
                        await self._edit_bot_message_text_safe(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=error_text,
                            parse_mode='Markdown'
                        )
                    else:
                        await update.message.reply_text(error_text)
            else:
                error_text = self._get_text("not_subscribed_test", language)
                if message_id:
                    await self._edit_bot_message_text_safe(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=error_text,
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(error_text)
                
        except Exception as e:
            logger.error(f"Error changing time for user {chat_id}: {e}")
            error_text = self._get_text("error", language)
            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_text,
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(error_text)

    async def _handle_change_meridian_time_input(self, update: Update, time_str: str, language: str) -> None:
        """Handle meridian reminder time change input."""
        chat_id = update.effective_chat.id
        user_state = self.user_states.get(chat_id, {})
        message_id = user_state.get("settings_message_id")

        if not is_valid_time_format(time_str):
            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=self._get_text("invalid_time", language),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(self._get_text("invalid_time", language))
            return

        try:
            user = await self.storage.get_user(chat_id)
            if not user:
                await update.message.reply_text(self._get_text("not_subscribed_test", language))
                return

            user.meridian_time_for_send = time_str
            await self.storage.save_user(user)
            await self.scheduler.schedule_user_immediately(chat_id)

            if chat_id in self.user_states:
                del self.user_states[chat_id]

            text = f"{self._get_text('meridian_time_saved', language)}\n\n{self._get_text('menu', language)}"
            keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error changing meridian time for user {chat_id}: {e}")
            await update.message.reply_text(self._get_text("error", language))
    

    
    async def _delete_message_safe(self, chat_id: int, message_id: int) -> bool:
        """Safely delete a message without raising errors."""
        try:
            await self.application.bot.delete_message(chat_id=chat_id, message_id=message_id)
            return True
        except Exception as e:
            logger.debug(f"Could not delete message {message_id} in chat {chat_id}: {e}")
            return False

    async def _edit_bot_message_text_safe(self, **kwargs):
        """Edit a bot message and ignore Telegram's no-op edit error."""
        try:
            return await self.application.bot.edit_message_text(**kwargs)
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                logger.debug("Ignored Telegram no-op edit for bot message")
                return None
            raise

    async def _edit_message_text_safe(self, query, text: str, **kwargs):
        """Edit a callback message and ignore Telegram's no-op edit error."""
        try:
            return await query.edit_message_text(text, **kwargs)
        except BadRequest as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                logger.debug("Ignored Telegram no-op edit for callback message")
                return query.message
            if "there is no text in the message to edit" in error_text and query.message:
                logger.debug("Replacing callback media message with text message")
                chat_id = query.message.chat.id
                try:
                    await query.delete_message()
                except Exception as delete_error:
                    logger.debug(f"Could not delete media message before text replacement: {delete_error}")
                return await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    **kwargs
                )
            raise
    
    async def _delete_user_message_delayed(self, chat_id: int, message_id: int, delay: float = 0.5) -> None:
        """Delete user message with a small delay for better UX."""
        try:
            await asyncio.sleep(delay)
            await self._delete_message_safe(chat_id, message_id)
        except Exception as e:
            logger.debug(f"Error deleting user message {message_id} in chat {chat_id}: {e}")
    
    async def _send_and_store_message(self, chat_id: int, text: str, message_type: str = "general", **kwargs) -> Optional[int]:
        """Send message and store its ID for dialog cleanup."""
        try:
            message = await self.application.bot.send_message(chat_id=chat_id, text=text, **kwargs)
            await self.storage.add_bot_message(chat_id, message.message_id, message_type)
            return message.message_id
        except Exception as e:
            logger.error(f"Error sending message to {chat_id}: {e}")
            return None
    
    async def _reply_and_store_message(self, update: Update, text: str, message_type: str = "general", **kwargs) -> Optional[int]:
        """Reply to message and store its ID for dialog cleanup."""
        try:
            message = await update.message.reply_text(text, **kwargs)
            await self.storage.add_bot_message(update.effective_chat.id, message.message_id, message_type)
            return message.message_id
        except Exception as e:
            logger.error(f"Error replying to message in {update.effective_chat.id}: {e}")
            return None
    
    async def _clear_user_dialog(self, chat_id: int) -> None:
        """Clear user dialog by deleting all stored bot messages."""
        try:
            bot_messages = await self.storage.get_user_bot_messages(chat_id)
            
            deleted_count = 0
            for bot_message in bot_messages:
                success = await self._delete_message_safe(chat_id, bot_message.message_id)
                if success:
                    deleted_count += 1
            
            # Clear stored messages after deletion attempt
            await self.storage.clear_user_bot_messages(chat_id)
            
            logger.info(f"Cleared dialog for user {chat_id}: deleted {deleted_count}/{len(bot_messages)} messages")
            
        except Exception as e:
            logger.error(f"Error clearing dialog for user {chat_id}: {e}")
    
    async def _clear_entire_dialog(self, chat_id: int) -> None:
        """Clear entire dialog by deleting all stored bot messages and attempting to clear more."""
        try:
            # Clear all stored bot messages
            await self._clear_user_dialog(chat_id)
            
            # Try to clear user state and any temporary messages
            if chat_id in self.user_states:
                del self.user_states[chat_id]
            
            logger.info(f"Cleared entire dialog for user {chat_id}")
                
        except Exception as e:
            logger.error(f"Error in clearing entire dialog for user {chat_id}: {e}")
    
    async def _handle_feedback_input(self, update: Update, feedback_text: str, language: str) -> None:
        """Handle feedback input from user."""
        chat_id = update.effective_chat.id
        
        try:
            # Validate feedback length
            if len(feedback_text) > 1000:
                text = self._get_text("feedback_too_long", language)
                keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
                await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
                del self.user_states[chat_id]
                return
            
            # Check rate limiting
            can_send = await self.storage.can_send_feedback(chat_id, rate_limit_minutes=10)
            if not can_send:
                text = self._get_text("feedback_rate_limit", language)
                keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
                await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
                del self.user_states[chat_id]
                return
            
            # Get user info
            user = await self.storage.get_user(chat_id)
            username = update.message.from_user.username or f"user_{chat_id}"
            
            # Create feedback object
            from datetime import datetime, timezone
            import uuid
            
            feedback = Feedback(
                id=str(uuid.uuid4())[:8],
                chat_id=chat_id,
                username=username,
                language=language,
                message=feedback_text,
                timestamp=datetime.now(timezone.utc).isoformat(),
                message_length=len(feedback_text)
            )
            
            # Save feedback
            success = await self.storage.add_feedback(feedback)
            
            # Clean up state
            del self.user_states[chat_id]
            
            if success:
                text = f"{self._get_text('feedback_sent', language)}\n\n{self._get_text('menu', language)}"
                
                # Notify admins about new feedback
                admin_text = f"💌 **New Feedback Received**\n\n" \
                           f"👤 User: {chat_id} (@{username})\n" \
                           f"🌐 Language: {language}\n" \
                           f"📏 Length: {len(feedback_text)} chars\n" \
                           f"💬 Message: {feedback_text}"
                
                for admin_id in self.admin_ids:
                    try:
                        await self.application.bot.send_message(admin_id, admin_text, parse_mode='Markdown')
                    except Exception:
                        pass  # Ignore errors for admin notifications
            else:
                text = f"{self._get_text('feedback_error', language)}\n\n{self._get_text('menu', language)}"
            
            keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
            message = await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
            
            # Delete the previous bot message (feedback prompt) for clean dialog
            if update.message.reply_to_message:
                await self._delete_message_safe(chat_id, update.message.reply_to_message.message_id)
                
        except Exception as e:
            logger.error(f"Error handling feedback from user {chat_id}: {e}")
            del self.user_states[chat_id]
            text = f"{self._get_text('error', language)}\n\n{self._get_text('menu', language)}"
            keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')

    async def _handle_stop_feedback_input(self, update: Update, feedback_text: str, language: str) -> None:
        """Handle optional feedback after the user stops the bot."""
        chat_id = update.effective_chat.id

        try:
            if len(feedback_text) > 1000:
                await update.message.reply_text(self._get_text("feedback_too_long", language))
                return

            username = update.message.from_user.username or f"user_{chat_id}"

            from datetime import datetime, timezone
            import uuid

            feedback = Feedback(
                id=str(uuid.uuid4())[:8],
                chat_id=chat_id,
                username=username,
                language=language,
                message=f"[stop_reason] {feedback_text}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                message_length=len(feedback_text)
            )

            success = await self.storage.add_feedback(feedback)

            if chat_id in self.user_states:
                del self.user_states[chat_id]

            if success:
                await update.message.reply_text(self._get_text("stop_feedback_thanks", language), parse_mode='Markdown')

                admin_text = (
                    "🛑 Stop feedback received\n\n"
                    f"User: {chat_id} (@{username})\n"
                    f"Language: {language}\n"
                    f"Length: {len(feedback_text)} chars\n"
                    f"Message: {feedback_text}"
                )

                for admin_id in self.admin_ids:
                    try:
                        await self.application.bot.send_message(admin_id, admin_text)
                    except Exception:
                        pass
            else:
                await update.message.reply_text(self._get_text("feedback_error", language))

        except Exception as e:
            logger.error(f"Error handling stop feedback from user {chat_id}: {e}")
            if chat_id in self.user_states:
                del self.user_states[chat_id]
            await update.message.reply_text(self._get_text("error", language))

    async def _show_principle_detail(self, query, principle: Dict[str, Any], language: str) -> None:
        """Show a selected Yama/Niyama principle in the current menu message."""
        principle_id = int(principle.get("id", 0))
        chat_id = query.message.chat.id
        keyboard = self._create_principles_menu_keyboard(language)
        text = self._format_principle_detail(principle, language)
        image_path = get_principle_image_path(principle_id)

        if image_path:
            caption = self._format_principle_detail(principle, language, max_length=1024)
            if not query.message.photo:
                try:
                    await query.delete_message()
                except Exception:
                    pass
                with open(image_path, "rb") as photo:
                    sent_message = await self.application.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                await self.storage.add_bot_message(chat_id, sent_message.message_id, "principle")
                return

            try:
                with open(image_path, "rb") as photo:
                    await query.edit_message_media(
                        media=InputMediaPhoto(
                            media=photo,
                            caption=caption,
                            parse_mode='HTML'
                        ),
                        reply_markup=keyboard
                    )
                await self.storage.add_bot_message(chat_id, query.message.message_id, "principle")
                return
            except BadRequest as e:
                if "message is not modified" in str(e).lower():
                    logger.debug("Ignored Telegram no-op media edit for principle detail")
                    return
                if "no media" in str(e).lower() or "there is no media" in str(e).lower():
                    try:
                        await query.delete_message()
                    except Exception:
                        pass
                    with open(image_path, "rb") as photo:
                        sent_message = await self.application.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo,
                            caption=caption,
                            reply_markup=keyboard,
                            parse_mode='HTML'
                        )
                    await self.storage.add_bot_message(chat_id, sent_message.message_id, "principle")
                    return
                logger.warning(f"Could not edit principle message as media for {chat_id}: {e}")
            except Exception as e:
                logger.warning(f"Could not show principle image {image_path} to {chat_id}: {e}")

        try:
            await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')
            await self.storage.add_bot_message(chat_id, query.message.message_id, "principle")
        except BadRequest as e:
            if "there is no text in the message to edit" in str(e).lower() and query.message.photo:
                await query.delete_message()
                sent_message = await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
                await self.storage.add_bot_message(chat_id, sent_message.message_id, "principle")
            else:
                raise

    def _fit_html_caption(self, text: str, max_length: int = 1024) -> str:
        """Fit simple HTML text into Telegram caption limit without cutting tags."""
        if len(text) <= max_length:
            return text

        parts = text.split("\n\n")
        kept = []
        for part in parts:
            candidate = "\n\n".join([*kept, part]) if kept else part
            if len(candidate) <= max_length - 3:
                kept.append(part)
            else:
                break

        if kept:
            return "\n\n".join(kept) + "..."

        plain = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
        return escape(plain[:max_length - 3].rstrip()) + "..."

    async def _show_meridian_card(
        self,
        query,
        text: str,
        keyboard: InlineKeyboardMarkup,
        language: str,
        meridian_id: Optional[str] = None,
        point_code: Optional[str] = None
    ) -> None:
        """Show meridian content with an image when available."""
        chat_id = query.message.chat.id
        image_path = get_meridian_image_path(meridian_id, point_code) if meridian_id else None

        if image_path:
            caption = self._fit_html_caption(text)
            is_gif = image_path.lower().endswith(".gif")
            has_media = bool(query.message.photo or query.message.animation)
            if not has_media:
                try:
                    await query.delete_message()
                except Exception:
                    pass
                with open(image_path, "rb") as media_file:
                    if is_gif:
                        sent_message = await self.application.bot.send_animation(
                            chat_id=chat_id,
                            animation=media_file,
                            caption=caption,
                            reply_markup=keyboard,
                            parse_mode='HTML'
                        )
                    else:
                        sent_message = await self.application.bot.send_photo(
                            chat_id=chat_id,
                            photo=media_file,
                            caption=caption,
                            reply_markup=keyboard,
                            parse_mode='HTML'
                        )
                await self.storage.add_bot_message(chat_id, sent_message.message_id, "meridian")
                return

            try:
                with open(image_path, "rb") as media_file:
                    media = (
                        InputMediaAnimation(media=media_file, caption=caption, parse_mode='HTML')
                        if is_gif
                        else InputMediaPhoto(media=media_file, caption=caption, parse_mode='HTML')
                    )
                    await query.edit_message_media(
                        media=media,
                        reply_markup=keyboard
                    )
                await self.storage.add_bot_message(chat_id, query.message.message_id, "meridian")
                return
            except BadRequest as e:
                if "message is not modified" in str(e).lower():
                    return
                logger.warning(f"Could not edit meridian message as media for {chat_id}: {e}")
            except Exception as e:
                logger.warning(f"Could not show meridian image {image_path} to {chat_id}: {e}")

        if query.message.photo or query.message.animation:
            try:
                await query.delete_message()
            except Exception:
                pass
            sent_message = await self.application.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
            await self.storage.add_bot_message(chat_id, sent_message.message_id, "meridian")
            return

        await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')
    
    async def _handle_feedback_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /feedback_stats command (admin only)."""
        chat_id = update.effective_chat.id
        
        if chat_id not in self.admin_ids:
            return
        
        # Check if update has message
        if not update.message:
            logger.warning("feedback_stats called without message")
            return
        
        try:
            stats = await self.storage.get_feedback_stats()
            
            # Format language statistics
            lang_stats = []
            for lang, count in stats["by_language"].items():
                lang_stats.append(f"  • {lang}: {count}")
            
            lang_text = "\n".join(lang_stats) if lang_stats else "  No data"
            
            text = self._get_admin_text(
                "feedback_stats",
                total_feedback=stats["total_feedback"],
                average_length=stats["average_length"],
                file_size_mb=stats["file_size_mb"],
                by_language=lang_text
            )
            
            # Send without Markdown to avoid parsing errors
            await update.message.reply_text(text)
            
        except Exception as e:
            logger.error(f"Error in feedback_stats handler: {e}")
            try:
                await update.message.reply_text("Error getting feedback statistics.")
            except:
                logger.error(f"Could not send error message to {chat_id}")
    
    async def _handle_feedback_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /feedback_list command (admin only)."""
        chat_id = update.effective_chat.id
        
        if chat_id not in self.admin_ids:
            return
        
        # Check if update has message
        if not update.message:
            logger.warning("feedback_list called without message")
            return
        
        try:
            # Parse limit argument
            limit = 10
            if context.args:
                try:
                    limit = int(context.args[0])
                    limit = max(1, min(limit, 50))  # Clamp between 1 and 50
                except ValueError:
                    await update.message.reply_text(self._get_admin_text("feedback_list_usage"))
                    return
            
            # Get feedback
            feedback_list = await self.storage.get_all_feedback(limit=limit)
            
            if not feedback_list:
                await update.message.reply_text(self._get_admin_text("no_feedback"))
                return
            
            # Format feedback list
            message_parts = [self._get_admin_text("feedback_list_header", count=len(feedback_list))]
            
            for feedback in feedback_list:
                # Truncate long messages and escape special characters
                message_text = feedback.message
                if len(message_text) > 100:
                    message_text = message_text[:97] + "..."
                
                # No need to escape since we're not using Markdown
                safe_message = message_text
                safe_username = feedback.username
                
                item_text = self._get_admin_text(
                    "feedback_item",
                    id=feedback.id,
                    timestamp=feedback.timestamp[:16],  # YYYY-MM-DD HH:MM
                    chat_id=feedback.chat_id,
                    username=safe_username,
                    language=feedback.language,
                    length=feedback.message_length,
                    message=safe_message
                )
                message_parts.append(item_text)
            
            full_message = "".join(message_parts)
            
            # Split message if too long and send without Markdown to avoid parsing errors
            if len(full_message) > 4000:
                for i in range(0, len(full_message), 4000):
                    chunk = full_message[i:i+4000]
                    await update.message.reply_text(chunk)
            else:
                await update.message.reply_text(full_message)
            
        except Exception as e:
            logger.error(f"Error in feedback_list handler: {e}")
            try:
                await update.message.reply_text("Error getting feedback list.")
            except:
                logger.error(f"Could not send error message to {chat_id}")
    

    
    async def _handle_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /admin command (admin only)."""
        chat_id = update.effective_chat.id
        
        if chat_id not in self.admin_ids:
            return
        
        # Check if update has message
        if not update.message:
            logger.warning("admin called without message")
            return
        
        try:
            text = self._get_admin_text("admin_help")
            # Send without Markdown to avoid parsing errors
            await update.message.reply_text(text)
            
        except Exception as e:
            logger.error(f"Error in admin handler: {e}")
            try:
                await update.message.reply_text("Error showing admin help.")
            except:
                logger.error(f"Could not send error message to {chat_id}")
