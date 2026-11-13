"""Command handlers for yoga bot."""

import asyncio
import logging
import re
from html import escape
from pathlib import Path
from types import SimpleNamespace
from typing import List, Dict, Any, Optional
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaAnimation, MenuButtonWebApp, WebAppInfo
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ApplicationHandlerStop
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
    fit_html_caption,
    get_principle_image_path,
    get_meridian_image_path,
    localized_point_name,
    MERIDIAN_METADATA
)
from .webapp import build_map_button, build_map_url, normalize_webapp_language
from . import feel as diary


logger = logging.getLogger(__name__)

MERIDIAN_POINTS_PAGE_SIZE = 7
MERIDIAN_SELECTION_PAGE_SIZE = 7
GOVERNING_VESSEL_SECRET_TASK_ID = "governing_vessel_forest_breathing"
MICROCOSMIC_ORBIT_SECRET_TASK_ID = "microcosmic_orbit_nature_breathing"
CUN_MEASUREMENT_IMAGE_PATH = Path(__file__).resolve().parent.parent / "images" / "meridians" / "cun_measurement.png"
MERIDIAN_VIDEO_PATHS = {
    "bladder": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "bladder.mp4",
    "conception_vessel": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "conception_vessel.mp4",
    "gallbladder": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "gallbladder.mp4",
    "governing_vessel": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "governing_vessel.mp4",
    "heart": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "heart.mp4",
    "kidney": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "kidney.mp4",
    "large_intestine": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "large_intestine.mp4",
    "liver": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "liver.mp4",
    "lung": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "lung.mp4",
    "pericardium": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "pericardium.mp4",
    "small_intestine": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "small_intestine.mp4",
    "spleen": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "spleen.mp4",
    "stomach": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "stomach.mp4",
    "triple_burner": Path(__file__).resolve().parent.parent / "videos" / "meridians" / "triple_burner.mp4",
}
CUN_MEASUREMENT_IMAGE_PATHS = {
    "en": Path(__file__).resolve().parent.parent / "images" / "meridians" / "cun_measurement_en.png",
    "ru": Path(__file__).resolve().parent.parent / "images" / "meridians" / "cun_measurement_ru.png",
    "uz": Path(__file__).resolve().parent.parent / "images" / "meridians" / "cun_measurement_uz.png",
    "kz": Path(__file__).resolve().parent.parent / "images" / "meridians" / "cun_measurement_kz.png",
}
MERIDIAN_MATERIALS_IMAGE_DIR = Path(__file__).resolve().parent.parent / "images" / "meridians" / "materials"
SHU_RIVER_IMAGE_PATHS = {
    "en": MERIDIAN_MATERIALS_IMAGE_DIR / "shu_river_en.png",
    "ru": MERIDIAN_MATERIALS_IMAGE_DIR / "shu_river_ru.png",
    "uz": MERIDIAN_MATERIALS_IMAGE_DIR / "shu_river_uz.png",
    "kz": MERIDIAN_MATERIALS_IMAGE_DIR / "shu_river_kz.png",
}
SHU_CHANNEL_IMAGE_PATHS = {
    "en": MERIDIAN_MATERIALS_IMAGE_DIR / "shu_channel_en.png",
    "ru": MERIDIAN_MATERIALS_IMAGE_DIR / "shu_channel_ru.png",
    "uz": MERIDIAN_MATERIALS_IMAGE_DIR / "shu_channel_uz.png",
    "kz": MERIDIAN_MATERIALS_IMAGE_DIR / "shu_channel_kz.png",
}


def _localized_material_image(paths: Dict[str, Path], language: str) -> Path:
    path = paths.get(language) or paths.get("en")
    return path if path and path.exists() else paths["en"]


def get_cun_measurement_image_path(language: str) -> Path:
    """Return localized cun measurement image with fallback to the generic asset."""
    localized_path = CUN_MEASUREMENT_IMAGE_PATHS.get(language)
    if localized_path and localized_path.exists():
        return localized_path
    return CUN_MEASUREMENT_IMAGE_PATH


def get_meridian_video_path(meridian_id: Optional[str]) -> Optional[Path]:
    """Return a meridian video path when the video is available."""
    if not meridian_id:
        return None
    video_path = MERIDIAN_VIDEO_PATHS.get(meridian_id)
    if video_path and video_path.exists():
        return video_path
    default_path = Path(__file__).resolve().parent.parent / "videos" / "meridians" / f"{meridian_id}.mp4"
    if default_path.exists():
        return default_path
    logger.warning("Meridian video is missing for id=%s. Expected path: %s", meridian_id, default_path)
    return None


# Multilingual texts
TEXTS = {'en': {'welcome': '🕊️ <b>Welcome to Journey of Ascension!</b>\n'
                   '\n'
                   'Yama and Niyama are the ethical foundation of inner practice. Meridians are the next '
                   'step: learning to feel attention, body, and energy through direct observation.\n'
                   '\n'
                   "Let's start with choosing your preferred language:",
        'language_chosen': '✅ Language set to English.',
        'timezone_step': '📍 Time zone\n\nChoose your time zone so reminders arrive at the right local time.',
        'timezone_custom': '⌨️ Enter manually',
        'timezone_saved': '✅ Time zone saved.',
        'time_step': '🧘🏻 <b>Yama/Niyama Reminder Time</b>\n'
                     '\n'
                     'Choose when the bot should send the daily principle. A steady time helps the practice '
                     'become part of ordinary life.\n'
                     '\n'
                     'Format: HH:MM, for example 08:00 or 20:30.',
        'time_saved': '✅ Reminder time saved.',
        'skip_days_step': '📅 <b>Quiet Days</b>\n'
                          '\n'
                          'Choose weekdays when the bot should stay silent and <b>not</b> send daily practice reminders.\n'
                          '\n'
                          'If you want reminders every day, choose <b>No quiet days</b>. If you want every day except Sunday, select only Sunday.',
        'setup_complete': '🎉 <b>The first step is set.</b>\n'
                          '\n'
                          '📋 <b>Your rhythm:</b>\n'
                          '🕐 Time: {time}\n'
                          '🌍 Time Zone: {timezone}\n'
                          '📅 Quiet Days: {skip_days}\n'
                          '\n'
                          'Use /menu when you want to open the lists, adjust the rhythm, or continue the next small step.',
        'already_subscribed': '🕊️ Journey of Ascension is already open here.\n'
                              '\n'
                              'Use /menu to choose practices or /settings to tune your practice rhythm.',
        'unsubscribed': 'The practice rhythm is paused. Daily reminders will stay silent for now.\n'
                        '\n'
                        'Use /start if you want to return.',
        'not_subscribed': 'The practice is not started in this chat yet. Use /start when you are ready to begin.',
        'current_settings': '⚙️ <b>Current practice rhythm</b>',
        'not_subscribed_test': "The practice rhythm is not set yet. Use /start to begin.",
        'test_failed': 'I could not send the reminder check right now. Please try again a little later.',
        'invalid_timezone': '❌ I could not recognize this time zone. Try a format like Europe/Moscow, '
                            'Asia/Tashkent, Asia/Almaty, or UTC.',
        'invalid_time': '❌ I could not recognize this time. Use HH:MM, for example 08:00 or 20:30.',
        'invalid_skip_days': '❌ I could not recognize these days. Use numbers from 0 to 6 separated by '
                             'commas.',
        'setup_error': '❌ I could not save this yet. Please try once more; your practice rhythm is worth setting carefully.',
        'error': 'Something interrupted the flow. Please try once more, or return to /menu.',
        'choose_language': 'Choose the language you want to use:',
        'english': '🇺🇸 English',
        'russian': '🇷🇺 Русский',
        'menu': '📋 <b>Journey of Ascension</b>',
        'menu_settings': '⚙️ Practice rhythm',
        'menu_test': '🧪 Check reminder',
        'menu_announce_update': '📢 Send update',
        'sending_test': '🧪 Sending a reminder check...',
        'menu_about': 'ℹ️ About the bot',
        'menu_feedback': '💌 Feedback and ideas',
        'menu_stop': '⏸ Pause practice',
        'settings_menu': '⚙️ <b>Practice rhythm</b>\n'
                         '\n'
                         'Here you can tune the rhythm of practice: what the bot reminds you about, when '
                         'messages arrive, and which days stay quiet.',
        'change_language': '🌐 Language',
        'change_time': '🧘🏻 Yama/Niyama Time',
        'change_timezone': '🌍 Time Zone',
        'change_skip_days': '📅 Quiet Days',
        'back_to_menu': '🔙 Back to menu',
        'skip_days_improved': '📅 <b>Quiet Days</b>\n'
                              '\n'
                              'Choose weekdays when the bot should stay silent and <b>not</b> send daily practice reminders.\n'
                              '\n'
                              'If you want reminders every day, choose <b>No quiet days</b>. If you want every day except Sunday, select only Sunday.',
        'no_skip_days': '✅ No quiet days selected — reminders can arrive every day',
        'about_text': '🕊️ <b>Journey of Ascension</b>\n'
                      '\n'
                      'This bot helps you return to practice in ordinary life: one clear focus, every day.\n'
                      '\n'
                      'Every day it helps you return to one concrete focus: a Yama/Niyama principle or a '
                      'meridian point. The aim is simple: notice where energy is spent unconsciously, stop '
                      'wasting it, and learn to direct attention with more care.\n'
                      '\n'
                      '<b>Yama/Niyama</b> works with behaviour, speech, thoughts, discipline, and honesty '
                      'with yourself.\n'
                      '\n'
                      '<b>Meridians</b> work with the body: channels, points, Qi flow, closed areas, breath, '
                      'touch, and attention.\n'
                      '\n'
                      'Small repetitions matter. They turn an idea into something you can actually live.',
        'feedback_prompt': '💌 <b>Feedback and ideas</b>\n'
                           '\n'
                           'Your experience matters. Write what felt useful, what felt unclear, or what '
                           'would make the practice more comfortable.',
        'feedback_sent': '✅ Thank you. Your feedback has been sent.',
        'feedback_too_long': '❌ The message is too long. Please keep it under 1000 characters.',
        'feedback_rate_limit': '⏰ Please wait a little before sending another feedback message.',
        'feedback_error': '❌ I could not save your feedback. Please try again later.',
        'onboarding_intro': '<b>Journey of Ascension</b>\n'
                            '\n'
                            'Practice begins with noticing where energy goes. When it is scattered, '
                            'attention gets noisy; when it is gathered, action becomes quieter and cleaner.\n'
                            '\n'
                            '<b>Yama and Niyama</b> are the foundation: they reduce the places where energy '
                            'leaks through speech, thoughts, habits, and reactions. <b>Ahimsa</b> begins '
                            'with not spending force on harm.\n'
                            '\n'
                            '<b>Meridians</b> bring the practice into the body. You learn to follow channels, '
                            'points, and quiet areas through touch, breath, and patient attention.\n'
                            '\n'
                            'What would you like to study?',
        'initial_mode_question': 'What would you like to study?',
        'timezone_step_principles': '📍 <b>Step 1/3: Time Zone</b>\n'
                                    '\n'
                                    'Choose your time zone so the bot can send <b>Yama/Niyama</b> reminders '
                                    'at the correct local time for you.',
        'timezone_step_meridians': '📍 <b>Step 1/3: Time Zone</b>\n'
                                   '\n'
                                   'Choose your time zone so the bot can send <b>meridian</b> study '
                                   'reminders at the correct local time for you.',
        'timezone_step_both': '📍 <b>Step 1/3: Time Zone</b>\n'
                              '\n'
                              'Choose your time zone so the bot can send <b>Yama/Niyama</b> and '
                              '<b>meridian</b> reminders at the correct local time for you.',
        'time_step_principles': '⏰ <b>Step 2/3: Reminder Time</b>\n'
                                '\n'
                                'Choose the time when the bot should send your daily <b>Yama/Niyama</b> '
                                'principle.\n'
                                '\n'
                                'Format: HH:MM, for example 08:00 or 20:30.',
        'time_step_meridians': '⏰ <b>Step 2/3: Reminder Time</b>\n'
                               '\n'
                               'Choose the time when the bot should send your daily <b>meridian</b> focus.\n'
                               '\n'
                               'Format: HH:MM, for example 08:00 or 20:30.',
        'time_step_both': '⏰ <b>Step 2/3: Reminder Time</b>\n'
                          '\n'
                          'Choose the time when the bot should send your daily <b>Yama/Niyama</b> principle '
                          'and <b>meridian</b> focus.\n'
                          '\n'
                          'Format: HH:MM, for example 08:00 or 20:30.',
        'continue_setup': 'Continue',
        'menu_principles': '🧘🏻✨ Yama/Niyama',
        'menu_meridians': '☯️ Meridians',
        'menu_modes': '🧭 My Path',
        'principles_menu': '🕊️ <b>Yama/Niyama</b>\n'
                           '\n'
                           'These are the first two limbs of classical yoga and the ethical foundation of '
                           'practice.\n'
                           '\n'
                           '<b>Yama</b> protects energy in relation to the world: non-harm, truthfulness, '
                           'non-stealing, moderation, and non-possessiveness.\n'
                           '\n'
                           '<b>Niyama</b> gathers energy inside: purity, contentment, discipline, '
                           'self-study, and surrender of the fruits of action.\n'
                           '\n'
                           'The daily principle is an accent for observation, not a replacement for the '
                           'others. We keep integrating all principles into life; each day one becomes '
                           'especially visible.\n'
                           '\n'
                           'Open one principle for today or view the full list.',
        'principles_random': 'Random principle',
        'principles_all': 'All principles',
        'principles_back': '🔙 Back to Yama/Niyama',
        'principles_empty': 'The principles did not open right now. Please return to Yama/Niyama or try again from /menu.',
        'change_modes': '🧭 My Path',
        'change_meridian_time': '☯️ Meridian Time',
        'mode_menu': '🧭 <b>My Path</b>\n'
                     '\n'
                     'Choose which practice you want to return to each day.\n'
                     '\n'
                     '<b>Yama/Niyama</b> is the foundation: less inner noise, fewer energy leaks, more '
                     'honesty in action.\n'
                     '\n'
                     '<b>Meridians</b> are the body layer: points, channels, Qi flow, and the skill of '
                     'patiently including places that are hard to feel at first.\n'
                     '\n'
                     'You can begin with one direction or keep both active together.',
        'mode_principles_only': 'Yama/Niyama foundation',
        'mode_meridians_only': 'Meridian study',
        'mode_both': 'Both directions',
        'mode_saved': '✅ <b>Your path has been updated.</b>',
        'meridian_time_step': '☯️ <b>Meridian Reminder Time</b>\n'
                              '\n'
                              'Enter time in HH:MM format, for example 20:00.',
        'meridian_time_saved': '✅ Meridian reminder time saved.',
        'meridian_mode_menu': '☯️ <b>Choose your meridian study path</b>\n'
                              '\n'
                              '<b>Bot route</b> is good when you are new: one channel, one point, one calm '
                              'step at a time. After completing a meridian, the next one opens naturally.\n'
                              '\n'
                              '<b>Free choice</b> is good when a specific meridian is calling your attention '
                              'or you already know what you want to study.\n'
                              '\n'
                              'You can change this later. Your progress and reminders stay saved.',
        'meridian_guided_path': '🧭 Bot route',
        'meridian_free_choice': '👐 Free choice',
        'meridian_change_path': '🧭 Start / choose path',
        'meridian_guided_saved': '✅ <b>Bot route selected.</b>\n'
                                 '\n'
                                 'We will move gently: one meridian, one point, one stable sensation at a time.',
        'meridian_free_saved': '✅ <b>Free choice selected.</b>\n\nChoose the meridian you want to explore now.',
        'meridian_measurements': '📏 Measure cun',
        'meridian_point_help': '🖐 How to find a point',
        'meridian_back': '🔙 Back to meridians',
        'page_indicator_hint': 'This is the page number. Use Previous or Next to move.',
        'meridian_measurements_text': '📏 <b>Measurement System in TCM</b>\n'
                                      '\n'
                                      '<b>Why this matters:</b> point descriptions often say “1 cun”, “1.5 '
                                      'cun”, “3 cun”, and so on. This guide helps you translate those '
                                      'instructions into your own body.\n'
                                      '\n'
                                      'Acupuncture point locations are often described in <b>cun</b>. A cun '
                                      'is not a fixed centimeter value: it is a body-relative unit measured '
                                      'on the person being studied.\n'
                                      '\n'
                                      '<b>0.5 cun:</b> half of your personal 1 cun. Use it for very small '
                                      'distances and refine by touch.\n'
                                      '\n'
                                      '<b>1 cun:</b> the width of the thumb at the interphalangeal joint.\n'
                                      '\n'
                                      '<b>1.5 cun:</b> the width of the index and middle fingers together.\n'
                                      '\n'
                                      '<b>2 cun:</b> the width of three fingers together: index, middle, and '
                                      'ring finger.\n'
                                      '\n'
                                      '<b>3 cun:</b> the width of four fingers together, from index to '
                                      'little finger.\n'
                                      '\n'
                                      '<b>5 cun:</b> measure 3 cun and add about 2 cun, or divide the '
                                      'anatomical segment into equal parts if the source gives a '
                                      'proportional distance.\n'
                                      '\n'
                                      '<b>Important:</b> cun is always measured on the body of the person '
                                      'you are working with. For example, 1 cun on your body and 1 cun on '
                                      "another person's body can be different in centimeters.\n"
                                      '\n'
                                      'Use cun as an orientation tool, then refine the point by touch: local '
                                      'sensitivity, a small hollow, warmth, pressure, or a clear response to '
                                      'attention.',
        'meridian_point_help_text': '🖐 <b>How to find a point</b>\n'
                                    '\n'
                                    'Start with the picture and cun measurements to find the general area. '
                                    'Then slow down and let the body clarify the exact point.\n'
                                    '\n'
                                    '<b>1.</b> Touch the area softly and look for a small hollow, '
                                    'sensitivity, warmth, pressure, or a place where attention catches more '
                                    'easily.\n'
                                    '\n'
                                    '<b>2.</b> If the point feels silent, treat it as not yet open: stay '
                                    'longer, gently massage it (except points marked ⚠), and breathe through it with attention.\n'
                                    '\n'
                                    '<b>3.</b> Do not force a result. A quiet, steady sensation is enough.\n'
                                    '\n'
                                    'When moving onward, keep the previous points in awareness and add the '
                                    'new one to the same line.',
        'meridians_menu': '☯️ <b>Meridians</b>\n'
                          '\n'
                          '<b>Why study meridians?</b>\n'
                          '\n'
                          'In the Chinese tradition, meridians describe pathways of Qi. In practice this '
                          'becomes very concrete: you notice where the body responds to attention, where '
                          'there is tension, and where sensation is still faint.\n'
                          '\n'
                          '<b>How it helps:</b> attention, breath, and gentle touch gradually bring '
                          'sensitivity back into a point. The area may become warmer, clearer, and easier '
                          'to connect with the whole channel.\n'
                          '\n'
                          "<b>How to start:</b> choose the bot route if you want a calm sequence, or free "
                          'choice if you already know which meridian you want to study.\n'
                          '\n'
                          'Before working with points, open the <b>cun</b> guide. It helps you find the '
                          'right area on your own body; the point itself is refined by fingers, breath, '
                          'and attention.\n'
                          '\n'
                          'This is a self-observation practice. It does not replace a doctor, diagnosis, '
                          'or treatment.',
        'choose_meridian': '☯️ <b>Choose a meridian:</b>',
        'current_meridian': '▶️ Continue practice',
        'meridian_start_points': 'Start with point 1',
        'all_points': 'All points',
        'next_point': 'Next point',
        'prev_point': 'Previous point',
        'complete_meridian': 'Complete meridian',
        'select_meridian': 'Choose meridian',
        'no_points': 'The points did not open right now. Return to the meridian list and try again from there.',
        'meridian_completed': (
            '✅ <b>Meridian completed</b>\n\n'
            'Before moving on, pass through the whole channel once more with attention: from the first point to the last. '
            'Notice where the line feels warm and clear, and where it still breaks or goes silent.\n\n'
            'When the sensation becomes calmer, choose the next channel.'
        ),
        'feature_announcement': '☯️ <b>Journey of Ascension update</b>\n'
                                '\n'
                                'Please move to the new bot: @journey_ascension_bot.\n'
                                '<b>This current bot will stop being supported soon.</b>\n'
                                '\n'
                                'We noticed bugs that could make reminders arrive irregularly, and we fixed them.\n'
                                '\n'
                                'We are also happy to present a new feature: <b>Chinese meridian study</b>.\n'
                                'Now you can choose a meridian, view its overview image and video, open points '
                                'with images, and move through the practice at your own pace.\n'
                                '\n'
                                'Open @journey_ascension_bot and press /start.',
        'stop_feedback_prompt': 'If you want, you can leave one short note about why you are pausing the practice. This is optional.',
        'stop_feedback_thanks': 'Thank you. Your note will help make the practice gentler and clearer.\n'
                                '\n'
                                'Use /start if you want to return.',
        'timezone_manual_prompt': 'Enter your time zone in IANA format.\n'
                                  '\n'
                                  'Examples: Europe/Moscow, Asia/Tashkent, Asia/Almaty, UTC'},
 'ru': {'welcome': '🕊️ <b>Добро пожаловать в Journey of Ascension!</b>\n'
                   '\n'
                   'Яма и Нияма остаются нравственным фундаментом внутренней практики. Меридианы — следующая '
                   'ступень: учиться чувствовать внимание, тело и энергию через прямое наблюдение.\n'
                   '\n'
                   'Начнём с выбора языка:',
        'language_chosen': '✅ Язык установлен: русский.',
        'timezone_step': '📍 Часовой пояс\n'
                         '\n'
                         'Выберите ваш часовой пояс, чтобы напоминания приходили в правильное местное время.',
        'timezone_custom': '⌨️ Ввести вручную',
        'timezone_saved': '✅ Часовой пояс сохранён.',
        'time_step': '🧘🏻 <b>Время напоминания по Яме/Нияме</b>\n'
                     '\n'
                     'Выберите, когда бот будет присылать ежедневный принцип. Постоянное время помогает '
                     'практике войти в обычную жизнь.\n'
                     '\n'
                     'Формат: ЧЧ:ММ, например 08:00 или 20:30.',
        'time_saved': '✅ Время напоминаний сохранено.',
        'skip_days_step': '📅 <b>Дни тишины</b>\n'
                          '\n'
                          'Выберите дни недели, когда бот должен молчать и <b>не</b> присылать ежедневные '
                          'напоминания по практике.\n'
                          '\n'
                          'Если хотите получать напоминания каждый день, выберите <b>Без дней тишины</b>. '
                          'Если хотите получать во все дни, кроме воскресенья, выберите только воскресенье.',
        'setup_complete': '🎉 <b>Первый шаг настроен.</b>\n'
                          '\n'
                          '📋 <b>Ваш ритм:</b>\n'
                          '🕐 Время: {time}\n'
                          '🌍 Часовой пояс: {timezone}\n'
                          '📅 Дни тишины: {skip_days}\n'
                          '\n'
                          'Используйте /menu, когда захотите открыть списки, изменить ритм или продолжить следующий небольшой шаг.',
        'already_subscribed': '🕊️ Journey of Ascension уже открыт здесь.\n'
                              '\n'
                              'Используйте /menu для выбора практик или /settings для настройки ритма практики.',
        'unsubscribed': 'Ритм практики остановлен. Ежедневные напоминания пока будут молчать.\n'
                        '\n'
                        'Если захотите вернуться, используйте /start.',
        'not_subscribed': 'Практика в этом чате ещё не запущена. Используйте /start, когда будете готовы начать.',
        'current_settings': '⚙️ <b>Текущий ритм практики</b>',
        'not_subscribed_test': 'Ритм практики ещё не настроен. Используйте /start, чтобы начать.',
        'test_failed': 'Сейчас не получилось проверить напоминание. Попробуйте немного позже.',
        'invalid_timezone': '❌ Не удалось распознать часовой пояс. Попробуйте формат Europe/Moscow, '
                            'Asia/Tashkent, Asia/Almaty или UTC.',
        'invalid_time': '❌ Не удалось распознать время. Используйте формат ЧЧ:ММ, например 08:00 или 20:30.',
        'invalid_skip_days': '❌ Не удалось распознать дни. Используйте числа от 0 до 6 через запятую.',
        'setup_error': '❌ Пока не получилось сохранить настройки. Попробуйте ещё раз: ритм практики лучше настроить спокойно и точно.',
        'error': 'Поток прервался. Попробуйте ещё раз или вернитесь в /menu.',
        'choose_language': 'Выберите язык, на котором хотите использовать бота:',
        'english': '🇺🇸 English',
        'russian': '🇷🇺 Русский',
        'menu': '📋 <b>Journey of Ascension</b>',
        'menu_settings': '⚙️ Ритм практики',
        'menu_test': '🧪 Проверить напоминание',
        'menu_announce_update': '📢 Разослать анонс',
        'sending_test': '🧪 Проверяю отправку напоминания...',
        'menu_about': 'ℹ️ О боте',
        'menu_feedback': '💌 Отзывы и идеи',
        'menu_stop': '⏸ Пауза практики',
        'settings_menu': '⚙️ <b>Ритм практики</b>\n'
                         '\n'
                         'Здесь можно настроить ритм практики: что бот напоминает, когда приходят сообщения '
                         'и в какие дни лучше оставить тишину.',
        'change_language': '🌐 Язык',
        'change_time': '🧘🏻 Время Ямы/Ниямы',
        'change_timezone': '🌍 Часовой пояс',
        'change_skip_days': '📅 Дни тишины',
        'back_to_menu': '🔙 Назад в меню',
        'skip_days_improved': '📅 <b>Дни тишины</b>\n'
                              '\n'
                              'Выберите дни недели, когда бот должен молчать и <b>не</b> присылать ежедневные '
                              'напоминания по практике.\n'
                              '\n'
                              'Если хотите получать напоминания каждый день, выберите <b>Без дней тишины</b>. '
                              'Если хотите получать во все дни, кроме воскресенья, выберите только воскресенье.',
        'no_skip_days': '✅ Дни тишины не выбраны — напоминания могут приходить каждый день',
        'about_text': '🕊️ <b>Journey of Ascension</b>\n'
                      '\n'
                      'Этот бот помогает возвращаться к практике в обычной жизни: один ясный фокус каждый день.\n'
                      '\n'
                      'Каждый день он возвращает к одному конкретному фокусу: принципу Ямы/Ниямы или точке '
                      'меридиана. Задача простая: замечать, где энергия уходит бессознательно, переставать '
                      'её растрачивать и учиться направлять внимание бережнее.\n'
                      '\n'
                      '<b>Яма/Нияма</b> работает с поведением, речью, мыслями, дисциплиной и честностью '
                      'перед собой.\n'
                      '\n'
                      '<b>Меридианы</b> работают через тело: каналы, точки, течение Ци, закрытые зоны, '
                      'дыхание, касание и внимание.\n'
                      '\n'
                      'Маленькие повторения важны. Они превращают идею в то, чем действительно можно жить.',
        'feedback_prompt': '💌 <b>Отзывы и идеи</b>\n'
                           '\n'
                           'Ваш опыт важен. Напишите, что оказалось полезным, что было непонятно или что '
                           'сделало бы практику удобнее.',
        'feedback_sent': '✅ Спасибо. Ваш отзыв отправлен.',
        'feedback_too_long': '❌ Сообщение слишком длинное. Пожалуйста, уложитесь в 1000 символов.',
        'feedback_rate_limit': '⏰ Пожалуйста, подождите немного перед следующим отзывом.',
        'feedback_error': '❌ Не удалось сохранить отзыв. Попробуйте позже.',
        'onboarding_intro': '<b>Journey of Ascension</b>\n'
                            '\n'
                            'Практика начинается с наблюдения: куда уходит энергия. Когда она рассеяна, '
                            'внимание шумит; когда собирается, действие становится тише и чище.\n'
                            '\n'
                            '<b>Яма и Нияма</b> — фундамент: они уменьшают утечки энергии через речь, '
                            'мысли, привычки и реакции. <b>Ахимса</b> начинается с того, чтобы не тратить '
                            'силу на вред.\n'
                            '\n'
                            '<b>Меридианы</b> переносят практику в тело. Вы учитесь проходить каналы, точки '
                            'и тихие зоны через касание, дыхание и терпеливое внимание.\n'
                            '\n'
                            'Что вы хотели бы изучать?',
        'initial_mode_question': 'Что вы хотели бы изучать?',
        'timezone_step_principles': '📍 <b>Шаг 1/3: Часовой пояс</b>\n'
                                    '\n'
                                    'Выберите ваш часовой пояс, чтобы бот присылал напоминания по <b>Яме и '
                                    'Нияме</b> в правильное для вас местное время.',
        'timezone_step_meridians': '📍 <b>Шаг 1/3: Часовой пояс</b>\n'
                                   '\n'
                                   'Выберите ваш часовой пояс, чтобы бот присылал материалы и напоминания по '
                                   '<b>меридианам</b> в правильное для вас местное время.',
        'timezone_step_both': '📍 <b>Шаг 1/3: Часовой пояс</b>\n'
                              '\n'
                              'Выберите ваш часовой пояс, чтобы бот присылал напоминания по <b>Яме/Нияме</b> '
                              'и материалы по <b>меридианам</b> в правильное для вас местное время.',
        'time_step_principles': '⏰ <b>Шаг 2/3: Время отправки</b>\n'
                                '\n'
                                'Укажите время, когда бот будет присылать ежедневный принцип '
                                '<b>Ямы/Ниямы</b>.\n'
                                '\n'
                                'Формат: ЧЧ:ММ, например 08:00 или 20:30.',
        'time_step_meridians': '⏰ <b>Шаг 2/3: Время отправки</b>\n'
                               '\n'
                               'Укажите время, когда бот будет присылать ежедневный фокус по '
                               '<b>меридианам</b>.\n'
                               '\n'
                               'Формат: ЧЧ:ММ, например 08:00 или 20:30.',
        'time_step_both': '⏰ <b>Шаг 2/3: Время отправки</b>\n'
                          '\n'
                          'Укажите время, когда бот будет присылать ежедневный принцип <b>Ямы/Ниямы</b> и '
                          'фокус по <b>меридианам</b>.\n'
                          '\n'
                          'Формат: ЧЧ:ММ, например 08:00 или 20:30.',
        'continue_setup': 'Продолжить',
        'menu_principles': '🧘🏻✨ Яма/Нияма',
        'menu_meridians': '☯️ Меридианы',
        'menu_modes': '🧭 Мой путь',
        'principles_menu': '🕊️ <b>Яма/Нияма</b>\n'
                           '\n'
                           'Это первые две ступени классической йоги и нравственный фундамент практики.\n'
                           '\n'
                           '<b>Яма</b> бережёт энергию в отношениях с миром: ненасилие, правдивость, '
                           'неворовство, умеренность и нестяжательство.\n'
                           '\n'
                           '<b>Нияма</b> собирает энергию внутри: чистота, удовлетворённость, дисциплина, '
                           'самоизучение и посвящение плодов практики высшему.\n'
                           '\n'
                           'Принцип дня — это акцент для наблюдения, а не замена остальных принципов. Мы '
                           'постепенно внедряем их все в жизнь; каждый день один становится особенно '
                           'заметным.\n'
                           '\n'
                           'Откройте принцип дня или посмотрите весь список.',
        'principles_random': 'Случайный принцип',
        'principles_all': 'Все принципы',
        'principles_back': '🔙 К Яме/Нияме',
        'principles_empty': 'Сейчас принципы не открылись. Вернитесь к Яме/Нияме или попробуйте снова из /menu.',
        'change_modes': '🧭 Мой путь',
        'change_meridian_time': '☯️ Время меридианов',
        'mode_menu': '🧭 <b>Мой путь</b>\n'
                     '\n'
                     'Выберите, к какой практике вы хотите возвращаться каждый день.\n'
                     '\n'
                     '<b>Яма/Нияма</b> — фундамент: меньше внутреннего шума, меньше утечек энергии, больше '
                     'честности в поступках.\n'
                     '\n'
                     '<b>Меридианы</b> — телесный слой: точки, каналы, течение Ци и навык спокойно включать '
                     'в внимание места, которые сначала почти не ощущаются.\n'
                     '\n'
                     'Можно начать с одного направления или оставить активными оба.',
        'mode_principles_only': 'Фундамент Ямы/Ниямы',
        'mode_meridians_only': 'Изучение меридианов',
        'mode_both': 'Оба направления',
        'mode_saved': '✅ <b>Ваш путь обновлён.</b>',
        'meridian_time_step': '☯️ <b>Время напоминания по меридианам</b>\n'
                              '\n'
                              'Введите время в формате ЧЧ:ММ, например 20:00.',
        'meridian_time_saved': '✅ Время напоминаний по меридианам сохранено.',
        'meridian_mode_menu': '☯️ <b>Выберите путь изучения меридианов</b>\n'
                              '\n'
                              '<b>Маршрут бота</b> подойдёт, если вы только начинаете: один канал, одна '
                              'точка, один спокойный шаг за раз. Завершили меридиан — открылся следующий.\n'
                              '\n'
                              '<b>Свободный выбор</b> подойдёт, если внимание уже тянется к конкретному '
                              'меридиану или вы знаете, что хотите изучить.\n'
                              '\n'
                              'Путь можно изменить позже. Прогресс и напоминания сохраняются.',
        'meridian_guided_path': '🧭 Маршрут бота',
        'meridian_free_choice': '👐 Свободный выбор',
        'meridian_change_path': '🧭 Начать или выбрать путь',
        'meridian_guided_saved': '✅ <b>Выбран маршрут бота.</b>\n'
                                 '\n'
                                 'Будем двигаться мягко: один меридиан, одна точка, одно устойчивое ощущение за раз.',
        'meridian_free_saved': '✅ <b>Выбран свободный выбор.</b>\n'
                               '\n'
                               'Выберите меридиан, который хотите исследовать сейчас.',
        'meridian_measurements': '📏 Как измерять цуни',
        'meridian_point_help': '🖐 Как искать точку',
        'meridian_back': '🔙 К меридианам',
        'page_indicator_hint': 'Это номер страницы. Для перехода используйте «Назад» или «Далее».',
        'meridian_measurements_text': '📏 <b>Система измерений в ТКМ</b>\n'
                                      '\n'
                                      '<b>Зачем это нужно:</b> в описаниях точек часто встречается «1 цунь», '
                                      '«1,5 цуня», «3 цуня» и так далее. Эта справка помогает перевести '
                                      'такие указания на своё тело.\n'
                                      '\n'
                                      'Расположение акупунктурных точек часто описывается в <b>цунях</b>. '
                                      'Цунь — это не фиксированное число сантиметров, а относительная мера '
                                      'тела конкретного человека.\n'
                                      '\n'
                                      '<b>0,5 цуня:</b> половина вашего личного 1 цуня. Используйте для '
                                      'очень малых расстояний и затем уточняйте точку через ощущения.\n'
                                      '\n'
                                      '<b>1 цунь:</b> ширина большого пальца в области межфалангового '
                                      'сустава.\n'
                                      '\n'
                                      '<b>1,5 цуня:</b> ширина двух пальцев вместе — указательного и '
                                      'среднего.\n'
                                      '\n'
                                      '<b>2 цуня:</b> ширина трёх пальцев вместе — указательного, среднего и '
                                      'безымянного.\n'
                                      '\n'
                                      '<b>3 цуня:</b> ширина четырёх сомкнутых пальцев — от указательного до '
                                      'мизинца.\n'
                                      '\n'
                                      '<b>5 цуней:</b> можно отмерить 3 цуня и добавить около 2 цуней, либо '
                                      'разделить нужный анатомический участок на равные части, если источник '
                                      'даёт пропорциональное расстояние.\n'
                                      '\n'
                                      '<b>Важно:</b> цунь всегда измеряется по телу того человека, с которым '
                                      'вы работаете. Поэтому 1 цунь на вашем теле и 1 цунь на теле другого '
                                      'человека могут отличаться в сантиметрах.\n'
                                      '\n'
                                      'Используйте цуни как ориентир, а затем уточняйте точку через тело: '
                                      'локальная чувствительность, небольшое углубление, тепло, давление или '
                                      'ясный отклик на внимание.',
        'meridian_point_help_text': '🖐 <b>Как искать точку</b>\n'
                                    '\n'
                                    'Сначала найдите примерную область по изображению и цуням. '
                                    'Потом замедлитесь и уточняйте точку уже через ощущения тела.\n'
                                    '\n'
                                    '<b>1.</b> Мягко касайтесь зоны и ищите небольшое углубление, '
                                    'чувствительность, тепло, давление или место, за которое внимание '
                                    'цепляется легче.\n'
                                    '\n'
                                    '<b>2.</b> Если точка молчит, считайте её пока закрытой: побудьте с ней '
                                    'дольше, мягко помассируйте (кроме точек со значком ⚠) и представляйте вдох и выдох через неё.\n'
                                    '\n'
                                    '<b>3.</b> Не выжимайте результат. Достаточно тихого устойчивого '
                                    'ощущения.\n'
                                    '\n'
                                    'Когда переходите к следующей точке, не бросайте предыдущие: удерживайте '
                                    'их фоном и добавляйте новую в ту же линию внимания.',
        'meridians_menu': '☯️ <b>Меридианы</b>\n'
                          '\n'
                          '<b>Зачем изучать меридианы?</b>\n'
                          '\n'
                          'В китайской традиции меридианы описывают пути, по которым движется Ци. В практике '
                          'это становится очень конкретным: вы замечаете, где тело отвечает на внимание, где '
                          'есть напряжение, а где ощущение пока слабое.\n'
                          '\n'
                          '<b>Как это помогает:</b> внимание, дыхание и мягкое касание постепенно возвращают '
                          'чувствительность в точку. Область становится теплее, яснее и легче соединяется с '
                          'общей линией канала.\n'
                          '\n'
                          '<b>Как начать:</b> выберите маршрут бота, если хотите спокойную последовательность, '
                          'или свободный выбор, если уже знаете, какой меридиан хотите изучить.\n'
                          '\n'
                          '<b>Перед точками:</b> откройте справку по <b>цуням</b>. Она поможет находить '
                          'нужную область на своём теле, а точку вы уточните пальцами, дыханием и вниманием.\n'
                          '\n'
                          'Это практика самонаблюдения. Она не заменяет врача, диагностику или лечение.',
        'choose_meridian': '☯️ <b>Выберите меридиан:</b>',
        'current_meridian': '▶️ Продолжить практику',
        'meridian_start_points': 'Начать с первой точки',
        'all_points': 'Все точки',
        'next_point': 'Следующая точка',
        'prev_point': 'Предыдущая точка',
        'complete_meridian': 'Завершить меридиан',
        'select_meridian': 'Выбрать меридиан',
        'no_points': 'Сейчас точки не открылись. Вернитесь к списку меридианов и попробуйте ещё раз оттуда.',
        'meridian_completed': (
            '✅ <b>Меридиан завершён</b>\n\n'
            'Перед тем как идти дальше, пройдите вниманием весь канал ещё раз: от первой точки до последней. '
            'Заметьте, где линия тёплая и ясная, а где она пока обрывается или молчит.\n\n'
            'Когда ощущение станет спокойнее, выбирайте следующий канал.'
        ),
        'feature_announcement': '☯️ <b>Обновление Journey of Ascension</b>\n'
                                '\n'
                                'Пожалуйста, переходите в нового бота: @journey_ascension_bot.\n'
                                '<b>Текущий бот скоро перестанет поддерживаться.</b>\n'
                                '\n'
                                'Мы заметили ошибки, из-за которых напоминания могли приходить нерегулярно, и исправили их.\n'
                                '\n'
                                'Также мы рады представить новую функцию: <b>изучение китайских меридианов</b>.\n'
                                'Теперь в боте можно выбрать меридиан, посмотреть общую схему и видео, открыть '
                                'точки с изображениями и двигаться по практике в своём темпе.\n'
                                '\n'
                                'Откройте @journey_ascension_bot и нажмите /start.',
        'stop_feedback_prompt': 'Если хотите, можете одним сообщением написать, почему ставите практику на паузу. Это необязательно.',
        'stop_feedback_thanks': 'Спасибо. Эта заметка поможет сделать практику мягче и понятнее.\n'
                                '\n'
                                'Если захотите вернуться, используйте /start.',
        'timezone_manual_prompt': 'Введите часовой пояс в формате IANA.\n'
                                  '\n'
                                  'Примеры: Europe/Moscow, Asia/Tashkent, Asia/Almaty, UTC'},
 'uz': {'welcome': '🕊️ <b>Journey of Ascension botiga xush kelibsiz!</b>\n'
                   '\n'
                   "Yama va Niyama ichki amaliyotning axloqiy poydevori bo'lib qoladi. Meridianlar keyingi "
                   "bosqich: diqqat, tana va energiyani bevosita kuzatish orqali sezishni o'rganish.\n"
                   '\n'
                   'Avval tilni tanlaymiz:',
        'language_chosen': "✅ Til o'zbekchaga o'rnatildi.",
        'timezone_step': '📍 Vaqt mintaqasi\n'
                         '\n'
                         "Eslatmalar to'g'ri mahalliy vaqtda kelishi uchun vaqt mintaqangizni tanlang.",
        'timezone_custom': "⌨️ Qo'lda kiritish",
        'timezone_saved': '✅ Vaqt mintaqasi saqlandi.',
        'time_step': '🧘🏻 <b>Yama/Niyama eslatma vaqti</b>\n'
                     '\n'
                     'Bot kundalik tamoyilni qachon yuborishini tanlang. Barqaror vaqt amaliyotni kundalik '
                     'hayotga kiritishga yordam beradi.\n'
                     '\n'
                     'Format: HH:MM, masalan 08:00 yoki 20:30.',
        'time_saved': '✅ Eslatma vaqti saqlandi.',
        'skip_days_step': '📅 <b>Sokin kunlar</b>\n'
                          '\n'
                          'Bot kundalik amaliyot eslatmalarini yubormaydigan hafta kunlarini tanlang.\n'
                          '\n'
                          "Har kuni ritm kerak bo'lsa, kunlarni tanlamang.",
        'setup_complete': '🎉 <b>Birinchi qadam sozlandi.</b>\n'
                          '\n'
                          '📋 <b>Ritmingiz:</b>\n'
                          '🕐 Vaqt: {time}\n'
                          '🌍 Vaqt mintaqasi: {timezone}\n'
                          '📅 Sokin kunlar: {skip_days}\n'
                          '\n'
                          "Ro'yxatlarni ochish, ritmni o'zgartirish yoki keyingi kichik qadamni davom ettirish uchun /menu dan foydalaning.",
        'already_subscribed': "🕊️ Journey of Ascension bu yerda allaqachon ochilgan.\n"
                              '\n'
                              "Amaliyotlarni tanlash uchun /menu yoki amaliyot ritmini sozlash uchun /settings "
                              "dan foydalaning.",
        'unsubscribed': "Amaliyot ritmi pauzaga qo'yildi. Kundalik eslatmalar hozircha kelmaydi.\n"
                        '\n'
                        "Qaytmoqchi bo'lsangiz, /start dan foydalaning.",
        'not_subscribed': "Bu chatda amaliyot hali boshlanmagan. Boshlashga tayyor bo'lsangiz, /start dan foydalaning.",
        'current_settings': '⚙️ <b>Joriy amaliyot ritmi</b>',
        'not_subscribed_test': "Amaliyot ritmi hali sozlanmagan. Boshlash uchun /start dan foydalaning.",
        'test_failed': "Hozir eslatmani tekshirish xabarini yubora olmadim. Birozdan keyin qayta urinib ko'ring.",
        'invalid_timezone': '❌ Bu vaqt mintaqasini taniy olmadim. Asia/Tashkent, Europe/Moscow, Asia/Almaty '
                            "yoki UTC kabi formatni sinab ko'ring.",
        'invalid_time': '❌ Bu vaqtni taniy olmadim. HH:MM formatidan foydalaning, masalan 08:00 yoki 20:30.',
        'invalid_skip_days': "❌ Kunlarni taniy olmadim. 0 dan 6 gacha bo'lgan raqamlarni vergul bilan "
                             'kiriting.',
        'setup_error': "❌ Hozircha sozlamalarni saqlay olmadim. Yana bir marta urinib ko'ring: amaliyot ritmini sokin va aniq sozlagan yaxshi.",
        'error': "Jarayon uzilib qoldi. Yana bir marta urinib ko'ring yoki /menu ga qayting.",
        'choose_language': 'Botdan qaysi tilda foydalanishni tanlang:',
        'english': '🇺🇸 English',
        'russian': '🇷🇺 Русский',
        'uzbek': "🇺🇿 O'zbek",
        'menu': '📋 <b>Journey of Ascension</b>',
        'menu_settings': '⚙️ Amaliyot ritmi',
        'menu_test': '🧪 Eslatmani tekshirish',
        'menu_announce_update': '📢 Yangilikni yuborish',
        'sending_test': '🧪 Eslatma tekshiruvi yuborilmoqda...',
        'menu_about': 'ℹ️ Bot haqida',
        'menu_feedback': '💌 Fikr va takliflar',
        'menu_stop': "⏸ Amaliyotni pauza qilish",
        'settings_menu': '⚙️ <b>Amaliyot ritmi</b>\n'
                         '\n'
                         'Bu yerda amaliyot ritmini sozlaysiz: bot nimani eslatadi, xabarlar qachon keladi '
                         'va qaysi kunlar sokin qoladi.',
        'change_language': '🌐 Til',
        'change_time': '🧘🏻 Yama/Niyama vaqti',
        'change_timezone': '🌍 Vaqt mintaqasi',
        'change_skip_days': '📅 Sokin kunlar',
        'back_to_menu': '🔙 Menyuga qaytish',
        'about_text': '🕊️ <b>Journey of Ascension</b>\n'
                      '\n'
                      "Bu bot kundalik hayotda amaliyotga qaytishga yordam beradi: har kuni bitta aniq fokus.\n"
                      '\n'
                      'Har kuni u sizni bitta aniq fokusga qaytaradi: Yama/Niyama tamoyiliga yoki meridian '
                      "nuqtasiga. Maqsad oddiy: energiya qayerda ongsiz sarflanayotganini ko'rish, uni "
                      "behuda ketkazmaslik va diqqatni ehtiyotkorroq yo'naltirishni o'rganish.\n"
                      '\n'
                      "<b>Yama/Niyama</b> xulq, nutq, fikr, intizom va o'zingizga nisbatan halollik bilan "
                      'ishlaydi.\n'
                      '\n'
                      '<b>Meridianlar</b> tana orqali ishlaydi: kanallar, nuqtalar, Qi oqimi, yopiq joylar, '
                      'nafas, teginish va diqqat.\n'
                      '\n'
                      "Kichik takrorlar muhim. Ular g'oyani yashash mumkin bo'lgan odatga aylantiradi.",
        'feedback_too_long': '❌ Xabar juda uzun. Iltimos, 1000 belgidan oshirmang.',
        'feedback_rate_limit': '⏰ Keyingi fikrni yuborishdan oldin biroz kuting.',
        'feedback_error': "❌ Fikringizni saqlab bo'lmadi. Iltimos, keyinroq urinib ko'ring.",
        'onboarding_intro': '<b>Journey of Ascension</b>\n'
                            '\n'
                            'Amaliyot energiya qayerga ketayotganini kuzatishdan boshlanadi. U tarqoq '
                            "bo'lsa, diqqat shovqinli; yig'ilsa, harakat sokinroq va tiniqroq bo'ladi.\n"
                            '\n'
                            '<b>Yama va Niyama</b> poydevor: ular energiyaning nutq, fikr, odat va '
                            "reaksiyalar orqali oqib ketishini kamaytiradi. <b>Ahimsa</b> kuchni zarar "
                            'yetkazishga sarflamaslikdan boshlanadi.\n'
                            '\n'
                            '<b>Meridianlar</b> amaliyotni tanaga olib kiradi. Siz kanallar, nuqtalar va '
                            "teginish, nafas hamda sabrli diqqat so'raydigan joylarni sezasiz.\n"
                            '\n'
                            "Nimani o'rganmoqchisiz?",
        'initial_mode_question': "Nimani o'rganmoqchisiz?",
        'timezone_step_principles': '📍 <b>1/3-qadam: Vaqt mintaqasi</b>\n'
                                    '\n'
                                    'Bot <b>Yama/Niyama</b> eslatmalarini sizning mahalliy vaqtingiz '
                                    "bo'yicha yuborishi uchun vaqt mintaqangizni tanlang.",
        'timezone_step_meridians': '📍 <b>1/3-qadam: Vaqt mintaqasi</b>\n'
                                   '\n'
                                   "Bot <b>meridianlar</b> bo'yicha material va eslatmalarni sizning "
                                   "mahalliy vaqtingiz bo'yicha yuborishi uchun vaqt mintaqangizni tanlang.",
        'timezone_step_both': '📍 <b>1/3-qadam: Vaqt mintaqasi</b>\n'
                              '\n'
                              "Bot <b>Yama/Niyama</b> va <b>meridianlar</b> bo'yicha eslatmalarni sizning "
                              "mahalliy vaqtingiz bo'yicha yuborishi uchun vaqt mintaqangizni tanlang.",
        'time_step_principles': '⏰ <b>2/3-qadam: Yuborish vaqti</b>\n'
                                '\n'
                                'Bot kundalik <b>Yama/Niyama</b> tamoyilini qachon yuborishini tanlang.\n'
                                '\n'
                                'Format: HH:MM, masalan 08:00 yoki 20:30.',
        'time_step_meridians': '⏰ <b>2/3-qadam: Yuborish vaqti</b>\n'
                               '\n'
                               'Bot kundalik <b>meridian</b> fokusini qachon yuborishini tanlang.\n'
                               '\n'
                               'Format: HH:MM, masalan 08:00 yoki 20:30.',
        'time_step_both': '⏰ <b>2/3-qadam: Yuborish vaqti</b>\n'
                          '\n'
                          'Bot kundalik <b>Yama/Niyama</b> tamoyili va <b>meridian</b> fokusini qachon '
                          'yuborishini tanlang.\n'
                          '\n'
                          'Format: HH:MM, masalan 08:00 yoki 20:30.',
        'continue_setup': 'Davom etish',
        'menu_principles': '🧘🏻✨ Yama/Niyama',
        'menu_meridians': '☯️ Meridianlar',
        'menu_modes': "🧭 Mening yo'lim",
        'principles_menu': '🕊️ <b>Yama/Niyama</b>\n'
                           '\n'
                           "Bular klassik yoganing birinchi ikki pog'onasi va amaliyotning axloqiy "
                           'poydevoridir.\n'
                           '\n'
                           '<b>Yama</b> dunyo bilan munosabatda energiyani asraydi: zarar yetkazmaslik, '
                           "rostgo'ylik, o'g'irlamaslik, mo'tadillik va ortiqcha egalik qilmaslik.\n"
                           '\n'
                           "<b>Niyama</b> energiyani ichkarida yig'adi: poklik, qanoat, intizom, o'zini "
                           "o'rganish va amaliyot mevasini oliy maqsadga bag'ishlash.\n"
                           '\n'
                           "Kun tamoyili qolgan tamoyillar o'rniga kelmaydi; u kuzatish uchun urg'u "
                           "beradi. Biz ularning barchasini hayotga asta-sekin kiritamiz, har kuni bittasi "
                           "aniqroq ko'rinadi.\n"
                           '\n'
                           "Bugungi tamoyilni oching yoki to'liq ro'yxatni ko'ring.",
        'principles_random': 'Tasodifiy tamoyil',
        'principles_all': 'Barcha tamoyillar',
        'principles_back': '🔙 Yama/Niyamaga qaytish',
        'principles_empty': "Hozir tamoyillar ochilmadi. Yama/Niyamaga qayting yoki /menu dan qayta urinib ko'ring.",
        'change_modes': "🧭 Mening yo'lim",
        'change_meridian_time': '☯️ Meridian vaqti',
        'mode_menu': "🧭 <b>Mening yo'lim</b>\n"
                     '\n'
                     'Har kuni qaysi amaliyotga qaytishni xohlayotganingizni tanlang.\n'
                     '\n'
                     "<b>Yama/Niyama</b> poydevor: ichki shovqin kamroq, energiya yo'qotish kamroq, "
                     "harakatlarda ko'proq halollik.\n"
                     '\n'
                     '<b>Meridianlar</b> tana qatlami: nuqtalar, kanallar, Qi oqimi va avval noaniq sezilgan '
                     "joylarni sabr bilan diqqatga qo'shish ko'nikmasi.\n"
                     '\n'
                     "Bitta yo'nalishdan boshlashingiz yoki ikkalasini ham faol qoldirishingiz mumkin.",
        'mode_principles_only': 'Yama/Niyama poydevori',
        'mode_meridians_only': "Meridianlarni o'rganish",
        'mode_both': "Ikkala yo'nalish",
        'mode_saved': "✅ <b>Yo'lingiz yangilandi.</b>",
        'meridian_time_step': '☯️ <b>Meridian eslatma vaqti</b>\n'
                              '\n'
                              'Vaqtni HH:MM formatida kiriting, masalan 20:00.',
        'meridian_time_saved': '✅ Meridian eslatma vaqti saqlandi.',
        'meridian_mode_menu': "☯️ <b>Meridianlarni o'rganish yo'lini tanlang</b>\n"
                              '\n'
                              "<b>Bot yo'nalishi</b> yangi boshlaganlar uchun qulay: bir kanal, bir nuqta, "
                              "bir sokin qadam. Meridian tugagach, keyingisi ochiladi.\n"
                              '\n'
                              "<b>Erkin tanlov</b> ma'lum meridian e'tiboringizni tortsa yoki nimani "
                              "o'rganmoqchi ekaningizni bilsangiz qulay.\n"
                              '\n'
                              "Yo'lni keyin o'zgartirish mumkin. Progress va eslatmalar saqlanadi.",
        'meridian_guided_path': "🧭 Bot yo'nalishi",
        'meridian_free_choice': '👐 Erkin tanlov',
        'meridian_change_path': "🧭 Boshlash yoki yo'l tanlash",
        'meridian_guided_saved': "✅ <b>Bot yo'nalishi tanlandi.</b>\n"
                                 '\n'
                                 "Yumshoq harakat qilamiz: bir meridian, bir nuqta, bir barqaror sezgi.",
        'meridian_free_saved': '✅ <b>Erkin tanlov tanlandi.</b>\n'
                               '\n'
                               "Hozir o'rganmoqchi bo'lgan meridianni tanlang.",
        'meridian_measurements': "📏 Cunni o'lchash",
        'meridian_point_help': '🖐 Nuqtani topish',
        'meridian_back': '🔙 Meridianlarga qaytish',
        'page_indicator_hint': "Bu sahifa raqami. O'tish uchun Oldingi yoki Keyingi tugmasidan foydalaning.",
        'meridian_measurements_text': "📏 <b>TKMdagi o'lchov tizimi</b>\n"
                                      '\n'
                                      "<b>Bu nima uchun kerak:</b> nuqta tavsiflarida ko'pincha “1 cun”, "
                                      "“1,5 cun”, “3 cun” kabi o'lchovlar uchraydi. Bu ma'lumot ularni o'z "
                                      'tanangizda topishga yordam beradi.\n'
                                      '\n'
                                      "Akupunktura nuqtalari ko'pincha <b>cun</b> orqali tasvirlanadi. Cun "
                                      "aniq santimetr emas: u o'rganilayotgan odam tanasiga nisbatan "
                                      "olinadigan o'lchovdir.\n"
                                      '\n'
                                      "<b>0,5 cun:</b> shaxsiy 1 cun o'lchovingizning yarmi. Juda kichik "
                                      'masofalar uchun ishlating va keyin nuqtani sezgi orqali aniqlang.\n'
                                      '\n'
                                      "<b>1 cun:</b> bosh barmoqning bo'g'im sohasidagi kengligi.\n"
                                      '\n'
                                      "<b>1,5 cun:</b> ikki barmoq kengligi: ko'rsatkich va o'rta barmoq.\n"
                                      '\n'
                                      "<b>2 cun:</b> uch barmoq kengligi: ko'rsatkich, o'rta va nomsiz "
                                      'barmoq.\n'
                                      '\n'
                                      "<b>3 cun:</b> to'rt barmoq kengligi: ko'rsatkichdan kichik "
                                      'barmoqqacha.\n'
                                      '\n'
                                      "<b>5 cun:</b> 3 cun o'lchab, taxminan 2 cun qo'shing yoki manbada "
                                      "proporsional masofa berilgan bo'lsa, anatomik qismni teng bo'laklarga "
                                      'ajrating.\n'
                                      '\n'
                                      '<b>Muhim:</b> cun doimo ishlayotgan odamning tanasiga qarab '
                                      "o'lchanadi. Shuning uchun sizdagi 1 cun va boshqa odamdagi 1 cun "
                                      'santimetrda farq qilishi mumkin.\n'
                                      '\n'
                                      "Cunni yo'nalish sifatida ishlating, keyin nuqtani tana orqali "
                                      'aniqlang: mahalliy sezgirlik, kichik chuqurcha, iliqlik, bosim yoki '
                                      'diqqatga aniq javob.',
        'meridian_point_help_text': '🖐 <b>Nuqtani qanday topish kerak</b>\n'
                                    '\n'
                                    "Avval rasm va cun o'lchovlari orqali taxminiy joyni toping. "
                                    'Keyin sekinlashing va aniq nuqtani tana sezgilari orqali toping.\n'
                                    '\n'
                                    '<b>1.</b> Joyga yumshoq teging va kichik chuqurcha, sezgirlik, '
                                    'issiqlik, bosim yoki diqqat osonroq ushlanadigan nuqtani qidiring.\n'
                                    '\n'
                                    "<b>2.</b> Agar nuqta jim bo'lsa, uni hali ochilmagan deb qabul qiling: "
                                    'uzoqroq turing, yengil massaj qiling (⚠ belgisi bor nuqtalardan tashqari) va shu nuqta orqali nafas '
                                    'olayotganingizni tasavvur qiling.\n'
                                    '\n'
                                    '<b>3.</b> Natijani majburlamang. Sokin va barqaror sezgi yetarli.\n'
                                    '\n'
                                    "Keyingi nuqtaga o'tganda oldingilarni fon sifatida sezib, yangi nuqtani "
                                    "shu diqqat chizig'iga qo'shing.",
        'meridians_menu': '☯️ <b>Meridianlar</b>\n'
                          '\n'
                          "<b>Meridianlarni nima uchun o'rganamiz?</b>\n"
                          '\n'
                          "Xitoy an'anasida meridianlar Qi harakatlanadigan yo'llar sifatida tasvirlanadi. "
                          "Amaliyotda bu aniq seziladi: tana qayerda diqqatga javob beradi, qayerda "
                          "taranglik bor, qayerda sezgi hali sust ekanini kuzatasiz.\n"
                          '\n'
                          "<b>Bu qanday yordam beradi:</b> diqqat, nafas va yumshoq teginish nuqtaga "
                          "sezgirlikni asta-sekin qaytaradi. Hudud iliqroq, ravshanroq bo'lishi va kanal "
                          "chizig'i bilan osonroq bog'lanishi mumkin.\n"
                          '\n'
                          "<b>Qanday boshlash:</b> sokin ketma-ketlik kerak bo'lsa, bot yo'nalishini "
                          "tanlang. Qaysi meridianni o'rganmoqchi ekaningizni bilsangiz, erkin tanlovni "
                          "tanlang.\n"
                          '\n'
                          "Nuqtalar bilan ishlashdan oldin <b>cun</b> bo'yicha qo'llanmani oching. U "
                          "kerakli hududni o'z tanangizda topishga yordam beradi; nuqtaning o'zi esa "
                          "barmoqlar, nafas va diqqat orqali aniqlanadi.\n"
                          '\n'
                          "Bu o'zini kuzatish amaliyoti. U shifokor, tashxis yoki davolanish o'rnini "
                          "bosmaydi.",
        'choose_meridian': '☯️ <b>Meridianni tanlang:</b>',
        'current_meridian': '▶️ Amaliyotni davom ettirish',
        'meridian_start_points': '1-nuqtadan boshlash',
        'all_points': 'Barcha nuqtalar',
        'next_point': 'Keyingi nuqta',
        'prev_point': 'Oldingi nuqta',
        'complete_meridian': 'Meridianni yakunlash',
        'select_meridian': 'Meridian tanlash',
        'no_points': "Hozir nuqtalar ochilmadi. Meridianlar ro'yxatiga qayting va u yerdan yana urinib ko'ring.",
        'meridian_completed': (
            "✅ <b>Meridian yakunlandi</b>\n\n"
            "Keyingi kanalga o'tishdan oldin butun kanalni yana bir marta diqqat bilan bosib chiqing: birinchi nuqtadan oxirgisigacha. "
            "Chiziq qayerda iliq va ravshan, qayerda esa uzilib yoki jim qolayotganini sezing.\n\n"
            "Sezgi sokinlashganda keyingi kanalni tanlang."
        ),
        'feature_announcement': "☯️ <b>Journey of Ascension yangilanishi</b>\n"
                                '\n'
                                "Iltimos, yangi botga o'ting: @journey_ascension_bot.\n"
                                "<b>Hozirgi bot tez orada qo'llab-quvvatlanmaydi.</b>\n"
                                '\n'
                                "Eslatmalar ba'zan muntazam kelmasligiga sabab bo'lgan xatolarni ko'rdik va ularni tuzatdik.\n"
                                '\n'
                                "Shuningdek, yangi funksiyani taqdim etishdan xursandmiz: <b>Xitoy meridianlarini o'rganish</b>.\n"
                                "Endi botda meridianni tanlash, umumiy sxema va videoni ko'rish, nuqtalarni "
                                "rasmlari bilan ochish va amaliyotni o'z sur'atingizda davom ettirish mumkin.\n"
                                '\n'
                                "@journey_ascension_bot ni oching va /start ni bosing.",
        'stop_feedback_prompt': "Xohlasangiz, amaliyotni nima uchun pauzaga qo'yayotganingizni bitta qisqa xabarda yozishingiz mumkin. Bu majburiy emas.",
        'stop_feedback_thanks': "Rahmat. Bu eslatma amaliyotni yumshoqroq va tushunarliroq qilishga yordam beradi.\n"
                                '\n'
                                "Qaytmoqchi bo'lsangiz, /start dan foydalaning.",
        'skip_days_improved': "📅 <b>O'tkazib yuboriladigan kunlar (ixtiyoriy)</b>\n"
                              '\n'
                              'Xohlasangiz, bot xabar yubormaydigan hafta kunlarini tanlashingiz mumkin.\n'
                              '\n'
                              "Masalan: <code>5,6</code> — dam olish kunlarini o'tkazib yuborish.\n"
                              'Agar har kuni xabar olishni istasangiz, hech narsa tanlamang.',
        'no_skip_days': '✅ Sokin kunlar tanlanmadi — eslatmalar har kuni kelishi mumkin',
        'feedback_prompt': '💌 <b>Fikr va takliflar</b>\n'
                           '\n'
                           "Tajribangiz muhim. Nima foydali bo'lganini, nima tushunarsiz qolganini yoki "
                           'amaliyotni nima qulayroq qilishini yozing.',
        'feedback_sent': '✅ Rahmat. Fikringiz yuborildi.',
        'timezone_manual_prompt': 'Vaqt mintaqasini IANA formatida kiriting.\n'
                                  '\n'
                                  'Misollar: Asia/Tashkent, Europe/Moscow, Asia/Almaty, UTC'},
 'kz': {'welcome': '🕊️ <b>Journey of Ascension ботына қош келдіңіз!</b>\n'
                   '\n'
                   'Яма мен Нияма ішкі тәжірибенің адамгершілік негізі болып қалады. Меридиандар — келесі '
                   'саты: зейін, дене және энергияны тікелей бақылау арқылы сезуді үйрену.\n'
                   '\n'
                   'Алдымен тілді таңдайық:',
        'language_chosen': '✅ Тіл қазақшаға орнатылды.',
        'timezone_step': '📍 Уақыт белдеуі\n'
                         '\n'
                         'Еске салулар дұрыс жергілікті уақытта келуі үшін уақыт белдеуіңізді таңдаңыз.',
        'timezone_custom': '⌨️ Қолмен енгізу',
        'timezone_saved': '✅ Уақыт белдеуі сақталды.',
        'time_step': '🧘🏻 <b>Яма/Нияма еске салу уақыты</b>\n'
                     '\n'
                     'Бот күнделікті қағиданы қашан жіберетінін таңдаңыз. Тұрақты уақыт тәжірибені '
                     'күнделікті өмірге енгізуге көмектеседі.\n'
                     '\n'
                     'Формат: HH:MM, мысалы 08:00 немесе 20:30.',
        'time_saved': '✅ Еске салу уақыты сақталды.',
        'skip_days_step': '📅 <b>Тыныш күндер</b>\n'
                          '\n'
                          'Бот күнделікті тәжірибе еске салуларын жібермейтін апта күндерін таңдаңыз.\n'
                          '\n'
                          'Күн сайынғы ырғақ керек болса, күндерді таңдамаңыз.',
        'setup_complete': '🎉 <b>Алғашқы қадам бапталды.</b>\n'
                          '\n'
                          '📋 <b>Ырғағыңыз:</b>\n'
                          '🕐 Уақыт: {time}\n'
                          '🌍 Уақыт белдеуі: {timezone}\n'
                          '📅 Тыныш күндер: {skip_days}\n'
                          '\n'
                          'Тізімдерді ашу, ырғақты өзгерту немесе келесі шағын қадамды жалғастыру үшін /menu қолданыңыз.',
        'already_subscribed': '🕊️ Journey of Ascension бұл жерде бұрыннан ашық.\n'
                              '\n'
                              'Тәжірибелерді таңдау үшін /menu немесе тәжірибе ырғағын реттеу үшін /settings '
                              'қолданыңыз.',
        'unsubscribed': 'Тәжірибе ырғағы тоқтатылды. Күнделікті еске салулар әзірге келмейді.\n'
                        '\n'
                        'Қайта оралғыңыз келсе, /start қолданыңыз.',
        'not_subscribed': 'Бұл чатта тәжірибе әлі басталмаған. Бастауға дайын болсаңыз, /start қолданыңыз.',
        'current_settings': '⚙️ <b>Қазіргі тәжірибе ырғағы</b>',
        'not_subscribed_test': 'Тәжірибе ырғағы әлі бапталмаған. Бастау үшін /start қолданыңыз.',
        'test_failed': 'Қазір еске салуды тексеру хабарын жібере алмадым. Сәл кейін қайталап көріңіз.',
        'invalid_timezone': '❌ Бұл уақыт белдеуін тани алмадым. Asia/Almaty, Asia/Tashkent, Europe/Moscow '
                            'немесе UTC сияқты форматты қолданып көріңіз.',
        'invalid_time': '❌ Бұл уақытты тани алмадым. HH:MM форматын қолданыңыз, мысалы 08:00 немесе 20:30.',
        'invalid_skip_days': '❌ Күндерді тани алмадым. 0-ден 6-ға дейінгі сандарды үтірмен енгізіңіз.',
        'setup_error': '❌ Әзірге баптауларды сақтай алмадым. Қайтадан көріңіз: тәжірибе ырғағын тыныш әрі нақты қойған жақсы.',
        'error': 'Жол үзіліп қалды. Қайтадан көріңіз немесе /menu бөліміне оралыңыз.',
        'choose_language': 'Ботты қай тілде қолданғыңыз келетінін таңдаңыз:',
        'english': '🇺🇸 English',
        'russian': '🇷🇺 Русский',
        'uzbek': "🇺🇿 O'zbek",
        'kazakh': '🇰🇿 Қазақша',
        'menu': '📋 <b>Journey of Ascension</b>',
        'menu_settings': '⚙️ Тәжірибе ырғағы',
        'menu_test': '🧪 Еске салуды тексеру',
        'menu_announce_update': '📢 Жаңартуды жіберу',
        'sending_test': '🧪 Еске салу тексеруі жіберіліп жатыр...',
        'menu_about': 'ℹ️ Бот туралы',
        'menu_feedback': '💌 Пікірлер мен ұсыныстар',
        'menu_stop': '⏸ Тәжірибені паузаға қою',
        'settings_menu': '⚙️ <b>Тәжірибе ырғағы</b>\n'
                         '\n'
                         'Мұнда тәжірибе ырғағын реттейсіз: бот нені еске салады, хабарлар қашан келеді және '
                         'қай күндер тыныш қалады.',
        'change_language': '🌐 Тіл',
        'change_time': '🧘🏻 Яма/Нияма уақыты',
        'change_timezone': '🌍 Уақыт белдеуі',
        'change_skip_days': '📅 Тыныш күндер',
        'back_to_menu': '🔙 Мәзірге қайту',
        'about_text': '🕊️ <b>Journey of Ascension</b>\n'
                      '\n'
                      'Бұл бот күнделікті өмірде тәжірибеге қайта оралуға көмектеседі: күн сайын бір анық фокус.\n'
                      '\n'
                      'Күн сайын ол сізді бір нақты фокусқа қайтарады: Яма/Нияма қағидасына немесе меридиан '
                      'нүктесіне. Мақсат қарапайым: энергияның қайда бейсаналы жұмсалып жатқанын көру, оны '
                      'босқа шашпау және зейінді ұқыптырақ бағыттауды үйрену.\n'
                      '\n'
                      '<b>Яма/Нияма</b> мінез-құлықпен, сөзбен, оймен, тәртіппен және өзіңізге адал болумен '
                      'жұмыс істейді.\n'
                      '\n'
                      '<b>Меридиандар</b> дене арқылы жұмыс істейді: арналар, нүктелер, Ци ағымы, жабық '
                      'аймақтар, тыныс, жанасу және зейін.\n'
                      '\n'
                      'Кішкентай қайталаулар маңызды. Олар идеяны өмірде қолдануға болатын дағдыға '
                      'айналдырады.',
        'feedback_too_long': '❌ Хабар тым ұзын. 1000 таңбадан асырмаңыз.',
        'feedback_rate_limit': '⏰ Келесі пікірді жібермес бұрын сәл күтіңіз.',
        'feedback_error': '❌ Пікіріңізді сақтау мүмкін болмады. Кейінірек қайталап көріңіз.',
        'onboarding_intro': '<b>Journey of Ascension</b>\n'
                            '\n'
                            'Тәжірибе энергияның қайда кетіп жатқанын байқаудан басталады. Ол шашыраса, '
                            'зейін шулайды; жиналса, әрекет тынышырақ әрі айқынырақ болады.\n'
                            '\n'
                            '<b>Яма мен Нияма</b> — негіз: олар энергияның сөз, ой, әдет және реакция '
                            'арқылы шашылуын азайтады. <b>Ахимса</b> күшті зиянға жұмсамаудан басталады.\n'
                            '\n'
                            '<b>Меридиандар</b> тәжірибені денеге әкеледі. Сіз арналар, нүктелер және '
                            'жанасу, тыныс пен сабырлы зейін сұрайтын аймақтарды сезесіз.\n'
                            '\n'
                            'Нені зерттегіңіз келеді?',
        'initial_mode_question': 'Нені зерттегіңіз келеді?',
        'timezone_step_principles': '📍 <b>1/3-қадам: Уақыт белдеуі</b>\n'
                                    '\n'
                                    'Бот <b>Яма/Нияма</b> еске салуларын сіздің жергілікті уақытыңызбен '
                                    'жіберуі үшін уақыт белдеуіңізді таңдаңыз.',
        'timezone_step_meridians': '📍 <b>1/3-қадам: Уақыт белдеуі</b>\n'
                                   '\n'
                                   'Бот <b>меридиандар</b> туралы материалдар мен еске салуларды сіздің '
                                   'жергілікті уақытыңызбен жіберуі үшін уақыт белдеуіңізді таңдаңыз.',
        'timezone_step_both': '📍 <b>1/3-қадам: Уақыт белдеуі</b>\n'
                              '\n'
                              'Бот <b>Яма/Нияма</b> және <b>меридиандар</b> бойынша еске салуларды сіздің '
                              'жергілікті уақытыңызбен жіберуі үшін уақыт белдеуіңізді таңдаңыз.',
        'time_step_principles': '⏰ <b>2/3-қадам: Жіберу уақыты</b>\n'
                                '\n'
                                'Бот күнделікті <b>Яма/Нияма</b> қағидасын қашан жіберетінін таңдаңыз.\n'
                                '\n'
                                'Формат: HH:MM, мысалы 08:00 немесе 20:30.',
        'time_step_meridians': '⏰ <b>2/3-қадам: Жіберу уақыты</b>\n'
                               '\n'
                               'Бот күнделікті <b>меридиан</b> фокусын қашан жіберетінін таңдаңыз.\n'
                               '\n'
                               'Формат: HH:MM, мысалы 08:00 немесе 20:30.',
        'time_step_both': '⏰ <b>2/3-қадам: Жіберу уақыты</b>\n'
                          '\n'
                          'Бот күнделікті <b>Яма/Нияма</b> қағидасын және <b>меридиан</b> фокусын қашан '
                          'жіберетінін таңдаңыз.\n'
                          '\n'
                          'Формат: HH:MM, мысалы 08:00 немесе 20:30.',
        'continue_setup': 'Жалғастыру',
        'menu_principles': '🧘🏻✨ Яма/Нияма',
        'menu_meridians': '☯️ Меридиандар',
        'menu_modes': '🧭 Менің жолым',
        'principles_menu': '🕊️ <b>Яма/Нияма</b>\n'
                           '\n'
                           'Бұл классикалық йоганың алғашқы екі сатысы және тәжірибенің адамгершілік '
                           'негізі.\n'
                           '\n'
                           '<b>Яма</b> әлеммен қарым-қатынаста энергияны сақтайды: зиян келтірмеу, '
                           'шыншылдық, ұрламау, ұстамдылық және дүниеқоңыздықтан арылу.\n'
                           '\n'
                           '<b>Нияма</b> энергияны іште жинайды: тазалық, қанағат, тәртіп, өзін-өзі зерттеу '
                           'және тәжірибе жемісін жоғары мақсатқа арнау.\n'
                           '\n'
                           'Күн қағидасы қалған қағидалардың орнына келмейді; ол бақылауға арналған екпін '
                           'ғана. Біз олардың бәрін өмірге біртіндеп енгіземіз, ал әр күні біреуі анығырақ '
                           'көрінеді.\n'
                           '\n'
                           'Бүгінгі қағиданы ашыңыз немесе толық тізімді көріңіз.',
        'principles_random': 'Кездейсоқ қағида',
        'principles_all': 'Барлық қағидалар',
        'principles_back': '🔙 Яма/Ниямаға қайту',
        'principles_empty': 'Қазір қағидалар ашылмады. Яма/Ниямаға оралыңыз немесе /menu арқылы қайта көріңіз.',
        'change_modes': '🧭 Менің жолым',
        'change_meridian_time': '☯️ Меридиан уақыты',
        'mode_menu': '🧭 <b>Менің жолым</b>\n'
                     '\n'
                     'Күн сайын қай тәжірибеге қайта оралғыңыз келетінін таңдаңыз.\n'
                     '\n'
                     '<b>Яма/Нияма</b> — негіз: ішкі шу азаяды, энергия шығыны азаяды, әрекетте адалдық '
                     'көбейеді.\n'
                     '\n'
                     '<b>Меридиандар</b> — дене қабаты: нүктелер, арналар, Ци ағымы және бастапқыда көмескі '
                     'сезілетін жерлерді сабырмен зейінге қосу дағдысы.\n'
                     '\n'
                     'Бір бағыттан бастауға немесе екеуін де белсенді қалдыруға болады.',
        'mode_principles_only': 'Яма/Нияма негізі',
        'mode_meridians_only': 'Меридиандарды зерттеу',
        'mode_both': 'Екі бағыт та',
        'mode_saved': '✅ <b>Жолыңыз жаңартылды.</b>',
        'meridian_time_step': '☯️ <b>Меридиан еске салу уақыты</b>\n'
                              '\n'
                              'Уақытты HH:MM форматында енгізіңіз, мысалы 20:00.',
        'meridian_time_saved': '✅ Меридиан еске салу уақыты сақталды.',
        'meridian_mode_menu': '☯️ <b>Меридиандарды зерттеу жолын таңдаңыз</b>\n'
                              '\n'
                              '<b>Бот бағыты</b> жаңадан бастаған адамға ыңғайлы: бір арна, бір нүкте, '
                              'бір тыныш қадам. Меридиан аяқталса, келесісі ашылады.\n'
                              '\n'
                              '<b>Еркін таңдау</b> белгілі бір меридиан назарыңызды тартса немесе нені '
                              'зерттегіңіз келетінін білсеңіз ыңғайлы.\n'
                              '\n'
                              'Жолды кейін өзгертуге болады. Прогресс пен еске салулар сақталады.',
        'meridian_guided_path': '🧭 Бот бағыты',
        'meridian_free_choice': '👐 Еркін таңдау',
        'meridian_change_path': '🧭 Бастау немесе жол таңдау',
        'meridian_guided_saved': '✅ <b>Бот бағыты таңдалды.</b>\n'
                                 '\n'
                                 'Баяу қозғаламыз: бір меридиан, бір нүкте, бір тұрақты сезім.',
        'meridian_free_saved': '✅ <b>Еркін таңдау таңдалды.</b>\n'
                               '\n'
                               'Қазір зерттегіңіз келетін меридианды таңдаңыз.',
        'meridian_measurements': '📏 Цуньді өлшеу',
        'meridian_point_help': '🖐 Нүктені табу',
        'meridian_back': '🔙 Меридиандарға қайту',
        'page_indicator_hint': 'Бұл бет нөмірі. Өту үшін Артқа немесе Келесі түймесін қолданыңыз.',
        'meridian_measurements_text': '📏 <b>ҚКМ-дегі өлшем жүйесі</b>\n'
                                      '\n'
                                      '<b>Бұл не үшін керек:</b> нүкте сипаттамаларында “1 цунь”, “1,5 '
                                      'цунь”, “3 цунь” сияқты өлшемдер жиі кездеседі. Бұл анықтама оларды өз '
                                      'денеңізден табуға көмектеседі.\n'
                                      '\n'
                                      'Акупунктура нүктелерінің орналасуы жиі <b>цунь</b> арқылы '
                                      'сипатталады. Цунь — нақты сантиметр емес, зерттеліп отырған адамның '
                                      'денесіне қатысты өлшем.\n'
                                      '\n'
                                      '<b>0,5 цунь:</b> жеке 1 цунь өлшеміңіздің жартысы. Өте кіші '
                                      'қашықтықтарға қолданыңыз, кейін нүктені сезім арқылы нақтылаңыз.\n'
                                      '\n'
                                      '<b>1 цунь:</b> бас бармақтың буын тұсындағы ені.\n'
                                      '\n'
                                      '<b>1,5 цунь:</b> екі саусақтың ені: сұқ және ортаңғы саусақ.\n'
                                      '\n'
                                      '<b>2 цунь:</b> үш саусақтың ені: сұқ, ортаңғы және аты жоқ саусақ.\n'
                                      '\n'
                                      '<b>3 цунь:</b> төрт саусақтың ені: сұқ саусақтан шынашаққа дейін.\n'
                                      '\n'
                                      '<b>5 цунь:</b> 3 цунь өлшеп, шамамен 2 цунь қосыңыз немесе дереккөз '
                                      'пропорциялық қашықтық берсе, анатомиялық бөлікті тең бөліктерге '
                                      'бөліңіз.\n'
                                      '\n'
                                      '<b>Маңызды:</b> цунь әрқашан жұмыс істеп отырған адамның денесіне '
                                      'қарай өлшенеді. Сондықтан сіздің денеңіздегі 1 цунь мен басқа адамның '
                                      'денесіндегі 1 цунь сантиметрмен әртүрлі болуы мүмкін.\n'
                                      '\n'
                                      'Цуньді бағдар ретінде қолданыңыз, кейін нүктені дене арқылы '
                                      'нақтылаңыз: жергілікті сезімталдық, шағын ойыс, жылу, қысым немесе '
                                      'зейінге айқын жауап.',
        'meridian_point_help_text': '🖐 <b>Нүктені қалай табу керек</b>\n'
                                    '\n'
                                    'Алдымен сурет пен цунь өлшемдері арқылы шамамен орынды табыңыз. '
                                    'Содан кейін баяулап, нақты нүктені дене сезімі арқылы анықтаңыз.\n'
                                    '\n'
                                    '<b>1.</b> Аймаққа жұмсақ тиіп, кішкентай ойыс, сезімталдық, жылу, қысым '
                                    'немесе зейін оңай ілінетін орынды іздеңіз.\n'
                                    '\n'
                                    '<b>2.</b> Егер нүкте үнсіз болса, оны әзірге ашылмаған деп қабылдаңыз: '
                                    'ұзағырақ болыңыз, жеңіл уқалаңыз (⚠ белгісі бар нүктелерден басқа) және сол нүкте арқылы тыныс алуды '
                                    'елестетіңіз.\n'
                                    '\n'
                                    '<b>3.</b> Нәтижені күштемеңіз. Тыныш әрі тұрақты сезім жеткілікті.\n'
                                    '\n'
                                    'Келесі нүктеге өткенде алдыңғыларды фонда сезіп, жаңа нүктені сол зейін '
                                    'сызығына қосыңыз.',
        'meridians_menu': '☯️ <b>Меридиандар</b>\n'
                          '\n'
                          '<b>Меридиандарды не үшін зерттейміз?</b>\n'
                          '\n'
                          'Қытай дәстүрінде меридиандар Ци қозғалатын жолдар ретінде сипатталады. '
                          'Тәжірибеде бұл өте нақты сезіледі: дене қай жерде зейінге жауап береді, қай '
                          'жерде кернеу бар, қай жерде сезім әзірге әлсіз екенін байқайсыз.\n'
                          '\n'
                          '<b>Бұл қалай көмектеседі:</b> зейін, тыныс және жұмсақ жанасу нүктеге '
                          'сезімталдықты біртіндеп қайтарады. Аймақ жылырақ, айқынырақ болып, арнаның '
                          'жалпы сызығымен оңайырақ байланыса бастауы мүмкін.\n'
                          '\n'
                          '<b>Қалай бастау:</b> тыныш реттілік керек болса, бот бағытын таңдаңыз. Қай '
                          'меридианды зерттегіңіз келетінін білсеңіз, еркін таңдауды таңдаңыз.\n'
                          '\n'
                          '<b>Нүктелерге дейін:</b> <b>цунь</b> нұсқаулығын ашыңыз. Ол керек аймақты өз '
                          'денеңізден табуға көмектеседі, ал нақты нүктені саусақ, тыныс және зейін арқылы '
                          'нақтылайсыз.\n'
                          '\n'
                          'Бұл өзін-өзі бақылау тәжірибесі. Ол дәрігерді, диагнозды немесе емді '
                          'алмастырмайды.',
        'choose_meridian': '☯️ <b>Меридианды таңдаңыз:</b>',
        'current_meridian': '▶️ Тәжірибені жалғастыру',
        'meridian_start_points': '1-нүктеден бастау',
        'all_points': 'Барлық нүктелер',
        'next_point': 'Келесі нүкте',
        'prev_point': 'Алдыңғы нүкте',
        'complete_meridian': 'Меридианды аяқтау',
        'select_meridian': 'Меридиан таңдау',
        'no_points': 'Қазір нүктелер ашылмады. Меридиандар тізіміне оралып, сол жерден қайта көріңіз.',
        'meridian_completed': (
            "✅ <b>Меридиан аяқталды</b>\n\n"
            "Келесі арнаға өтпес бұрын, бүкіл арнаны зейінмен тағы бір рет өтіңіз: бірінші нүктеден соңғысына дейін. "
            "Сызық қай жерде жылы әрі анық, қай жерде әзірге үзіліп немесе үнсіз қалатынын байқаңыз.\n\n"
            "Сезім тынышталған кезде келесі арнаны таңдаңыз."
        ),
        'feature_announcement': '☯️ <b>Journey of Ascension жаңартуы</b>\n'
                                '\n'
                                'Өтінеміз, жаңа ботқа өтіңіз: @journey_ascension_bot.\n'
                                '<b>Қазіргі бот жақында қолдауды тоқтатады.</b>\n'
                                '\n'
                                'Еске салғыштар кейде тұрақты келмеуіне себеп болған қателерді байқадық және оларды түзеттік.\n'
                                '\n'
                                'Сондай-ақ жаңа мүмкіндікті қуана ұсынамыз: <b>қытай меридиандарын зерттеу</b>.\n'
                                'Енді ботта меридианды таңдап, жалпы схемасы мен видеосын көруге, нүктелерді '
                                'суреттерімен ашуға және тәжірибені өз қарқыныңызбен жалғастыруға болады.\n'
                                '\n'
                                '@journey_ascension_bot ашып, /start басыңыз.',
        'stop_feedback_prompt': 'Қаласаңыз, тәжірибені не үшін паузаға қойып жатқаныңызды бір қысқа хабарламамен жаза аласыз. Бұл міндетті емес.',
        'stop_feedback_thanks': 'Рақмет. Бұл жазба тәжірибені жұмсағырақ әрі түсініктірек етуге көмектеседі.\n'
                                '\n'
                                'Қайта оралғыңыз келсе, /start қолданыңыз.',
        'skip_days_improved': '📅 <b>Өткізіп жіберілетін күндер (міндетті емес)</b>\n'
                              '\n'
                              'Қаласаңыз, бот хабар жібермейтін апта күндерін таңдай аласыз.\n'
                              '\n'
                              'Мысалы: <code>5,6</code> — демалыс күндерін өткізіп жіберу.\n'
                              'Күн сайын хабар алғыңыз келсе, ештеңе таңдамаңыз.',
        'no_skip_days': '✅ Тыныш күндер таңдалмады — еске салулар күн сайын келуі мүмкін',
        'feedback_prompt': '💌 <b>Пікірлер мен ұсыныстар</b>\n'
                           '\n'
                           'Тәжірибеңіз маңызды. Не пайдалы болғанын, не түсініксіз қалғанын немесе '
                           'тәжірибені не ыңғайлырақ ететінін жазыңыз.',
        'feedback_sent': '✅ Рақмет. Пікіріңіз жіберілді.',
        'timezone_manual_prompt': 'Уақыт белдеуін IANA форматында енгізіңіз.\n'
                                  '\n'
                                  'Мысалдар: Asia/Almaty, Asia/Tashkent, Europe/Moscow, UTC'}}

# Admin texts (always in English, no Markdown to avoid parsing errors)
ADMIN_TEXTS = {
    "next_principle": "📋 Random principle for user {user_id}:\n\n{principle}\n\n💡 Principles are chosen randomly for each user",
    "no_principles": "No available principles for user {user_id}.",
    "add_disabled": (
        "Content editing is disabled in chat.\n\n"
        "Principles must stay synchronized across all four languages, with image, group, description, and practice text. "
        "Update bot/principles.json in the repository and run the UX audits before release."
    ),
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
    "resend_today_start": "Resending today's reminders to {count} active users...",
    "resend_today_result": (
        "Today's reminders resent.\n\n"
        "Users reached: {reached}\n"
        "Deliveries sent: {deliveries}\n"
        "Users with errors: {failed}\n"
        "Active users: {total}"
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
    "progress_usage": "Usage: /progress [limit] (default: 30, max: 100)",
    "admin_help": (
        "🔧 Admin Commands:\n\n"
        "📊 Statistics:\n"
        "• /stats - Bot usage statistics\n"
        "• /feedback_stats - Feedback statistics\n"
        "• /feedback_list [limit] - View recent feedback\n"
        "• /progress [limit] - View users' meridian progress and secret tasks\n"
        "• /subscribers - Who is subscribed, with links to their Telegram profiles\n\n"
        "📨 Messages:\n"
        "• /next - Show random principle for user\n"
        "• /resend_today - Resend today's practices to all active users\n"
        "• /broadcast <message> - Send message to all users\n"
        "• /broadcast meridians_announcement - Send localized meridians announcement\n\n"
        "All commands are admin-only and require proper permissions."
    )
}

TEXTS_UPDATE = {
    "en": {
        "welcome": (
            "🕊️ <b>Welcome to Journey of Ascension!</b>\n\n"
            "Yama and Niyama are the ethical foundation of inner practice. "
            "Meridians are the next step: learning to feel attention, body, and energy through direct observation.\n\n"
            "Let's start with choosing your preferred language:"
        ),
        "onboarding_intro": (
            "<b>Journey of Ascension</b>\n\n"
            "Yama and Niyama teach you not to waste strength in thought, speech and action; meridians bring the same work into the body, where you learn to notice points and lines with attention and breath. "
            "You can start with one path, add the other later in the menu, and open the 3D map below even before choosing.\n\n"
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
            "📍 <b>Step 1/4: Time Zone</b>\n\n"
            "Choose your time zone so the bot can send <b>Yama/Niyama</b> and <b>meridian</b> reminders at the correct local time for you."
        ),
        "time_step_principles": (
            "⏰ <b>Step 2/3: Reminder Time</b>\n\n"
            "Choose the time when the bot should send your daily <b>Yama/Niyama</b> principle."
        ),
        "time_step_meridians": (
            "⏰ <b>Step 2/3: Reminder Time</b>\n\n"
            "Choose the time when the bot should send your daily <b>meridian</b> focus."
        ),
        "time_step_both": (
            "⏰ <b>Step 2/4: Reminder Time</b>\n\n"
            "First choose the time for your daily <b>Yama/Niyama</b> principle. The meridian reminder time comes next."
        ),
        "continue_setup": "Continue",
        "menu": "📋 <b>Journey of Ascension</b>",
        "menu_principles": "🧘🏻✨ Yama/Niyama",
        "menu_meridians": "☯️ Meridians",
        "menu_modes": "🧭 My Path",
        "menu_stop": "⏸ Pause practice",
        "settings_menu": (
            "⚙️ <b>Practice rhythm</b>\n\n"
            "This is where you keep the practice comfortable: choose the active path, set separate reminder times, and leave quiet days when you need more space.\n\n"
            "Change only what genuinely helps your rhythm stay steady."
        ),
        "change_language": "🌐 Language",
        "change_time": "🕊️ Yama/Niyama Time",
        "change_timezone": "🌍 Time Zone",
        "change_skip_days": "📅 Quiet Days",
        "time_step": (
            "🕊️ <b>Yama/Niyama Reminder Time</b>\n\n"
            "Choose when the bot should send the daily principle. A steady time helps the practice become part of ordinary life.\n\n"
            "Format: HH:MM, for example 08:00 or 20:30."
        ),
        "skip_days_step": (
            "📅 <b>Quiet Days</b>\n\n"
            "Choose the weekdays when the bot should stay silent and <b>not</b> send daily practice reminders.\n\n"
            "If you want reminders every day, choose <b>No quiet days</b>. If you want every day except Sunday, select only Sunday."
        ),
        "principles_menu": (
            "🕊️ <b>Yama/Niyama</b>\n\n"
            "These are the first two limbs of classical yoga. They are not a list of nice ideas; they are a training of how not to waste energy through speech, habits, reactions, desires, and inner disorder.\n\n"
            "<b>Yama</b> works with your contact with the world: non-harm, truthfulness, non-stealing, moderation, and non-possessiveness. It teaches you to stop losing force in conflict, pressure, comparison, and grabbing.\n\n"
            "<b>Niyama</b> works with your inner ground: purity, contentment, discipline, self-study, and surrender of the fruits of action. It gathers attention back into a cleaner rhythm.\n\n"
            "The daily principle is only the accent of the day. It does not mean you practise Ahimsa today and forget it tomorrow. We keep all principles in life at once; each day one of them comes closer to the surface.\n\n"
            "Open one principle for today or view the full list."
        ),
        "useful_materials": "📚 Useful materials",
        "useful_materials_soon": (
            "📚 <b>Useful materials</b>\n\n"
            "Coming Soon.\n\n"
            "Later this section will contain links to articles and other materials for deeper study."
        ),
        "meridian_materials_text": (
            "📚 <b>Useful materials</b>\n\n"
            "<b>Types of standard acupuncture points</b>\n\n"
            "Classical permanent meridians contain from 9 to 67 acupuncture points; the traditional total is 361 points. The paired meridians I-XII have standard points that differ by their effect.\n\n"
            "<b>Tonifying points</b> activate the meridian and support the work of the related internal organs.\n\n"
            "<b>Sedating points</b> calm excessive activity, soften internal tension, and help release nervous overstrain.\n\n"
            "<b>Assistant points</b> strengthen the action of a tonifying or sedating point and, depending on the method of stimulation, can sometimes replace them.\n\n"
            "<b>Stabilizing points</b> help balance energy between paired meridians.\n\n"
            "<b>Alarm points</b> help assess the functional state of a meridian and its related organ. Some are located on their own meridian, others outside it.\n\n"
            "Acupuncture points on the classical permanent meridians are also divided into distal and proximal groups. Distal points are below the elbow and knee joints; proximal points are all the others. Distal points usually have a wider range of indications.\n\n"
            "<b>The points that begin and end meridians are considered especially effective.</b>\n\n"
            "<b>What happens when energy circulation in meridians is disturbed?</b>\n\n"
            "According to classical Chinese acupuncture theory, the work of the organs depends on internal energy. In a healthy state, energy circulates freely through Yang and Yin meridians and remains in harmony. When a pathological process develops, this harmony is disturbed: some meridians may show excess, while others may show deficiency. Correct work with acupuncture points is traditionally used to help restore balanced energy circulation.\n\n"
            "<b>Examples of excess energy</b> may include arterial hypertension, gastritis with increased acidity, spastic constipation, lung conditions accompanied by bronchospasm, muscle hypertonicity, and impaired circulation in the lower limbs caused by vascular spasm.\n\n"
            "<b>Examples of energy deficiency</b> may include arterial hypotension, gastritis with low acidity, atonic constipation, paresis and paralysis, muscle atrophy, and chronic conditions that lead to exhaustion and reduced protective reserves.\n\n"
            "<i>This material is for study and self-observation. It does not replace medical diagnosis or treatment.</i>\n\n"
            "<b>Methods of influencing acupuncture points</b>\n\n"
            "In acupuncture, the effect depends not only on the point, but also on the method of influence. Traditionally, two approaches are described: a stimulating, or tonifying, method and an inhibiting, or sedating, method. In the first case, energy is added to the meridian; in the second, excessive activity is reduced.\n\n"
            "<b>Tonifying method:</b> the needle is inserted quickly, its tip is directed along the meridian, and rotation is performed clockwise. Usually more points are used. The needles remain for a short time, from 30 seconds to 2-10 minutes, and are removed slowly.\n\n"
            "<b>Sedating method:</b> the needle is directed against the flow of energy in the meridian and rotated counterclockwise. Usually fewer points are used. Sessions are longer: from 20-40 minutes to several hours. The needles are removed with a quick movement.\n\n"
            "In real treatment, the method, duration, and number of sessions are chosen individually by a qualified specialist after consultation and examination.\n\n"
            "<b>Term note:</b> proximal means closer to the center of the body or to the median line; distal means farther from the center. For example, the shoulder is the proximal part of the arm, while the hand is distal."
        ),
        "meridian_materials_menu": "📚 <b>Useful materials</b>\n\nChoose what to open.",
        "meridian_materials_basics": "Basic articles",
        "meridian_materials_shu": "Five shu-points",
        "principles_random": "Random principle",
        "principles_all": "All principles",
        "principles_back": "🔙 Back to Yama/Niyama",
        "principles_empty": "The principles did not open right now. Please return to Yama/Niyama or try again from /menu.",
        "change_modes": "🧭 My Path",
        "change_meridian_time": "☯️ Meridian Time",
        "mode_menu": (
            "🧭 <b>My Path</b>\n\n"
            "Choose the rhythm that is honest for you now. The point is not to take on more than you can carry; the point is to return regularly and not lose the thread.\n\n"
            "<b>Yama/Niyama</b> keeps the foundation active: less energy spent on conflict, haste, excess, self-harm, and automatic reactions.\n\n"
            "<b>Meridians</b> adds the body layer: points, channels, Qi flow, and patient work with places that are still hard to feel.\n\n"
            "<b>Both directions</b> works well when you want ethics and body awareness to support each other every day."
        ),
        "mode_principles_only": "Yama/Niyama foundation",
        "mode_meridians_only": "Meridian study",
        "mode_both": "Both directions",
        "mode_saved": "✅ <b>Your path has been updated.</b>",
        "meridian_time_step": "☯️ <b>Meridian Reminder Time</b>\n\nEnter time in HH:MM format, for example 20:00.",
        "meridian_time_setup_step": (
            "☯️ <b>Step 3/4: Meridian Reminder Time</b>\n\n"
            "Now choose when the bot should return you to the current meridian or point. This can be a different time from the Yama/Niyama principle."
        ),
        "meridian_time_saved": "✅ Meridian reminder time saved.",
        "meridian_mode_menu": (
            "☯️ <b>Choose your meridian study path</b>\n\n"
            "<b>Bot route</b> is good when you are new: one channel, one point, one calm step at a time. After completing a meridian, the next one opens naturally.\n\n"
            "<b>Free choice</b> is good when a specific meridian is calling your attention or you already know what you want to study.\n\n"
            "You can change this later. Your progress and reminders stay saved."
        ),
        "meridian_guided_path": "🧭 Bot route",
        "meridian_free_choice": "👐 Free choice",
        "meridian_change_path": "🧭 Start / choose path",
        "meridian_guided_saved": "✅ <b>Bot route selected.</b>\n\nWe will move gently: one meridian, one point, one stable sensation at a time.",
        "meridian_free_saved": "✅ <b>Free choice selected.</b>\n\nChoose the meridian you want to explore now.",
        "meridian_measurements": "📏 Measure cun",
        "meridian_measurements_image_caption": "📏 <b>Cun at a glance</b>\nLook at this first: it shows how to estimate 1, 1.5, 2, 3, and 5 cun on the hand.",
        "meridian_point_help": "🖐 How to find a point",
        "meridian_video": "🎥 Meridian video",
        "meridian_video_caption": "🎥 <b>Meridian video</b>\nWatch the channel path, then return to the point practice and check what is easier to feel in the body.",
        "meridian_video_missing": "🎥 <b>Meridian video</b>\n\nThe video for this meridian will be added later. For now, continue with the image, point description, and attention practice.",
        "meridian_back": "🔙 Back to meridians",
        "back_to_current_focus": "🔙 Back to current focus",
        "page_indicator_hint": "This is the page number. Use Previous or Next to move.",
        "meridian_measurements_text": (
            "📏 <b>Measurement System in TCM</b>\n\n"
            "<b>Why this matters:</b> point descriptions often say “1 cun”, “1.5 cun”, “3 cun”, and so on. Without a body-based measure, these numbers stay abstract; with cun, you can at least get into the right area.\n\n"
            "Acupuncture point locations are often described in <b>cun</b>. A cun is not a fixed centimeter value: it is a body-relative unit measured on the person being studied.\n\n"
            "<b>0.5 cun:</b> half of your personal 1 cun. Use it for very small distances and refine by touch.\n\n"
            "<b>1 cun:</b> the width of the thumb at the interphalangeal joint.\n\n"
            "<b>1.5 cun:</b> the width of the index and middle fingers together.\n\n"
            "<b>2 cun:</b> the width of three fingers together: index, middle, and ring finger.\n\n"
            "<b>3 cun:</b> the width of four fingers together, from index to little finger.\n\n"
            "<b>5 cun:</b> measure 3 cun and add about 2 cun, or divide the anatomical segment into equal parts if the source gives a proportional distance.\n\n"
            "<b>Important:</b> cun is always measured on the body of the person you are working with. For example, 1 cun on your body and 1 cun on another person's body can be different in centimeters.\n\n"
            "First get close by cun. Then slow down and let the body clarify the exact place: local sensitivity, a small hollow, warmth, pressure, or a clearer response to attention."
        ),
        "meridian_point_help_text": (
            "🖐 <b>How to find a point</b>\n\n"
            "Use the picture and cun measurements to get into the right area. The exact point is found more slowly: by touch, breath, and attention.\n\n"
            "<b>1.</b> Touch the area gently. Look for a small hollow, sensitivity, warmth, pressure, or a place where attention holds more easily.\n\n"
            "<b>2.</b> If the point is hard to feel, treat it as not yet open for practice. Stay longer, gently massage it (except points marked ⚠), and imagine breathing in and out through this place.\n\n"
            "<b>3.</b> Do not force a result. A quiet, steady sensation is enough.\n\n"
            "When you move to the next point, keep the previous ones in the background and add the new point to the same line of attention."
        ),
        "meridians_menu": (
            "☯️ <b>Meridians</b>\n\n"
            "<b>Why study meridians?</b>\n\n"
            "In Chinese tradition, meridians are the channels through which Qi moves. For practice, this is not a theory to believe in blindly. It is a way to observe the body: where sensation is clear, where the line breaks, where a point feels warm, tense, empty, or silent.\n\n"
            "<b>What you train:</b> attention, breath, and gentle touch. A point that does not answer at first can be treated as closed for now: stay longer, massage it lightly (except points marked ⚠), breathe through it with attention, and wait until the sensation becomes steadier.\n\n"
            "<b>How to move:</b> each new point is added to the previous ones. First feel point 1. Then keep it in the background and add point 2. Over time the meridian becomes one living line rather than separate dots.\n\n"
            "<b>Choose a path:</b> use the bot route if you want a calm sequence from the beginning, or free choice if a specific meridian already draws your attention.\n\n"
            "<b>Before points:</b> open the <b>cun</b> guide. It helps you find the area; the exact point is refined with fingers, breath, and attention.\n\n"
            "This is self-observation and inner discipline. It does not replace medical diagnosis or treatment."
        ),
        "choose_meridian": (
            "☯️ <b>Choose a meridian</b>\n\n"
            "This is free choice mode. Pick the channel you want to study now; it will become your current practice focus."
        ),
        "current_meridian": "▶️ Continue practice",
        "meridian_start_points": "Start with point 1",
        "all_points": "All points",
        "next_point": "Next point",
        "prev_point": "Previous point",
        "complete_meridian": "Complete meridian",
        "select_meridian": "Choose meridian",
        "no_points": "The points did not open right now. Return to the meridian list and try again from there.",
        "meridian_completed": (
            "✅ <b>Meridian completed</b>\n\n"
            "Before moving on, pass through the whole channel once more with attention: from the first point to the last. "
            "Notice where the line feels warm and clear, and where it still breaks or goes silent.\n\n"
            "When the sensation becomes calmer, choose the next channel."
        ),
        "meridian_route_completed": (
            "✅ <b>The meridian route is complete</b>\n\n"
            "You have passed through all meridians in the bot route. Do not rush to start again. Spend a few days returning to the channels that felt least clear: they usually show where attention is still learning to stay.\n\n"
            "When you are ready, choose any meridian freely or start the route again."
        ),
        "about_text": (
            "🕊️ <b>Journey of Ascension</b>\n\n"
            "This bot is made for people who want spiritual practice to become part of real life: not only something to read about, and not something remembered after the day has already carried you away.\n\n"
            "Here energy means what you can actually notice: attention, vitality, steadiness, warmth in the body, and the ability to act without draining yourself. When energy goes into conflict, hurry, resentment, excess, self-harm, or neglect, you feel it in the mind and in the body.\n\n"
            "<b>Yama/Niyama</b> gives the foundation: daily principles that help close those leaks through behaviour, speech, thought, discipline, and honesty with yourself.\n\n"
            "<b>Meridians</b> give the body layer: channels, points, Qi flow, sensitive and closed areas, breath, touch, and the habit of patiently returning attention to the same place.\n\n"
            "The bot does one simple job: it keeps the thread of practice from disappearing in the noise of the day and shows the next small step."
        ),
        "feature_announcement": (
            "☯️ <b>Journey of Ascension update</b>\n\n"
            "Please move to the new bot: @journey_ascension_bot.\n"
            "<b>This current bot will stop being supported soon.</b>\n\n"
            "We noticed bugs that could make reminders arrive irregularly, and we fixed them.\n\n"
            "We are also happy to present a new feature: <b>Chinese meridian study</b>.\n"
            "Now you can choose a meridian, view its overview image and video, open points with images, and move through the practice at your own pace.\n\n"
            "Open @journey_ascension_bot and press /start."
        ),
        "already_subscribed": "🕊️ Journey of Ascension is already open here.\n\nUse /menu to choose practices or /settings to tune your practice rhythm.",
        "not_subscribed": "The practice is not started in this chat yet. Use /start when you are ready to begin.",
        "unsubscribed": "The practice rhythm is paused. Daily reminders will stay silent for now.\n\nUse /start if you want to return.",
        "stop_feedback_prompt": "If you want, you can leave one short note about why you are pausing the practice. This is optional.",
        "stop_feedback_skip": "No note",
        "stop_feedback_skipped": "Done. No note is needed.\n\nUse /start if you want to return.",
        "stop_feedback_thanks": "Thank you. Your note will help make the practice gentler and clearer.\n\nUse /start if you want to return.",
        "not_subscribed_test": "The practice rhythm is not set yet. Use /start to begin.",
        "setup_complete": (
            "🎉 <b>The first step is set.</b>\n\n"
            "📋 <b>Your rhythm:</b>\n"
            "🕐 Time: {time}\n"
            "🌍 Time Zone: {timezone}\n"
            "📅 Quiet Days: {skip_days}\n\n"
            "Use /menu when you want to open the lists, adjust the rhythm, or continue the next small step."
        )
    },
    "ru": {
        "welcome": (
            "🕊️ <b>Добро пожаловать в Journey of Ascension!</b>\n\n"
            "Яма и Нияма остаются нравственным фундаментом внутренней практики. "
            "Меридианы — следующая ступень: учиться чувствовать внимание, тело и энергию через прямое наблюдение.\n\n"
            "Начнём с выбора языка:"
        ),
        "onboarding_intro": (
            "<b>Journey of Ascension</b>\n\n"
            "Яма и Нияма учат не растрачивать силы в мыслях, речи и поступках, а меридианы переносят ту же работу в тело: вы учитесь замечать точки и линии вниманием и дыханием. "
            "Можно начать с одного пути, второй добавить позже в меню, а 3D-карту ниже открыть и до выбора.\n\n"
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
            "📍 <b>Шаг 1/4: Часовой пояс</b>\n\n"
            "Выберите ваш часовой пояс, чтобы бот присылал напоминания по <b>Яме/Нияме</b> и материалы по <b>меридианам</b> в правильное для вас местное время."
        ),
        "time_step_principles": (
            "⏰ <b>Шаг 2/3: Время отправки</b>\n\n"
            "Укажите время, когда бот будет присылать ежедневный принцип <b>Ямы/Ниямы</b>."
        ),
        "time_step_meridians": (
            "⏰ <b>Шаг 2/3: Время отправки</b>\n\n"
            "Укажите время, когда бот будет присылать ежедневный фокус по <b>меридианам</b>."
        ),
        "time_step_both": (
            "⏰ <b>Шаг 2/4: Время отправки</b>\n\n"
            "Сначала укажите время для ежедневного принципа <b>Ямы/Ниямы</b>. Время меридианов выберем следующим шагом."
        ),
        "continue_setup": "Продолжить",
        "menu": "📋 <b>Journey of Ascension</b>",
        "menu_principles": "🧘🏻✨ Яма/Нияма",
        "menu_meridians": "☯️ Меридианы",
        "menu_modes": "🧭 Мой путь",
        "menu_stop": "⏸ Пауза практики",
        "settings_menu": (
            "⚙️ <b>Ритм практики</b>\n\n"
            "Здесь вы держите практику удобной: выбираете активный путь, настраиваете отдельные времена напоминаний и оставляете дни тишины, когда нужно больше пространства.\n\n"
            "Меняйте только то, что действительно помогает ритму оставаться живым и устойчивым."
        ),
        "change_language": "🌐 Язык",
        "change_time": "🕊️ Время Ямы/Ниямы",
        "change_timezone": "🌍 Часовой пояс",
        "change_skip_days": "📅 Дни тишины",
        "time_step": (
            "🕊️ <b>Время напоминания по Яме/Нияме</b>\n\n"
            "Выберите, когда бот будет присылать ежедневный принцип. Постоянное время помогает практике войти в обычную жизнь.\n\n"
            "Формат: ЧЧ:ММ, например 08:00 или 20:30."
        ),
        "skip_days_step": (
            "📅 <b>Дни тишины</b>\n\n"
            "Выберите дни недели, когда бот должен молчать и <b>не</b> присылать ежедневные напоминания по практике.\n\n"
            "Если хотите получать напоминания каждый день, выберите <b>Без дней тишины</b>. Если хотите получать во все дни, кроме воскресенья, выберите только воскресенье."
        ),
        "principles_menu": (
            "🕊️ <b>Яма/Нияма</b>\n\n"
            "Это первые две ступени классической йоги. Тренировка того, как сохранять энергию через управление речью, мыслями, своими желаниями и реакциями.\n\n"
            "<b>Яма</b> работает с вашим контактом с миром: бережное отношение к себе и миру, правдивость, признание и уважение чужих ценностей, умеренность и нестяжательство. Она учит сохранять силу и энергию.\n\n"
            "<b>Нияма</b> работает с внутренней опорой: чистота, удовлетворённость, дисциплина, самоизучение и посвящение плодов практики высшему. Она собирает внимание в более чистый ритм.\n\n"
            "Принцип дня — это только акцент. Это не значит, что сегодня мы практикуем Ахимсу, а завтра забываем о ней. Мы держим все принципы в жизни одновременно; просто каждый день один из них выходит ближе к поверхности.\n\n"
            "Откройте принцип дня или посмотрите весь список."
        ),
        "useful_materials": "📚 Полезные материалы",
        "useful_materials_soon": (
            "📚 <b>Полезные материалы</b>\n\n"
            "Coming Soon.\n\n"
            "Позже здесь будут ссылки на статьи и другие материалы для более глубокого изучения."
        ),
        "meridian_materials_text": (
            "📚 <b>Полезные материалы</b>\n\n"
            "<b>Виды стандартных акупунктурных точек</b>\n\n"
            "На постоянных классических меридианах находится от 9 до 67 акупунктурных точек; традиционное общее количество — 361 точка. Парные меридианы I-XII имеют стандартные точки, которые различаются по воздействию.\n\n"
            "<b>Тонизирующие точки</b> активизируют меридиан и поддерживают работу соответствующих внутренних органов.\n\n"
            "<b>Седативные точки</b> оказывают успокаивающее действие, снижают чрезмерную активность внутренних органов и помогают снять нервное напряжение.\n\n"
            "<b>Точки-пособники</b> усиливают действие тонизирующей или успокаивающей точки, а в зависимости от метода воздействия могут заменять их.\n\n"
            "<b>Стабилизирующие точки</b> помогают удерживать равновесие энергии в парных меридианах.\n\n"
            "<b>Сигнальные точки</b>, или точки тревоги, помогают определить функциональное состояние меридиана и связанного с ним органа. Одни находятся на своём меридиане, другие — за его пределами.\n\n"
            "Точки на постоянных классических меридианах также делят на дистальные и проксимальные. Дистальные расположены ниже локтевых и коленных суставов, проксимальные — все остальные. У дистальных точек обычно более широкий перечень показаний.\n\n"
            "<b>Наиболее эффективными считаются точки, которыми начинаются и заканчиваются меридианы.</b>\n\n"
            "<b>К чему приводит нарушение циркуляции энергии в меридианах?</b>\n\n"
            "Согласно древнекитайской теории акупунктуры, деятельность органов зависит от внутренней энергии. У здорового человека энергия в меридианах Ян и Инь циркулирует свободно и находится в гармонии. При развитии патологического процесса гармония нарушается: в одних меридианах возникает избыток, а в других — недостаток энергии. Правильное воздействие на точки иглорефлексотерапии традиционно используется для восстановления нормальной циркуляции энергии.\n\n"
            "<b>Примеры избытка энергии</b>: артериальная гипертония, гастрит с повышенной кислотностью, спастические запоры, заболевания лёгких с бронхоспазмом, гипертонус мышц, нарушение кровообращения в нижних конечностях вследствие спазма сосудов.\n\n"
            "<b>Примеры недостатка энергии</b>: артериальная гипотония, гастрит с пониженной кислотностью, атонические запоры, парезы и параличи, мышечная атрофия, хронические заболевания, которые приводят к истощению и снижению защитных сил организма.\n\n"
            "<i>Материал дан для изучения и самонаблюдения. Он не заменяет медицинскую диагностику и лечение.</i>\n\n"
            "<b>Методы воздействия на акупунктурные точки</b>\n\n"
            "В иглорефлексотерапии эффект зависит не только от выбранной точки, но и от метода воздействия. Традиционно выделяют два подхода: возбуждающий, или тонизирующий, и тормозящий, или седативный. В первом случае в меридиан как бы добавляют энергию, во втором — снижают чрезмерную активность.\n\n"
            "<b>Тонизирующий метод:</b> иглу вводят быстро, её кончик направляют по ходу меридиана, вращение выполняют по часовой стрелке. Обычно воздействуют на большее количество точек. Иглы оставляют ненадолго: от 30 секунд до 2-10 минут, извлекают медленно.\n\n"
            "<b>Седативный метод:</b> иглу направляют против течения энергии в меридиане и вращают против часовой стрелки. Обычно воздействуют на меньшее количество точек. Сеансы более продолжительные: от 20-40 минут до нескольких часов. Иглы извлекают быстрым движением.\n\n"
            "В реальном лечении методика, длительность и количество сеансов подбираются индивидуально квалифицированным специалистом после консультации и обследования.\n\n"
            "<b>Пояснение термина:</b> проксимальный означает расположенный ближе к центру тела или к срединной линии; дистальный — дальше от центра. Например, плечо — проксимальный отдел руки, а кисть — дистальный."
        ),
        "meridian_materials_menu": "📚 <b>Полезные материалы</b>\n\nВыберите, что открыть.",
        "meridian_materials_basics": "Базовые статьи",
        "meridian_materials_shu": "Пять шу-точек",
        "principles_random": "Случайный принцип",
        "principles_all": "Все принципы",
        "principles_back": "🔙 К Яме/Нияме",
        "principles_empty": "Сейчас принципы не открылись. Вернитесь к Яме/Нияме или попробуйте снова из /menu.",
        "change_modes": "🧭 Мой путь",
        "change_meridian_time": "☯️ Время меридианов",
        "mode_menu": (
            "🧭 <b>Мой путь</b>\n\n"
            "Выберите ритм, который сейчас честно подходит вам. Задача не в том, чтобы взять на себя слишком много, а в том, чтобы регулярно возвращаться и не терять нить практики.\n\n"
            "<b>Яма/Нияма</b> держит фундамент: меньше энергии уходит в конфликт, спешку, излишества, вред себе и автоматические реакции.\n\n"
            "<b>Меридианы</b> добавляют телесный слой: точки, каналы, течение Ци и терпеливую работу с местами, которые пока трудно почувствовать.\n\n"
            "<b>Оба направления</b> подойдут, если вы хотите, чтобы этика и телесное внимание поддерживали друг друга каждый день."
        ),
        "mode_principles_only": "Фундамент Ямы/Ниямы",
        "mode_meridians_only": "Изучение меридианов",
        "mode_both": "Оба направления",
        "mode_saved": "✅ <b>Ваш путь обновлён.</b>",
        "meridian_time_step": "☯️ <b>Время напоминания по меридианам</b>\n\nВведите время в формате ЧЧ:ММ, например 20:00.",
        "meridian_time_setup_step": (
            "☯️ <b>Шаг 3/4: Время меридианов</b>\n\n"
            "Теперь выберите, когда бот будет возвращать вас к текущему <b>меридиану</b> или точке. Это время может отличаться от времени принципа Ямы/Ниямы."
        ),
        "meridian_time_saved": "✅ Время напоминаний по меридианам сохранено.",
        "meridian_mode_menu": (
            "☯️ <b>Выберите путь изучения меридианов</b>\n\n"
            "<b>Маршрут бота</b> подойдёт, если вы только начинаете: один канал, одна точка, один спокойный шаг за раз. Завершили меридиан — открылся следующий.\n\n"
            "<b>Свободный выбор</b> подойдёт, если внимание уже тянется к конкретному меридиану или вы знаете, что хотите изучить.\n\n"
            "Путь можно изменить позже. Прогресс и напоминания сохраняются."
        ),
        "meridian_guided_path": "🧭 Маршрут бота",
        "meridian_free_choice": "👐 Свободный выбор",
        "meridian_change_path": "🧭 Начать или выбрать путь",
        "meridian_guided_saved": "✅ <b>Выбран маршрут бота.</b>\n\nБудем двигаться мягко: один меридиан, одна точка, одно устойчивое ощущение за раз.",
        "meridian_free_saved": "✅ <b>Выбран свободный выбор.</b>\n\nВыберите меридиан, который хотите исследовать сейчас.",
        "meridian_measurements": "📏 Как измерять цуни",
        "meridian_measurements_image_caption": "📏 <b>Цуни наглядно</b>\nСначала посмотрите на эту схему: она показывает, как примерно отмерять 1, 1,5, 2, 3 и 5 цуней по руке.",
        "meridian_point_help": "🖐 Как искать точку",
        "meridian_video": "🎥 Видео меридиана",
        "meridian_video_caption": "🎥 <b>Видео меридиана</b>\nПосмотрите ход канала, а затем вернитесь к практике точек и проверьте, что стало легче почувствовать в теле.",
        "meridian_video_missing": "🎥 <b>Видео меридиана</b>\n\nВидео для этого меридиана добавим позже. Пока продолжайте по схеме, описанию точки и практике внимания.",
        "meridian_back": "🔙 К меридианам",
        "back_to_current_focus": "🔙 К текущему фокусу",
        "page_indicator_hint": "Это номер страницы. Для перехода используйте «Назад» или «Далее».",
        "meridian_measurements_text": (
            "📏 <b>Система измерений в ТКМ</b>\n\n"
            "<b>Зачем это нужно:</b> в описаниях точек часто встречается «1 цунь», «1,5 цуня», «3 цуня» и так далее. Без телесной меры это остаётся абстракцией; с цунями вы хотя бы попадаете в нужную область.\n\n"
            "Расположение акупунктурных точек часто описывается в <b>цунях</b>. Цунь — это не фиксированное число сантиметров, а относительная мера тела конкретного человека.\n\n"
            "<b>0,5 цуня:</b> половина вашего личного 1 цуня. Используйте для очень малых расстояний и затем уточняйте точку через ощущения.\n\n"
            "<b>1 цунь:</b> ширина большого пальца в области межфалангового сустава.\n\n"
            "<b>1,5 цуня:</b> ширина двух пальцев вместе — указательного и среднего.\n\n"
            "<b>2 цуня:</b> ширина трёх пальцев вместе — указательного, среднего и безымянного.\n\n"
            "<b>3 цуня:</b> ширина четырёх сомкнутых пальцев — от указательного до мизинца.\n\n"
            "<b>5 цуней:</b> можно отмерить 3 цуня и добавить около 2 цуней, либо разделить нужный анатомический участок на равные части, если источник даёт пропорциональное расстояние.\n\n"
            "<b>Важно:</b> цунь всегда измеряется по телу того человека, с которым вы работаете. Поэтому 1 цунь на вашем теле и 1 цунь на теле другого человека могут отличаться в сантиметрах.\n\n"
            "Сначала приблизьтесь по цуням. Потом замедлитесь и уточняйте точку через тело: локальную чувствительность, небольшое углубление, тепло, давление или более ясный отклик на внимание."
        ),
        "meridian_point_help_text": (
            "🖐 <b>Как искать точку</b>\n\n"
            "По изображению и цуням найдите нужную область. Саму точку ищите медленнее: пальцами, дыханием и вниманием.\n\n"
            "<b>1.</b> Мягко касайтесь зоны. Ищите небольшое углубление, чувствительность, тепло, давление или место, где внимание удерживается легче.\n\n"
            "<b>2.</b> Если точка почти не ощущается, считайте её пока закрытой для практики. Побудьте с ней дольше, мягко помассируйте (кроме точек со значком ⚠) и представляйте вдох и выдох через это место.\n\n"
            "<b>3.</b> Не выжимайте результат. Достаточно тихого устойчивого ощущения.\n\n"
            "Когда переходите к следующей точке, не бросайте предыдущие: удерживайте их фоном и добавляйте новую в ту же линию внимания."
        ),
        "meridians_menu": (
            "☯️ <b>Меридианы</b>\n\n"
            "<b>Зачем изучать меридианы?</b>\n\n"
            "В китайской традиции меридианы — это каналы, по которым движется Ци. Один из способов практиковать — наблюдать тело: где ощущение ясное, где линия обрывается, где точка тёплая или холодная, напряжённая или расслабленная, пустая или «молчит».\n\n"
            "<b>Что мы тренируем:</b> внимание, дыхание и мягкое касание. Если точка сначала «не отвечает», можно считать её пока «закрытой» для практики: задержитесь дольше, легко помассируйте (кроме точек со значком ⚠), подышите через неё вниманием и дождитесь более устойчивого ощущения.\n\n"
            "<b>Как двигаться:</b> каждая новая точка добавляется к предыдущим. Сначала почувствуйте первую. Потом удерживайте её фоном в своём внимании и добавляйте вторую. Постепенно меридиан становится одной живой линией, по которой вы начнёте чувствовать движение Ци.\n\n"
            "<b>Выберите путь:</b> маршрут бота подойдёт, если пока не знаете, с чего начать. Свободный выбор — если вы опытный практик и привыкли всё проверять на своём личном опыте.\n\n"
            "<b>Перед точками:</b> откройте справку по <b>цуням</b>. Она помогает найти область, а точное место уточняется пальцами, дыханием и вниманием.\n\n"
            "<i>Это практика самонаблюдения и внутренней дисциплины. Она не заменяет медицинскую диагностику и лечение.</i>"
        ),
        "choose_meridian": (
            "☯️ <b>Выберите меридиан</b>\n\n"
            "Это режим свободного выбора. Нажмите на канал, который хотите изучать сейчас; он станет текущим фокусом практики."
        ),
        "current_meridian": "▶️ Продолжить практику",
        "meridian_start_points": "Начать с первой точки",
        "all_points": "Все точки",
        "next_point": "Следующая точка",
        "prev_point": "Предыдущая точка",
        "complete_meridian": "Завершить меридиан",
        "select_meridian": "Выбрать меридиан",
        "no_points": "Сейчас точки не открылись. Вернитесь к списку меридианов и попробуйте ещё раз оттуда.",
        "meridian_completed": (
            "✅ <b>Меридиан завершён</b>\n\n"
            "Перед тем как идти дальше, пройдите вниманием весь канал ещё раз: от первой точки до последней. "
            "Заметьте, где линия тёплая и ясная, а где она пока обрывается или молчит.\n\n"
            "Когда ощущение станет спокойнее, выбирайте следующий канал."
        ),
        "meridian_route_completed": (
            "✅ <b>Маршрут меридианов завершён</b>\n\n"
            "Вы прошли все меридианы в маршруте бота. Не спешите сразу начинать заново. Несколько дней возвращайтесь к каналам, которые ощущались менее ясно: обычно именно они показывают, где вниманию ещё нужно научиться держаться.\n\n"
            "Когда будете готовы, выберите любой меридиан свободно или начните маршрут заново."
        ),
        "about_text": (
            "🕊️ <b>Journey of Ascension</b>\n\n"
            "Этот бот для тех, кто хочет, чтобы духовная практика входила в реальную жизнь: не оставалась только текстом для чтения и не вспоминалась вечером, когда день уже унёс вас по привычным реакциям.\n\n"
            "Энергия здесь — то, что можно заметить: внимание, живость, устойчивость, тепло в теле и способность действовать, не опустошая себя. Когда энергия уходит в конфликт, спешку, обиду, излишества, вред себе или невнимание к себе, это чувствуется и в уме, и в теле.\n\n"
            "<b>Яма/Нияма</b> даёт фундамент: ежедневные принципы помогают закрывать эти утечки через поведение, речь, мысли, дисциплину и честность перед собой.\n\n"
            "<b>Меридианы</b> дают телесный слой: каналы, точки, течение Ци, чувствительные и закрытые зоны, дыхание, касание и привычку терпеливо возвращать внимание в одно и то же место.\n\n"
            "Задача бота простая: не дать нити практики исчезнуть в шуме дня и показать следующий небольшой шаг."
        ),
        "feature_announcement": (
            "☯️ <b>Обновление Journey of Ascension</b>\n\n"
            "Пожалуйста, переходите в нового бота: @journey_ascension_bot.\n"
            "<b>Текущий бот скоро перестанет поддерживаться.</b>\n\n"
            "Мы заметили ошибки, из-за которых напоминания могли приходить нерегулярно, и исправили их.\n\n"
            "Также мы рады представить новую функцию: <b>изучение китайских меридианов</b>.\n"
            "Теперь в боте можно выбрать меридиан, посмотреть общую схему и видео, открыть точки с изображениями и двигаться по практике в своём темпе.\n\n"
            "Откройте @journey_ascension_bot и нажмите /start."
        ),
        "already_subscribed": "🕊️ Journey of Ascension уже открыт здесь.\n\nИспользуйте /menu для выбора практик или /settings для настройки ритма практики.",
        "not_subscribed": "Практика в этом чате ещё не запущена. Используйте /start, когда будете готовы начать.",
        "unsubscribed": "Ритм практики остановлен. Ежедневные напоминания пока будут молчать.\n\nЕсли захотите вернуться, используйте /start.",
        "stop_feedback_prompt": "Если хотите, можете одним сообщением написать, почему ставите практику на паузу. Это необязательно.",
        "stop_feedback_skip": "Без заметки",
        "stop_feedback_skipped": "Готово. Заметка не нужна.\n\nЕсли захотите вернуться, используйте /start.",
        "stop_feedback_thanks": "Спасибо. Эта заметка поможет сделать практику мягче и понятнее.\n\nЕсли захотите вернуться, используйте /start.",
        "not_subscribed_test": "Ритм практики ещё не настроен. Используйте /start, чтобы начать.",
        "setup_complete": (
            "🎉 <b>Первый шаг настроен.</b>\n\n"
            "📋 <b>Ваш ритм:</b>\n"
            "🕐 Время: {time}\n"
            "🌍 Часовой пояс: {timezone}\n"
            "📅 Дни тишины: {skip_days}\n\n"
            "Используйте /menu, когда захотите открыть списки, изменить ритм или продолжить следующий небольшой шаг."
        )
    },
    "uz": {
        "welcome": (
            "🕊️ <b>Journey of Ascension botiga xush kelibsiz!</b>\n\n"
            "Yama va Niyama ichki amaliyotning axloqiy poydevori bo'lib qoladi. "
            "Meridianlar keyingi bosqich: diqqat, tana va energiyani bevosita kuzatish orqali sezishni o'rganish.\n\n"
            "Avval tilni tanlaymiz:"
        ),
        "onboarding_intro": (
            "<b>Journey of Ascension</b>\n\n"
            "Yama va Niyama fikr, so'z va harakatda kuchni behuda sarflamaslikka o'rgatadi, meridianlar esa shu ishni tanaga olib kiradi: nuqta va chiziqlarni diqqat va nafas bilan sezishni o'rganasiz. "
            "Bitta yo'ldan boshlash, ikkinchisini keyin menyuda qo'shish, pastdagi 3D xaritani esa tanlashdan oldin ham ochish mumkin.\n\n"
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
            "📍 <b>1/4-qadam: Vaqt mintaqasi</b>\n\n"
            "Bot <b>Yama/Niyama</b> va <b>meridianlar</b> bo'yicha eslatmalarni sizning mahalliy vaqtingiz bo'yicha yuborishi uchun vaqt mintaqangizni tanlang."
        ),
        "time_step_principles": (
            "⏰ <b>2/3-qadam: Yuborish vaqti</b>\n\n"
            "Bot kundalik <b>Yama/Niyama</b> tamoyilini qachon yuborishini tanlang."
        ),
        "time_step_meridians": (
            "⏰ <b>2/3-qadam: Yuborish vaqti</b>\n\n"
            "Bot kundalik <b>meridian</b> fokusini qachon yuborishini tanlang."
        ),
        "time_step_both": (
            "⏰ <b>2/4-qadam: Yuborish vaqti</b>\n\n"
            "Avval kundalik <b>Yama/Niyama</b> tamoyili vaqtini tanlang. Meridian eslatmasi vaqtini keyingi qadamda tanlaymiz."
        ),
        "continue_setup": "Davom etish",
        "menu": "📋 <b>Journey of Ascension</b>",
        "menu_principles": "🧘🏻✨ Yama/Niyama",
        "menu_meridians": "☯️ Meridianlar",
        "menu_modes": "🧭 Mening yo'lim",
        "menu_stop": "⏸ Amaliyotni pauza qilish",
        "settings_menu": (
            "⚙️ <b>Amaliyot ritmi</b>\n\n"
            "Bu yerda amaliyotni qulay ushlab turasiz: faol yo'lni tanlaysiz, eslatmalar vaqtini alohida sozlaysiz va kerak bo'lsa sokin kunlarni qoldirasiz.\n\n"
            "Faqat ritmingiz barqaror va tirik qolishiga yordam beradigan narsani o'zgartiring."
        ),
        "change_language": "🌐 Til",
        "change_time": "🕊️ Yama/Niyama vaqti",
        "change_timezone": "🌍 Vaqt mintaqasi",
        "change_skip_days": "📅 Sokin kunlar",
        "time_step": (
            "🕊️ <b>Yama/Niyama eslatma vaqti</b>\n\n"
            "Bot kundalik tamoyilni qachon yuborishini tanlang. Barqaror vaqt amaliyotni kundalik hayotga kiritishga yordam beradi.\n\n"
            "Format: HH:MM, masalan 08:00 yoki 20:30."
        ),
        "skip_days_step": (
            "📅 <b>Sokin kunlar</b>\n\n"
            "Bot jim turishi va kundalik amaliyot eslatmalarini <b>yubormasligi</b> kerak bo'lgan hafta kunlarini tanlang.\n\n"
            "Har kuni eslatma olishni istasangiz, <b>Sokin kunlarsiz</b> ni tanlang. Yakshanbadan tashqari har kuni olishni istasangiz, faqat yakshanbani tanlang."
        ),
        "principles_menu": (
            "🕊️ <b>Yama/Niyama</b>\n\n"
            "Bular klassik yoganing birinchi ikki pog'onasi. Bu chiroyli fikrlar ro'yxati emas, balki energiyani so'z, odat, reaksiya, istak va ichki tartibsizlik orqali behuda sarflamaslik mashqidir.\n\n"
            "<b>Yama</b> dunyo bilan munosabatda ishlaydi: zarar yetkazmaslik, rostgo'ylik, o'g'irlamaslik, mo'tadillik va ortiqcha egalik qilmaslik. U kuchni ziddiyat, bosim, taqqoslash va ortiqcha narsaga yopishishda yo'qotmaslikni o'rgatadi.\n\n"
            "<b>Niyama</b> ichki tayanch bilan ishlaydi: poklik, qanoat, intizom, o'zini o'rganish va amaliyot mevasini oliy maqsadga bag'ishlash. U diqqatni tozaroq ritmga yig'adi.\n\n"
            "Kun tamoyili faqat urg'u. Bu bugun Ahimsani mashq qilib, ertaga uni unutamiz degani emas. Biz barcha tamoyillarni hayotda birga ushlab turamiz; har kuni bittasi yuzaga yaqinroq chiqadi.\n\n"
            "Bugungi tamoyilni oching yoki to'liq ro'yxatni ko'ring."
        ),
        "useful_materials": "📚 Foydali materiallar",
        "useful_materials_soon": (
            "📚 <b>Foydali materiallar</b>\n\n"
            "Coming Soon.\n\n"
            "Keyinroq bu yerda chuqurroq o'rganish uchun maqolalar va boshqa materiallarga havolalar bo'ladi."
        ),
        "meridian_materials_text": (
            "📚 <b>Foydali materiallar</b>\n\n"
            "<b>Standart akupunktura nuqtalarining turlari</b>\n\n"
            "Doimiy klassik meridianlarda 9 tadan 67 tagacha akupunktura nuqtasi bo'ladi; an'anaviy umumiy soni 361 ta nuqta deb olinadi. I-XII juft meridianlarda ta'siriga ko'ra farqlanadigan standart nuqtalar bor.\n\n"
            "<b>Tonizatsiya qiluvchi nuqtalar</b> meridianni faollashtiradi va tegishli ichki organlar ishini qo'llab-quvvatlaydi.\n\n"
            "<b>Sedativ nuqtalar</b> ortiqcha faollikni tinchlantiradi, ichki taranglikni yumshatadi va asabiy zo'riqishni kamaytirishga yordam beradi.\n\n"
            "<b>Yordamchi nuqtalar</b> tonizatsiya qiluvchi yoki tinchlantiruvchi nuqtaning ta'sirini kuchaytiradi; ta'sir usuliga qarab ularning o'rnini ham bosishi mumkin.\n\n"
            "<b>Barqarorlashtiruvchi nuqtalar</b> juft meridianlar orasidagi energiya muvozanatini saqlashga yordam beradi.\n\n"
            "<b>Signal nuqtalar</b>, ya'ni xavotir nuqtalari, meridian va unga bog'liq organ holatini baholashga yordam beradi. Ularning ayrimlari o'z meridianida, boshqalari esa undan tashqarida joylashadi.\n\n"
            "Klassik doimiy meridianlardagi nuqtalar distal va proksimal guruhlarga ham bo'linadi. Distal nuqtalar tirsak va tizza bo'g'imlaridan pastda joylashadi; proksimal nuqtalar esa qolgan barcha nuqtalardir. Distal nuqtalarning qo'llanish doirasi odatda kengroq bo'ladi.\n\n"
            "<b>Meridian boshlanadigan va tugaydigan nuqtalar ayniqsa samarali hisoblanadi.</b>\n\n"
            "<b>Meridianlarda energiya aylanishi buzilsa, nima bo'ladi?</b>\n\n"
            "Qadimgi Xitoy akupunktura nazariyasiga ko'ra, organlarning faoliyati ichki energiyaga bog'liq. Sog'lom holatda energiya Yang va Yin meridianlarida erkin aylanadi va uyg'unlikda bo'ladi. Patologik jarayon rivojlanganda bu uyg'unlik buziladi: ayrim meridianlarda ortiqchalik, boshqalarida esa yetishmovchilik paydo bo'lishi mumkin. Akupunktura nuqtalari bilan to'g'ri ishlash an'anaviy ravishda energiya aylanishini muvozanatga qaytarishga yordam beradi deb qaraladi.\n\n"
            "<b>Energiya ortiqchaligiga misollar</b>: arterial gipertoniya, kislotalilik oshgan gastrit, spastik qabziyat, bronxospazm bilan kechadigan o'pka kasalliklari, mushak gipertonusi, tomir spazmi sabab pastki oyoqlarda qon aylanishining buzilishi.\n\n"
            "<b>Energiya yetishmovchiligiga misollar</b>: arterial gipotoniya, kislotalilik pasaygan gastrit, atonik qabziyat, parez va falajlar, mushak atrofiyasi, charchash va himoya kuchlarining pasayishiga olib keladigan surunkali kasalliklar.\n\n"
            "<i>Bu material o'rganish va o'zini kuzatish uchun berilgan. U tibbiy tashxis va davolash o'rnini bosmaydi.</i>\n\n"
            "<b>Akupunktura nuqtalariga ta'sir qilish usullari</b>\n\n"
            "Akupunkturada ta'sir faqat tanlangan nuqtaga emas, balki ta'sir qilish usuliga ham bog'liq. An'anaviy ravishda ikki yondashuv bor: qo'zg'atuvchi yoki tonizatsiya qiluvchi usul va tormozlovchi yoki sedativ usul. Birinchisida meridianga energiya qo'shiladi, ikkinchisida esa ortiqcha faollik pasaytiriladi.\n\n"
            "<b>Tonizatsiya qiluvchi usul:</b> igna tez kiritiladi, uchi meridian yo'nalishi bo'ylab qaratiladi va soat mili bo'yicha aylantiriladi. Odatda ko'proq nuqtalarga ta'sir qilinadi. Ignalar qisqa vaqtga, 30 soniyadan 2-10 daqiqagacha qoldiriladi va sekin chiqariladi.\n\n"
            "<b>Sedativ usul:</b> igna meridiandagi energiya oqimiga qarshi yo'naltiriladi va soat miliga qarshi aylantiriladi. Odatda kamroq nuqtalarga ta'sir qilinadi. Seanslar uzoqroq davom etadi: 20-40 daqiqadan bir necha soatgacha. Ignalar tez harakat bilan chiqariladi.\n\n"
            "Haqiqiy davolashda usul, davomiylik va seanslar soni malakali mutaxassis tomonidan maslahat va tekshiruvdan keyin individual tanlanadi.\n\n"
            "<b>Atama izohi:</b> proksimal tananing markaziga yoki o'rta chiziqqa yaqinroq joylashgan degani; distal esa markazdan uzoqroq degani. Masalan, yelka qo'lning proksimal qismi, kaft esa distal qismidir."
        ),
        "meridian_materials_menu": "📚 <b>Foydali materiallar</b>\n\nNimani ochishni tanlang.",
        "meridian_materials_basics": "Asosiy maqolalar",
        "meridian_materials_shu": "Besh shu-nuqta",
        "principles_random": "Tasodifiy tamoyil",
        "principles_all": "Barcha tamoyillar",
        "principles_back": "🔙 Yama/Niyamaga qaytish",
        "principles_empty": "Hozir tamoyillar ochilmadi. Yama/Niyamaga qayting yoki /menu dan qayta urinib ko'ring.",
        "change_modes": "🧭 Mening yo'lim",
        "change_meridian_time": "☯️ Meridian vaqti",
        "mode_menu": (
            "🧭 <b>Mening yo'lim</b>\n\n"
            "Hozir sizga halol mos keladigan ritmni tanlang. Maqsad ko'p narsani birdan olish emas; maqsad muntazam qaytish va amaliyot ipini yo'qotmaslik.\n\n"
            "<b>Yama/Niyama</b> poydevorni ushlab turadi: ziddiyat, shoshilish, ortiqchalik, o'zingizga zarar va avtomatik reaksiyalarga kamroq energiya ketadi.\n\n"
            "<b>Meridianlar</b> tana qatlamini qo'shadi: nuqtalar, kanallar, Qi oqimi va hali qiyin seziladigan joylar bilan sabrli ishlash.\n\n"
            "<b>Ikkala yo'nalish</b> etika va tana sezgirligi har kuni bir-birini qo'llab-quvvatlashini xohlaganingizda mos keladi."
        ),
        "mode_principles_only": "Yama/Niyama poydevori",
        "mode_meridians_only": "Meridianlarni o'rganish",
        "mode_both": "Ikkala yo'nalish",
        "mode_saved": "✅ <b>Yo'lingiz yangilandi.</b>",
        "meridian_time_step": "☯️ <b>Meridian eslatma vaqti</b>\n\nVaqtni HH:MM formatida kiriting, masalan 20:00.",
        "meridian_time_setup_step": (
            "☯️ <b>3/4-qadam: Meridian eslatma vaqti</b>\n\n"
            "Endi bot sizni joriy meridian yoki nuqtaga qachon qaytarishini tanlang. Bu vaqt Yama/Niyama tamoyili vaqtidan farq qilishi mumkin."
        ),
        "meridian_time_saved": "✅ Meridian eslatma vaqti saqlandi.",
        "meridian_mode_menu": (
            "☯️ <b>Meridianlarni o'rganish yo'lini tanlang</b>\n\n"
            "<b>Bot yo'nalishi</b> yangi boshlaganlar uchun qulay: bir kanal, bir nuqta, bir sokin qadam. Meridian tugagach, keyingisi ochiladi.\n\n"
            "<b>Erkin tanlov</b> ma'lum meridian e'tiboringizni tortsa yoki nimani o'rganmoqchi ekaningizni bilsangiz qulay.\n\n"
            "Yo'lni keyin o'zgartirish mumkin. Progress va eslatmalar saqlanadi."
        ),
        "meridian_guided_path": "🧭 Bot yo'nalishi",
        "meridian_free_choice": "👐 Erkin tanlov",
        "meridian_change_path": "🧭 Boshlash yoki yo'l tanlash",
        "meridian_guided_saved": "✅ <b>Bot yo'nalishi tanlandi.</b>\n\nYumshoq harakat qilamiz: bir meridian, bir nuqta, bir barqaror sezgi.",
        "meridian_free_saved": "✅ <b>Erkin tanlov tanlandi.</b>\n\nHozir o'rganmoqchi bo'lgan meridianni tanlang.",
        "meridian_measurements": "📏 Cunni o'lchash",
        "meridian_measurements_image_caption": "📏 <b>Cun ko'rinishda</b>\nAvval shu sxemaga qarang: u qo'lda 1, 1,5, 2, 3 va 5 cunni taxminan qanday o'lchashni ko'rsatadi.",
        "meridian_point_help": "🖐 Nuqtani topish",
        "meridian_video": "🎥 Meridian videosi",
        "meridian_video_caption": "🎥 <b>Meridian videosi</b>\nKanal yo'lini ko'ring, keyin nuqtalar amaliyotiga qaytib, tanada nimani osonroq sezayotganingizni tekshiring.",
        "meridian_video_missing": "🎥 <b>Meridian videosi</b>\n\nBu meridian videosi keyinroq qo'shiladi. Hozircha rasm, nuqta tavsifi va diqqat amaliyoti bilan davom eting.",
        "meridian_back": "🔙 Meridianlarga qaytish",
        "back_to_current_focus": "🔙 Joriy fokusga qaytish",
        "page_indicator_hint": "Bu sahifa raqami. O'tish uchun Oldingi yoki Keyingi tugmasidan foydalaning.",
        "meridian_measurements_text": (
            "📏 <b>TKMdagi o'lchov tizimi</b>\n\n"
            "<b>Bu nima uchun kerak:</b> nuqta tavsiflarida ko'pincha “1 cun”, “1,5 cun”, “3 cun” kabi o'lchovlar uchraydi. Tana o'lchovi bo'lmasa, bu raqamlar mavhum qoladi; cun esa kerakli joyga yaqinlashishga yordam beradi.\n\n"
            "Akupunktura nuqtalari ko'pincha <b>cun</b> orqali tasvirlanadi. Cun aniq santimetr emas: u o'rganilayotgan odam tanasiga nisbatan olinadigan o'lchovdir.\n\n"
            "<b>0,5 cun:</b> shaxsiy 1 cun o'lchovingizning yarmi. Juda kichik masofalar uchun ishlating va keyin nuqtani sezgi orqali aniqlang.\n\n"
            "<b>1 cun:</b> bosh barmoqning bo'g'im sohasidagi kengligi.\n\n"
            "<b>1,5 cun:</b> ikki barmoq kengligi: ko'rsatkich va o'rta barmoq.\n\n"
            "<b>2 cun:</b> uch barmoq kengligi: ko'rsatkich, o'rta va nomsiz barmoq.\n\n"
            "<b>3 cun:</b> to'rt barmoq kengligi: ko'rsatkichdan kichik barmoqqacha.\n\n"
            "<b>5 cun:</b> 3 cun o'lchab, taxminan 2 cun qo'shing yoki manbada proporsional masofa berilgan bo'lsa, anatomik qismni teng bo'laklarga ajrating.\n\n"
            "<b>Muhim:</b> cun doimo ishlayotgan odamning tanasiga qarab o'lchanadi. Shuning uchun sizdagi 1 cun va boshqa odamdagi 1 cun santimetrda farq qilishi mumkin.\n\n"
            "Avval cun orqali yaqinlashing. Keyin sekinlashib, nuqtani tana orqali aniqlang: mahalliy sezgirlik, kichik chuqurcha, iliqlik, bosim yoki diqqatga ravshanroq javob."
        ),
        "meridian_point_help_text": (
            "🖐 <b>Nuqtani qanday topish kerak</b>\n\n"
            "Rasm va cun o'lchovlari orqali kerakli joyga yaqinlashing. Aniq nuqtani esa sekinroq toping: barmoq, nafas va diqqat bilan.\n\n"
            "<b>1.</b> Joyga yumshoq teging. Kichik chuqurcha, sezgirlik, issiqlik, bosim yoki diqqat osonroq ushlanadigan nuqtani qidiring.\n\n"
            "<b>2.</b> Agar nuqta deyarli sezilmasa, uni amaliyot uchun hali ochilmagan deb qabul qiling. Uzoqroq turing, yengil massaj qiling (⚠ belgisi bor nuqtalardan tashqari) va shu joy orqali nafas olayotganingizni tasavvur qiling.\n\n"
            "<b>3.</b> Natijani majburlamang. Sokin va barqaror sezgi yetarli.\n\n"
            "Keyingi nuqtaga o'tganda oldingilarni fon sifatida sezib, yangi nuqtani shu diqqat chizig'iga qo'shing."
        ),
        "meridians_menu": (
            "☯️ <b>Meridianlar</b>\n\n"
            "<b>Meridianlarni nima uchun o'rganamiz?</b>\n\n"
            "Xitoy an'anasida meridianlar Qi harakat qiladigan kanallar deb tasvirlanadi. Amaliyot uchun bu ko'r-ko'rona ishoniladigan nazariya emas. Bu tanani kuzatish usuli: qayerda sezgi ravshan, qayerda chiziq uziladi, qaysi nuqta iliq, tarang, bo'sh yoki jim.\n\n"
            "<b>Nimani mashq qilamiz:</b> diqqat, nafas va yumshoq teginish. Agar nuqta boshida javob bermasa, uni hozircha amaliyot uchun yopiq deb qabul qiling: uzoqroq turing, yengil massaj qiling (⚠ belgisi bor nuqtalardan tashqari), shu joy orqali diqqat bilan nafas oling va sezgi barqarorroq bo'lishini kuting.\n\n"
            "<b>Qanday harakat qilamiz:</b> har bir yangi nuqta oldingilariga qo'shiladi. Avval birinchi nuqtani sezing. Keyin uni fon sifatida ushlab, ikkinchisini qo'shing. Vaqt o'tishi bilan meridian alohida nuqtalar emas, bitta tirik chiziq bo'lib sezila boshlaydi.\n\n"
            "<b>Yo'lni tanlang:</b> boshidan sokin ketma-ketlik kerak bo'lsa bot yo'nalishini tanlang. Ma'lum meridian e'tiboringizni tortsa, erkin tanlovni tanlang.\n\n"
            "<b>Nuqtalardan oldin:</b> <b>cun</b> bo'yicha qo'llanmani oching. U kerakli sohani topishga yordam beradi; aniq joy esa barmoq, nafas va diqqat bilan aniqlanadi.\n\n"
            "Bu o'zini kuzatish va ichki intizom amaliyoti. U tibbiy tashxis yoki davolanish o'rnini bosmaydi."
        ),
        "choose_meridian": (
            "☯️ <b>Meridianni tanlang</b>\n\n"
            "Bu erkin tanlov rejimi. Hozir o'rganmoqchi bo'lgan kanalni tanlang; u joriy amaliyot fokusiga aylanadi."
        ),
        "current_meridian": "▶️ Amaliyotni davom ettirish",
        "meridian_start_points": "1-nuqtadan boshlash",
        "all_points": "Barcha nuqtalar",
        "next_point": "Keyingi nuqta",
        "prev_point": "Oldingi nuqta",
        "complete_meridian": "Meridianni yakunlash",
        "select_meridian": "Meridian tanlash",
        "no_points": "Hozir nuqtalar ochilmadi. Meridianlar ro'yxatiga qayting va u yerdan yana urinib ko'ring.",
        "meridian_completed": (
            "✅ <b>Meridian yakunlandi</b>\n\n"
            "Keyingi kanalga o'tishdan oldin butun kanalni yana bir marta diqqat bilan bosib chiqing: birinchi nuqtadan oxirgisigacha. "
            "Chiziq qayerda iliq va ravshan, qayerda esa uzilib yoki jim qolayotganini sezing.\n\n"
            "Sezgi sokinlashganda keyingi kanalni tanlang."
        ),
        "meridian_route_completed": (
            "✅ <b>Meridian yo'nalishi yakunlandi</b>\n\n"
            "Bot yo'nalishidagi barcha meridianlardan o'tdingiz. Darhol qayta boshlashga shoshilmang. Bir necha kun kamroq ravshan sezilgan kanallarga qayting: odatda ular diqqat qayerda hali turishni o'rganayotganini ko'rsatadi.\n\n"
            "Tayyor bo'lganda istalgan meridianni erkin tanlang yoki yo'nalishni boshidan boshlang."
        ),
        "about_text": (
            "🕊️ <b>Journey of Ascension</b>\n\n"
            "Bu bot ruhiy amaliyot real hayotga kirishini istaganlar uchun: u faqat o'qiladigan matn bo'lib qolmasin va kun sizni odatiy reaksiyalarga olib ketgandan keyin kechqurun esga tushmasin.\n\n"
            "Bu yerda energiya kuzatiladigan narsa: diqqat, hayotiylik, barqarorlik, tanadagi iliqlik va o'zingizni bo'shatmasdan harakat qilish qobiliyati. Energiya ziddiyat, shoshilish, xafagarchilik, ortiqchalik, o'zingizga zarar yoki o'zingizga e'tiborsizlikka ketsa, bu ongda ham, tanada ham seziladi.\n\n"
            "<b>Yama/Niyama</b> poydevor beradi: kundalik tamoyillar xulq, so'z, fikr, intizom va o'zingizga halollik orqali shu oqimlarni yopishga yordam beradi.\n\n"
            "<b>Meridianlar</b> tana qatlamini beradi: kanallar, nuqtalar, Qi oqimi, sezgir va yopiq joylar, nafas, teginish va diqqatni sabr bilan bir joyga qaytarish odati.\n\n"
            "Botning vazifasi oddiy: amaliyot ipi kun shovqinida yo'qolib ketmasin va keyingi kichik qadam ko'rinib tursin."
        ),
        "feature_announcement": (
            "☯️ <b>Journey of Ascension yangilanishi</b>\n\n"
            "Iltimos, yangi botga o'ting: @journey_ascension_bot.\n"
            "<b>Hozirgi bot tez orada qo'llab-quvvatlanmaydi.</b>\n\n"
            "Eslatmalar ba'zan muntazam kelmasligiga sabab bo'lgan xatolarni ko'rdik va ularni tuzatdik.\n\n"
            "Shuningdek, yangi funksiyani taqdim etishdan xursandmiz: <b>Xitoy meridianlarini o'rganish</b>.\n"
            "Endi botda meridianni tanlash, umumiy sxema va videoni ko'rish, nuqtalarni rasmlari bilan ochish va amaliyotni o'z sur'atingizda davom ettirish mumkin.\n\n"
            "@journey_ascension_bot ni oching va /start ni bosing."
        ),
        "already_subscribed": "🕊️ Journey of Ascension bu yerda allaqachon ochilgan.\n\nAmaliyotlarni tanlash uchun /menu yoki amaliyot ritmini sozlash uchun /settings dan foydalaning.",
        "not_subscribed": "Bu chatda amaliyot hali boshlanmagan. Boshlashga tayyor bo'lsangiz, /start dan foydalaning.",
        "unsubscribed": "Amaliyot ritmi pauzaga qo'yildi. Kundalik eslatmalar hozircha kelmaydi.\n\nQaytmoqchi bo'lsangiz, /start dan foydalaning.",
        "stop_feedback_prompt": "Xohlasangiz, amaliyotni nima uchun pauzaga qo'yayotganingizni bitta qisqa xabarda yozishingiz mumkin. Bu majburiy emas.",
        "stop_feedback_skip": "Izohsiz",
        "stop_feedback_skipped": "Tayyor. Izoh yozish shart emas.\n\nQaytmoqchi bo'lsangiz, /start dan foydalaning.",
        "stop_feedback_thanks": "Rahmat. Bu eslatma amaliyotni yumshoqroq va tushunarliroq qilishga yordam beradi.\n\nQaytmoqchi bo'lsangiz, /start dan foydalaning.",
        "not_subscribed_test": "Amaliyot ritmi hali sozlanmagan. Boshlash uchun /start dan foydalaning.",
        "skip_days_improved": (
            "📅 <b>Sokin kunlar</b>\n\n"
            "Bot jim turishi va kundalik amaliyot eslatmalarini <b>yubormasligi</b> kerak bo'lgan hafta kunlarini tanlang.\n\n"
            "Har kuni eslatma olishni istasangiz, <b>Sokin kunlarsiz</b> ni tanlang. Yakshanbadan tashqari har kuni olishni istasangiz, faqat yakshanbani tanlang."
        ),
        "no_skip_days": "✅ Sokin kunlar tanlanmadi — eslatmalar har kuni yuboriladi",
        "feedback_prompt": (
            "💌 <b>Fikr va takliflar</b>\n\n"
            "Botni yanada qulay, tirik va foydali qilish uchun fikringiz muhim.\n\n"
            "Nima yoqdi? Nima noqulay? Qaysi amaliyot yoki kontent yetishmayapti?\n\n"
            "Bitta xabar bilan yozishingiz mumkin."
        ),
        "feedback_sent": "✅ Rahmat. Fikringiz ishlab chiquvchilarga yuborildi.",
        "setup_complete": (
            "🎉 <b>Birinchi qadam sozlandi.</b>\n\n"
            "📋 <b>Ritmingiz:</b>\n"
            "🕐 Vaqt: {time}\n"
            "🌍 Vaqt mintaqasi: {timezone}\n"
            "📅 Sokin kunlar: {skip_days}\n\n"
            "Ro'yxatlarni ochish, ritmni o'zgartirish yoki keyingi kichik qadamni davom ettirish uchun /menu dan foydalaning."
        )
    },
    "kz": {
        "welcome": (
            "🕊️ <b>Journey of Ascension ботына қош келдіңіз!</b>\n\n"
            "Яма мен Нияма ішкі тәжірибенің адамгершілік негізі болып қалады. "
            "Меридиандар — келесі саты: зейін, дене және энергияны тікелей бақылау арқылы сезуді үйрену.\n\n"
            "Алдымен тілді таңдайық:"
        ),
        "onboarding_intro": (
            "<b>Journey of Ascension</b>\n\n"
            "Яма мен Нияма ойда, сөзде және әрекетте күшті босқа шашпауға үйретеді, ал меридиандар осы жұмысты денеге әкеледі: нүктелер мен сызықтарды зейін мен тыныс арқылы сезуді үйренесіз. "
            "Бір жолдан бастап, екіншісін кейін мәзірден қосуға, ал төмендегі 3D картаны таңдауға дейін де ашуға болады.\n\n"
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
            "📍 <b>1/4-қадам: Уақыт белдеуі</b>\n\n"
            "Бот <b>Яма/Нияма</b> және <b>меридиандар</b> бойынша еске салуларды сіздің жергілікті уақытыңызбен жіберуі үшін уақыт белдеуіңізді таңдаңыз."
        ),
        "time_step_principles": (
            "⏰ <b>2/3-қадам: Жіберу уақыты</b>\n\n"
            "Бот күнделікті <b>Яма/Нияма</b> қағидасын қашан жіберетінін таңдаңыз."
        ),
        "time_step_meridians": (
            "⏰ <b>2/3-қадам: Жіберу уақыты</b>\n\n"
            "Бот күнделікті <b>меридиан</b> фокусын қашан жіберетінін таңдаңыз."
        ),
        "time_step_both": (
            "⏰ <b>2/4-қадам: Жіберу уақыты</b>\n\n"
            "Алдымен күнделікті <b>Яма/Нияма</b> қағидасының уақытын таңдаңыз. Меридиан еске салуының уақытын келесі қадамда таңдаймыз."
        ),
        "continue_setup": "Жалғастыру",
        "menu": "📋 <b>Journey of Ascension</b>",
        "menu_principles": "🧘🏻✨ Яма/Нияма",
        "menu_meridians": "☯️ Меридиандар",
        "menu_modes": "🧭 Менің жолым",
        "menu_stop": "⏸ Тәжірибені паузаға қою",
        "settings_menu": (
            "⚙️ <b>Тәжірибе ырғағы</b>\n\n"
            "Мұнда тәжірибені өзіңізге ыңғайлы ұстайсыз: белсенді жолды таңдайсыз, еске салу уақыттарын бөлек қоясыз және қажет болса тыныш күндер қалдырасыз.\n\n"
            "Ырғақ тірі әрі тұрақты болуына көмектесетін нәрсені ғана өзгертіңіз."
        ),
        "change_language": "🌐 Тіл",
        "change_time": "🕊️ Яма/Нияма уақыты",
        "change_timezone": "🌍 Уақыт белдеуі",
        "change_skip_days": "📅 Тыныш күндер",
        "time_step": (
            "🕊️ <b>Яма/Нияма еске салу уақыты</b>\n\n"
            "Бот күнделікті қағиданы қашан жіберетінін таңдаңыз. Тұрақты уақыт тәжірибені күнделікті өмірге енгізуге көмектеседі.\n\n"
            "Формат: HH:MM, мысалы 08:00 немесе 20:30."
        ),
        "skip_days_step": (
            "📅 <b>Тыныш күндер</b>\n\n"
            "Бот тыныш болып, күнделікті тәжірибе еске салуларын <b>жібермейтін</b> апта күндерін таңдаңыз.\n\n"
            "Еске салуларды күн сайын алғыңыз келсе, <b>Тыныш күндерсіз</b> таңдаңыз. Жексенбіден басқа күн сайын алғыңыз келсе, тек жексенбіні таңдаңыз."
        ),
        "principles_menu": (
            "🕊️ <b>Яма/Нияма</b>\n\n"
            "Бұл классикалық йоганың алғашқы екі сатысы. Әдемі ойлардың тізімі емес, энергияны сөз, әдет, реакция, қалау және ішкі ретсіздік арқылы босқа шашпау жаттығуы.\n\n"
            "<b>Яма</b> әлеммен байланыста жұмыс істейді: зиян келтірмеу, шыншылдық, ұрламау, ұстамдылық және артыққа жабыспау. Ол күшті қақтығысқа, қысымға, салыстыруға және артық нәрсені қармауға жоғалтпауға үйретеді.\n\n"
            "<b>Нияма</b> ішкі тірекпен жұмыс істейді: тазалық, қанағат, тәртіп, өзін-өзі зерттеу және тәжірибе жемісін жоғары мақсатқа арнау. Ол зейінді таза ырғаққа жинайды.\n\n"
            "Күн қағидасы — тек екпін. Бұл бүгін Ахимсаны жасап, ертең оны ұмытамыз деген сөз емес. Біз барлық қағидаларды өмірде бірге ұстаймыз; әр күні біреуі бетке жақынырақ шығады.\n\n"
            "Бүгінгі қағиданы ашыңыз немесе толық тізімді көріңіз."
        ),
        "useful_materials": "📚 Пайдалы материалдар",
        "useful_materials_soon": (
            "📚 <b>Пайдалы материалдар</b>\n\n"
            "Coming Soon.\n\n"
            "Кейінірек мұнда тереңірек зерттеуге арналған мақалалар мен басқа материалдарға сілтемелер болады."
        ),
        "meridian_materials_text": (
            "📚 <b>Пайдалы материалдар</b>\n\n"
            "<b>Стандартты акупунктура нүктелерінің түрлері</b>\n\n"
            "Тұрақты классикалық меридиандарда 9-дан 67-ге дейін акупунктура нүктесі болады; дәстүрлі жалпы саны — 361 нүкте. I-XII жұп меридиандарда әсеріне қарай бөлінетін стандартты нүктелер бар.\n\n"
            "<b>Тонизациялайтын нүктелер</b> меридианды белсендіреді және тиісті ішкі ағзалардың жұмысын қолдайды.\n\n"
            "<b>Седативті нүктелер</b> артық белсенділікті тыныштандырады, ішкі ширығуды жұмсартады және жүйке кернеуін азайтуға көмектеседі.\n\n"
            "<b>Көмекші нүктелер</b> тонизациялайтын немесе тыныштандыратын нүктенің әсерін күшейтеді; әсер ету әдісіне қарай кейде олардың орнын баса алады.\n\n"
            "<b>Тұрақтандырушы нүктелер</b> жұп меридиандардағы энергия тепе-теңдігін сақтауға көмектеседі.\n\n"
            "<b>Сигналдық нүктелер</b>, немесе дабыл нүктелері, меридиан мен оған байланысты ағзаның функционалдық күйін бағалауға көмектеседі. Олардың бір бөлігі өз меридианында, бір бөлігі одан тыс орналасады.\n\n"
            "Классикалық тұрақты меридиандардағы нүктелер дистальды және проксимальды топтарға да бөлінеді. Дистальды нүктелер шынтақ және тізе буындарынан төмен орналасады; проксимальды нүктелер — қалғандарының бәрі. Дистальды нүктелердің қолданылу аясы әдетте кеңірек.\n\n"
            "<b>Меридиан басталатын және аяқталатын нүктелер әсіресе тиімді деп есептеледі.</b>\n\n"
            "<b>Меридиандардағы энергия айналымы бұзылса, не болады?</b>\n\n"
            "Ежелгі қытай акупунктура теориясына сәйкес, ағзалардың қызметі ішкі энергияға байланысты. Сау адамда энергия Ян және Инь меридиандарында еркін айналып, үйлесімде болады. Патологиялық процесс дамығанда бұл үйлесім бұзылады: кейбір меридиандарда артықтық, ал басқаларында жетіспеушілік пайда болуы мүмкін. Акупунктура нүктелерімен дұрыс жұмыс істеу дәстүрлі түрде энергия айналымын теңестіруге көмектеседі деп қарастырылады.\n\n"
            "<b>Энергия артықтығына мысалдар</b>: артериялық гипертония, қышқылдығы жоғары гастрит, спастикалық іш қату, бронхоспазммен жүретін өкпе аурулары, бұлшықет гипертонусы, тамыр спазмы салдарынан төменгі аяқтардағы қан айналымының бұзылуы.\n\n"
            "<b>Энергия жетіспеушілігіне мысалдар</b>: артериялық гипотония, қышқылдығы төмен гастрит, атониялық іш қату, парездер мен салдану, бұлшықет атрофиясы, әлсіреу мен қорғаныс күштерінің төмендеуіне әкелетін созылмалы аурулар.\n\n"
            "<i>Бұл материал оқу және өзін-өзі бақылау үшін берілген. Ол медициналық диагностика мен емдеуді алмастырмайды.</i>\n\n"
            "<b>Акупунктура нүктелеріне әсер ету әдістері</b>\n\n"
            "Акупунктурада әсер тек таңдалған нүктеге ғана емес, әсер ету әдісіне де байланысты. Дәстүрлі түрде екі тәсіл айтылады: қоздырушы, немесе тонизациялайтын әдіс және тежеуші, немесе седативті әдіс. Біріншісінде меридианға энергия қосылады, екіншісінде артық белсенділік төмендетіледі.\n\n"
            "<b>Тонизациялайтын әдіс:</b> ине тез енгізіледі, ұшы меридиан бағытымен бағытталады және сағат тілі бағытымен айналдырылады. Әдетте көбірек нүктеге әсер етеді. Инелер қысқа уақытқа, 30 секундтан 2-10 минутқа дейін қалдырылады және баяу шығарылады.\n\n"
            "<b>Седативті әдіс:</b> ине меридиандағы энергия ағынына қарсы бағытталып, сағат тіліне қарсы айналдырылады. Әдетте аздау нүктеге әсер етеді. Сеанстар ұзағырақ болады: 20-40 минуттан бірнеше сағатқа дейін. Инелер жылдам қозғалыспен шығарылады.\n\n"
            "Нақты емдеуде әдіс, ұзақтық және сеанс саны білікті маманмен кеңес пен тексеруден кейін жеке таңдалады.\n\n"
            "<b>Термин түсіндірмесі:</b> проксимальды — дене орталығына немесе орта сызыққа жақынырақ орналасқан деген сөз; дистальды — орталықтан алысырақ. Мысалы, иық — қолдың проксимальды бөлігі, ал қол басы — дистальды бөлігі."
        ),
        "meridian_materials_menu": "📚 <b>Пайдалы материалдар</b>\n\nНені ашатыныңызды таңдаңыз.",
        "meridian_materials_basics": "Негізгі мақалалар",
        "meridian_materials_shu": "Бес шу-нүкте",
        "principles_random": "Кездейсоқ қағида",
        "principles_all": "Барлық қағидалар",
        "principles_back": "🔙 Яма/Ниямаға қайту",
        "principles_empty": "Қазір қағидалар ашылмады. Яма/Ниямаға оралыңыз немесе /menu арқылы қайта көріңіз.",
        "change_modes": "🧭 Менің жолым",
        "change_meridian_time": "☯️ Меридиан уақыты",
        "mode_menu": (
            "🧭 <b>Менің жолым</b>\n\n"
            "Қазір өзіңізге шын сәйкес келетін ырғақты таңдаңыз. Мақсат — бәрін бірден мойынға алу емес; мақсат — тұрақты оралып, тәжірибе жібін жоғалтпау.\n\n"
            "<b>Яма/Нияма</b> негізді ұстап тұрады: қақтығысқа, асығыстыққа, артықтыққа, өзіңізге зиянға және автоматты реакцияларға аз энергия кетеді.\n\n"
            "<b>Меридиандар</b> дене қабатын қосады: нүктелер, арналар, Ци ағымы және әзірге сезілуі қиын жерлермен сабырлы жұмыс.\n\n"
            "<b>Екі бағыт та</b> этика мен дене зейіні күн сайын бірін-бірі қолдасын десеңіз жарайды."
        ),
        "mode_principles_only": "Яма/Нияма негізі",
        "mode_meridians_only": "Меридиандарды зерттеу",
        "mode_both": "Екі бағыт та",
        "mode_saved": "✅ <b>Жолыңыз жаңартылды.</b>",
        "meridian_time_step": "☯️ <b>Меридиан еске салу уақыты</b>\n\nУақытты HH:MM форматында енгізіңіз, мысалы 20:00.",
        "meridian_time_setup_step": (
            "☯️ <b>3/4-қадам: Меридиан еске салу уақыты</b>\n\n"
            "Енді бот сізді ағымдағы меридианға немесе нүктеге қашан қайтаратынын таңдаңыз. Бұл уақыт Яма/Нияма қағидасының уақытынан бөлек болуы мүмкін."
        ),
        "meridian_time_saved": "✅ Меридиан еске салу уақыты сақталды.",
        "meridian_mode_menu": (
            "☯️ <b>Меридиандарды зерттеу жолын таңдаңыз</b>\n\n"
            "<b>Бот бағыты</b> жаңадан бастаған адамға ыңғайлы: бір арна, бір нүкте, бір тыныш қадам. Меридиан аяқталса, келесісі ашылады.\n\n"
            "<b>Еркін таңдау</b> белгілі бір меридиан назарыңызды тартса немесе нені зерттегіңіз келетінін білсеңіз ыңғайлы.\n\n"
            "Жолды кейін өзгертуге болады. Прогресс пен еске салулар сақталады."
        ),
        "meridian_guided_path": "🧭 Бот бағыты",
        "meridian_free_choice": "👐 Еркін таңдау",
        "meridian_change_path": "🧭 Бастау немесе жол таңдау",
        "meridian_guided_saved": "✅ <b>Бот бағыты таңдалды.</b>\n\nБаяу қозғаламыз: бір меридиан, бір нүкте, бір тұрақты сезім.",
        "meridian_free_saved": "✅ <b>Еркін таңдау таңдалды.</b>\n\nҚазір зерттегіңіз келетін меридианды таңдаңыз.",
        "meridian_measurements": "📏 Цуньді өлшеу",
        "meridian_measurements_image_caption": "📏 <b>Цунь көрнекі түрде</b>\nАлдымен осы сызбаға қараңыз: ол қол арқылы 1, 1,5, 2, 3 және 5 цуньді шамамен қалай өлшеуді көрсетеді.",
        "meridian_point_help": "🖐 Нүктені табу",
        "meridian_video": "🎥 Меридиан видеосы",
        "meridian_video_caption": "🎥 <b>Меридиан видеосы</b>\nАрнаның жолын көріңіз, содан кейін нүктелер тәжірибесіне оралып, денеде нені оңайырақ сезетініңізді тексеріңіз.",
        "meridian_video_missing": "🎥 <b>Меридиан видеосы</b>\n\nБұл меридианның видеосы кейін қосылады. Әзірге суретпен, нүкте сипаттамасымен және зейін тәжірибесімен жалғастырыңыз.",
        "meridian_back": "🔙 Меридиандарға қайту",
        "back_to_current_focus": "🔙 Ағымдағы фокусқа қайту",
        "page_indicator_hint": "Бұл бет нөмірі. Өту үшін Артқа немесе Келесі түймесін қолданыңыз.",
        "meridian_measurements_text": (
            "📏 <b>ҚКМ-дегі өлшем жүйесі</b>\n\n"
            "<b>Бұл не үшін керек:</b> нүкте сипаттамаларында “1 цунь”, “1,5 цунь”, “3 цунь” сияқты өлшемдер жиі кездеседі. Денеге қатысты өлшем болмаса, бұл сандар түсініксіз болып қалады; цунь керек аймаққа жақындауға көмектеседі.\n\n"
            "Акупунктура нүктелерінің орналасуы жиі <b>цунь</b> арқылы сипатталады. Цунь — нақты сантиметр емес, зерттеліп отырған адамның денесіне қатысты өлшем.\n\n"
            "<b>0,5 цунь:</b> жеке 1 цунь өлшеміңіздің жартысы. Өте кіші қашықтықтарға қолданыңыз, кейін нүктені сезім арқылы нақтылаңыз.\n\n"
            "<b>1 цунь:</b> бас бармақтың буын тұсындағы ені.\n\n"
            "<b>1,5 цунь:</b> екі саусақтың ені: сұқ және ортаңғы саусақ.\n\n"
            "<b>2 цунь:</b> үш саусақтың ені: сұқ, ортаңғы және аты жоқ саусақ.\n\n"
            "<b>3 цунь:</b> төрт саусақтың ені: сұқ саусақтан шынашаққа дейін.\n\n"
            "<b>5 цунь:</b> 3 цунь өлшеп, шамамен 2 цунь қосыңыз немесе дереккөз пропорциялық қашықтық берсе, анатомиялық бөлікті тең бөліктерге бөліңіз.\n\n"
            "<b>Маңызды:</b> цунь әрқашан жұмыс істеп отырған адамның денесіне қарай өлшенеді. Сондықтан сіздің денеңіздегі 1 цунь мен басқа адамның денесіндегі 1 цунь сантиметрмен әртүрлі болуы мүмкін.\n\n"
            "Алдымен цунь арқылы жақындаңыз. Содан кейін баяулап, нүктені дене арқылы нақтылаңыз: жергілікті сезімталдық, шағын ойыс, жылу, қысым немесе зейінге анығырақ жауап."
        ),
        "meridian_point_help_text": (
            "🖐 <b>Нүктені қалай табу керек</b>\n\n"
            "Сурет пен цунь өлшемдері арқылы керек аймаққа жақындаңыз. Нақты нүктені баяуырақ табыңыз: саусақпен, тыныспен және зейінмен.\n\n"
            "<b>1.</b> Аймаққа жұмсақ тиіңіз. Кішкентай ойыс, сезімталдық, жылу, қысым немесе зейін оңай ілінетін орынды іздеңіз.\n\n"
            "<b>2.</b> Егер нүкте әрең сезілсе, оны тәжірибе үшін әзірге ашылмаған деп қабылдаңыз. Ұзағырақ болыңыз, жеңіл уқалаңыз (⚠ белгісі бар нүктелерден басқа) және сол жер арқылы тыныс алуды елестетіңіз.\n\n"
            "<b>3.</b> Нәтижені күштемеңіз. Тыныш әрі тұрақты сезім жеткілікті.\n\n"
            "Келесі нүктеге өткенде алдыңғыларды фонда сезіп, жаңа нүктені сол зейін сызығына қосыңыз."
        ),
        "meridians_menu": (
            "☯️ <b>Меридиандар</b>\n\n"
            "<b>Меридиандарды не үшін зерттейміз?</b>\n\n"
            "Қытай дәстүрінде меридиандар Ци қозғалатын арналар ретінде сипатталады. Тәжірибе үшін бұл соқыр сенім емес. Бұл денені бақылау тәсілі: сезім қай жерде анық, сызық қай жерде үзіледі, нүкте қай жерде жылы, кернеулі, бос немесе үнсіз.\n\n"
            "<b>Нені жаттықтырамыз:</b> зейін, тыныс және жұмсақ жанасу. Егер нүкте басында жауап бермесе, оны әзірге тәжірибе үшін жабық деп қабылдаңыз: ұзағырақ болыңыз, жеңіл уқалаңыз (⚠ белгісі бар нүктелерден басқа), сол жер арқылы зейінмен тыныстаңыз және сезім тұрақтырақ болғанын күтіңіз.\n\n"
            "<b>Қалай қозғаламыз:</b> әр жаңа нүкте алдыңғыларына қосылады. Алдымен бірінші нүктені сезіңіз. Кейін оны фонда ұстап, екіншісін қосыңыз. Уақыт өте меридиан бөлек нүктелер емес, бір тірі сызық болып сезіледі.\n\n"
            "<b>Жолды таңдаңыз:</b> басынан тыныш реттілік керек болса, бот бағытын таңдаңыз. Белгілі бір меридиан назарыңызды тартса, еркін таңдауды таңдаңыз.\n\n"
            "<b>Нүктелерден бұрын:</b> <b>цунь</b> нұсқаулығын ашыңыз. Ол қажетті аймақты табуға көмектеседі; нақты орын саусақ, тыныс және зейін арқылы нақтыланады.\n\n"
            "Бұл өзін бақылау және ішкі тәртіп тәжірибесі. Ол медициналық диагнозды немесе емді алмастырмайды."
        ),
        "choose_meridian": (
            "☯️ <b>Меридианды таңдаңыз</b>\n\n"
            "Бұл еркін таңдау режимі. Қазір зерттегіңіз келетін арнаны таңдаңыз; ол ағымдағы тәжірибе фокусына айналады."
        ),
        "current_meridian": "▶️ Тәжірибені жалғастыру",
        "meridian_start_points": "1-нүктеден бастау",
        "all_points": "Барлық нүктелер",
        "next_point": "Келесі нүкте",
        "prev_point": "Алдыңғы нүкте",
        "complete_meridian": "Меридианды аяқтау",
        "select_meridian": "Меридиан таңдау",
        "no_points": "Қазір нүктелер ашылмады. Меридиандар тізіміне оралып, сол жерден қайта көріңіз.",
        "meridian_completed": (
            "✅ <b>Меридиан аяқталды</b>\n\n"
            "Келесі арнаға өтпес бұрын, бүкіл арнаны зейінмен тағы бір рет өтіңіз: бірінші нүктеден соңғысына дейін. "
            "Сызық қай жерде жылы әрі анық, қай жерде әзірге үзіліп немесе үнсіз қалатынын байқаңыз.\n\n"
            "Сезім тынышталған кезде келесі арнаны таңдаңыз."
        ),
        "meridian_route_completed": (
            "✅ <b>Меридиан бағыты аяқталды</b>\n\n"
            "Бот бағыты бойынша барлық меридиандардан өттіңіз. Бірден қайта бастауға асықпаңыз. Бірнеше күн анығырақ сезілмеген арналарға оралыңыз: көбіне олар зейін әлі қай жерде тұрақтауды үйреніп жатқанын көрсетеді.\n\n"
            "Дайын болғанда кез келген меридианды еркін таңдаңыз немесе бағытты басынан бастаңыз."
        ),
        "about_text": (
            "🕊️ <b>Journey of Ascension</b>\n\n"
            "Бұл бот рухани тәжірибе нақты өмірге кірсін дейтін адамдарға арналған: ол тек оқылатын мәтін болып қалмасын және күн сізді үйреншікті реакцияларға алып кеткен соң ғана кешке еске түспесін.\n\n"
            "Мұнда энергия — байқауға болатын нәрсе: зейін, тіршілік күші, тұрақтылық, денедегі жылу және өзіңізді сарқымай әрекет ету қабілеті. Энергия қақтығысқа, асығыстыққа, ренішке, артықтыққа, өзіңізге зиянға немесе өзіңізге көңіл бөлмеуге кетсе, ол санада да, денеде де сезіледі.\n\n"
            "<b>Яма/Нияма</b> негіз береді: күнделікті қағидалар мінез-құлық, сөз, ой, тәртіп және өзіңізге адалдық арқылы осы ағып кетулерді жабуға көмектеседі.\n\n"
            "<b>Меридиандар</b> дене қабатын береді: арналар, нүктелер, Ци ағымы, сезімтал және жабық аймақтар, тыныс, жанасу және зейінді сабырмен бір жерге қайта әкелу әдеті.\n\n"
            "Боттың міндеті қарапайым: тәжірибе жібі күн шуында жоғалып кетпесін және келесі шағын қадам көрініп тұрсын."
        ),
        "feature_announcement": (
            "☯️ <b>Journey of Ascension жаңартуы</b>\n\n"
            "Өтінеміз, жаңа ботқа өтіңіз: @journey_ascension_bot.\n"
            "<b>Қазіргі бот жақында қолдауды тоқтатады.</b>\n\n"
            "Еске салғыштар кейде тұрақты келмеуіне себеп болған қателерді байқадық және оларды түзеттік.\n\n"
            "Сондай-ақ жаңа мүмкіндікті қуана ұсынамыз: <b>қытай меридиандарын зерттеу</b>.\n"
            "Енді ботта меридианды таңдап, жалпы схемасы мен видеосын көруге, нүктелерді суреттерімен ашуға және тәжірибені өз қарқыныңызбен жалғастыруға болады.\n\n"
            "@journey_ascension_bot ашып, /start басыңыз."
        ),
        "already_subscribed": "🕊️ Journey of Ascension бұл жерде бұрыннан ашық.\n\nТәжірибелерді таңдау үшін /menu немесе тәжірибе ырғағын реттеу үшін /settings қолданыңыз.",
        "not_subscribed": "Бұл чатта тәжірибе әлі басталмаған. Бастауға дайын болсаңыз, /start қолданыңыз.",
        "unsubscribed": "Тәжірибе ырғағы тоқтатылды. Күнделікті еске салулар әзірге келмейді.\n\nҚайта оралғыңыз келсе, /start қолданыңыз.",
        "stop_feedback_prompt": "Қаласаңыз, тәжірибені не үшін паузаға қойып жатқаныңызды бір қысқа хабарламамен жаза аласыз. Бұл міндетті емес.",
        "stop_feedback_skip": "Жазбасыз",
        "stop_feedback_skipped": "Дайын. Жазба қалдыру міндетті емес.\n\nҚайта оралғыңыз келсе, /start қолданыңыз.",
        "stop_feedback_thanks": "Рақмет. Бұл жазба тәжірибені жұмсағырақ әрі түсініктірек етуге көмектеседі.\n\nҚайта оралғыңыз келсе, /start қолданыңыз.",
        "not_subscribed_test": "Тәжірибе ырғағы әлі бапталмаған. Бастау үшін /start қолданыңыз.",
        "skip_days_improved": (
            "📅 <b>Тыныш күндер</b>\n\n"
            "Бот тыныш болып, күнделікті тәжірибе еске салуларын <b>жібермейтін</b> апта күндерін таңдаңыз.\n\n"
            "Еске салуларды күн сайын алғыңыз келсе, <b>Тыныш күндерсіз</b> таңдаңыз. Жексенбіден басқа күн сайын алғыңыз келсе, тек жексенбіні таңдаңыз."
        ),
        "no_skip_days": "✅ Тыныш күндер таңдалмаған — еске салулар күн сайын жіберіледі",
        "feedback_prompt": (
            "💌 <b>Пікірлер мен ұсыныстар</b>\n\n"
            "Ботты ыңғайлы, тірі және пайдалы ету үшін сіздің пікіріңіз маңызды.\n\n"
            "Не ұнады? Не ыңғайсыз? Қандай тәжірибе немесе контент жетіспейді?\n\n"
            "Бір хабарлама ретінде жаза аласыз."
        ),
        "feedback_sent": "✅ Рақмет. Пікіріңіз әзірлеушілерге жіберілді.",
        "setup_complete": (
            "🎉 <b>Алғашқы қадам бапталды.</b>\n\n"
            "📋 <b>Ырғағыңыз:</b>\n"
            "🕐 Уақыт: {time}\n"
            "🌍 Уақыт белдеуі: {timezone}\n"
            "📅 Тыныш күндер: {skip_days}\n\n"
            "Тізімдерді ашу, ырғақты өзгерту немесе келесі шағын қадамды жалғастыру үшін /menu қолданыңыз."
        )
    }
}

LIVE_TEXT_OVERRIDES = {
    "en": {
        "language_chosen": "✅ Language set to English.",
        "choose_language": "Choose the language you want to use:",
        "uzbek": "🇺🇿 O'zbek",
        "kazakh": "🇰🇿 Қазақша",
        "timezone_step": "📍 Time zone\n\nChoose your time zone so reminders arrive at the right local time.",
        "timezone_custom": "⌨️ Enter manually",
        "timezone_manual_prompt": "Enter your time zone in IANA format.\n\nExamples: Europe/Moscow, Asia/Tashkent, Asia/Almaty, UTC",
        "timezone_saved": "✅ Time zone saved.",
        "time_saved": "✅ Reminder time saved.",
        "invalid_timezone": "❌ I could not recognize this time zone. Try a format like Europe/Moscow, Asia/Tashkent, Asia/Almaty, or UTC.",
        "invalid_time": "❌ I could not recognize this time. Use HH:MM, for example 08:00 or 20:30.",
        "invalid_skip_days": "❌ I could not recognize these days. Use numbers from 0 to 6 separated by commas.",
        "setup_error": "❌ I could not save this yet. Please try once more; your practice rhythm is worth setting carefully.",
        "error": "Something interrupted the flow. Please try once more, or return to /menu.",
        "test_failed": "I could not send the reminder check right now. Please try again a little later.",
        "menu_settings": "⚙️ Practice rhythm",
        "menu_test": "🧪 Check reminder",
        "sending_test": "🧪 Sending a reminder check...",
        "menu_about": "ℹ️ About the bot",
        "menu_feedback": "💌 Feedback and ideas",
        "back_to_menu": "🔙 Back to menu",
        "no_skip_days": "✅ No quiet days selected — reminders can arrive every day",
        "skip_days_improved": (
            "📅 <b>Quiet Days</b>\n\n"
            "Choose the weekdays when the bot should stay silent and <b>not</b> send daily practice reminders.\n\n"
            "If you want reminders every day, choose <b>No quiet days</b>. If you want every day except Sunday, select only Sunday."
        ),
        "current_settings": "⚙️ <b>Current practice rhythm</b>",
        "feedback_prompt": (
            "💌 <b>Feedback and ideas</b>\n\n"
            "Your experience matters. Write what felt useful, what felt unclear, or what would make the practice more comfortable."
        ),
        "feedback_sent": "✅ Thank you. Your feedback has been sent.",
        "feedback_too_long": "❌ The message is too long. Please keep it under 1000 characters.",
        "feedback_rate_limit": "⏰ Please wait a little before sending another feedback message.",
        "feedback_error": "❌ I could not save your feedback right now. Please try again later.",
    },
    "ru": {
        "language_chosen": "✅ Язык установлен: русский.",
        "choose_language": "Выберите язык, на котором хотите использовать бота:",
        "uzbek": "🇺🇿 O'zbek",
        "kazakh": "🇰🇿 Қазақша",
        "timezone_step": "📍 Часовой пояс\n\nВыберите ваш часовой пояс, чтобы напоминания приходили в правильное местное время.",
        "timezone_custom": "⌨️ Ввести вручную",
        "timezone_manual_prompt": "Введите часовой пояс в формате IANA.\n\nПримеры: Europe/Moscow, Asia/Tashkent, Asia/Almaty, UTC",
        "timezone_saved": "✅ Часовой пояс сохранён.",
        "time_saved": "✅ Время напоминаний сохранено.",
        "invalid_timezone": "❌ Не удалось распознать часовой пояс. Попробуйте формат Europe/Moscow, Asia/Tashkent, Asia/Almaty или UTC.",
        "invalid_time": "❌ Не удалось распознать время. Используйте формат ЧЧ:ММ, например 08:00 или 20:30.",
        "invalid_skip_days": "❌ Не удалось распознать дни. Используйте числа от 0 до 6 через запятую.",
        "setup_error": "❌ Пока не получилось сохранить настройки. Попробуйте ещё раз: ритм практики лучше настроить спокойно и точно.",
        "error": "Поток прервался. Попробуйте ещё раз или вернитесь в /menu.",
        "test_failed": "Сейчас не получилось проверить напоминание. Попробуйте немного позже.",
        "menu_settings": "⚙️ Ритм практики",
        "menu_test": "🧪 Проверить напоминание",
        "sending_test": "🧪 Проверяю отправку напоминания...",
        "menu_about": "ℹ️ О боте",
        "menu_feedback": "💌 Отзывы и идеи",
        "back_to_menu": "🔙 Назад в меню",
        "no_skip_days": "✅ Дни тишины не выбраны — напоминания могут приходить каждый день",
        "skip_days_improved": (
            "📅 <b>Дни тишины</b>\n\n"
            "Выберите дни недели, когда бот должен молчать и <b>не</b> присылать ежедневные напоминания по практике.\n\n"
            "Если хотите получать напоминания каждый день, выберите <b>Без дней тишины</b>. Если хотите получать во все дни, кроме воскресенья, выберите только воскресенье."
        ),
        "current_settings": "⚙️ <b>Текущий ритм практики</b>",
        "feedback_prompt": (
            "💌 <b>Отзывы и идеи</b>\n\n"
            "Ваш опыт важен. Напишите, что оказалось полезным, что было непонятно или что сделало бы практику удобнее."
        ),
        "feedback_sent": "✅ Спасибо. Ваш отзыв отправлен.",
        "feedback_too_long": "❌ Сообщение слишком длинное. Пожалуйста, уложитесь в 1000 символов.",
        "feedback_rate_limit": "⏰ Пожалуйста, подождите немного перед следующим отзывом.",
        "feedback_error": "❌ Сейчас не получилось сохранить отзыв. Попробуйте позже.",
    },
    "uz": {
        "language_chosen": "✅ Til o'zbekchaga o'rnatildi.",
        "choose_language": "Botdan qaysi tilda foydalanishni tanlang:",
        "kazakh": "🇰🇿 Қазақша",
        "timezone_step": "📍 Vaqt mintaqasi\n\nEslatmalar to'g'ri mahalliy vaqtda kelishi uchun vaqt mintaqangizni tanlang.",
        "timezone_custom": "⌨️ Qo'lda kiritish",
        "timezone_manual_prompt": "Vaqt mintaqasini IANA formatida kiriting.\n\nMisollar: Asia/Tashkent, Europe/Moscow, Asia/Almaty, UTC",
        "timezone_saved": "✅ Vaqt mintaqasi saqlandi.",
        "time_saved": "✅ Eslatma vaqti saqlandi.",
        "invalid_timezone": "❌ Bu vaqt mintaqasini taniy olmadim. Asia/Tashkent, Europe/Moscow, Asia/Almaty yoki UTC kabi formatni sinab ko'ring.",
        "invalid_time": "❌ Bu vaqtni taniy olmadim. HH:MM formatidan foydalaning, masalan 08:00 yoki 20:30.",
        "invalid_skip_days": "❌ Kunlarni taniy olmadim. 0 dan 6 gacha bo'lgan raqamlarni vergul bilan kiriting.",
        "setup_error": "❌ Hozircha sozlamalarni saqlay olmadim. Yana bir marta urinib ko'ring: amaliyot ritmini sokin va aniq sozlagan yaxshi.",
        "error": "Jarayon uzilib qoldi. Yana bir marta urinib ko'ring yoki /menu ga qayting.",
        "test_failed": "Hozir eslatmani tekshirish xabarini yubora olmadim. Birozdan keyin qayta urinib ko'ring.",
        "menu_settings": "⚙️ Amaliyot ritmi",
        "menu_test": "🧪 Eslatmani tekshirish",
        "sending_test": "🧪 Eslatma tekshiruvi yuborilmoqda...",
        "menu_about": "ℹ️ Bot haqida",
        "menu_feedback": "💌 Fikr va takliflar",
        "back_to_menu": "🔙 Menyuga qaytish",
        "no_skip_days": "✅ Sokin kunlar tanlanmadi — eslatmalar har kuni kelishi mumkin",
        "current_settings": "⚙️ <b>Joriy amaliyot ritmi</b>",
        "feedback_prompt": (
            "💌 <b>Fikr va takliflar</b>\n\n"
            "Tajribangiz muhim. Nima foydali bo'lganini, nima tushunarsiz qolganini yoki amaliyotni nima qulayroq qilishini yozing."
        ),
        "feedback_sent": "✅ Rahmat. Fikringiz yuborildi.",
        "feedback_too_long": "❌ Xabar juda uzun. Iltimos, 1000 belgidan oshirmang.",
        "feedback_rate_limit": "⏰ Keyingi fikrni yuborishdan oldin biroz kuting.",
        "feedback_error": "❌ Hozir fikringizni saqlay olmadim. Iltimos, keyinroq urinib ko'ring.",
    },
    "kz": {
        "language_chosen": "✅ Тіл қазақшаға орнатылды.",
        "choose_language": "Ботты қай тілде қолданғыңыз келетінін таңдаңыз:",
        "timezone_step": "📍 Уақыт белдеуі\n\nЕске салулар дұрыс жергілікті уақытта келуі үшін уақыт белдеуіңізді таңдаңыз.",
        "timezone_custom": "⌨️ Қолмен енгізу",
        "timezone_manual_prompt": "Уақыт белдеуін IANA форматында енгізіңіз.\n\nМысалдар: Asia/Almaty, Asia/Tashkent, Europe/Moscow, UTC",
        "timezone_saved": "✅ Уақыт белдеуі сақталды.",
        "time_saved": "✅ Еске салу уақыты сақталды.",
        "invalid_timezone": "❌ Бұл уақыт белдеуін тани алмадым. Asia/Almaty, Asia/Tashkent, Europe/Moscow немесе UTC сияқты форматты қолданып көріңіз.",
        "invalid_time": "❌ Бұл уақытты тани алмадым. HH:MM форматын қолданыңыз, мысалы 08:00 немесе 20:30.",
        "invalid_skip_days": "❌ Күндерді тани алмадым. 0-ден 6-ға дейінгі сандарды үтірмен енгізіңіз.",
        "setup_error": "❌ Әзірге баптауларды сақтай алмадым. Қайтадан көріңіз: тәжірибе ырғағын тыныш әрі нақты қойған жақсы.",
        "error": "Жол үзіліп қалды. Қайтадан көріңіз немесе /menu бөліміне оралыңыз.",
        "test_failed": "Қазір еске салуды тексеру хабарын жібере алмадым. Сәл кейін қайталап көріңіз.",
        "menu_settings": "⚙️ Тәжірибе ырғағы",
        "menu_test": "🧪 Еске салуды тексеру",
        "sending_test": "🧪 Еске салу тексеруі жіберіліп жатыр...",
        "menu_about": "ℹ️ Бот туралы",
        "menu_feedback": "💌 Пікірлер мен ұсыныстар",
        "back_to_menu": "🔙 Мәзірге қайту",
        "no_skip_days": "✅ Тыныш күндер таңдалмады — еске салулар күн сайын келуі мүмкін",
        "current_settings": "⚙️ <b>Қазіргі тәжірибе ырғағы</b>",
        "feedback_prompt": (
            "💌 <b>Пікірлер мен ұсыныстар</b>\n\n"
            "Тәжірибеңіз маңызды. Не пайдалы болғанын, не түсініксіз қалғанын немесе тәжірибені не ыңғайлырақ ететінін жазыңыз."
        ),
        "feedback_sent": "✅ Рақмет. Пікіріңіз жіберілді.",
        "feedback_too_long": "❌ Хабар тым ұзын. 1000 таңбадан асырмаңыз.",
        "feedback_rate_limit": "⏰ Келесі пікірді жібермес бұрын сәл күтіңіз.",
        "feedback_error": "❌ Қазір пікіріңізді сақтай алмадым. Кейінірек қайталап көріңіз.",
    },
}

for _language, _updates in TEXTS_UPDATE.items():
    TEXTS.setdefault(_language, {}).update(_updates)

SHU_POINTS_ARTICLE_OVERRIDES = {
    # Names follow the map (webapp/assets/point_categories.json): well, spring, stream, river, sea.
    # The classical indications are told as tradition; the bot's practice is attention or a light touch,
    # no needles and no warming (moxibustion).
    "ru": {
        "meridian_materials_sending": "📚 <b>Пять шу-точек</b>\n\nОтправлю материал как статью: текстовыми блоками и изображениями в тех местах, где они нужны по смыслу.",
        "shu_intro_text": (
            "📚 <b>Пять шу-точек</b>\n\n"
            "Пять шу-точек — это пять типов специфических точек <b>двенадцати главных каналов</b>, которые расположены <b>на дистальных отделах</b> каналов: между пальцами руки и локтем или между пальцами ноги и коленом.\n\n"
            "<b>Пять шу-точек</b> (五输穴 wǔ shū xué):\n\n"
            "• точки-колодцы (井 <i>цзин</i>);\n"
            "• точки-родники (荥 <i>ин</i>);\n"
            "• точки-потоки (输 <i>шу</i>);\n"
            "• точки-реки (经 <i>цзин</i>);\n"
            "• точки-моря (合 <i>хэ</i>).\n\n"
            "Другие названия: 5 античных шу-точек, транспортировочные точки или точки 5 первоэлементов.\n\n"
            "<b>Древние китайские мыслители сравнивали пять точек, расположенных между пальцами и коленом/локтем, с течением воды: от колодца до моря.</b>"
        ),
        "shu_flow_text": (
            "Точки на кончиках пальцев кисти или стопы — это <b>колодец</b>: здесь поток только выходит на поверхность. Дальше он набирает силу, как родник, ручей и река, и у колена или локтя уходит вглубь в <b>точке-море</b>.\n\n"
            "Так обозначена тенденция к <b>нарастанию глубины и ширины канала</b> от кончиков пальцев к локтю или колену. На кончике пальца канал узкий и поверхностный, а в области колена и локтя — широкий и глубокий.\n\n"
            "Важно: нарастание размера и глубины канала <b>не зависит от направления течения</b>. Эта закономерность справедлива для Инь- и Ян-каналов рук и ног.\n\n"
            "Даже если каналы Инь рук текут от груди к пальцам кисти, а каналы Ян рук — от пальцев к голове, сравнение точек на кончиках пальцев с колодцем, а точек у локтя — с морем остаётся верным."
        ),
        "shu_indications_text": (
            "<blockquote>Традиция описывает шу-точки как более поверхностные, чем остальные точки каналов. Их действие в ней считается более быстрым, поэтому классические тексты упоминают их особенно часто.</blockquote>\n\n"
            "<b>Классические показания пяти шу-точек.</b> Это описание традиции, а не совет по лечению.\n\n"
            "— <b>точки-колодцы</b> — в старых текстах их связывают с острыми состояниями и обмороком;\n"
            "— <b>точки-родники</b> — состояния со свойствами жара;\n"
            "— <b>точки-потоки</b> — боль в суставах;\n"
            "— <b>точки-реки</b> — наружный синдром с лихорадкой и ознобом, кашель, одышка, болезни горла;\n"
            "— <b>точки-моря</b> — желудок, кишечник и другие фу-органы.\n\n"
            "⚠️ При неотложном состоянии сразу вызывайте скорую помощь (103 или 112). Точки не заменяют врача. В этом боте с ними работают только вниманием или лёгким касанием, без игл и прогревания."
        ),
        "shu_sources_text": (
            "<b>1. ТОЧКИ-КОЛОДЦЫ</b> (井 jǐng, <i>цзин</i>)\n\n"
            "<b>井</b> jǐng, цзин = колодец.\n"
            "В этих точках канал тоньше всего и расположен <b>наиболее поверхностно</b>. Обычно точки-колодцы находятся у оснований ногтей пальцев рук и ног.\n\n"
            "Исключение составляют точка-колодец ножного шао-инь канала почек <b>Юн-цюань R1</b>, расположенная на подошве в углублении на границе передней трети и задних двух третей, и точка-колодец ручного цзюэ-инь канала перикарда <b>Чжун-чун MC9</b>, расположенная на кончике среднего пальца руки.\n\n"
            "В традиции через точки-колодцы энергия канала выходит на поверхность, и старые тексты связывают их с помощью при обмороке и упадке сил. Это историческое описание, а не инструкция: при неотложном состоянии вызывайте скорую помощь.\n\n"
            "Точка (1) <b>шао-шан</b> — канал лёгких.\n"
            "Точка (2) <b>чжун-чун</b> — канал перикарда.\n"
            "Точка (3) <b>шао-чун</b> — канал сердца.\n"
            "Точка (4) <b>инь-бай</b> — канал селезёнки.\n"
            "Точка (5) <b>да-дунь</b> — канал печени.\n"
            "Точка (6) <b>юн-цюань</b> — канал почек.\n"
            "Точка (7) <b>шан-ян</b> — канал толстой кишки.\n"
            "Точка (8) <b>гуань-чун</b> — канал Сань-цзяо.\n"
            "Точка (9) <b>шао-цзэ</b> — канал тонкой кишки.\n"
            "Точка (10) <b>ли-дуй</b> — канал желудка.\n"
            "Точка (11) <b>цзу-цяо-инь</b> — канал желчного пузыря.\n"
            "Точка (12) <b>чжи-инь</b> — канал мочевого пузыря."
        ),
        "shu_brooks_text": (
            "<b>2. ТОЧКИ-РОДНИКИ</b> (荥 yíng, <i>ин</i>)\n\n"
            "<b>荥</b> yíng, ин = родник, небольшой поток.\n"
            "Достигая этих точек, канальная Ци становится обильнее, как родник, который только набирает силу.\n\n"
            "В традиции точки-родники связывают с охлаждением <b>Жара</b>. По классическим описаниям точки-родники на ногах действуют сильнее, чем такие же точки на руках.\n\n"
            "Точка (1) <b>юй-цзи</b> — канал лёгких.\n"
            "Точка (2) <b>лао-гун</b> — канал перикарда.\n"
            "Точка (3) <b>шао-фу</b> — канал сердца.\n"
            "Точка (4) <b>да-ду</b> — канал селезёнки.\n"
            "Точка (5) <b>жань-гу</b> — канал почек.\n"
            "Точка (6) <b>син-цзянь</b> — канал печени.\n"
            "Точка (7) <b>эр-цзянь</b> — канал толстой кишки.\n"
            "Точка (8) <b>е-мэнь</b> — канал Сань-цзяо."
        ),
        "shu_brooks_after_image_text": (
            "Точка (9) <b>цянь-гу</b> — канал тонкой кишки.\n"
            "Точка (10) <b>нэй-тин</b> — канал желудка.\n"
            "Точка (11) <b>ся-си</b> — канал желчного пузыря.\n"
            "Точка (12) <b>цзу-тун-гу</b> — канал мочевого пузыря."
        ),
        "shu_rapids_text": (
            "<b>3. ТОЧКИ-ПОТОКИ</b> (输 shū, <i>шу</i>)\n\n"
            "<b>输</b> shū, шу = переносить, доставлять.\n"
            "В этих точках поток становится заметнее и глубже, как ручей. По традиции здесь собирается защитная Ци.\n\n"
            "Классические тексты связывают точки-потоки с болью в суставах, тяжестью в теле и состояниями сырости и холода в канале.\n\n"
            "<i>Старое правило: когда болезнь то приходит, то уходит, выбирают точки-потоки.</i>\n\n"
            "Точка (1) <b>тай-юань</b>\n"
            "Точка (2) <b>да-лин</b>\n"
            "Точка (3) <b>шэнь-мэнь</b>\n"
            "Точка (4) <b>тай-бай</b>\n"
            "Точка (5) <b>тай-си</b>\n"
            "Точка (6) <b>тай-чун</b>\n"
            "Точка (7) <b>сань-цзянь</b>\n"
            "Точка (8) <b>чжун-чжу</b>\n"
            "Точка (9) <b>хоу-си</b>\n"
            "Точка (10) <b>сянь-гу</b>\n"
            "Точка (11) <b>цзу-линь-ци</b>\n"
            "Точка (12) <b>шу-гу</b>"
        ),
        "shu_rivers_text": (
            "<b>4. ТОЧКИ-РЕКИ</b> (经 jīng, <i>цзин</i>)\n\n"
            "<b>经</b> jīng, цзин = проходить насквозь.\n\n"
            "В этих точках Ци канала становится ещё шире и ровнее, как полноводная река в середине русла.\n\n"
            "В традиции точки-реки связывают с дыханием и голосом: кашлем, одышкой, болезнями горла. Прогревание, о котором пишут старые тексты, в этом боте не применяется: с точками работают вниманием или лёгким касанием.\n\n"
            "<i>Старое правило: когда болезнь проявляется в голосе, выбирают точки-реки.</i>\n\n"
            "(1) <b>Цзин-цюй</b>\n"
            "(2) <b>Цзянь-ши</b>\n"
            "(3) <b>Лин-дао</b>\n"
            "(4) <b>Шан-цю</b>"
        ),
        "shu_rivers_after_image_text": (
            "(5) <b>Чжун-фэн</b>\n"
            "(6) <b>Фу-лю</b>\n"
            "(7) <b>Ян-си</b>\n"
            "(8) <b>Чжи-гоу</b>\n"
            "(9) <b>Ян-гу</b>\n"
            "(10) <b>Цзе-си</b>\n"
            "(11) <b>Ян-фу</b>\n"
            "(12) <b>Кунь-лунь</b>"
        ),
        "shu_mouths_text": (
            "<b>5. ТОЧКИ-МОРЯ</b> (合 hé, <i>хэ</i>)\n\n"
            "Точки-моря — пятые точки, всегда расположенные на уровне локтя или колена.\n\n"
            "<b>合</b> hé, хэ = соединение. Здесь поток уходит вглубь, как река, впадающая в море, и Ци канала соединяется с Ци всего организма.\n\n"
            "В традиции точки-моря связывают с желудком, кишечником и другими фу-органами, а также с нарушением тока Ци. Прогревание из старых текстов здесь тоже не применяется: только внимание и лёгкое касание.\n\n"
            "(1) <b>Чи-цзэ</b>\n"
            "(2) <b>Цюй-цзэ</b>\n"
            "(3) <b>Шао-хай</b>\n"
            "(4) <b>Инь-лин-цюань</b>\n"
            "(5) <b>Цюй-цюань</b>"
        ),
        "shu_mouths_after_image_1_text": (
            "(6) <b>Инь-гу</b>\n"
            "(7) <b>Цюй-чи</b>\n"
            "(8) <b>Тянь-цзин</b>\n"
            "(9) <b>Сяо-хай</b>"
        ),
        "shu_mouths_after_image_2_text": (
            "(10) <b>Цзу-сань-ли</b>\n"
            "(11) <b>Ян-лин-цюань</b>\n"
            "(12) <b>Вэй-чжун</b>"
        ),
        "shu_final_text": (
            "<b>По материалам</b>\n\n"
            "Джованни Мачоча, <i>Основы китайской медицины</i>, том 3.\n"
            "П. В. Белоусов, <i>Акупунктурные точки китайской чжэньцзю-терапии</i>.\n\n"
            "<blockquote>Материал ознакомительный: он пересказывает традицию и не является советом по лечению. При неотложном состоянии вызывайте скорую помощь (103 или 112), по вопросам здоровья обращайтесь к врачу.</blockquote>\n\n"
            "<b>Фу-органы</b>, или янские органы: желудок, толстая кишка, тонкая кишка, мочевой пузырь, желчный пузырь и три части туловища — тройной обогреватель. Эти органы являются полыми и связаны с перевариванием, всасыванием и выделением."
        ),
    },
    "en": {
        "meridian_materials_sending": "📚 <b>Five shu-points</b>\n\nI will send this as an article: text blocks and images placed where they belong.",
        "shu_intro_text": (
            "📚 <b>Five shu-points</b>\n\n"
            "The five shu-points are five types of specific points of the <b>twelve main channels</b>. They are located on the <b>distal parts</b> of the channels: between fingers and elbow, or between toes and knee.\n\n"
            "<b>Five shu-points</b> (五输穴 wǔ shū xué):\n\n"
            "• Jing-Well points (井 <i>jǐng</i>);\n"
            "• Ying-Spring points (荥 <i>yíng</i>);\n"
            "• Shu-Stream points (输 <i>shū</i>);\n"
            "• Jing-River points (经 <i>jīng</i>);\n"
            "• He-Sea points (合 <i>hé</i>).\n\n"
            "They are also called the five antique shu-points, transport points, or five-element points.\n\n"
            "<b>Ancient Chinese thinkers compared these five points with flowing water, from a well to the sea.</b>"
        ),
        "shu_flow_text": (
            "Points at the tips of fingers or toes are the <b>well</b>: the flow only surfaces here. Then it gathers strength like a spring, a stream and a river, and near the elbow or knee it goes deep at the <b>sea point</b>.\n\n"
            "This shows a movement toward <b>greater depth and width of the channel</b> from fingertips or toes toward the elbow or knee. At the fingertip the channel is narrow and superficial; near the elbow or knee it is wider and deeper.\n\n"
            "Important: this increase in size and depth <b>does not depend on the direction of channel flow</b>. The same rule applies to Yin and Yang channels of the arms and legs."
        ),
        "shu_indications_text": (
            "<blockquote>Tradition describes shu-points as lying closer to the surface than other channel points and considers their action faster, so the classical texts mention them especially often.</blockquote>\n\n"
            "<b>Classical indications.</b> This describes the tradition; it is not treatment advice.\n\n"
            "— <b>Jing-Well points</b> — old texts link them with acute states and fainting;\n"
            "— <b>Ying-Spring points</b> — conditions with Heat qualities;\n"
            "— <b>Shu-Stream points</b> — joint pain;\n"
            "— <b>Jing-River points</b> — exterior patterns with fever and chills, cough, shortness of breath and throat disorders;\n"
            "— <b>He-Sea points</b> — the stomach, intestines and other Fu organs.\n\n"
            "⚠️ In an emergency, call an ambulance right away (112 or your local emergency number). The points do not replace a doctor. In this bot they are practised with attention or a light touch only, no needles and no warming."
        ),
        "shu_sources_text": (
            "<b>1. JING-WELL POINTS</b> (井 jǐng)\n\n"
            "<b>井</b> jǐng = well.\n"
            "Here the channel is thinnest and <b>most superficial</b>. Usually Jing-Well points are near the nail bases of fingers and toes.\n\n"
            "Exceptions include <b>Kidney R1 Yong-quan</b> on the sole (in the depression at the junction of its anterior third and posterior two thirds) and <b>Pericardium MC9 Zhong-chong</b> on the tip of the middle finger.\n\n"
            "In the tradition, channel energy surfaces at the well points, and old texts link them with reviving from fainting and exhaustion. This is a historical description, not an instruction: in an emergency, call an ambulance.\n\n"
            "(1) <b>Shao-shang</b> — Lung.\n(2) <b>Zhong-chong</b> — Pericardium.\n(3) <b>Shao-chong</b> — Heart.\n(4) <b>Yin-bai</b> — Spleen.\n(5) <b>Da-dun</b> — Liver.\n(6) <b>Yong-quan</b> — Kidney.\n(7) <b>Shang-yang</b> — Large Intestine.\n(8) <b>Guan-chong</b> — Triple Burner.\n(9) <b>Shao-ze</b> — Small Intestine.\n(10) <b>Li-dui</b> — Stomach.\n(11) <b>Zu-qiao-yin</b> — Gallbladder.\n(12) <b>Zhi-yin</b> — Bladder."
        ),
        "shu_brooks_text": (
            "<b>2. YING-SPRING POINTS</b> (荥 yíng)\n\n"
            "<b>荥</b> yíng = spring, a small flow.\n"
            "When Qi reaches these points, it becomes more abundant, like a spring that is just gathering strength.\n\n"
            "The tradition links them with clearing <b>Heat</b>. In the classical descriptions the foot Ying-Spring points are stronger than the same points on the hands.\n\n"
            "(1) <b>Yu-ji</b> — Lung.\n(2) <b>Lao-gong</b> — Pericardium.\n(3) <b>Shao-fu</b> — Heart.\n(4) <b>Da-du</b> — Spleen.\n(5) <b>Ran-gu</b> — Kidney.\n(6) <b>Xing-jian</b> — Liver.\n(7) <b>Er-jian</b> — Large Intestine.\n(8) <b>Ye-men</b> — Triple Burner."
        ),
        "shu_brooks_after_image_text": "(9) <b>Qian-gu</b> — Small Intestine.\n(10) <b>Nei-ting</b> — Stomach.\n(11) <b>Xia-xi</b> — Gallbladder.\n(12) <b>Zu-tong-gu</b> — Bladder.",
        "shu_rapids_text": (
            "<b>3. SHU-STREAM POINTS</b> (输 shū)\n\n"
            "<b>输</b> shū = to transport.\n"
            "Here the flow becomes more noticeable and deeper, like a stream. Protective Qi is traditionally said to gather here.\n\n"
            "The classical texts link these points with joint pain, heaviness and patterns of dampness and cold.\n\n"
            "(1) <b>Tai-yuan</b>\n(2) <b>Da-ling</b>\n(3) <b>Shen-men</b>\n(4) <b>Tai-bai</b>\n(5) <b>Tai-xi</b>\n(6) <b>Tai-chong</b>\n(7) <b>San-jian</b>\n(8) <b>Zhong-zhu</b>\n(9) <b>Hou-xi</b>\n(10) <b>Xian-gu</b>\n(11) <b>Zu-lin-qi</b>\n(12) <b>Shu-gu</b>"
        ),
        "shu_rivers_text": (
            "<b>4. JING-RIVER POINTS</b> (经 jīng)\n\n"
            "<b>经</b> jīng = to pass through.\n\n"
            "Here channel Qi becomes wider and steadier, like a full river in its bed. The tradition links Jing-River points with breath and voice: cough, shortness of breath and throat disorders. The warming described in old texts is not used in this bot: the points are practised with attention or a light touch.\n\n"
            "(1) <b>Jing-qu</b>\n(2) <b>Jian-shi</b>\n(3) <b>Ling-dao</b>\n(4) <b>Shang-qiu</b>"
        ),
        "shu_rivers_after_image_text": "(5) <b>Zhong-feng</b>\n(6) <b>Fu-liu</b>\n(7) <b>Yang-xi</b>\n(8) <b>Zhi-gou</b>\n(9) <b>Yang-gu</b>\n(10) <b>Jie-xi</b>\n(11) <b>Yang-fu</b>\n(12) <b>Kun-lun</b>",
        "shu_mouths_text": (
            "<b>5. HE-SEA POINTS</b> (合 hé)\n\n"
            "He-Sea points are the fifth points and are always near the elbow or knee. <b>合</b> hé = union, joining. Here the flow goes deep, like a river entering the sea, and channel Qi joins the Qi of the whole body.\n\n"
            "The tradition links them with the stomach, intestines and other Fu organs. Warming from the old texts is not used here either: attention and a light touch only.\n\n"
            "(1) <b>Chi-ze</b>\n(2) <b>Qu-ze</b>\n(3) <b>Shao-hai</b>\n(4) <b>Yin-ling-quan</b>\n(5) <b>Qu-quan</b>"
        ),
        "shu_mouths_after_image_1_text": "(6) <b>Yin-gu</b>\n(7) <b>Qu-chi</b>\n(8) <b>Tian-jing</b>\n(9) <b>Xiao-hai</b>",
        "shu_mouths_after_image_2_text": "(10) <b>Zu-san-li</b>\n(11) <b>Yang-ling-quan</b>\n(12) <b>Wei-zhong</b>",
        "shu_final_text": (
            "<b>Sources</b>\n\n"
            "Giovanni Maciocia, <i>The Foundations of Chinese Medicine</i>, vol. 3.\n"
            "P. V. Belousov, <i>Acupuncture Points of Chinese Zhenjiu Therapy</i>.\n\n"
            "<blockquote>This material is educational: it retells the tradition and is not treatment advice. In an emergency, call an ambulance; for health questions, see a doctor.</blockquote>\n\n"
            "<b>Fu organs</b> are Yang organs: stomach, large intestine, small intestine, bladder, gallbladder and triple burner."
        ),
    },
    "uz": {
        "meridian_materials_sending": "📚 <b>Besh shu-nuqta</b>\n\nMaterialni maqola sifatida yuboraman: matn bloklari va rasmlar o'z joyida turadi.",
        "shu_intro_text": (
            "📚 <b>Besh shu-nuqta</b>\n\n"
            "Besh shu-nuqta — <b>o'n ikki asosiy kanalning</b> besh turdagi maxsus nuqtalari. Ular kanallarning <b>distal qismlarida</b>: qo'l barmoqlari va tirsak orasida yoki oyoq barmoqlari va tizza orasida joylashadi.\n\n"
            "<b>Besh shu-nuqta</b> (五输穴 wǔ shū xué):\n\n"
            "• quduq nuqtalari (井 <i>jing</i>);\n"
            "• buloq nuqtalari (荥 <i>ying</i>);\n"
            "• soy nuqtalari (输 <i>shu</i>);\n"
            "• daryo nuqtalari (经 <i>jing</i>);\n"
            "• dengiz nuqtalari (合 <i>he</i>).\n\n"
            "Ular antik shu-nuqtalar, transport nuqtalari yoki besh unsur nuqtalari deb ham ataladi.\n\n"
            "<b>Qadimgi Xitoy mutafakkirlari bu besh nuqtani quduqdan dengizgacha oqayotgan suvga qiyoslagan.</b>"
        ),
        "shu_flow_text": (
            "Barmoq uchlaridagi nuqtalar — <b>quduq</b>: oqim shu yerda endigina yuzaga chiqadi. Keyin u buloq, soy va daryodek kuchayib boradi va tirsak yoki tizza yonida <b>dengiz nuqtasida</b> chuqurga ketadi.\n\n"
            "Kanalning chuqurligi va kengligi ortishi energiya oqimining yo'nalishiga bog'liq emas. Bu qonuniyat qo'l va oyoqdagi Yin hamda Yang kanallariga birdek tegishli."
        ),
        "shu_indications_text": (
            "<b>Klassik ko'rsatmalar.</b> Bu an'ananing tavsifi, davolash bo'yicha maslahat emas.\n\n"
            "— <b>quduq nuqtalari</b> — eski matnlarda o'tkir holatlar va hushdan ketish bilan bog'lanadi;\n"
            "— <b>buloq nuqtalari</b> — Issiqlik xususiyatiga ega holatlar;\n"
            "— <b>soy nuqtalari</b> — bo'g'im og'rig'i;\n"
            "— <b>daryo nuqtalari</b> — isitma va titroq, yo'tal, hansirash va tomoq kasalliklari bilan bog'liq tashqi sindromlar;\n"
            "— <b>dengiz nuqtalari</b> — oshqozon, ichak va boshqa Fu organlari.\n\n"
            "⚠️ Shoshilinch holatda darhol tez yordam chaqiring (103 yoki 112). Nuqtalar shifokorni almashtirmaydi. Bu botda ular bilan faqat diqqat yoki yengil teginish orqali ishlanadi, ignasiz va isitmasdan."
        ),
        "shu_sources_text": (
            "<b>1. QUDUQ NUQTALARI</b> (井 jǐng)\n\n"
            "<b>井</b> jǐng = quduq.\n"
            "Bu yerda kanal eng nozik va <b>eng yuzaki</b> bo'ladi. Odatda quduq nuqtalari qo'l va oyoq tirnoqlari asosida joylashadi. Istisnolar: oyoq tagidagi <b>Yong-quan R1</b> (old uchdan bir va orqa uchdan ikki qism chegarasidagi chuqurchada) va o'rta barmoq uchidagi <b>Zhong-chong MC9</b>.\n\n"
            "An'anaga ko'ra kanal energiyasi quduq nuqtalarida yuzaga chiqadi, eski matnlar ularni hushdan ketish va holsizlikda yordam bilan bog'laydi. Bu tarixiy tavsif, ko'rsatma emas: shoshilinch holatda tez yordam chaqiring.\n\n"
            "(1) <b>Shao-shang</b> — O'pka.\n(2) <b>Zhong-chong</b> — Perikard.\n(3) <b>Shao-chong</b> — Yurak.\n(4) <b>Yin-bai</b> — Taloq.\n(5) <b>Da-dun</b> — Jigar.\n(6) <b>Yong-quan</b> — Buyrak.\n(7) <b>Shang-yang</b> — Yo'g'on ichak.\n(8) <b>Guan-chong</b> — Uch isitkich.\n(9) <b>Shao-ze</b> — Ingichka ichak.\n(10) <b>Li-dui</b> — Oshqozon.\n(11) <b>Zu-qiao-yin</b> — O't pufagi.\n(12) <b>Zhi-yin</b> — Siydik pufagi."
        ),
        "shu_brooks_text": (
            "<b>2. BULOQ NUQTALARI</b> (荥 yíng)\n\n"
            "<b>荥</b> yíng = buloq, kichik oqim.\n"
            "Qi bu nuqtalarga yetganda ko'payadi, go'yo endi kuch yig'ayotgan buloq kabi.\n\n"
            "An'anada ular <b>Issiqlikni</b> sovitish bilan bog'lanadi. Klassik tavsiflarga ko'ra oyoqdagi buloq nuqtalari qo'ldagilardan kuchliroq.\n\n"
            "(1) <b>Yu-ji</b> — O'pka.\n(2) <b>Lao-gong</b> — Perikard.\n(3) <b>Shao-fu</b> — Yurak.\n(4) <b>Da-du</b> — Taloq.\n(5) <b>Ran-gu</b> — Buyrak.\n(6) <b>Xing-jian</b> — Jigar.\n(7) <b>Er-jian</b> — Yo'g'on ichak.\n(8) <b>Ye-men</b> — Uch isitkich."
        ),
        "shu_brooks_after_image_text": "(9) <b>Qian-gu</b> — Ingichka ichak.\n(10) <b>Nei-ting</b> — Oshqozon.\n(11) <b>Xia-xi</b> — O't pufagi.\n(12) <b>Zu-tong-gu</b> — Siydik pufagi.",
        "shu_rapids_text": (
            "<b>3. SOY NUQTALARI</b> (输 shū)\n\n"
            "<b>输</b> shū = tashimoq, yetkazmoq.\n"
            "Bu nuqtalarda oqim soydek sezilarliroq va chuqurroq bo'ladi. An'anaga ko'ra himoya Qi shu yerda to'planadi.\n\n"
            "Klassik matnlar ularni bo'g'im og'rig'i, tanadagi og'irlik va namlik-sovuqlik holatlari bilan bog'laydi.\n\n"
            "(1) <b>Tai-yuan</b>\n(2) <b>Da-ling</b>\n(3) <b>Shen-men</b>\n(4) <b>Tai-bai</b>\n(5) <b>Tai-xi</b>\n(6) <b>Tai-chong</b>\n(7) <b>San-jian</b>\n(8) <b>Zhong-zhu</b>\n(9) <b>Hou-xi</b>\n(10) <b>Xian-gu</b>\n(11) <b>Zu-lin-qi</b>\n(12) <b>Shu-gu</b>"
        ),
        "shu_rivers_text": (
            "<b>4. DARYO NUQTALARI</b> (经 jīng)\n\n"
            "<b>经</b> jīng = o'tib ketmoq.\n\n"
            "Bu yerda kanal Qi o'z o'zanida oqayotgan to'liq daryodek kengroq va bir tekis bo'ladi. An'anada daryo nuqtalari nafas va ovoz bilan bog'lanadi: yo'tal, hansirash, tomoq kasalliklari. Eski matnlardagi isitish bu botda qo'llanilmaydi: nuqtalar bilan diqqat yoki yengil teginish orqali ishlanadi.\n\n"
            "(1) <b>Jing-qu</b>\n(2) <b>Jian-shi</b>\n(3) <b>Ling-dao</b>\n(4) <b>Shang-qiu</b>"
        ),
        "shu_rivers_after_image_text": "(5) <b>Zhong-feng</b>\n(6) <b>Fu-liu</b>\n(7) <b>Yang-xi</b>\n(8) <b>Zhi-gou</b>\n(9) <b>Yang-gu</b>\n(10) <b>Jie-xi</b>\n(11) <b>Yang-fu</b>\n(12) <b>Kun-lun</b>",
        "shu_mouths_text": (
            "<b>5. DENGIZ NUQTALARI</b> (合 hé)\n\n"
            "Bu beshinchi nuqtalar bo'lib, doimo tirsak yoki tizza darajasida joylashadi. <b>合</b> hé = birlashish. Bu yerda oqim dengizga quyilayotgan daryodek chuqurga ketadi va kanal Qi butun organizm Qi bilan qo'shiladi.\n\n"
            "An'anada ular oshqozon, ichak va boshqa Fu organlari bilan bog'lanadi. Eski matnlardagi isitish bu yerda ham qo'llanilmaydi: faqat diqqat va yengil teginish.\n\n"
            "(1) <b>Chi-ze</b>\n(2) <b>Qu-ze</b>\n(3) <b>Shao-hai</b>\n(4) <b>Yin-ling-quan</b>\n(5) <b>Qu-quan</b>"
        ),
        "shu_mouths_after_image_1_text": "(6) <b>Yin-gu</b>\n(7) <b>Qu-chi</b>\n(8) <b>Tian-jing</b>\n(9) <b>Xiao-hai</b>",
        "shu_mouths_after_image_2_text": "(10) <b>Zu-san-li</b>\n(11) <b>Yang-ling-quan</b>\n(12) <b>Wei-zhong</b>",
        "shu_final_text": (
            "<b>Manbalar</b>\n\n"
            "Giovanni Maciocia, <i>The Foundations of Chinese Medicine</i>, 3-jild.\n"
            "P. V. Belousov, <i>Xitoy chjenszyu terapiyasining akupunktura nuqtalari</i>.\n\n"
            "<blockquote>Material tanishish uchun: u an'anani hikoya qiladi va davolash bo'yicha maslahat emas. Shoshilinch holatda tez yordam chaqiring, sog'liq masalalarida shifokorga murojaat qiling.</blockquote>\n\n"
            "<b>Fu organlari</b> yoki Yang organlari: oshqozon, yo'g'on ichak, ingichka ichak, siydik pufagi, o't pufagi va uch isitkich."
        ),
    },
    "kz": {
        "meridian_materials_sending": "📚 <b>Бес шу-нүкте</b>\n\nМатериалды мақала ретінде жіберемін: мәтін бөліктері мен суреттер өз орнында тұрады.",
        "shu_intro_text": (
            "📚 <b>Бес шу-нүкте</b>\n\n"
            "Бес шу-нүкте — <b>он екі негізгі арнаның</b> бес түрлі арнайы нүктесі. Олар арналардың <b>дистальды бөліктерінде</b>: қол саусақтары мен шынтақ арасында немесе аяқ саусақтары мен тізе арасында орналасады.\n\n"
            "<b>Бес шу-нүкте</b> (五输穴 wǔ shū xué):\n\n"
            "• құдық нүктелері (井 <i>цзин</i>);\n"
            "• бұлақ нүктелері (荥 <i>ин</i>);\n"
            "• жылға нүктелері (输 <i>шу</i>);\n"
            "• өзен нүктелері (经 <i>цзин</i>);\n"
            "• теңіз нүктелері (合 <i>хэ</i>).\n\n"
            "Оларды антикалық шу-нүктелер, тасымалдаушы нүктелер немесе бес стихия нүктелері деп те атайды.\n\n"
            "<b>Ежелгі қытай ойшылдары бұл бес нүктені құдықтан теңізге дейін аққан суға теңеген.</b>"
        ),
        "shu_flow_text": (
            "Саусақ ұштарындағы нүктелер — <b>құдық</b>: ағын осы жерде енді ғана бетке шығады. Содан кейін ол бұлақ, жылға және өзендей күшейіп, шынтақ не тізе тұсында <b>теңіз нүктесінде</b> тереңге кетеді.\n\n"
            "Арнаның тереңдігі мен кеңдігінің артуы энергия ағымының бағытына тәуелді емес. Бұл заңдылық қол мен аяқтағы Инь және Ян арналарына бірдей қатысты."
        ),
        "shu_indications_text": (
            "<b>Классикалық көрсеткіштер.</b> Бұл дәстүрдің сипаттамасы, емдеу бойынша кеңес емес.\n\n"
            "— <b>құдық нүктелері</b> — ескі мәтіндерде жедел жағдайлармен және талумен байланыстырылады;\n"
            "— <b>бұлақ нүктелері</b> — Ыстық қасиеті бар жағдайлар;\n"
            "— <b>жылға нүктелері</b> — буын ауруы;\n"
            "— <b>өзен нүктелері</b> — қызба мен қалтырау, жөтел, ентігу және тамақ аурулары бар сыртқы синдромдар;\n"
            "— <b>теңіз нүктелері</b> — асқазан, ішек және басқа Фу-ағзалар.\n\n"
            "⚠️ Шұғыл жағдайда дереу жедел жәрдем шақырыңыз (103 немесе 112). Нүктелер дәрігерді алмастырмайды. Бұл ботта олармен тек зейін немесе жеңіл жанасу арқылы жұмыс істейді, инесіз және жылытусыз."
        ),
        "shu_sources_text": (
            "<b>1. ҚҰДЫҚ НҮКТЕЛЕРІ</b> (井 jǐng, <i>цзин</i>)\n\n"
            "<b>井</b> jǐng = құдық.\n"
            "Бұл жерде арна ең жіңішке және <b>ең беткі</b> орналасады. Әдетте құдық нүктелері қол мен аяқ тырнақтарының түбінде болады. Ерекшеліктер: табандағы <b>Юн-цюань R1</b> (алдыңғы үштен бір мен артқы үштен екі бөлігінің шекарасындағы ойықта) және ортаңғы саусақ ұшындағы <b>Чжун-чун MC9</b>.\n\n"
            "Дәстүр бойынша арна энергиясы құдық нүктелерінде бетке шығады, ескі мәтіндер оларды талу мен әлсіздікке көмекпен байланыстырады. Бұл тарихи сипаттама, нұсқау емес: шұғыл жағдайда жедел жәрдем шақырыңыз.\n\n"
            "(1) <b>Шао-шан</b> — Өкпе.\n(2) <b>Чжун-чун</b> — Перикард.\n(3) <b>Шао-чун</b> — Жүрек.\n(4) <b>Инь-бай</b> — Көкбауыр.\n(5) <b>Да-дунь</b> — Бауыр.\n(6) <b>Юн-цюань</b> — Бүйрек.\n(7) <b>Шан-ян</b> — Тоқ ішек.\n(8) <b>Гуань-чун</b> — Үш жылытқыш.\n(9) <b>Шао-цзэ</b> — Ащы ішек.\n(10) <b>Ли-дуй</b> — Асқазан.\n(11) <b>Цзу-цяо-инь</b> — Өт қабы.\n(12) <b>Чжи-инь</b> — Қуық."
        ),
        "shu_brooks_text": (
            "<b>2. БҰЛАҚ НҮКТЕЛЕРІ</b> (荥 yíng, <i>ин</i>)\n\n"
            "<b>荥</b> yíng = бұлақ, шағын ағын.\n"
            "Ци бұл нүктелерге жеткенде молаяды, енді ғана күш жинап жатқан бұлаққа ұқсайды.\n\n"
            "Дәстүрде олар <b>Ыстықты</b> салқындатумен байланыстырылады. Классикалық сипаттамалар бойынша аяқтағы бұлақ нүктелері қолдағылардан күштірек.\n\n"
            "(1) <b>Юй-цзи</b> — Өкпе.\n(2) <b>Лао-гун</b> — Перикард.\n(3) <b>Шао-фу</b> — Жүрек.\n(4) <b>Да-ду</b> — Көкбауыр.\n(5) <b>Жань-гу</b> — Бүйрек.\n(6) <b>Син-цзянь</b> — Бауыр.\n(7) <b>Эр-цзянь</b> — Тоқ ішек.\n(8) <b>Е-мэнь</b> — Үш жылытқыш."
        ),
        "shu_brooks_after_image_text": "(9) <b>Цянь-гу</b> — Ащы ішек.\n(10) <b>Нэй-тин</b> — Асқазан.\n(11) <b>Ся-си</b> — Өт қабы.\n(12) <b>Цзу-тун-гу</b> — Қуық.",
        "shu_rapids_text": (
            "<b>3. ЖЫЛҒА НҮКТЕЛЕРІ</b> (输 shū, <i>шу</i>)\n\n"
            "<b>输</b> shū = тасымалдау, жеткізу.\n"
            "Бұл нүктелерде ағын жылғадай байқалатын әрі тереңірек болады. Дәстүр бойынша қорғаныс Ци осында жиналады.\n\n"
            "Классикалық мәтіндер оларды буын ауруымен, денедегі ауырлықпен және ылғал-суық жағдайларымен байланыстырады.\n\n"
            "(1) <b>Тай-юань</b>\n(2) <b>Да-лин</b>\n(3) <b>Шэнь-мэнь</b>\n(4) <b>Тай-бай</b>\n(5) <b>Тай-си</b>\n(6) <b>Тай-чун</b>\n(7) <b>Сань-цзянь</b>\n(8) <b>Чжун-чжу</b>\n(9) <b>Хоу-си</b>\n(10) <b>Сянь-гу</b>\n(11) <b>Цзу-линь-ци</b>\n(12) <b>Шу-гу</b>"
        ),
        "shu_rivers_text": (
            "<b>4. ӨЗЕН НҮКТЕЛЕРІ</b> (经 jīng, <i>цзин</i>)\n\n"
            "<b>经</b> jīng = өтіп кету.\n\n"
            "Бұл жерде арна Ци өз арнасымен аққан толық өзендей кеңірек әрі бірқалыпты болады. Дәстүрде өзен нүктелері тыныс пен дауыспен байланыстырылады: жөтел, ентігу, тамақ аурулары. Ескі мәтіндердегі жылыту бұл ботта қолданылмайды: нүктелермен зейін немесе жеңіл жанасу арқылы жұмыс істейді.\n\n"
            "(1) <b>Цзин-цюй</b>\n(2) <b>Цзянь-ши</b>\n(3) <b>Лин-дао</b>\n(4) <b>Шан-цю</b>"
        ),
        "shu_rivers_after_image_text": "(5) <b>Чжун-фэн</b>\n(6) <b>Фу-лю</b>\n(7) <b>Ян-си</b>\n(8) <b>Чжи-гоу</b>\n(9) <b>Ян-гу</b>\n(10) <b>Цзе-си</b>\n(11) <b>Ян-фу</b>\n(12) <b>Кунь-лунь</b>",
        "shu_mouths_text": (
            "<b>5. ТЕҢІЗ НҮКТЕЛЕРІ</b> (合 hé, <i>хэ</i>)\n\n"
            "Бұл бесінші нүктелер, олар әрқашан шынтақ немесе тізе деңгейінде орналасады. <b>合</b> hé = қосылу. Мұнда ағын теңізге құятын өзендей тереңге кетеді, арна Ци бүкіл ағзаның Ци-імен қосылады.\n\n"
            "Дәстүрде олар асқазан, ішек және басқа Фу-ағзалармен байланыстырылады. Ескі мәтіндердегі жылыту мұнда да қолданылмайды: тек зейін және жеңіл жанасу.\n\n"
            "(1) <b>Чи-цзэ</b>\n(2) <b>Цюй-цзэ</b>\n(3) <b>Шао-хай</b>\n(4) <b>Инь-лин-цюань</b>\n(5) <b>Цюй-цюань</b>"
        ),
        "shu_mouths_after_image_1_text": "(6) <b>Инь-гу</b>\n(7) <b>Цюй-чи</b>\n(8) <b>Тянь-цзин</b>\n(9) <b>Сяо-хай</b>",
        "shu_mouths_after_image_2_text": "(10) <b>Цзу-сань-ли</b>\n(11) <b>Ян-лин-цюань</b>\n(12) <b>Вэй-чжун</b>",
        "shu_final_text": (
            "<b>Дереккөздер</b>\n\n"
            "Джованни Мачоча, <i>The Foundations of Chinese Medicine</i>, 3-том.\n"
            "П. В. Белоусов, <i>Қытай чжэньцзю-терапиясының акупунктуралық нүктелері</i>.\n\n"
            "<blockquote>Материал танысуға арналған: ол дәстүрді баяндайды және емдеу бойынша кеңес емес. Шұғыл жағдайда жедел жәрдем шақырыңыз, денсаулық мәселелері бойынша дәрігерге жүгініңіз.</blockquote>\n\n"
            "<b>Фу-ағзалар</b> немесе Ян-ағзалар: асқазан, тоқ ішек, ащы ішек, қуық, өт қабы және үш жылытқыш."
        ),
    },
}

for _language, _updates in SHU_POINTS_ARTICLE_OVERRIDES.items():
    TEXTS.setdefault(_language, {}).update(_updates)

for _language, _updates in LIVE_TEXT_OVERRIDES.items():
    TEXTS.setdefault(_language, {}).update(_updates)

MERIDIAN_COMPLETION_TEXT_OVERRIDES = {
    "en": {
        "complete_meridian": "✅ Meridian studied / next",
        "complete_meridian_confirm": (
            "✅ <b>Finish this meridian?</b>\n\n"
            "You have not opened all points yet. If you already studied this meridian on your own, "
            "confirm and the bot will move you to the next meridian in the route."
        ),
        "complete_meridian_confirm_yes": "✅ Yes, move to the next meridian",
        "complete_meridian_confirm_no": "↩️ Continue this meridian",
    },
    "ru": {
        "complete_meridian": "✅ Меридиан изучен / дальше",
        "complete_meridian_confirm": (
            "✅ <b>Завершить этот меридиан?</b>\n\n"
            "Вы ещё не открыли все точки в боте. Если вы уже изучили этот меридиан самостоятельно, "
            "подтвердите, и бот переведёт вас к следующему меридиану маршрута."
        ),
        "complete_meridian_confirm_yes": "✅ Да, перейти к следующему",
        "complete_meridian_confirm_no": "↩️ Продолжить этот меридиан",
    },
    "uz": {
        "complete_meridian": "✅ Meridian o‘rganildi / keyingisi",
        "complete_meridian_confirm": (
            "✅ <b>Bu meridianni yakunlaysizmi?</b>\n\n"
            "Siz hali botdagi barcha nuqtalarni ochmadingiz. Agar meridianni mustaqil o‘rgangan bo‘lsangiz, "
            "tasdiqlang va bot sizni yo‘nalishdagi keyingi meridianga o‘tkazadi."
        ),
        "complete_meridian_confirm_yes": "✅ Ha, keyingisiga o‘tish",
        "complete_meridian_confirm_no": "↩️ Shu meridianni davom ettirish",
    },
    "kz": {
        "complete_meridian": "✅ Меридиан зерттелді / келесі",
        "complete_meridian_confirm": (
            "✅ <b>Бұл меридианды аяқтайсыз ба?</b>\n\n"
            "Сіз боттағы барлық нүктені әлі ашқан жоқсыз. Егер меридианды өзіңіз зерттеп қойған болсаңыз, "
            "растаңыз, сонда бот сізді бағыттағы келесі меридианға өткізеді."
        ),
        "complete_meridian_confirm_yes": "✅ Иә, келесіге өту",
        "complete_meridian_confirm_no": "↩️ Осы меридианды жалғастыру",
    },
}

for _language, _updates in MERIDIAN_COMPLETION_TEXT_OVERRIDES.items():
    TEXTS.setdefault(_language, {}).update(_updates)

SECRET_TASK_TEXT_OVERRIDES = {
    "en": {
        "secret_task_offer_governing": (
            "🌲 <b>Secret task</b>\n\n"
            "You have completed the Governing Vessel in the bot route. Do you want to open a practice task before moving to the next meridian?"
        ),
        "secret_task_yes": "🌲 Yes, open the task",
        "secret_task_no": "Not now, continue",
        "secret_task_governing": (
            "🌲 <b>Secret task: breathe with the Governing Vessel</b>\n\n"
            "Go to a forest, park, garden, or any quiet place in nature. Sit calmly, ideally with your back near a tree.\n\n"
            "Remember the whole Governing Vessel: from the lower point, up the spine, through the neck, head, and face. "
            "Do not rush. First feel the points you remember. Then let them connect into one line.\n\n"
            "Breathe as if the whole meridian is breathing with you. On the inhale, feel attention rising along the back line. "
            "On the exhale, let the body soften and release excess tension.\n\n"
            "The task is complete when the line becomes easier to feel as one living channel, not as separate points."
        ),
        "secret_task_continue": "➡️ Continue to next meridian",
        "secret_task_done": "✅ Task done",
        "secret_task_done_text": "✅ <b>Secret task marked as done.</b>\n\nThe route can continue.",
    },
    "ru": {
        "secret_task_offer_governing": (
            "🌲 <b>Секретное задание</b>\n\n"
            "Вы завершили Заднесрединный меридиан в маршруте бота. Хотите открыть практическое задание перед переходом к следующему меридиану?"
        ),
        "secret_task_yes": "🌲 Да, открыть задание",
        "secret_task_no": "Не сейчас, продолжить",
        "secret_task_governing": (
            "🌲 <b>Секретное задание: дыхание Заднесрединным меридианом</b>\n\n"
            "Сходите в лес, парк, сад или любое спокойное место на природе. Сядьте спокойно, по возможности спиной к дереву.\n\n"
            "Вспомните весь Заднесрединный меридиан: от нижней точки, вверх по позвоночнику, через шею, голову и лицо. "
            "Не спешите. Сначала почувствуйте те точки, которые уже помните. Затем соедините их в одну линию.\n\n"
            "Дышите так, будто весь меридиан дышит вместе с вами. На вдохе чувствуйте, как внимание поднимается по задней линии. "
            "На выдохе позволяйте телу смягчаться и отпускать лишнее напряжение.\n\n"
            "Задание выполнено, когда линию становится легче чувствовать целиком, как живой канал, а не как отдельные точки."
        ),
        "secret_task_continue": "➡️ Перейти к следующему меридиану",
        "secret_task_done": "✅ Задание выполнено",
        "secret_task_done_text": "✅ <b>Секретное задание отмечено как выполненное.</b>\n\nМаршрут можно продолжать.",
    },
    "uz": {
        "secret_task_offer_governing": (
            "🌲 <b>Maxfiy topshiriq</b>\n\n"
            "Siz bot yo‘nalishida Orqa o‘rta meridianni yakunladingiz. Keyingi meridianga o‘tishdan oldin amaliy topshiriqni ochasizmi?"
        ),
        "secret_task_yes": "🌲 Ha, topshiriqni ochish",
        "secret_task_no": "Hozir emas, davom etish",
        "secret_task_governing": (
            "🌲 <b>Maxfiy topshiriq: Orqa o‘rta meridian bilan nafas olish</b>\n\n"
            "O‘rmon, park, bog‘ yoki tabiatdagi sokin joyga boring. Imkon bo‘lsa, daraxtga orqangizni yaqin qilib tinch o‘tiring.\n\n"
            "Butun Orqa o‘rta meridianni eslang: pastki nuqtadan umurtqa bo‘ylab yuqoriga, bo‘yin, bosh va yuz orqali. "
            "Shoshilmang. Avval esingizda qolgan nuqtalarni his qiling. Keyin ularni bitta chiziqqa ulang.\n\n"
            "Butun meridian siz bilan birga nafas olayotgandek nafas oling. Nafas olayotganda e'tibor orqa chiziq bo‘ylab ko‘tarilishini his qiling. "
            "Nafas chiqarishda tana yumshasin va ortiqcha taranglik qo‘yib yuborilsin.\n\n"
            "Chiziqni alohida nuqtalar emas, bitta tirik kanal sifatida his qilish osonlashganda topshiriq bajarilgan bo‘ladi."
        ),
        "secret_task_continue": "➡️ Keyingi meridianga o‘tish",
        "secret_task_done": "✅ Topshiriq bajarildi",
        "secret_task_done_text": "✅ <b>Maxfiy topshiriq bajarildi deb belgilandi.</b>\n\nYo‘nalishni davom ettirish mumkin.",
    },
    "kz": {
        "secret_task_offer_governing": (
            "🌲 <b>Құпия тапсырма</b>\n\n"
            "Сіз бот бағытында Артқы ортаңғы меридианды аяқтадыңыз. Келесі меридианға өтпес бұрын практикалық тапсырманы ашқыңыз келе ме?"
        ),
        "secret_task_yes": "🌲 Иә, тапсырманы ашу",
        "secret_task_no": "Қазір емес, жалғастыру",
        "secret_task_governing": (
            "🌲 <b>Құпия тапсырма: Артқы ортаңғы меридианмен тыныстау</b>\n\n"
            "Орманға, паркке, баққа немесе табиғаттағы тыныш жерге барыңыз. Мүмкін болса, арқаңызды ағашқа жақын қойып, тыныш отырыңыз.\n\n"
            "Артқы ортаңғы меридианды түгел еске түсіріңіз: төменгі нүктеден омыртқа бойымен жоғары, мойын, бас және бет арқылы. "
            "Асықпаңыз. Алдымен есте қалған нүктелерді сезіңіз. Содан кейін оларды бір сызыққа қосыңыз.\n\n"
            "Бүкіл меридиан сізбен бірге тыныстап тұрғандай тыныс алыңыз. Дем алғанда назардың артқы сызық бойымен көтерілгенін сезіңіз. "
            "Дем шығарғанда дененің жұмсарып, артық кернеуді босатуына мүмкіндік беріңіз.\n\n"
            "Сызықты бөлек нүктелер емес, бір тірі арна ретінде сезіну жеңілдегенде тапсырма орындалды деп санауға болады."
        ),
        "secret_task_continue": "➡️ Келесі меридианға өту",
        "secret_task_done": "✅ Тапсырма орындалды",
        "secret_task_done_text": "✅ <b>Құпия тапсырма орындалды деп белгіленді.</b>\n\nБағытты жалғастыруға болады.",
    },
}

for _language, _updates in SECRET_TASK_TEXT_OVERRIDES.items():
    TEXTS.setdefault(_language, {}).update(_updates)

MICROCOSMIC_ORBIT_SECRET_TASK_TEXT_OVERRIDES = {
    "en": {
        "secret_task_offer_orbit": (
            "☯️ <b>Secret task</b>\n\n"
            "You have completed the Governing Vessel and the Conception Vessel. "
            "Do you want to open a practice with the central circle before moving to the next meridian?"
        ),
        "secret_task_orbit": (
            "☯️ <b>Secret task: central circle practice</b>\n\n"
            "Go to nature or a quiet park. Sit comfortably, soften the body, and let the breath become calm.\n\n"
            "<b>Forward circle:</b> on the inhale, feel energy rising from below upward along the Governing Vessel: "
            "through the base of the body, spine, neck, and head. On the exhale, let attention descend along the Conception Vessel: "
            "through the face, throat, chest, belly, and lower body. Let the two central lines connect into one soft circle.\n\n"
            "<b>Reverse, feminine circle:</b> then try the opposite direction: raise attention up the front surface of the body "
            "and let it descend down the back.\n\n"
            "Do not force the effect. Observe how the sensations change: where the circle moves easily, where the line breaks, "
            "where warmth, calm, density, lightness, or freedom appears."
        ),
        "secret_task_orbit_done_text": "✅ <b>Central circle practice marked as done.</b>\n\nThe route can continue.",
    },
    "ru": {
        "secret_task_offer_orbit": (
            "☯️ <b>Секретное задание</b>\n\n"
            "Вы прошли Заднесрединный и Переднесрединный меридианы. "
            "Хотите открыть практику центрального круга перед переходом к следующему меридиану?"
        ),
        "secret_task_orbit": (
            "☯️ <b>Секретное задание: центральный круг</b>\n\n"
            "Сходите на природу или в спокойный парк. Сядьте удобно, смягчите тело и дайте дыханию успокоиться.\n\n"
            "<b>Прямой круг:</b> на вдохе представляйте и чувствуйте, как энергия поднимается снизу вверх по Заднесрединному меридиану: "
            "через основание тела, спину, шею и голову. На выдохе опускайте внимание по Переднесрединному меридиану: "
            "через лицо, горло, грудь, живот и ниже. Пусть две центральные линии соединятся в один мягкий круг.\n\n"
            "<b>Обратный, женский круг:</b> затем попробуйте наоборот: поднимайте внимание по передней поверхности тела вверх "
            "и опускайте по спине вниз.\n\n"
            "Не добивайтесь эффекта силой. Наблюдайте, как меняются ощущения: где круг идёт легко, где линия обрывается, "
            "где появляется тепло, спокойствие, плотность, лёгкость или освобождение."
        ),
        "secret_task_orbit_done_text": "✅ <b>Практика центрального круга отмечена как выполненная.</b>\n\nМаршрут можно продолжать.",
    },
    "uz": {
        "secret_task_offer_orbit": (
            "☯️ <b>Maxfiy topshiriq</b>\n\n"
            "Siz Orqa o'rta va Old o'rta meridianlarni yakunladingiz. "
            "Keyingi meridianga o'tishdan oldin markaziy aylana amaliyotini ochasizmi?"
        ),
        "secret_task_orbit": (
            "☯️ <b>Maxfiy topshiriq: markaziy aylana</b>\n\n"
            "Tabiatga yoki sokin parkka boring. Qulay o'tiring, tanani yumshating va nafas tinchlansin.\n\n"
            "<b>To'g'ri aylana:</b> nafas olayotganda energiya pastdan yuqoriga Orqa o'rta meridian bo'ylab ko'tarilayotganini his qiling: "
            "tana asosi, umurtqa, bo'yin va bosh orqali. Nafas chiqarayotganda e'tiborni Old o'rta meridian bo'ylab pastga tushiring: "
            "yuz, tomoq, ko'krak, qorin va pastki tana orqali. Ikki markaziy chiziq bitta yumshoq aylanaga ulansin.\n\n"
            "<b>Teskari, ayol aylana:</b> keyin aksincha sinab ko'ring: e'tiborni tananing old yuzasi bo'ylab yuqoriga ko'taring "
            "va orqa tomondan pastga tushiring.\n\n"
            "Natijani zo'rlamang. Sezgilar qanday o'zgarishini kuzating: aylana qayerda oson yuradi, qayerda chiziq uziladi, "
            "qayerda iliqlik, xotirjamlik, zichlik, yengillik yoki erkinlik paydo bo'ladi."
        ),
        "secret_task_orbit_done_text": "✅ <b>Markaziy aylana amaliyoti bajarildi deb belgilandi.</b>\n\nYo'nalishni davom ettirish mumkin.",
    },
    "kz": {
        "secret_task_offer_orbit": (
            "☯️ <b>Құпия тапсырма</b>\n\n"
            "Сіз Артқы ортаңғы және Алдыңғы ортаңғы меридиандарды аяқтадыңыз. "
            "Келесі меридианға өтпей тұрып орталық шеңбер практикасын ашқыңыз келе ме?"
        ),
        "secret_task_orbit": (
            "☯️ <b>Құпия тапсырма: орталық шеңбер</b>\n\n"
            "Табиғатқа немесе тыныш паркке барыңыз. Ыңғайлы отырыңыз, денені жұмсартыңыз және тыныстың тынышталуына мүмкіндік беріңіз.\n\n"
            "<b>Тікелей шеңбер:</b> дем алғанда энергияның төменнен жоғары Артқы ортаңғы меридиан бойымен көтерілгенін сезіңіз: "
            "дене негізі, арқа, мойын және бас арқылы. Дем шығарғанда назарды Алдыңғы ортаңғы меридиан бойымен төмен түсіріңіз: "
            "бет, тамақ, кеуде, іш және төменгі дене арқылы. Екі орталық сызық бір жұмсақ шеңберге қосылсын.\n\n"
            "<b>Кері, әйел шеңбері:</b> содан кейін керісінше жасап көріңіз: назарды дененің алдыңғы бетімен жоғары көтеріп, "
            "арқа бойымен төмен түсіріңіз.\n\n"
            "Әсерді күшпен шақырмаңыз. Сезімдердің қалай өзгеретінін бақылаңыз: шеңбер қай жерде жеңіл жүреді, қай жерде сызық үзіледі, "
            "қай жерде жылу, тыныштық, тығыздық, жеңілдік немесе босану сезімі пайда болады."
        ),
        "secret_task_orbit_done_text": "✅ <b>Орталық шеңбер практикасы орындалды деп белгіленді.</b>\n\nБағытты жалғастыруға болады.",
    },
}

for _language, _updates in MICROCOSMIC_ORBIT_SECRET_TASK_TEXT_OVERRIDES.items():
    TEXTS.setdefault(_language, {}).update(_updates)

MERIDIAN_PRACTICE_ADVICE_TEXT_OVERRIDES = {
    "en": {
        "meridian_practice_advice": "🌿 Practice advice",
        "meridian_practice_advice_text": (
            "🌿 <b>Practice advice</b>\n\n"
            "<b>Best place:</b> if possible, practice meridian meditations in nature: in a forest, garden, near water, or in a quiet park. "
            "Choose a place that feels pleasant to you, where the atmosphere helps you settle down.\n\n"
            "Nature carries a lot of living energy: plants, trees, earth, air, water, birds, and animals all create a stronger field of life than a busy city street. "
            "This makes it easier to calm down, breathe deeper, and feel the body more clearly.\n\n"
            "<b>If nature is not available:</b> practice at home. The main thing is quiet conditions: no rush, no interruptions, no need to answer messages or talk to anyone.\n\n"
            "Meridian meditation needs not only concentration, but also inner calm. Before starting, sit comfortably, soften the body, breathe naturally, and only then move attention to the points."
        ),
    },
    "ru": {
        "meridian_practice_advice": "🌿 Советы для практики",
        "meridian_practice_advice_text": (
            "🌿 <b>Советы для практики</b>\n\n"
            "<b>Лучшее место:</b> если есть возможность, занимайтесь медитациями по меридианам на природе: в лесу, саду, у воды или в спокойном парке. "
            "Выберите место, которое вам нравится, где приятная атмосфера и телу легче успокоиться.\n\n"
            "На природе много живой энергии: растения, деревья, земля, воздух, вода, птицы и животные создают более сильное поле жизни, чем городская суета. "
            "Так легче расслабиться, глубже дышать и яснее чувствовать тело.\n\n"
            "<b>Если нет возможности выйти на природу:</b> занимайтесь дома. Главное, чтобы были спокойные условия: без спешки, без отвлечений, без необходимости отвечать на сообщения или разговаривать.\n\n"
            "Медитация по меридианам требует не только концентрации, но и внутреннего спокойствия. Перед началом сядьте удобно, смягчите тело, выровняйте дыхание и только потом переводите внимание к точкам."
        ),
    },
    "uz": {
        "meridian_practice_advice": "🌿 Amaliyot bo‘yicha maslahat",
        "meridian_practice_advice_text": (
            "🌿 <b>Amaliyot bo‘yicha maslahat</b>\n\n"
            "<b>Eng yaxshi joy:</b> imkon bo‘lsa, meridian meditatsiyalarini tabiatda bajaring: o‘rmon, bog‘, suv bo‘yi yoki sokin parkda. "
            "O‘zingizga yoqadigan, muhiti yoqimli va tanangiz tinchlanishi oson bo‘lgan joyni tanlang.\n\n"
            "Tabiatda hayot energiyasi ko‘proq seziladi: o‘simliklar, daraxtlar, yer, havo, suv, qushlar va hayvonlar shahar shovqiniga qaraganda kuchliroq tiriklik muhitini yaratadi. "
            "Shunda tinchlanish, chuqurroq nafas olish va tanani aniqroq sezish osonlashadi.\n\n"
            "<b>Agar tabiatga chiqish imkoni bo‘lmasa:</b> uyda shug‘ullaning. Muhimi, sharoit sokin bo‘lsin: shoshilmasdan, chalg‘imasdan, xabarlarga javob berish yoki gaplashish zaruratisiz.\n\n"
            "Meridian meditatsiyasi nafaqat diqqatni, balki ichki xotirjamlikni ham talab qiladi. Boshlashdan oldin qulay o‘tiring, tanani yumshating, nafasni tabiiy qiling va keyin diqqatni nuqtalarga olib boring."
        ),
    },
    "kz": {
        "meridian_practice_advice": "🌿 Практикаға кеңес",
        "meridian_practice_advice_text": (
            "🌿 <b>Практикаға кеңес</b>\n\n"
            "<b>Ең жақсы орын:</b> мүмкіндік болса, меридиан медитацияларын табиғатта жасаңыз: орманда, бақта, су маңында немесе тыныш паркте. "
            "Өзіңізге ұнайтын, атмосферасы жағымды және денеңізге тынышталу жеңіл болатын жерді таңдаңыз.\n\n"
            "Табиғатта тіршілік энергиясы көбірек сезіледі: өсімдіктер, ағаштар, жер, ауа, су, құстар мен жануарлар қала қарбаласына қарағанда тірі өрісті күштірек жасайды. "
            "Сонда тынышталу, тереңірек тыныс алу және денені анық сезу жеңілдейді.\n\n"
            "<b>Егер табиғатқа шығу мүмкін болмаса:</b> үйде айналысыңыз. Ең бастысы, жағдай тыныш болсын: асықпай, алаңдамай, хабарламаларға жауап бермей және сөйлеспей.\n\n"
            "Меридиан медитациясына тек концентрация емес, ішкі тыныштық та қажет. Бастамас бұрын ыңғайлы отырыңыз, денені жұмсартыңыз, тынысты табиғи етіңіз, содан кейін ғана зейінді нүктелерге бағыттаңыз."
        ),
    },
}

for _language, _updates in MERIDIAN_PRACTICE_ADVICE_TEXT_OVERRIDES.items():
    TEXTS.setdefault(_language, {}).update(_updates)

MERIDIAN_MAP_3D_TEXT_OVERRIDES = {
    "en": {
        "meridian_map_3d": "🧍 3D meridian map",
        "map3d_announcement": (
            "🧍 <b>New: a 3D meridian map</b>\n\n"
            "The bot now has a three-dimensional map of all 12 main meridians, Du Mai, Ren Mai and the six "
            "extraordinary vessels, with 361 points placed right on the body.\n\n"
            "What you can do with it:\n"
            "• turn the figure with one finger and zoom in on any spot;\n"
            "• open any point to see where it is, what it is for and how it helps;\n"
            "• show all yin or all yang meridians at once;\n"
            "• put the figure into an asana or a mudra, and the points and lines stay in place;\n"
            "• pick a background: Kailash, the pyramids, Altai, Tian Shan, Stonehenge.\n\n"
            "Open the map with the button below or from the meridians menu."
        ),
    },
    "ru": {
        "meridian_map_3d": "🧍 3D-карта меридианов",
        "map3d_announcement": (
            "🧍 <b>Новое: 3D-карта меридианов</b>\n\n"
            "В боте появилась объёмная карта: все 12 основных меридианов, Ду-май, Жэнь-май и шесть чудесных "
            "сосудов, 361 точка прямо на теле.\n\n"
            "Что с ней можно делать:\n"
            "• крутить фигуру пальцем и приближать нужное место;\n"
            "• открыть любую точку и посмотреть, где она, зачем нужна и чем полезна;\n"
            "• показать сразу все иньские или все янские меридианы;\n"
            "• поставить фигуру в асану или мудру, точки и линии останутся на своих местах;\n"
            "• выбрать фон: Кайлас, пирамиды, Алтай, Тянь-Шань, Стоунхендж.\n\n"
            "Открыть карту можно кнопкой ниже или из меню меридианов."
        ),
    },
    "uz": {
        "meridian_map_3d": "🧍 Meridianlarning 3D xaritasi",
        "map3d_announcement": (
            "🧍 <b>Yangilik: meridianlarning 3D xaritasi</b>\n\n"
            "Botda hajmli xarita paydo bo'ldi: 12 asosiy meridian, Du-mai, Ren-mai va oltita g'aroyib tomir, "
            "tananing o'zida 361 ta nuqta.\n\n"
            "Xarita bilan nima qilish mumkin:\n"
            "• figurani barmoq bilan aylantirish va kerakli joyni yaqinlashtirish;\n"
            "• istalgan nuqtani ochib, u qayerda, nima uchun kerak va nimaga foydali ekanini ko'rish;\n"
            "• barcha in yoki barcha yan meridianlarini birdaniga ko'rsatish;\n"
            "• figurani asana yoki mudraga qo'yish, nuqtalar va chiziqlar o'z joyida qoladi;\n"
            "• fonni tanlash: Kaylas, piramidalar, Oltoy, Tyan-Shan, Stounxenj.\n\n"
            "Xaritani pastdagi tugma yoki meridianlar menyusi orqali oching."
        ),
    },
    "kz": {
        "meridian_map_3d": "🧍 Меридиандардың 3D картасы",
        "map3d_announcement": (
            "🧍 <b>Жаңалық: меридиандардың 3D картасы</b>\n\n"
            "Ботта көлемді карта пайда болды: 12 негізгі меридиан, Ду-май, Жэнь-май және алты ғажайып тамыр, "
            "дененің өзінде 361 нүкте.\n\n"
            "Картамен не істеуге болады:\n"
            "• фигураны саусақпен айналдырып, керек жерді жақындату;\n"
            "• кез келген нүктені ашып, оның қайда екенін, не үшін керек екенін және пайдасын көру;\n"
            "• барлық инь немесе барлық ян меридиандарын бірден көрсету;\n"
            "• фигураны асанаға немесе мудраға қою, нүктелер мен сызықтар орнында қалады;\n"
            "• фонды таңдау: Қайлас, пирамидалар, Алтай, Тянь-Шань, Стоунхендж.\n\n"
            "Картаны төмендегі батырмамен немесе меридиандар мәзірінен ашыңыз."
        ),
    },
}

for _language, _updates in MERIDIAN_MAP_3D_TEXT_OVERRIDES.items():
    TEXTS.setdefault(_language, {}).update(_updates)

MERIDIAN_MAP_ACCESS_TEXT_OVERRIDES = {
    "en": {
        "meridian_show_on_body": "📍 Show on the body",
        "map_menu_button": "Map",
        "map_command_text": "🧍 <b>3D meridian map</b>\n\nAll meridians and 361 points right on the body. Open it with the button below.",
        "map_private_only": "The 3D map opens only in a private chat with the bot.",
        "map_unavailable": "The 3D map is not available right now.",
        "setup_map_hint": "🧍 Every point is also on the 3D body map: the button below or /map.",
    },
    "ru": {
        "meridian_show_on_body": "📍 Показать на теле",
        "map_menu_button": "Карта",
        "map_command_text": "🧍 <b>3D-карта меридианов</b>\n\nВсе меридианы и 361 точка прямо на теле. Откройте карту кнопкой ниже.",
        "map_private_only": "3D-карта открывается только в личном чате с ботом.",
        "map_unavailable": "3D-карта сейчас недоступна.",
        "setup_map_hint": "🧍 Любую точку можно посмотреть на 3D-карте тела: кнопка ниже или /map.",
    },
    "uz": {
        "meridian_show_on_body": "📍 Tanada ko'rsatish",
        "map_menu_button": "Xarita",
        "map_command_text": "🧍 <b>Meridianlarning 3D xaritasi</b>\n\nBarcha meridianlar va 361 ta nuqta tananing o'zida. Xaritani pastdagi tugma bilan oching.",
        "map_private_only": "3D xarita faqat bot bilan shaxsiy chatda ochiladi.",
        "map_unavailable": "3D xarita hozircha mavjud emas.",
        "setup_map_hint": "🧍 Istalgan nuqtani tananing 3D xaritasida ko'rish mumkin: pastdagi tugma yoki /map.",
    },
    "kz": {
        "meridian_show_on_body": "📍 Денеден көрсету",
        "map_menu_button": "Карта",
        "map_command_text": "🧍 <b>Меридиандардың 3D картасы</b>\n\nБарлық меридиан және 361 нүкте дененің өзінде. Картаны төмендегі батырмамен ашыңыз.",
        "map_private_only": "3D карта тек ботпен жеке чатта ашылады.",
        "map_unavailable": "3D карта қазір қолжетімсіз.",
        "setup_map_hint": "🧍 Кез келген нүктені дененің 3D картасынан көруге болады: төмендегі батырма немесе /map.",
    },
}

for _language, _updates in MERIDIAN_MAP_ACCESS_TEXT_OVERRIDES.items():
    TEXTS.setdefault(_language, {}).update(_updates)

SETUP_TIME_CHOICES = ("07:00", "08:00", "09:00", "20:00")

SETUP_TIME_TEXT_OVERRIDES = {
    "en": {
        "setup_time_other": "✏️ Other",
        "setup_time_buttons_hint": "Pick a time with a button. For a different time, tap “Other” and type it as HH:MM.",
        "setup_time_custom_prompt": "⌨️ Type the time as HH:MM, for example 07:30 or 21:15.",
    },
    "ru": {
        "setup_time_other": "✏️ Другое",
        "setup_time_buttons_hint": "Выберите время кнопкой. Если нужно другое, нажмите «Другое» и введите его в формате ЧЧ:ММ.",
        "setup_time_custom_prompt": "⌨️ Введите время в формате ЧЧ:ММ, например 07:30 или 21:15.",
    },
    "uz": {
        "setup_time_other": "✏️ Boshqa",
        "setup_time_buttons_hint": "Vaqtni tugma bilan tanlang. Boshqa vaqt kerak bo'lsa, «Boshqa» tugmasini bosing va uni HH:MM formatida kiriting.",
        "setup_time_custom_prompt": "⌨️ Vaqtni HH:MM formatida kiriting, masalan 07:30 yoki 21:15.",
    },
    "kz": {
        "setup_time_other": "✏️ Басқа",
        "setup_time_buttons_hint": "Уақытты батырмамен таңдаңыз. Басқа уақыт керек болса, «Басқа» батырмасын басып, оны HH:MM форматында енгізіңіз.",
        "setup_time_custom_prompt": "⌨️ Уақытты HH:MM форматында енгізіңіз, мысалы 07:30 немесе 21:15.",
    },
}

for _language, _updates in SETUP_TIME_TEXT_OVERRIDES.items():
    TEXTS.setdefault(_language, {}).update(_updates)

DEPRECATED_TEXT_KEYS = ("feedback_request", "feedback_received", "skip_days_saved")
for _language_texts in TEXTS.values():
    for _key in DEPRECATED_TEXT_KEYS:
        _language_texts.pop(_key, None)


class BotHandlers:
    """Handlers for bot commands."""

    def __init__(
        self,
        application: Application,
        storage: JsonStorage,
        scheduler: YogaScheduler,
        principles_manager: PrinciplesManager,
        meridians_manager: MeridiansManager,
        admin_ids: List[int],
        webapp_url: str = ""
    ):
        self.application = application
        self.storage = storage
        self.scheduler = scheduler
        self.principles_manager = principles_manager
        self.meridians_manager = meridians_manager
        self.admin_ids = admin_ids
        self.webapp_url = webapp_url
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
        self.application.add_handler(CommandHandler("map", self._handle_map))

        # Admin commands.
        self.application.add_handler(
            MessageHandler(
                filters.Regex(r"^/(stats|feedback_stats|feedback_list|progress|broadcast|resend_today)(?:@\w+)?(?:\s|$)"),
                self._handle_admin_text_command_fallback
            ),
            group=-1
        )
        self.application.add_handler(CommandHandler("next", self._handle_next))
        self.application.add_handler(CommandHandler("add", self._handle_add_principle))
        self.application.add_handler(CommandHandler("stats", self._handle_stats))
        self.application.add_handler(CommandHandler("broadcast", self._handle_broadcast))
        self.application.add_handler(CommandHandler("resend_today", self._handle_resend_today))
        self.application.add_handler(CommandHandler("feedback_stats", self._handle_feedback_stats))
        self.application.add_handler(CommandHandler("feedback_list", self._handle_feedback_list))
        self.application.add_handler(CommandHandler("progress", self._handle_progress))
        self.application.add_handler(CommandHandler("admin", self._handle_admin))
        self.application.add_handler(CommandHandler("subscribers", self._handle_subscribers))

        # Callback query handlers.
        self.application.add_handler(CallbackQueryHandler(self._handle_language_callback, pattern="^lang_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_intro_callback, pattern="^intro_mode_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_timezone_callback, pattern="^tz_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_setup_time_callback, pattern="^settime_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_skipday_callback, pattern="^skipday_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_menu_callback, pattern="^menu_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_principles_callback, pattern="^principles_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_settings_callback, pattern="^settings_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_change_callback, pattern="^change_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_mode_callback, pattern="^mode_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_stop_feedback_skip_callback, pattern="^stop_feedback_skip$"))
        self.application.add_handler(CallbackQueryHandler(self._handle_meridian_callback, pattern="^meridian_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_broadcast_callback, pattern="^broadcast_"))
        self.application.add_handler(CallbackQueryHandler(self._handle_admin_callback, pattern="^admin_"))

        # General message handler for registration flow.
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

    def _get_text(self, key: str, language: str = "en", **kwargs) -> str:
        """Get localized text."""
        return TEXTS.get(language, TEXTS["en"]).get(key, key).format(**kwargs)

    def _extract_command_args(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> List[str]:
        """Return command arguments even when a text fallback handled the command."""
        if getattr(context, "args", None):
            return list(context.args)
        message = getattr(update, "message", None)
        text = getattr(message, "text", "") or ""
        parts = text.split(maxsplit=1)
        return parts[1].split() if len(parts) > 1 else []

    async def _handle_admin_text_command_fallback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Catch critical admin commands as plain text if CommandHandler does not answer."""
        message = update.message
        if not message or not message.text:
            return

        command = message.text.split(maxsplit=1)[0].split("@", 1)[0].lower()
        logger.info("Admin text command fallback received %s from chat %s", command, update.effective_chat.id)

        if command == "/stats":
            await self._handle_stats(update, context)
            raise ApplicationHandlerStop
        if command == "/feedback_stats":
            await self._handle_feedback_stats(update, context)
            raise ApplicationHandlerStop
        if command == "/feedback_list":
            await self._handle_feedback_list(update, context)
            raise ApplicationHandlerStop
        if command == "/progress":
            await self._handle_progress(update, context)
            raise ApplicationHandlerStop
        if command == "/broadcast":
            await self._handle_broadcast(update, context)
            raise ApplicationHandlerStop
        if command == "/resend_today":
            await self._handle_resend_today(update, context)
            raise ApplicationHandlerStop

    def _as_html(self, text: str) -> str:
        """Normalize legacy Markdown-bold text for HTML parse mode."""
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    def _text_html(self, key: str, language: str = "en", **kwargs) -> str:
        """Get localized text normalized for HTML parse mode."""
        return self._as_html(self._get_text(key, language, **kwargs))

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

    def _setup_time_prompt(self, language: str, user_state: Dict[str, Any], custom: bool = False) -> str:
        """Prompt of the current setup time step: the buttons hint, or the typing prompt after "Other"."""
        if user_state.get("step") == "meridian_time":
            step_text = self._get_text("meridian_time_setup_step", language)
        else:
            step_text = self._get_time_step_text(language, user_state)
        hint_key = "setup_time_custom_prompt" if custom else "setup_time_buttons_hint"
        return f"{step_text}\n\n{escape(self._get_text(hint_key, language))}"

    def _create_setup_time_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Ready-made reminder times for setup; "Other" switches to typing HH:MM."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(value, callback_data=f"settime_{value}") for value in SETUP_TIME_CHOICES[:2]],
            [InlineKeyboardButton(value, callback_data=f"settime_{value}") for value in SETUP_TIME_CHOICES[2:]],
            [InlineKeyboardButton(self._get_text("setup_time_other", language), callback_data="settime_other")],
        ])

    def _format_principles_list(self, language: str) -> str:
        """Format all Yama/Niyama principles as a compact catalogue heading."""
        principles = self.principles_manager.get_all_principles(language)
        if not principles:
            return self._get_text("principles_empty", language)

        title = self._get_text("principles_all", language)
        intro = {
            "en": "Choose any principle to open its image and practice card. These are not separate lessons to collect; they are ten doors back to the same everyday attention.",
            "ru": "Выберите любой принцип, чтобы открыть картинку и карточку практики. Это не отдельные уроки для коллекции, а десять дверей к одному и тому же вниманию в обычной жизни.",
            "uz": "Rasm va amaliyot kartasini ochish uchun istalgan tamoyilni tanlang. Bu yig'ib boriladigan alohida darslar emas; ular kundalik diqqatga qaytaradigan o'nta eshik.",
            "kz": "Сурет пен тәжірибе картасын ашу үшін кез келген қағиданы таңдаңыз. Бұлар жинайтын бөлек сабақтар емес; күнделікті зейінге қайтаратын он есік.",
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
        """Format a selected principle exactly like the daily principle card."""
        return format_principle_message(principle, language, max_length or 4096)

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        chat_id = update.effective_chat.id

        try:
            # Check if user already exists.
            user = await self.storage.get_user(chat_id)
            if user and user.is_active:
                text = self._get_text("already_subscribed", user.language)
                await update.message.reply_text(text, parse_mode='HTML')
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
                    keyboard = self._create_main_menu_keyboard_for_user(chat_id, language, user)
                    await self._set_user_map_menu_button(chat_id, language)
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
                keyboard = self._create_registration_modes_keyboard(language, chat_id)

                # the "Map" chat button from the first message on, not only after the setup is finished
                await self._set_user_map_menu_button(chat_id, language)
                logger.debug(f"Sending onboarding intro in {language} to user {chat_id}")
                try:
                    await self._edit_message_text_safe(query, combined_msg, reply_markup=keyboard, parse_mode='HTML')
                except BadRequest as e:
                    # a map URL Telegram refuses must not leave the newcomer stuck on the language choice
                    logger.warning(f"Onboarding intro with the map button refused for {chat_id}: {e}")
                    await self._edit_message_text_safe(
                        query, combined_msg, reply_markup=self._create_registration_modes_keyboard(language), parse_mode='HTML'
                    )

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
                    f"{self._get_text('timezone_manual_prompt', language)}"
                )
                await self._edit_message_text_safe(query, custom_msg, parse_mode='HTML')
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
                                keyboard = self._create_main_menu_keyboard_for_user(chat_id, language, user)
                                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')
                            else:
                                await self._edit_message_text_safe(query, self._get_text("setup_error", language), parse_mode='HTML')
                    else:
                        # Handle new registration
                        self.user_states[chat_id]["timezone"] = timezone_str
                        self.user_states[chat_id]["step"] = "time"

                        confirmation = self._get_text("timezone_saved", language)
                        time_msg = self._setup_time_prompt(language, self.user_states[chat_id])

                        combined_msg = f"{confirmation}\n\n{time_msg}"

                        await self._edit_message_text_safe(
                            query, combined_msg, reply_markup=self._create_setup_time_keyboard(language), parse_mode='HTML'
                        )
                else:
                    await self._edit_message_text_safe(query, self._get_text("invalid_timezone", language), parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error in timezone callback for user {chat_id}: {e}")
            language = self.user_states.get(chat_id, {}).get("language", "en")
            await self._edit_message_text_safe(query, self._get_text("error", language))

    async def _handle_setup_time_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the reminder time buttons of the setup steps (typing HH:MM keeps working too)."""
        query = update.callback_query
        chat_id = query.message.chat.id
        value = query.data.split("_", 1)[1]

        try:
            await query.answer()
            user_state = self.user_states.get(chat_id)
            if not user_state or user_state.get("step") not in ("time", "meridian_time"):
                logger.debug(f"Invalid state for setup time callback {chat_id}: {user_state}")
                return

            language = user_state["language"]
            user_state["registration_message_id"] = query.message.message_id
            if value == "other":
                await self._edit_message_text_safe(
                    query, self._setup_time_prompt(language, user_state, custom=True), parse_mode='HTML'
                )
                return
            if value not in SETUP_TIME_CHOICES:
                return

            # the typed-input handlers edit the registration message and read only the chat and the message
            as_message = SimpleNamespace(effective_chat=update.effective_chat, message=query.message)
            if user_state["step"] == "time":
                await self._handle_time_input(as_message, value, language)
            else:
                await self._handle_setup_meridian_time_input(as_message, value, language)

        except Exception as e:
            logger.error(f"Error in setup time callback for user {chat_id}: {e}")
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
        text = f"{self._text_html('skip_days_step', language)}\n\n{self._format_skip_days_note(selected_days, language)}"

        keyboard = self._create_skip_days_keyboard(language, selected_days)
        await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')

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
                                confirmation = "✅ Quiet days cleared — daily reminders are enabled"
                            elif language == "ru":
                                confirmation = "✅ Дни тишины очищены — ежедневные напоминания включены"
                            elif language == "uz":
                                confirmation = "✅ Sokin kunlar tozalandi — kundalik eslatmalar yoqildi"
                            elif language == "kz":
                                confirmation = "✅ Тыныш күндер тазартылды — күнделікті еске салулар қосылды"

                        text = f"{escape(confirmation)}\n\n{self._text_html('menu', language)}"
                        keyboard = self._create_main_menu_keyboard_for_user(chat_id, language, user)

                        await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')
                    else:
                        await self._edit_message_text_safe(query, self._get_text("setup_error", language), parse_mode='HTML')

            except Exception as e:
                logger.error(f"Error updating skip days for user {chat_id}: {e}")
                await self._edit_message_text_safe(query, self._get_text("error", language), parse_mode='HTML')

        else:
            # Handle new registration
            from bot.storage import User

            user = User(
                chat_id=chat_id,
                language=language,
                timezone=user_state["timezone"],
                time_for_send=user_state["time"],
                meridian_time_for_send=user_state.get("meridian_time", user_state["time"]),
                skip_day_id=selected_days,
                principles_enabled=user_state.get("principles_enabled", True),
                meridians_enabled=user_state.get("meridians_enabled", False),
                is_active=True
            )
            if user.meridians_enabled and not user.current_meridian_id:
                user.meridian_learning_mode = "guided"
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
                text += f"\n\n{self._text_html('menu', language)}"
                keyboard = self._create_main_menu_keyboard_for_user(chat_id, language, user)
                logger.debug(f"Final setup message for user {chat_id} in language {language}: {text[:150]}...")

                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')
                # Store the final message ID
                await self.storage.add_bot_message(chat_id, query.message.message_id, "setup_complete")
                await self._set_user_map_menu_button(chat_id, language)
            else:
                await self._edit_message_text_safe(query, self._get_text("setup_error", language), parse_mode='HTML')

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
                text = self._as_html(f"{self._get_text('unsubscribed', language)}\n\n{self._get_text('stop_feedback_prompt', language)}")
                self.user_states[chat_id] = {"step": "stop_feedback", "language": language}
                # Remove user from scheduler
                await self.scheduler.remove_user_jobs(chat_id)
            else:
                self.user_states.pop(chat_id, None)
                text = self._get_text("not_subscribed", language)

            # Send final message directly through bot API
            reply_markup = self._create_stop_feedback_keyboard(language) if success else None
            await self.application.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML')

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
                language = user.language if user else "en"
                await update.message.reply_text(self._get_text("not_subscribed_test", language=language))
                return

            skip_days_display = self._format_skip_days(user.skip_day_id, user.language)

            text = f"{self._format_current_settings(user, user.language, skip_days_display)}\n\n{self._get_text('settings_menu', language=user.language)}"
            keyboard = self._create_settings_menu_keyboard(user.language, user)

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

            success = await self.scheduler.send_reminder_check_message(chat_id, user.language)
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
            await update.message.reply_text(self._get_admin_text("add_disabled"))
        except Exception as e:
            logger.error(f"Error in add principle handler: {e}")

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
            args = self._extract_command_args(update, context)
            logger.info("Broadcast command received from admin %s with args=%s", chat_id, args)

            if not args:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🧍 Announce the 3D meridian map", callback_data="broadcast_map3d_announcement")],
                    [InlineKeyboardButton("📢 Send update announcement", callback_data="broadcast_meridians_announcement")],
                ])
                await update.message.reply_text(
                    f"{self._get_admin_text('broadcast_usage')}\n\nOr choose a localized template:",
                    reply_markup=keyboard
                )
                return

            broadcast_text = " ".join(args)
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

    async def _handle_resend_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Resend regular daily practices to all active users."""
        chat_id = update.effective_chat.id
        if chat_id not in self.admin_ids or not update.message:
            return

        try:
            active_users = await self.storage.get_all_active_users()
            await update.message.reply_text(
                self._get_admin_text("resend_today_start", count=len(active_users))
            )
            reached, failed, deliveries = await self.scheduler.resend_daily_reminders_to_all()
            await update.message.reply_text(
                self._get_admin_text(
                    "resend_today_result",
                    reached=reached,
                    deliveries=deliveries,
                    failed=failed,
                    total=len(active_users)
                )
            )
        except Exception as e:
            logger.error("Error resending daily reminders: %s", e)
            await update.message.reply_text("Error while resending today's reminders.")

    async def _send_localized_broadcast(self, text_key: str, context: ContextTypes.DEFAULT_TYPE,
                                        map_button: bool = False) -> tuple:
        """Send a localized broadcast template to all active users (map_button: with the 3D map button)."""
        active_users = await self.storage.get_all_active_users()
        sent_count = 0
        failed_count = 0

        for user in active_users:
            try:
                text = self._get_text(text_key, user.language)
                markup = None
                if map_button:
                    button = self._create_meridian_map_button(user.language, user)
                    markup = InlineKeyboardMarkup([[button]]) if button else None
                await context.bot.send_message(user.chat_id, text, parse_mode='HTML', reply_markup=markup)
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

            registration_steps = {"intro", "timezone", "timezone_manual", "time", "meridian_time", "skip_days"}
            user = await self.storage.get_user(chat_id)
            if user and not user.is_active and step not in registration_steps and step != "stop_feedback":
                self.user_states.pop(chat_id, None)
                await update.message.reply_text(self._get_text("not_subscribed_test", language), parse_mode='HTML')
                return

            if step == "timezone" or step == "timezone_manual":
                await self._handle_timezone_input(update, message_text, language)
            elif step == "time":
                await self._handle_time_input(update, message_text, language)
            elif step == "meridian_time":
                await self._handle_setup_meridian_time_input(update, message_text, language)
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
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(self._get_text("invalid_timezone", language), parse_mode='HTML')
            return

        # Save timezone and move to next step.
        self.user_states[chat_id]["timezone"] = timezone_str
        self.user_states[chat_id]["step"] = "time"

        confirmation = self._get_text("timezone_saved", language)
        time_msg = self._setup_time_prompt(language, user_state)

        combined_msg = f"{confirmation}\n\n{time_msg}"
        keyboard = self._create_setup_time_keyboard(language)

        if message_id:
            await self._edit_bot_message_text_safe(
                chat_id=chat_id,
                message_id=message_id,
                text=combined_msg,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(combined_msg, reply_markup=keyboard, parse_mode='HTML')

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
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(self._get_text("invalid_time", language))
            return

        # Save time and move to next step.
        self.user_states[chat_id]["time"] = time_str

        if user_state.get("principles_enabled", True) and user_state.get("meridians_enabled", False):
            self.user_states[chat_id]["step"] = "meridian_time"
            confirmation = self._get_text("time_saved", language)
            meridian_time_msg = self._setup_time_prompt(language, user_state)
            combined_msg = f"{escape(confirmation)}\n\n{meridian_time_msg}"
            keyboard = self._create_setup_time_keyboard(language)

            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=combined_msg,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(combined_msg, reply_markup=keyboard, parse_mode='HTML')
            return

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
                user.meridian_learning_mode = "guided"
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
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_text(self._get_text("setup_error", language), parse_mode='HTML')
                return

            await self.scheduler.schedule_user_immediately(chat_id)
            del self.user_states[chat_id]

            text = self._format_setup_complete(user, language, self._format_skip_days([], language))
            text += f"\n\n{self._text_html('menu', language)}"
            keyboard = self._create_main_menu_keyboard_for_user(chat_id, language, user)
            await self._set_user_map_menu_button(chat_id, language)

            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
                await self.storage.add_bot_message(chat_id, message_id, "setup_complete")
            else:
                sent = await update.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')
                await self.storage.add_bot_message(chat_id, sent.message_id, "setup_complete")
            return

        self.user_states[chat_id]["step"] = "skip_days"
        self.user_states[chat_id]["selected_skip_days"] = []  # Initialize empty selection

        confirmation = self._get_text("time_saved", language)
        skip_days_msg = self._text_html("skip_days_step", language)

        combined_msg = f"{escape(confirmation)}\n\n{skip_days_msg}\n\n{self._format_skip_days_note([], language)}"

        keyboard = self._create_skip_days_keyboard(language, [])

        if message_id:
            await self._edit_bot_message_text_safe(
                chat_id=chat_id,
                message_id=message_id,
                text=combined_msg,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(combined_msg, parse_mode='HTML')


    async def _handle_setup_meridian_time_input(self, update: Update, time_str: str, language: str) -> None:
        """Handle separate meridian reminder time during registration."""
        chat_id = update.effective_chat.id
        user_state = self.user_states[chat_id]
        message_id = user_state.get("registration_message_id")

        if not is_valid_time_format(time_str):
            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=self._get_text("invalid_time", language),
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(self._get_text("invalid_time", language), parse_mode='HTML')
            return

        self.user_states[chat_id]["meridian_time"] = time_str
        self.user_states[chat_id]["step"] = "skip_days"
        self.user_states[chat_id]["selected_skip_days"] = []

        confirmation = self._get_text("meridian_time_saved", language)
        skip_days_msg = self._text_html("skip_days_step", language)
        combined_msg = f"{escape(confirmation)}\n\n{skip_days_msg}\n\n{self._format_skip_days_note([], language)}"
        keyboard = self._create_skip_days_keyboard(language, [])

        if message_id:
            await self._edit_bot_message_text_safe(
                chat_id=chat_id,
                message_id=message_id,
                text=combined_msg,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(combined_msg, reply_markup=keyboard, parse_mode='HTML')



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

    def _format_skip_days_note(self, skip_days: List[int], language: str, current: bool = False) -> str:
        """Format current skip-days state for HTML messages."""
        if skip_days:
            label = {
                "en": "Quiet days now" if current else "Bot will stay silent on",
                "ru": "Текущие дни тишины" if current else "Бот будет молчать в эти дни",
                "uz": "Hozirgi sokin kunlar" if current else "Bot shu kunlarda jim turadi",
                "kz": "Қазіргі тыныш күндер" if current else "Бот осы күндері тыныш болады",
            }.get(language, "Bot will stay silent on")
            return f"🔸 <b>{label}:</b> {escape(self._format_skip_days(skip_days, language))}"

        empty = {
            "en": "No quiet days selected — reminders will be sent daily",
            "ru": "Дни тишины не выбраны — напоминания будут приходить каждый день",
            "uz": "Sokin kunlar tanlanmagan — eslatmalar har kuni yuboriladi",
            "kz": "Тыныш күндер таңдалмаған — еске салулар күн сайын жіберіледі",
        }.get(language, "No days selected — messages will be sent daily")
        return f"🔸 <b>{empty}</b>"

    def _format_setup_complete(self, user, language: str, skip_days_display: str) -> str:
        """Format setup summary according to the selected practice modes."""
        labels = {
            "en": {
                "done": "🎉 <b>The first step is set.</b>",
                "settings": "📋 <b>Your rhythm:</b>",
                "mode": "🧭 Practice:",
                "principles": "Yama/Niyama",
                "meridians": "Meridians",
                "both": "Yama/Niyama + Meridians",
                "time": "🕐 Time:",
                "principle_time": "🕐 Yama/Niyama time:",
                "meridian_time": "☯️ Meridian time:",
                "timezone": "🌍 Time zone:",
                "skip": "📅 Quiet days:",
                "next_principles": "From here the practice is simple: return to one principle during the day and notice where it changes thought, speech, or action. The other principles are not paused; today's card is only the doorway.",
                "next_meridians": "At the chosen time the bot will bring you back to the current meridian or point. Nothing moves forward automatically: you add the next point only when the sensation is ready enough.",
                "next_both": "Your rhythm now has two layers: an ethical focus for the day and a body focus through meridians. Let them support each other: less wasted energy, more attention in the body.",
                "hint": "Use /menu when you want to open the lists, adjust the rhythm, or continue the next small step.",
            },
            "ru": {
                "done": "🎉 <b>Первый шаг настроен.</b>",
                "settings": "📋 <b>Ваш ритм:</b>",
                "mode": "🧭 Практика:",
                "principles": "Яма/Нияма",
                "meridians": "Меридианы",
                "both": "Яма/Нияма + Меридианы",
                "time": "🕐 Время:",
                "principle_time": "🕐 Время Ямы/Ниямы:",
                "meridian_time": "☯️ Время меридианов:",
                "timezone": "🌍 Часовой пояс:",
                "skip": "📅 Дни тишины:",
                "next_principles": "Дальше всё просто: возвращайтесь к одному принципу в течение дня и замечайте, как он меняет мысли, речь и поступки. Остальные принципы не выключаются; карточка дня только задаёт вход.",
                "next_meridians": "В выбранное время бот вернёт вас к текущему меридиану или точке. Ничего не двигается вперёд автоматически: следующую точку стоит добавлять только когда ощущение уже достаточно готово.",
                "next_both": "Теперь у ритма два слоя: нравственный фокус дня и телесный фокус через меридианы. Пусть они поддерживают друг друга: меньше слитой энергии, больше внимания в теле.",
                "hint": "Используйте /menu, когда захотите открыть списки, изменить ритм или продолжить следующий небольшой шаг.",
            },
            "uz": {
                "done": "🎉 <b>Birinchi qadam sozlandi.</b>",
                "settings": "📋 <b>Ritmingiz:</b>",
                "mode": "🧭 Amaliyot:",
                "principles": "Yama/Niyama",
                "meridians": "Meridianlar",
                "both": "Yama/Niyama + Meridianlar",
                "time": "🕐 Vaqt:",
                "principle_time": "🕐 Yama/Niyama vaqti:",
                "meridian_time": "☯️ Meridian vaqti:",
                "timezone": "🌍 Vaqt mintaqasi:",
                "skip": "📅 Sokin kunlar:",
                "next_principles": "Endi ish oddiy: kun davomida bitta tamoyilga qayting va u fikr, so'z va harakatni qanday o'zgartirishini kuzating. Boshqa tamoyillar to'xtamaydi; kun kartasi faqat kirish eshigi.",
                "next_meridians": "Tanlangan vaqtda bot sizni joriy meridian yoki nuqtaga qaytaradi. Hech narsa avtomatik oldinga siljimaydi: keyingi nuqtani sezgi yetarlicha tayyor bo'lganda qo'shasiz.",
                "next_both": "Endi ritm ikki qatlamdan iborat: kunning axloqiy fokusi va meridianlar orqali tana fokusi. Ular bir-birini qo'llasin: kamroq energiya yo'qotish, tanada ko'proq diqqat.",
                "hint": "Ro'yxatlarni ochish, ritmni o'zgartirish yoki keyingi kichik qadamni davom ettirish uchun /menu dan foydalaning.",
            },
            "kz": {
                "done": "🎉 <b>Алғашқы қадам бапталды.</b>",
                "settings": "📋 <b>Ырғағыңыз:</b>",
                "mode": "🧭 Тәжірибе:",
                "principles": "Яма/Нияма",
                "meridians": "Меридиандар",
                "both": "Яма/Нияма + Меридиандар",
                "time": "🕐 Уақыт:",
                "principle_time": "🕐 Яма/Нияма уақыты:",
                "meridian_time": "☯️ Меридиан уақыты:",
                "timezone": "🌍 Уақыт белдеуі:",
                "skip": "📅 Тыныш күндер:",
                "next_principles": "Енді жұмыс қарапайым: күн ішінде бір қағидаға қайта оралып, оның ойды, сөзді және әрекетті қалай өзгертетінін байқаңыз. Қалған қағидалар тоқтамайды; күн картасы тек кіру есігі.",
                "next_meridians": "Таңдалған уақытта бот сізді ағымдағы меридианға немесе нүктеге қайтарады. Ештеңе автоматты түрде алға жылжымайды: келесі нүктені сезім жеткілікті дайын болғанда қосасыз.",
                "next_both": "Енді ырғақ екі қабаттан тұрады: күннің этикалық фокусы және меридиандар арқылы дене фокусы. Олар бірін-бірі қолдасын: энергия аз шашылсын, денеде зейін көбейсін.",
                "hint": "Тізімдерді ашу, ырғақты өзгерту немесе келесі шағын қадамды жалғастыру үшін /menu қолданыңыз.",
            },
        }.get(language)

        if user.principles_enabled and user.meridians_enabled:
            mode = labels["both"]
            next_text = labels["next_both"]
        elif user.meridians_enabled:
            mode = labels["meridians"]
            next_text = labels["next_meridians"]
        else:
            mode = labels["principles"]
            next_text = labels["next_principles"]

        lines = [
            labels["done"],
            "",
            labels["settings"],
            f"{labels['mode']} {mode}",
            f"{labels['timezone']} <code>{escape(user.timezone)}</code>",
        ]

        if user.principles_enabled and user.meridians_enabled:
            lines.extend([
                f"{labels['principle_time']} <code>{escape(user.time_for_send)}</code>",
                f"{labels['meridian_time']} <code>{escape(user.meridian_time_for_send)}</code>",
                f"{labels['skip']} {escape(skip_days_display)}",
            ])
        elif user.principles_enabled:
            lines.extend([
                f"{labels['time']} <code>{escape(user.time_for_send)}</code>",
                f"{labels['skip']} {escape(skip_days_display)}",
            ])
        else:
            lines.extend([
                f"{labels['meridian_time']} <code>{escape(user.meridian_time_for_send)}</code>",
                f"{labels['skip']} {escape(skip_days_display)}",
            ])

        lines.extend(["", next_text])
        if self.webapp_url and getattr(user, "chat_id", 0) > 0:
            # the 3D map row of the main menu sits right under this message
            lines.extend(["", self._get_text("setup_map_hint", language)])
        lines.extend(["", labels["hint"]])
        return "\n".join(lines)

    def _format_current_settings(self, user, language: str, skip_days_display: str) -> str:
        """Format a concise current settings snapshot for /settings."""
        labels = {
            "en": {
                "title": "⚙️ <b>Current practice rhythm</b>",
                "language": "🌐 Language:",
                "mode": "🧭 Active path:",
                "principles": "Yama/Niyama",
                "meridians": "Meridians",
                "both": "Yama/Niyama + Meridians",
                "timezone": "🌍 Time zone:",
                "principle_time": "🕊️ Yama/Niyama time:",
                "meridian_time": "☯️ Meridian time:",
                "quiet": "📅 Quiet days:",
            },
            "ru": {
                "title": "⚙️ <b>Текущий ритм практики</b>",
                "language": "🌐 Язык:",
                "mode": "🧭 Активный путь:",
                "principles": "Яма/Нияма",
                "meridians": "Меридианы",
                "both": "Яма/Нияма + Меридианы",
                "timezone": "🌍 Часовой пояс:",
                "principle_time": "🕊️ Время Ямы/Ниямы:",
                "meridian_time": "☯️ Время меридианов:",
                "quiet": "📅 Дни тишины:",
            },
            "uz": {
                "title": "⚙️ <b>Joriy amaliyot ritmi</b>",
                "language": "🌐 Til:",
                "mode": "🧭 Faol yo'l:",
                "principles": "Yama/Niyama",
                "meridians": "Meridianlar",
                "both": "Yama/Niyama + Meridianlar",
                "timezone": "🌍 Vaqt mintaqasi:",
                "principle_time": "🕊️ Yama/Niyama vaqti:",
                "meridian_time": "☯️ Meridian vaqti:",
                "quiet": "📅 Sokin kunlar:",
            },
            "kz": {
                "title": "⚙️ <b>Қазіргі тәжірибе ырғағы</b>",
                "language": "🌐 Тіл:",
                "mode": "🧭 Белсенді жол:",
                "principles": "Яма/Нияма",
                "meridians": "Меридиандар",
                "both": "Яма/Нияма + Меридиандар",
                "timezone": "🌍 Уақыт белдеуі:",
                "principle_time": "🕊️ Яма/Нияма уақыты:",
                "meridian_time": "☯️ Меридиан уақыты:",
                "quiet": "📅 Тыныш күндер:",
            },
        }.get(language)

        language_display = {"en": "English", "ru": "Русский", "uz": "O'zbek", "kz": "Қазақша"}.get(language, "English")
        if user.principles_enabled and user.meridians_enabled:
            mode = labels["both"]
        elif user.meridians_enabled:
            mode = labels["meridians"]
        else:
            mode = labels["principles"]

        lines = [
            labels["title"],
            "",
            f"{labels['language']} {escape(language_display)}",
            f"{labels['mode']} {escape(mode)}",
            f"{labels['timezone']} <code>{escape(user.timezone)}</code>",
        ]
        if user.principles_enabled:
            lines.append(f"{labels['principle_time']} <code>{escape(user.time_for_send)}</code>")
        if user.meridians_enabled:
            lines.append(f"{labels['meridian_time']} <code>{escape(user.meridian_time_for_send)}</code>")
        lines.append(f"{labels['quiet']} {escape(skip_days_display)}")
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
            keyboard.append([InlineKeyboardButton("🎯 No quiet days", callback_data="skipday_none")])
            keyboard.append([InlineKeyboardButton("📅 Skip weekends", callback_data="skipday_weekends")])
        elif language == "ru":
            keyboard.append([InlineKeyboardButton("🎯 Без дней тишины", callback_data="skipday_none")])
            keyboard.append([InlineKeyboardButton("📅 Пропускать выходные", callback_data="skipday_weekends")])
        elif language == "uz":
            keyboard.append([InlineKeyboardButton("🎯 Sokin kunlarsiz", callback_data="skipday_none")])
            keyboard.append([InlineKeyboardButton("📅 Dam olish kunlarini o'tkazish", callback_data="skipday_weekends")])
        elif language == "kz":
            keyboard.append([InlineKeyboardButton("🎯 Тыныш күндерсіз", callback_data="skipday_none")])
            keyboard.append([InlineKeyboardButton("📅 Демалыс күндерін өткізу", callback_data="skipday_weekends")])

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

    def _create_main_menu_keyboard(
        self,
        language: str,
        is_admin: bool = False,
        map_button: Optional[InlineKeyboardButton] = None
    ) -> InlineKeyboardMarkup:
        """Create main menu keyboard (map_button: the 3D map row, private chats only)."""
        keyboard = [
            [
                InlineKeyboardButton(self._get_text("menu_principles", language), callback_data="menu_principles"),
                InlineKeyboardButton(self._get_text("menu_meridians", language), callback_data="menu_meridians")
            ],
        ]
        if map_button:
            keyboard.append([map_button])
        keyboard.extend([
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
        ])
        if is_admin:
            keyboard.append([
                InlineKeyboardButton(self._get_text("menu_test", language), callback_data="menu_test"),
                InlineKeyboardButton(self._get_text("menu_announce_update", language), callback_data="broadcast_meridians_announcement")
            ])
        return InlineKeyboardMarkup(keyboard)

    def _create_main_menu_keyboard_for_user(
        self,
        chat_id: int,
        language: str,
        user: Optional[User] = None
    ) -> InlineKeyboardMarkup:
        """Create main menu keyboard with admin-only actions when applicable."""
        # web_app buttons are accepted only in private chats (positive chat ids)
        map_button = self._create_meridian_map_button(language, user) if chat_id > 0 else None
        return self._create_main_menu_keyboard(language, is_admin=chat_id in self.admin_ids, map_button=map_button)

    def _create_settings_menu_keyboard(self, language: str, user: Optional[User] = None) -> InlineKeyboardMarkup:
        """Create settings keyboard that reflects the user's active practice modes."""
        principles_enabled = bool(getattr(user, "principles_enabled", True))
        meridians_enabled = bool(getattr(user, "meridians_enabled", False))

        keyboard = [
            [InlineKeyboardButton(self._get_text("change_modes", language), callback_data="change_modes")]
        ]

        time_row = []
        if principles_enabled:
            time_row.append(InlineKeyboardButton(self._get_text("change_time", language), callback_data="change_time"))
        if meridians_enabled:
            time_row.append(InlineKeyboardButton(self._get_text("change_meridian_time", language), callback_data="change_meridian_time"))
        if time_row:
            keyboard.append(time_row)

        keyboard.extend([
            [
                InlineKeyboardButton(self._get_text("change_language", language), callback_data="change_language"),
                InlineKeyboardButton(self._get_text("change_timezone", language), callback_data="change_timezone")
            ],
            [InlineKeyboardButton(self._get_text("change_skip_days", language), callback_data="change_skip_days")],
            [InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")]
        ])
        return InlineKeyboardMarkup(keyboard)

    def _create_principles_menu_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create Yama/Niyama section keyboard."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(self._get_text("principles_random", language), callback_data="principles_random"),
                InlineKeyboardButton(self._get_text("principles_all", language), callback_data="principles_all")
            ],
            [InlineKeyboardButton(self._get_text("useful_materials", language), callback_data="principles_materials")],
            [InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")]
        ])

    def _create_principle_detail_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create keyboard for a selected Yama/Niyama principle card."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(self._get_text("principles_random", language), callback_data="principles_random"),
                InlineKeyboardButton(self._get_text("principles_all", language), callback_data="principles_all")
            ],
            [InlineKeyboardButton(self._get_text("useful_materials", language), callback_data="principles_materials")],
            [InlineKeyboardButton(self._get_text("principles_back", language), callback_data="principles_back")],
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
        keyboard.append([InlineKeyboardButton(self._get_text("principles_back", language), callback_data="principles_back")])
        return InlineKeyboardMarkup(keyboard)

    def _create_practice_modes_keyboard(self, language: str, user: Optional[User] = None) -> InlineKeyboardMarkup:
        """Create practice mode selection keyboard with the current mode marked."""
        current_mode = None
        if user:
            if user.principles_enabled and user.meridians_enabled:
                current_mode = "both"
            elif user.meridians_enabled:
                current_mode = "meridians"
            elif user.principles_enabled:
                current_mode = "principles"

        def mode_label(key: str, mode: str) -> str:
            label = self._get_text(key, language)
            return f"✅ {label}" if current_mode == mode else label

        return InlineKeyboardMarkup([
            [InlineKeyboardButton(mode_label("mode_principles_only", "principles"), callback_data="mode_principles")],
            [InlineKeyboardButton(mode_label("mode_meridians_only", "meridians"), callback_data="mode_meridians")],
            [InlineKeyboardButton(mode_label("mode_both", "both"), callback_data="mode_both")],
            [InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")]
        ])

    def _create_stop_feedback_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create optional feedback skip keyboard after stopping the bot."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("stop_feedback_skip", language), callback_data="stop_feedback_skip")]
        ])

    def _create_registration_modes_keyboard(self, language: str, chat_id: int = 0) -> InlineKeyboardMarkup:
        """Create initial practice mode keyboard for new-user onboarding.

        In a private chat it also offers the 3D map: a newcomer can look at the meridians before choosing
        (the map was offered only after the whole setup, UX council round 2).
        """
        rows = [
            [InlineKeyboardButton(self._get_text("mode_meridians_only", language), callback_data="intro_mode_meridians")],
            [InlineKeyboardButton(self._get_text("mode_principles_only", language), callback_data="intro_mode_principles")],
            [InlineKeyboardButton(self._get_text("mode_both", language), callback_data="intro_mode_both")],
        ]
        map_button = self._create_meridian_map_button(language) if chat_id > 0 else None
        if map_button:
            rows.append([map_button])
        return InlineKeyboardMarkup(rows)

    def _create_meridians_menu_keyboard(self, language: str, user: Optional[User] = None) -> InlineKeyboardMarkup:
        """Create compact meridians section keyboard."""
        keyboard = []
        if user and user.meridians_enabled and user.current_meridian_id:
            keyboard.append([InlineKeyboardButton(self._get_text("current_meridian", language), callback_data="meridian_current")])
        keyboard.extend([
            [InlineKeyboardButton(self._get_text("meridian_change_path", language), callback_data="meridian_path")],
        ])
        if user and user.point_feel:
            # the sensation diary appears once there is something in it
            keyboard.append([InlineKeyboardButton(diary.text("menu", language), callback_data="meridian_diary")])
        keyboard.extend([
            [InlineKeyboardButton(self._get_text("meridian_practice_advice", language), callback_data="meridian_practice_advice")],
            [InlineKeyboardButton(self._get_text("meridian_measurements", language), callback_data="meridian_measurements")],
            [InlineKeyboardButton(self._get_text("useful_materials", language), callback_data="meridian_materials")],
        ])
        map_button = self._create_meridian_map_button(language, user)
        if map_button:
            keyboard.append([map_button])
        keyboard.append([InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")])
        return InlineKeyboardMarkup(keyboard)

    def _create_meridian_map_button(
        self,
        language: str,
        user: Optional[User] = None,
        point_code: Optional[str] = None,
        meridian_id: Optional[str] = None,
        text_key: str = "meridian_map_3d"
    ) -> Optional[InlineKeyboardButton]:
        """Mini App button for the 3D meridian map (shown to everyone once WEBAPP_URL is set).

        point_code opens the map on that point, meridian_id selects a meridian; the URL also carries
        the language and the user's practice progress (see webapp.build_map_url).
        """
        return build_map_button(
            self.webapp_url, self._get_text(text_key, language), language, user,
            point_code=point_code, meridian_id=meridian_id
        )

    def _create_point_map_button(
        self,
        language: str,
        user: Optional[User],
        meridian_id: Optional[str],
        point_index: Optional[int]
    ) -> Optional[InlineKeyboardButton]:
        """Show-on-the-body button: the map opened on the point, or on the meridian before the first point."""
        if not meridian_id:
            return None
        if point_index is None or point_index < 0:
            return self._create_meridian_map_button(language, user, meridian_id=meridian_id, text_key="meridian_show_on_body")
        meridian = self.meridians_manager.get_meridian_by_id(meridian_id)
        points = meridian.get("points", []) if meridian else []
        if point_index >= len(points):
            return None
        return self._create_meridian_map_button(
            language, user, point_code=points[point_index].get("code") or "", text_key="meridian_show_on_body"
        )

    async def _set_user_map_menu_button(self, chat_id: int, language: str) -> None:
        """Chat menu button "Map" in the user's language (Telegram has no per-language default for it)."""
        if not self.webapp_url or chat_id <= 0:
            return
        try:
            await self.application.bot.set_chat_menu_button(
                chat_id=chat_id,
                menu_button=MenuButtonWebApp(
                    text=self._get_text("map_menu_button", language),
                    web_app=WebAppInfo(url=build_map_url(self.webapp_url, language))
                )
            )
        except Exception as e:
            logger.warning(f"Could not set the map menu button for chat {chat_id}: {e}")

    def _create_meridian_materials_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create meridian materials article selection keyboard."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("meridian_materials_basics", language), callback_data="meridian_materials:base")],
            [InlineKeyboardButton(self._get_text("meridian_materials_shu", language), callback_data="meridian_materials:shu")],
            [InlineKeyboardButton(self._get_text("meridian_back", language), callback_data="meridian_main")]
        ])

    def _localized_meridian_name(self, meridian: Optional[Dict[str, Any]], language: str) -> str:
        """Return a meridian name in the user's language."""
        if not meridian:
            return ""
        localized = meridian.get("i18n", {})
        return localized.get(language, localized.get("en", {})).get("name", meridian.get("id", ""))

    def _get_pair_meridian_id(self, meridian_id: Optional[str]) -> Optional[str]:
        """Return paired meridian id for ordinary paired channels."""
        if not meridian_id:
            return None
        pair_id = MERIDIAN_METADATA.get(meridian_id, {}).get("pair")
        return pair_id if pair_id and pair_id != "none" else None

    def _pair_meridian_button(self, meridian_id: Optional[str], language: str) -> Optional[InlineKeyboardButton]:
        """Create a button that opens the paired meridian card."""
        pair_id = self._get_pair_meridian_id(meridian_id)
        if not pair_id:
            return None
        pair_meridian = self.meridians_manager.get_meridian_by_id(pair_id)
        if not pair_meridian:
            return None
        prefixes = {
            "en": "Paired",
            "ru": "Парный",
            "uz": "Juft",
            "kz": "Жұп",
        }
        prefix = prefixes.get(language, prefixes["en"])
        return InlineKeyboardButton(
            f"{prefix}: {self._localized_meridian_name(pair_meridian, language)}",
            callback_data=f"meridian_pair:{pair_id}"
        )

    def _create_meridian_practice_keyboard(
        self,
        language: str,
        at_intro: bool = False,
        point_index: Optional[int] = None,
        points_count: Optional[int] = None,
        meridian_id: Optional[str] = None,
        user: Optional[User] = None
    ) -> InlineKeyboardMarkup:
        """Create navigation keyboard for an opened meridian or point (user: for the map button)."""
        map_button = (
            self._create_point_map_button(language, user, meridian_id, None if at_intro else point_index)
            if user else None
        )
        if at_intro:
            start_callback = (
                f"meridian_point:{meridian_id}:0"
                if meridian_id
                else "meridian_next"
            )
            keyboard = [
                [InlineKeyboardButton(
                    self._get_text("meridian_start_points", language),
                    callback_data=start_callback
                )],
            ]
            if map_button:
                keyboard.append([map_button])
            keyboard.extend([
                [InlineKeyboardButton(self._get_text("meridian_video", language), callback_data="meridian_video")],
                [
                    InlineKeyboardButton(self._get_text("all_points", language), callback_data="meridian_all"),
                    InlineKeyboardButton(self._get_text("meridian_point_help", language), callback_data="meridian_point_help")
                ],
            ])
            pair_button = self._pair_meridian_button(meridian_id, language)
            if pair_button:
                keyboard.append([pair_button])
            keyboard.extend([
                [InlineKeyboardButton(self._get_text("complete_meridian", language), callback_data="meridian_complete")],
                [InlineKeyboardButton(self._get_text("meridian_back", language), callback_data="meridian_main")]
            ])
            return InlineKeyboardMarkup(keyboard)

        navigation_row = []
        point_prefix = f"meridian_point:{meridian_id}:" if meridian_id else "meridian_point:"
        if point_index is None or point_index > 0:
            previous_index = max(0, (point_index or 0) - 1)
            navigation_row.append(InlineKeyboardButton(
                self._get_text("prev_point", language),
                callback_data=f"{point_prefix}{previous_index}"
            ))
        if point_index is None or points_count is None or point_index < points_count - 1:
            next_index = 0 if point_index is None else point_index + 1
            navigation_row.append(InlineKeyboardButton(
                self._get_text("next_point", language),
                callback_data=f"{point_prefix}{next_index}"
            ))

        keyboard = []
        if navigation_row:
            keyboard.append(navigation_row)
        # the sensation diary: how the point responded (bot/feel.py)
        if meridian_id and point_index is not None and point_index >= 0:
            point_code = self._point_code_at(meridian_id, point_index)
            if point_code:
                keyboard.extend(diary.collapsed_rows(
                    meridian_id, point_index, diary.feel_of(user.point_feel if user else None, point_code), language
                ))
        if map_button:
            keyboard.append([map_button])
        keyboard.extend([
            [InlineKeyboardButton(self._get_text("meridian_video", language), callback_data="meridian_video")],
            [
                InlineKeyboardButton(self._get_text("all_points", language), callback_data="meridian_all"),
                InlineKeyboardButton(self._get_text("meridian_point_help", language), callback_data="meridian_point_help")
            ],
        ])
        if points_count is None or points_count > 0:
            keyboard.append([InlineKeyboardButton(self._get_text("complete_meridian", language), callback_data="meridian_complete")])
        keyboard.append([InlineKeyboardButton(self._get_text("meridian_back", language), callback_data="meridian_main")])
        return InlineKeyboardMarkup(keyboard)

    def _point_code_at(self, meridian_id: Optional[str], point_index: Optional[int]) -> Optional[str]:
        """Code of a meridian's point by index, None when there is no such point."""
        meridian = self.meridians_manager.get_meridian_by_id(meridian_id) if meridian_id else None
        points = meridian.get("points", []) if meridian else []
        if point_index is None or point_index < 0 or point_index >= len(points):
            return None
        return points[point_index].get("code")

    def _diary_point_title(self, point: Dict[str, Any], language: str) -> str:
        name = localized_point_name(point, language) if point else ""
        code = point.get("code", "") if point else ""
        return f"{code} {name}".strip() if name and name != code else code

    async def _handle_feel_callback(self, query, user: Optional[User], language: str) -> None:
        """Diary buttons under a point message: open the five feelings, save one, or fold them back."""
        parsed = diary.parse_callback(query.data or "")
        if not parsed or not user or not user.is_active:
            await query.answer()
            return
        kind, meridian_id, point_index, feel = parsed
        point_code = self._point_code_at(meridian_id, point_index)
        if not point_code:
            await query.answer()
            return
        current = diary.feel_of(user.point_feel, point_code)
        toast = None
        if kind == "set":
            if feel == current:
                diary.set_feel(user.point_feel, point_code, "")
                current = None
                toast = diary.text("cleared", language)
            else:
                diary.set_feel(user.point_feel, point_code, feel)
                current = feel
                toast = diary.text("saved", language, label=diary.feel_label(feel, language).lower())
            await self.storage.save_user(user)
        rows = (diary.open_rows if kind == "open" else diary.collapsed_rows)(meridian_id, point_index, current, language)
        markup = diary.swap_feel_rows(query.message.reply_markup if query.message else None, rows)
        await query.answer(toast or None)
        if markup is not None:
            try:
                await query.edit_message_reply_markup(reply_markup=markup)
            except BadRequest as e:
                if "not modified" not in str(e).lower():
                    logger.warning(f"Could not update the diary buttons for {user.chat_id}: {e}")

    def _create_meridian_path_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create meridian learning mode selection keyboard."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("meridian_guided_path", language), callback_data="meridian_path:guided")],
            [InlineKeyboardButton(self._get_text("meridian_free_choice", language), callback_data="meridian_path:free")],
            [InlineKeyboardButton(self._get_text("meridian_back", language), callback_data="meridian_main")]
        ])

    def _create_meridian_route_completed_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create keyboard shown after the guided meridian route is complete."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("meridian_guided_path", language), callback_data="meridian_path:guided")],
            [InlineKeyboardButton(self._get_text("meridian_free_choice", language), callback_data="meridian_path:free")],
            [InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")]
        ])

    def _create_meridian_complete_confirm_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create confirmation keyboard for finishing a meridian before the last point."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("complete_meridian_confirm_yes", language), callback_data="meridian_complete_confirm")],
            [InlineKeyboardButton(self._get_text("complete_meridian_confirm_no", language), callback_data="meridian_current")],
            [InlineKeyboardButton(self._get_text("all_points", language), callback_data="meridian_all")]
        ])

    def _create_secret_task_offer_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create keyboard for the governing vessel secret task offer."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("secret_task_yes", language), callback_data="meridian_secret_yes")],
            [InlineKeyboardButton(self._get_text("secret_task_no", language), callback_data="meridian_secret_no")]
        ])

    def _create_secret_task_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create keyboard for an opened secret task."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("secret_task_done", language), callback_data="meridian_secret_done")],
            [InlineKeyboardButton(self._get_text("secret_task_continue", language), callback_data="meridian_secret_continue")]
        ])

    def _create_orbit_secret_task_offer_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create keyboard for the central orbit secret task offer."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("secret_task_yes", language), callback_data="meridian_secret_orbit_yes")],
            [InlineKeyboardButton(self._get_text("secret_task_no", language), callback_data="meridian_secret_orbit_no")]
        ])

    def _create_orbit_secret_task_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create keyboard for the opened central orbit secret task."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("secret_task_done", language), callback_data="meridian_secret_orbit_done")],
            [InlineKeyboardButton(self._get_text("secret_task_continue", language), callback_data="meridian_secret_orbit_continue")]
        ])

    async def _advance_after_governing_secret_task(self, query, user: User, language: str) -> None:
        """Move guided user from the governing vessel to the next route meridian."""
        next_meridian = self.meridians_manager.get_next_meridian("governing_vessel", user.completed_meridians)
        if next_meridian:
            user.current_meridian_id = next_meridian["id"]
            user.current_point_index = -1
            await self.storage.save_user(user)
            text = f"{self._get_text('meridian_completed', language)}\n\n{format_meridian_intro(next_meridian, language)}"
            await self._show_meridian_card(
                query,
                text,
                self._create_meridian_practice_keyboard(
                    language,
                    at_intro=True,
                    meridian_id=next_meridian.get("id"),
                    user=user
                ),
                language,
                next_meridian.get("id")
            )
            return

        user.current_meridian_id = None
        user.current_point_index = -1
        await self.storage.save_user(user)
        await self._edit_message_text_safe(
            query,
            self._get_text("meridian_route_completed", language),
            reply_markup=self._create_meridian_route_completed_keyboard(language),
            parse_mode='HTML'
        )

    async def _advance_after_orbit_secret_task(self, query, user: User, language: str) -> None:
        """Move guided user from the central pair to the next route meridian."""
        next_meridian = self.meridians_manager.get_next_meridian("conception_vessel", user.completed_meridians)
        if next_meridian:
            user.current_meridian_id = next_meridian["id"]
            user.current_point_index = -1
            await self.storage.save_user(user)
            text = f"{self._get_text('meridian_completed', language)}\n\n{format_meridian_intro(next_meridian, language)}"
            await self._show_meridian_card(
                query,
                text,
                self._create_meridian_practice_keyboard(
                    language,
                    at_intro=True,
                    meridian_id=next_meridian.get("id"),
                    user=user
                ),
                language,
                next_meridian.get("id")
            )
            return

        user.current_meridian_id = None
        user.current_point_index = -1
        await self.storage.save_user(user)
        await self._edit_message_text_safe(
            query,
            self._get_text("meridian_route_completed", language),
            reply_markup=self._create_meridian_route_completed_keyboard(language),
            parse_mode='HTML'
        )

    def _create_meridian_help_keyboard(self, language: str, user: Optional[User] = None) -> InlineKeyboardMarkup:
        """Create keyboard for meridian reference screens without surprising auto-starts."""
        keyboard = []
        if user and user.meridians_enabled and user.current_meridian_id:
            keyboard.append([InlineKeyboardButton(self._get_text("current_meridian", language), callback_data="meridian_current")])
        keyboard.append([InlineKeyboardButton(self._get_text("meridian_measurements", language), callback_data="meridian_measurements")])
        keyboard.append([InlineKeyboardButton(self._get_text("meridian_back", language), callback_data="meridian_main")])
        return InlineKeyboardMarkup(keyboard)

    def _create_meridian_choice_keyboard(self, language: str, page: int = 0) -> InlineKeyboardMarkup:
        """Create a calm paginated meridian selection keyboard."""
        meridians = self.meridians_manager.get_recommended_path_meridians()
        total_pages = max(1, (len(meridians) + MERIDIAN_SELECTION_PAGE_SIZE - 1) // MERIDIAN_SELECTION_PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        start = page * MERIDIAN_SELECTION_PAGE_SIZE
        end = min(start + MERIDIAN_SELECTION_PAGE_SIZE, len(meridians))
        keyboard = []
        for index in range(start, end, 2):
            row = []
            for meridian in meridians[index:min(index + 2, end)]:
                localized = meridian.get("i18n", {}).get(language, meridian.get("i18n", {}).get("en", {}))
                name = localized.get("name", meridian.get("id"))
                row.append(InlineKeyboardButton(
                    name,
                    callback_data=f"meridian_select:{meridian.get('id')}"
                ))
            keyboard.append(row)
        if total_pages > 1:
            labels = {
                "en": ("◀️ Previous", "Page", "Next ▶️"),
                "ru": ("◀️ Назад", "Стр.", "Далее ▶️"),
                "uz": ("◀️ Oldingi", "Sahifa", "Keyingi ▶️"),
                "kz": ("◀️ Артқа", "Бет", "Келесі ▶️"),
            }.get(language, ("◀️ Previous", "Page", "Next ▶️"))
            navigation = []
            if page > 0:
                navigation.append(InlineKeyboardButton(labels[0], callback_data=f"meridian_choice_page:{page - 1}"))
            navigation.append(InlineKeyboardButton(f"{labels[1]} {page + 1}/{total_pages}", callback_data="meridian_noop"))
            if page < total_pages - 1:
                navigation.append(InlineKeyboardButton(labels[2], callback_data=f"meridian_choice_page:{page + 1}"))
            keyboard.append(navigation)
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
            code = point.get("code", "")
            name = localized_point_name(point, language)
            keyboard.append([
                InlineKeyboardButton(
                    f"{index + 1}. {code} {name}".strip(),
                    callback_data=f"meridian_point:{meridian.get('id')}:{index}"
                )
            ])
        if total_pages > 1:
            navigation = []
            labels = {
                "en": ("◀️ Previous", "Page", "Next ▶️"),
                "ru": ("◀️ Назад", "Стр.", "Далее ▶️"),
                "uz": ("◀️ Oldingi", "Sahifa", "Keyingi ▶️"),
                "kz": ("◀️ Артқа", "Бет", "Келесі ▶️"),
            }.get(language, ("◀️ Previous", "Page", "Next ▶️"))
            if page > 0:
                navigation.append(InlineKeyboardButton(labels[0], callback_data=f"meridian_points_page:{page - 1}"))
            navigation.append(InlineKeyboardButton(f"{labels[1]} {page + 1}/{total_pages}", callback_data="meridian_noop"))
            if page < total_pages - 1:
                navigation.append(InlineKeyboardButton(labels[2], callback_data=f"meridian_points_page:{page + 1}"))
            keyboard.append(navigation)
        keyboard.append([InlineKeyboardButton(self._get_text("back_to_current_focus", language), callback_data="meridian_current")])
        return InlineKeyboardMarkup(keyboard)

    def _format_meridian_points_page_text(self, language: str, page: int, total_pages: int) -> str:
        """Build text for the paginated point chooser."""
        choose_point = {
            "en": "Choose a point: its image and practice will open, and it will become your current focus. Nothing moves forward by itself.",
            "ru": "Выберите точку: откроется изображение и практика, а точка станет текущим фокусом. Бот не перейдёт дальше сам.",
            "uz": "Nuqtani tanlang: rasm va amaliyot ochiladi, nuqta esa joriy fokusga aylanadi. Bot o'zi oldinga o'tmaydi.",
            "kz": "Нүктені таңдаңыз: сурет пен тәжірибе ашылады, нүкте ағымдағы фокусқа айналады. Бот өзі әрі қарай өтпейді.",
        }.get(language, "Choose a point to open its image and practice. Nothing moves forward by itself.")
        return f"<b>{self._get_text('all_points', language)}</b>\n\n{choose_point}"

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
            keyboard = self._create_main_menu_keyboard_for_user(chat_id, language, user)

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

    async def _handle_map(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /map command: the 3D meridian map button (works without registration)."""
        chat = update.effective_chat
        chat_id = chat.id
        language = "ru"

        try:
            user = await self.storage.get_user(chat_id)
            if user:
                language = user.language
            else:
                language = normalize_webapp_language(getattr(update.effective_user, "language_code", "") or "")

            if chat.type != "private":
                await update.message.reply_text(self._get_text("map_private_only", language))
                return

            button = self._create_meridian_map_button(language, user)
            if not button:
                await update.message.reply_text(self._get_text("map_unavailable", language))
                return

            await update.message.reply_text(
                self._get_text("map_command_text", language),
                reply_markup=InlineKeyboardMarkup([[button]]),
                parse_mode='HTML'
            )
            await self._set_user_map_menu_button(chat_id, language)

        except Exception as e:
            logger.error(f"Error in map handler for chat {chat_id}: {e}")
            await update.message.reply_text(self._get_text("error", language))

    async def _handle_menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle main menu callback queries."""
        query = update.callback_query
        chat_id = query.message.chat.id
        action = query.data.split("_", 1)[1]  # Extract action after "menu_"

        try:
            await query.answer()

            user = await self.storage.get_user(chat_id)
            language = user.language if user else "en"

            if action != "stop" and (not user or not user.is_active):
                await self._edit_message_text_safe(query, self._get_text("not_subscribed_test", language))
                return

            if action == "settings":
                text = self._as_html(self._get_text("settings_menu", language))
                keyboard = self._create_settings_menu_keyboard(language, user)
                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')

            elif action == "principles":
                text = self._get_text("principles_menu", language)
                keyboard = self._create_principles_menu_keyboard(language)
                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')

            elif action == "modes":
                text = self._get_text("mode_menu", language)
                keyboard = self._create_practice_modes_keyboard(language, user)
                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')

            elif action == "meridians":
                text = self._get_text("meridians_menu", language)
                keyboard = self._create_meridians_menu_keyboard(language, user)
                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')

            elif action == "test":
                await self._edit_message_text_safe(query, self._get_text("sending_test", language))
                success = await self.scheduler.send_full_reminder_check_message(chat_id, language)
                if success:
                    text = self._as_html(self._get_text("menu", language))
                    keyboard = self._create_main_menu_keyboard_for_user(chat_id, language, user)
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
                    await self._edit_message_text_safe(
                        query,
                        text,
                        reply_markup=self._create_stop_feedback_keyboard(language),
                        parse_mode='HTML'
                    )
                else:
                    self.user_states.pop(chat_id, None)
                    await self._edit_message_text_safe(query, self._get_text("not_subscribed", language))

            elif action == "main":
                text = self._as_html(self._get_text("menu", language))
                keyboard = self._create_main_menu_keyboard_for_user(chat_id, language, user)
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
            if not user or not user.is_active:
                await self._edit_message_text_safe(query, self._get_text("not_subscribed_test", language))
                return

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
            elif action == "materials":
                text = self._get_text("useful_materials_soon", language)
                keyboard = self._create_principles_menu_keyboard(language)
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
            if not user or not user.is_active:
                await self._edit_message_text_safe(query, self._get_text("not_subscribed_test", language))
                return

            text = self._as_html(self._get_text("settings_menu", language))
            keyboard = self._create_settings_menu_keyboard(language, user)
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
            if not user or not user.is_active:
                await self._edit_message_text_safe(query, self._get_text("not_subscribed_test", language))
                return

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
                    parse_mode='HTML'
                )

            elif setting == "modes":
                text = self._get_text("mode_menu", language)
                keyboard = self._create_practice_modes_keyboard(language, user)
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
                    parse_mode='HTML'
                )

            elif setting == "timezone":
                self.user_states[chat_id] = {"step": "change_timezone", "language": language, "settings_message_id": query.message.message_id}
                keyboard = self._create_timezone_keyboard(language, add_back_button=True)
                await self._edit_message_text_safe(query,
                    self._get_text("timezone_step", language),
                    reply_markup=keyboard,
                    parse_mode='HTML'
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

                text = f"{self._text_html('skip_days_step', language)}\n\n{self._format_skip_days_note(current_skip_days, language, current=True)}"

                keyboard = self._create_skip_days_keyboard(language, current_skip_days, add_back_button=True)

                await self._edit_message_text_safe(query,
                    text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )

        except Exception as e:
            logger.error(f"Error in change callback for user {chat_id}: {e}")
            await self._edit_message_text_safe(query, self._get_text("error", language))

    async def _handle_mode_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle practice mode selection."""
        query = update.callback_query
        chat_id = query.message.chat.id
        mode = query.data.split("_", 1)[1]
        language = "en"

        try:
            await query.answer()
            user = await self.storage.get_user(chat_id)
            language = user.language if user else "en"
            if not user or not user.is_active:
                await self._edit_message_text_safe(query, self._get_text("not_subscribed_test", language))
                return

            user.principles_enabled = mode in ["principles", "both"]
            user.meridians_enabled = mode in ["meridians", "both"]

            if (
                user.meridians_enabled
                and getattr(user, "meridian_learning_mode", None)
                and not user.current_meridian_id
            ):
                next_meridian = self.meridians_manager.get_next_meridian(None, user.completed_meridians)
                if not next_meridian and user.completed_meridians:
                    user.completed_meridians = []
                    next_meridian = self.meridians_manager.get_next_meridian(None, user.completed_meridians)
                if next_meridian:
                    user.current_meridian_id = next_meridian["id"]
                    user.current_point_index = -1

            await self.storage.save_user(user)
            await self.scheduler.schedule_user_immediately(chat_id)

            if user.meridians_enabled and not getattr(user, "meridian_learning_mode", None):
                text = f"{self._get_text('mode_saved', language)}\n\n{self._get_text('meridian_mode_menu', language)}"
                keyboard = self._create_meridian_path_keyboard(language)
            else:
                text = f"{self._get_text('mode_saved', language)}\n\n{self._get_text('menu', language)}"
                keyboard = self._create_main_menu_keyboard_for_user(chat_id, language, user)
            await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error in mode callback for user {chat_id}: {e}")
            await self._edit_message_text_safe(query, self._get_text("error", language))

    async def _handle_stop_feedback_skip_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle optional stop-feedback skip."""
        query = update.callback_query
        chat_id = query.message.chat.id

        try:
            user_state = self.user_states.get(chat_id, {})
            language = user_state.get("language", "en")
            user = await self.storage.get_user(chat_id)
            if user:
                language = user.language

            await query.answer()
            self.user_states.pop(chat_id, None)
            await self._edit_message_text_safe(
                query,
                self._as_html(self._get_text("stop_feedback_skipped", language)),
                parse_mode='HTML'
            )

        except Exception as e:
            logger.error(f"Error in stop feedback skip callback for user {chat_id}: {e}")

    async def _handle_meridian_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle meridian study navigation."""
        query = update.callback_query
        chat_id = query.message.chat.id
        action = query.data.split("_", 1)[1]

        try:
            user = await self.storage.get_user(chat_id)
            language = user.language if user else "en"
            if action == "noop":
                await query.answer(self._get_text("page_indicator_hint", language), show_alert=False)
                return

            if action.startswith("feel"):
                # answers the query itself: saving a feeling shows a short toast
                await self._handle_feel_callback(query, user, language)
                return

            await query.answer()
            if not user or not user.is_active:
                await self._edit_message_text_safe(query, self._get_text("not_subscribed_test", language))
                return

            if action == "secret_yes":
                user.secret_tasks[GOVERNING_VESSEL_SECRET_TASK_ID] = "opened"
                await self.storage.save_user(user)
                await self._edit_message_text_safe(
                    query,
                    self._get_text("secret_task_governing", language),
                    reply_markup=self._create_secret_task_keyboard(language),
                    parse_mode='HTML'
                )
                return

            if action == "secret_no":
                user.secret_tasks[GOVERNING_VESSEL_SECRET_TASK_ID] = "skipped"
                await self.storage.save_user(user)
                await self._advance_after_governing_secret_task(query, user, language)
                return

            if action == "secret_done":
                user.secret_tasks[GOVERNING_VESSEL_SECRET_TASK_ID] = "done"
                await self.storage.save_user(user)
                await self._edit_message_text_safe(
                    query,
                    self._get_text("secret_task_done_text", language),
                    reply_markup=self._create_secret_task_keyboard(language),
                    parse_mode='HTML'
                )
                return

            if action == "secret_continue":
                user.secret_tasks.setdefault(GOVERNING_VESSEL_SECRET_TASK_ID, "opened")
                await self.storage.save_user(user)
                await self._advance_after_governing_secret_task(query, user, language)
                return

            if action == "secret_orbit_yes":
                user.secret_tasks[MICROCOSMIC_ORBIT_SECRET_TASK_ID] = "opened"
                await self.storage.save_user(user)
                await self._edit_message_text_safe(
                    query,
                    self._get_text("secret_task_orbit", language),
                    reply_markup=self._create_orbit_secret_task_keyboard(language),
                    parse_mode='HTML'
                )
                return

            if action == "secret_orbit_no":
                user.secret_tasks[MICROCOSMIC_ORBIT_SECRET_TASK_ID] = "skipped"
                await self.storage.save_user(user)
                await self._advance_after_orbit_secret_task(query, user, language)
                return

            if action == "secret_orbit_done":
                user.secret_tasks[MICROCOSMIC_ORBIT_SECRET_TASK_ID] = "done"
                await self.storage.save_user(user)
                await self._edit_message_text_safe(
                    query,
                    self._get_text("secret_task_orbit_done_text", language),
                    reply_markup=self._create_orbit_secret_task_keyboard(language),
                    parse_mode='HTML'
                )
                return

            if action == "secret_orbit_continue":
                user.secret_tasks.setdefault(MICROCOSMIC_ORBIT_SECRET_TASK_ID, "opened")
                await self.storage.save_user(user)
                await self._advance_after_orbit_secret_task(query, user, language)
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
                cun_image_path = get_cun_measurement_image_path(language)
                if cun_image_path.exists():
                    try:
                        with open(cun_image_path, "rb") as photo:
                            sent_message = await self.application.bot.send_photo(
                                chat_id=chat_id,
                                photo=photo,
                                caption=self._get_text("meridian_measurements_image_caption", language),
                                parse_mode='HTML'
                            )
                        await self.storage.add_bot_message(chat_id, sent_message.message_id, "meridian")
                    except Exception as e:
                        logger.warning(f"Could not send cun measurement image to {chat_id}: {e}")
                await self._edit_message_text_safe(
                    query,
                    self._get_text("meridian_measurements_text", language),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(self._get_text("meridian_point_help", language), callback_data="meridian_point_help")],
                        [InlineKeyboardButton(self._get_text("meridian_back", language), callback_data="meridian_main")]
                    ]),
                    parse_mode='HTML'
                )
                return

            if action == "point_help":
                await self._edit_message_text_safe(
                    query,
                    self._get_text("meridian_point_help_text", language),
                    reply_markup=self._create_meridian_help_keyboard(language, user),
                    parse_mode='HTML'
                )
                return

            if action == "diary":
                text, rows = diary.diary_page(
                    user.point_feel, self.meridians_manager, language, self._diary_point_title
                )
                rows.append([InlineKeyboardButton(self._get_text("meridian_back", language), callback_data="meridian_main")])
                await self._edit_message_text_safe(
                    query, text, reply_markup=InlineKeyboardMarkup(rows), parse_mode='HTML'
                )
                return

            if action == "practice_advice":
                await self._edit_message_text_safe(
                    query,
                    self._get_text("meridian_practice_advice_text", language),
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
                        if not next_meridian and user.completed_meridians:
                            user.completed_meridians = []
                            next_meridian = self.meridians_manager.get_next_meridian(None, user.completed_meridians)
                        if next_meridian:
                            user.current_meridian_id = next_meridian["id"]
                            user.current_point_index = -1
                    await self.storage.save_user(user)
                    await self.scheduler.schedule_user_immediately(chat_id)
                    meridian = self.meridians_manager.get_meridian_by_id(user.current_meridian_id) if user.current_meridian_id else None
                    intro = format_meridian_intro(meridian, language) if meridian else self._get_text("meridians_menu", language)
                    text = f"{self._get_text('meridian_guided_saved', language)}\n\n{intro}"
                    await self._show_meridian_card(
                        query,
                        text,
                        self._create_meridian_practice_keyboard(language, at_intro=True, meridian_id=meridian.get("id") if meridian else None, user=user),
                        language,
                        meridian.get("id") if meridian else None
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
                text = self._get_text("meridians_menu", language)
                keyboard = self._create_meridians_menu_keyboard(language, user)
                await self._edit_message_text_safe(query,
                    text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
                return

            if action == "materials":
                await self._edit_message_text_safe(
                    query,
                    self._get_text("meridian_materials_menu", language),
                    reply_markup=self._create_meridian_materials_keyboard(language),
                    parse_mode='HTML'
                )
                return

            if action.startswith("materials:"):
                material_id = action.split(":", 1)[1]
                if material_id == "base":
                    await self._edit_message_text_safe(
                        query,
                        self._get_text("meridian_materials_text", language),
                        reply_markup=self._create_meridian_materials_keyboard(language),
                        parse_mode='HTML'
                    )
                    return
                if material_id == "shu":
                    await self._edit_message_text_safe(
                        query,
                        self._get_text("meridian_materials_sending", language),
                        reply_markup=self._create_meridian_materials_keyboard(language),
                        parse_mode='HTML'
                    )
                    await self._send_shu_points_material(chat_id, language)
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

            if action.startswith("choice_page:"):
                try:
                    page = int(action.split(":", 1)[1])
                except ValueError:
                    page = 0
                await self._edit_message_text_safe(
                    query,
                    self._get_text("choose_meridian", language),
                    reply_markup=self._create_meridian_choice_keyboard(language, page),
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
                    self._create_meridian_practice_keyboard(language, at_intro=True, meridian_id=meridian.get("id"), user=user),
                    language,
                    meridian.get("id")
                )
                return

            if action.startswith("pair:"):
                meridian_id = action.split(":", 1)[1]
                meridian = self.meridians_manager.get_meridian_by_id(meridian_id)
                if not meridian:
                    await self._edit_message_text_safe(query, self._get_text("error", language))
                    return
                user.current_meridian_id = meridian_id
                user.current_point_index = -1
                user.meridians_enabled = True
                await self.storage.save_user(user)
                await self.scheduler.schedule_user_immediately(chat_id)
                text = format_meridian_intro(meridian, language)
                await self._show_meridian_card(
                    query,
                    text,
                    self._create_meridian_practice_keyboard(language, at_intro=True, meridian_id=meridian.get("id"), user=user),
                    language,
                    meridian.get("id")
                )
                return

            if action == "current" and not getattr(user, "meridian_learning_mode", None):
                await self._edit_message_text_safe(
                    query,
                    self._get_text("meridian_mode_menu", language),
                    reply_markup=self._create_meridian_path_keyboard(language),
                    parse_mode='HTML'
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
            if user.current_point_index < -1 or user.current_point_index >= len(points):
                user.current_point_index = -1
                await self.storage.save_user(user)

            if action == "video":
                video_path = get_meridian_video_path(meridian.get("id"))
                if not video_path:
                    await self._edit_message_text_safe(
                        query,
                        self._get_text("meridian_video_missing", language),
                        reply_markup=self._create_meridian_practice_keyboard(
                            language,
                            at_intro=user.current_point_index < 0,
                            point_index=user.current_point_index if user.current_point_index >= 0 else None,
                            points_count=len(points),
                            meridian_id=meridian.get("id"),
                            user=user
                        ),
                        parse_mode='HTML'
                    )
                    return

                try:
                    with open(video_path, "rb") as video:
                        sent_message = await self.application.bot.send_video(
                            chat_id=chat_id,
                            video=video,
                            caption=self._get_text("meridian_video_caption", language),
                            parse_mode='HTML'
                        )
                    await self.storage.add_bot_message(chat_id, sent_message.message_id, "meridian")
                except Exception as e:
                    logger.warning(f"Could not send meridian video {video_path} to {chat_id}: {e}")
                    await self._edit_message_text_safe(
                        query,
                        self._get_text("meridian_video_missing", language),
                        reply_markup=self._create_meridian_practice_keyboard(
                            language,
                            at_intro=user.current_point_index < 0,
                            point_index=user.current_point_index if user.current_point_index >= 0 else None,
                            points_count=len(points),
                            meridian_id=meridian.get("id"),
                            user=user
                        ),
                        parse_mode='HTML'
                    )
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
                        points_count=len(points),
                        meridian_id=meridian.get("id"),
                        user=user
                    ),
                    language,
                    meridian.get("id"),
                    point_code
                )
                return

            if action == "all":
                if not points:
                    text = self._get_text("no_points", language)
                    keyboard = self._create_meridians_menu_keyboard(language, user)
                else:
                    total_pages = max(1, (len(points) + MERIDIAN_POINTS_PAGE_SIZE - 1) // MERIDIAN_POINTS_PAGE_SIZE)
                    text = self._format_meridian_points_page_text(language, 0, total_pages)
                    keyboard = self._create_meridian_points_keyboard(meridian, language, page=0)
                await self._show_meridian_card(query, text, keyboard, language)
                return

            if action.startswith("points_page:"):
                if not points:
                    await self._edit_message_text_safe(query, self._get_text("no_points", language), reply_markup=self._create_meridians_menu_keyboard(language, user), parse_mode='HTML')
                    return
                page = int(action.split(":", 1)[1])
                total_pages = max(1, (len(points) + MERIDIAN_POINTS_PAGE_SIZE - 1) // MERIDIAN_POINTS_PAGE_SIZE)
                page = max(0, min(page, total_pages - 1))
                text = self._format_meridian_points_page_text(language, page, total_pages)
                keyboard = self._create_meridian_points_keyboard(meridian, language, page=page)
                await self._show_meridian_card(query, text, keyboard, language)
                return

            if action.startswith("point:"):
                point_parts = action.split(":")
                if len(point_parts) == 3:
                    requested_meridian = self.meridians_manager.get_meridian_by_id(point_parts[1])
                    if not requested_meridian:
                        await self._edit_message_text_safe(query, self._get_text("error", language))
                        return
                    meridian = requested_meridian
                    points = meridian.get("points", [])
                    user.current_meridian_id = meridian.get("id")
                    point_index = int(point_parts[2])
                else:
                    # Compatibility with point buttons published before callbacks carried context.
                    point_index = int(point_parts[1])
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
                    self._create_meridian_practice_keyboard(
                        language,
                        point_index=point_index,
                        points_count=len(points),
                        meridian_id=meridian.get("id"),
                        user=user
                    ),
                    language,
                    meridian.get("id"),
                    point_code,
                    append=True
                )
                return

            if action in ["next", "prev"]:
                if not points:
                    await self._edit_message_text_safe(query, self._get_text("no_points", language), reply_markup=self._create_meridians_menu_keyboard(language, user), parse_mode='HTML')
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
                    self._create_meridian_practice_keyboard(
                        language,
                        point_index=user.current_point_index,
                        points_count=len(points),
                        meridian_id=meridian.get("id"),
                        user=user
                    ),
                    language,
                    meridian.get("id"),
                    point_code,
                    append=True
                )
                return

            if action in ("complete", "complete_confirm"):
                if action == "complete" and points and user.current_point_index < len(points) - 1:
                    await self._edit_message_text_safe(
                        query,
                        self._get_text("complete_meridian_confirm", language),
                        reply_markup=self._create_meridian_complete_confirm_keyboard(language),
                        parse_mode='HTML'
                    )
                    return

                if user.current_meridian_id and user.current_meridian_id not in user.completed_meridians:
                    user.completed_meridians.append(user.current_meridian_id)

                if (
                    getattr(user, "meridian_learning_mode", None) == "guided"
                    and user.current_meridian_id == "governing_vessel"
                    and GOVERNING_VESSEL_SECRET_TASK_ID not in user.secret_tasks
                ):
                    user.secret_tasks[GOVERNING_VESSEL_SECRET_TASK_ID] = "offered"
                    await self.storage.save_user(user)
                    await self._edit_message_text_safe(
                        query,
                        self._get_text("secret_task_offer_governing", language),
                        reply_markup=self._create_secret_task_offer_keyboard(language),
                        parse_mode='HTML'
                    )
                    return

                if (
                    getattr(user, "meridian_learning_mode", None) == "guided"
                    and user.current_meridian_id == "conception_vessel"
                    and {"governing_vessel", "conception_vessel"}.issubset(set(user.completed_meridians))
                    and MICROCOSMIC_ORBIT_SECRET_TASK_ID not in user.secret_tasks
                ):
                    user.secret_tasks[MICROCOSMIC_ORBIT_SECRET_TASK_ID] = "offered"
                    await self.storage.save_user(user)
                    await self._edit_message_text_safe(
                        query,
                        self._get_text("secret_task_offer_orbit", language),
                        reply_markup=self._create_orbit_secret_task_offer_keyboard(language),
                        parse_mode='HTML'
                    )
                    return

                route_completed = False
                if getattr(user, "meridian_learning_mode", None) == "guided":
                    next_meridian = self.meridians_manager.get_next_meridian(user.current_meridian_id, user.completed_meridians)
                    if next_meridian:
                        user.current_meridian_id = next_meridian["id"]
                        user.current_point_index = -1
                    else:
                        route_completed = True
                        user.current_meridian_id = None
                        user.current_point_index = -1
                else:
                    user.current_meridian_id = None
                    user.current_point_index = -1

                await self.storage.save_user(user)
                text = (
                    self._get_text("meridian_route_completed", language)
                    if route_completed
                    else self._get_text("meridian_completed", language)
                )
                if user.current_meridian_id:
                    next_meridian = self.meridians_manager.get_meridian_by_id(user.current_meridian_id)
                    if next_meridian:
                        next_text = f"{text}\n\n{format_meridian_intro(next_meridian, language)}"
                        await self._show_meridian_card(
                            query,
                            next_text,
                            self._create_meridian_practice_keyboard(
                                language,
                                at_intro=True,
                                meridian_id=next_meridian.get("id"),
                                user=user
                            ),
                            language,
                            next_meridian.get("id")
                        )
                        return
                    await self._edit_message_text_safe(
                        query,
                        text,
                        reply_markup=self._create_meridians_menu_keyboard(language, user),
                        parse_mode='HTML'
                    )
                    return

                await self._edit_message_text_safe(
                    query,
                    text,
                    reply_markup=(
                        self._create_meridian_route_completed_keyboard(language)
                        if route_completed
                        else self._create_meridian_choice_keyboard(language)
                    ),
                    parse_mode='HTML'
                )

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
            if action == "map3d_announcement":
                # preview first: the admin gets the announcement in every language exactly as users will see
                # it (text and the map button), then confirms; nothing goes out from this first press
                if not self.webapp_url:
                    await self._edit_message_text_safe(query, "WEBAPP_URL is not set: the map button would be missing.")
                    return
                for lang in ("ru", "en", "uz", "kz"):
                    button = self._create_meridian_map_button(lang)
                    await context.bot.send_message(
                        chat_id, f"[{lang}]\n\n" + self._get_text("map3d_announcement", lang), parse_mode='HTML',
                        reply_markup=InlineKeyboardMarkup([[button]]) if button else None)
                total = len(await self.storage.get_all_active_users())
                await context.bot.send_message(
                    chat_id, f"Preview above. Send the 3D map announcement to {total} active users?",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"✅ Send to all ({total})", callback_data="broadcast_map3d_confirm")],
                        [InlineKeyboardButton("✖️ Cancel", callback_data="broadcast_map3d_cancel")],
                    ]))
                await self._edit_message_text_safe(query, "Preview sent below.")
                return
            if action == "map3d_cancel":
                await self._edit_message_text_safe(query, "Announcement cancelled, nothing was sent.")
                return
            if action == "map3d_confirm":
                await self._edit_message_text_safe(query, "Sending…")
                sent_count, failed_count, total = await self._send_localized_broadcast(
                    "map3d_announcement", context, map_button=True)
                result_text = self._get_admin_text("broadcast_result", sent=sent_count, failed=failed_count, total=total)
                await self._edit_message_text_safe(query, result_text)
                return
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
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(self._get_text("invalid_timezone", language), parse_mode='HTML')
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
                    keyboard = self._create_main_menu_keyboard_for_user(chat_id, language, user)

                    if message_id:
                        await self._edit_bot_message_text_safe(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=text,
                            reply_markup=keyboard,
                            parse_mode='HTML'
                        )
                    else:
                        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')
                else:
                    error_text = self._get_text("setup_error", language)
                    if message_id:
                        await self._edit_bot_message_text_safe(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=error_text,
                            parse_mode='HTML'
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
                        parse_mode='HTML'
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
                    parse_mode='HTML'
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
                    parse_mode='HTML'
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
                    keyboard = self._create_main_menu_keyboard_for_user(chat_id, language, user)

                    if message_id:
                        await self._edit_bot_message_text_safe(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=text,
                            reply_markup=keyboard,
                            parse_mode='HTML'
                        )
                    else:
                        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')
                else:
                    error_text = self._get_text("setup_error", language)
                    if message_id:
                        await self._edit_bot_message_text_safe(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=error_text,
                            parse_mode='HTML'
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
                        parse_mode='HTML'
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
                    parse_mode='HTML'
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
                    parse_mode='HTML'
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
            keyboard = self._create_main_menu_keyboard_for_user(chat_id, language, user)
            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')
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
                await update.message.reply_text(text, reply_markup=keyboard)
                del self.user_states[chat_id]
                return

            # Check rate limiting
            can_send = await self.storage.can_send_feedback(chat_id, rate_limit_minutes=10)
            if not can_send:
                text = self._get_text("feedback_rate_limit", language)
                keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
                await update.message.reply_text(text, reply_markup=keyboard)
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
                admin_text = f"💌 New feedback received\n\n" \
                           f"👤 User: {chat_id} (@{username})\n" \
                           f"🌐 Language: {language}\n" \
                           f"📏 Length: {len(feedback_text)} chars\n" \
                           f"💬 Message: {feedback_text}"

                for admin_id in self.admin_ids:
                    try:
                        await self.application.bot.send_message(admin_id, admin_text)
                    except Exception:
                        pass  # Ignore errors for admin notifications
            else:
                text = f"{self._get_text('feedback_error', language)}\n\n{self._get_text('menu', language)}"

            keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
            message = await update.message.reply_text(self._as_html(text), reply_markup=keyboard, parse_mode='HTML')

            # Delete the previous bot message (feedback prompt) for clean dialog
            if update.message.reply_to_message:
                await self._delete_message_safe(chat_id, update.message.reply_to_message.message_id)

        except Exception as e:
            logger.error(f"Error handling feedback from user {chat_id}: {e}")
            if chat_id in self.user_states:
                del self.user_states[chat_id]
            text = f"{self._get_text('error', language)}\n\n{self._get_text('menu', language)}"
            keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
            await update.message.reply_text(self._as_html(text), reply_markup=keyboard, parse_mode='HTML')

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
                await update.message.reply_text(self._as_html(self._get_text("stop_feedback_thanks", language)), parse_mode='HTML')

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

    async def _send_material_message(self, chat_id: int, text: str) -> None:
        sent_message = await self.application.bot.send_message(chat_id, text, parse_mode='HTML')
        await self.storage.add_bot_message(chat_id, sent_message.message_id, "meridian")

    async def _send_material_photo(self, chat_id: int, image_path: Path, caption: Optional[str] = None) -> None:
        if not image_path.exists():
            logger.warning("Material image is missing: %s", image_path)
            return
        with open(image_path, "rb") as photo:
            sent_message = await self.application.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode='HTML' if caption else None
            )
        await self.storage.add_bot_message(chat_id, sent_message.message_id, "meridian")

    async def _send_shu_points_material(self, chat_id: int, language: str) -> None:
        """Send five shu-points material as ordered text and image blocks."""
        await self._send_material_message(chat_id, self._get_text("shu_intro_text", language))
        await self._send_material_photo(chat_id, _localized_material_image(SHU_RIVER_IMAGE_PATHS, language))
        await self._send_material_message(chat_id, self._get_text("shu_flow_text", language))
        await self._send_material_photo(chat_id, _localized_material_image(SHU_CHANNEL_IMAGE_PATHS, language))
        await self._send_material_message(chat_id, self._get_text("shu_indications_text", language))

        await self._send_material_message(chat_id, self._get_text("shu_sources_text", language))
        await self._send_material_photo(chat_id, MERIDIAN_MATERIALS_IMAGE_DIR / "shu_sources.png")

        await self._send_material_message(chat_id, self._get_text("shu_brooks_text", language))
        await self._send_material_photo(chat_id, MERIDIAN_MATERIALS_IMAGE_DIR / "shu_brooks_1.png")
        await self._send_material_message(chat_id, self._get_text("shu_brooks_after_image_text", language))
        await self._send_material_photo(chat_id, MERIDIAN_MATERIALS_IMAGE_DIR / "shu_brooks_2.png")

        await self._send_material_message(chat_id, self._get_text("shu_rapids_text", language))
        await self._send_material_photo(chat_id, MERIDIAN_MATERIALS_IMAGE_DIR / "shu_rapids.png")

        await self._send_material_message(chat_id, self._get_text("shu_rivers_text", language))
        await self._send_material_photo(chat_id, MERIDIAN_MATERIALS_IMAGE_DIR / "shu_rivers_1.png")
        await self._send_material_message(chat_id, self._get_text("shu_rivers_after_image_text", language))
        await self._send_material_photo(chat_id, MERIDIAN_MATERIALS_IMAGE_DIR / "shu_rivers_2.png")

        await self._send_material_message(chat_id, self._get_text("shu_mouths_text", language))
        await self._send_material_photo(chat_id, MERIDIAN_MATERIALS_IMAGE_DIR / "shu_mouths_1.png")
        await self._send_material_message(chat_id, self._get_text("shu_mouths_after_image_1_text", language))
        await self._send_material_photo(chat_id, MERIDIAN_MATERIALS_IMAGE_DIR / "shu_mouths_2.png")
        await self._send_material_message(chat_id, self._get_text("shu_mouths_after_image_2_text", language))
        await self._send_material_photo(chat_id, MERIDIAN_MATERIALS_IMAGE_DIR / "shu_mouths_3.png")
        await self._send_material_message(chat_id, self._get_text("shu_final_text", language))

    async def _show_principle_detail(self, query, principle: Dict[str, Any], language: str) -> None:
        """Show a selected Yama/Niyama principle in the current menu message."""
        principle_id = int(principle.get("id", 0))
        chat_id = query.message.chat.id
        keyboard = self._create_principle_detail_keyboard(language)
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
        return fit_html_caption(text, max_length)

    async def _show_meridian_card(
        self,
        query,
        text: str,
        keyboard: InlineKeyboardMarkup,
        language: str,
        meridian_id: Optional[str] = None,
        point_code: Optional[str] = None,
        append: bool = False
    ) -> None:
        """Show meridian content with an image when available."""
        chat_id = query.message.chat.id
        image_path = get_meridian_image_path(meridian_id, point_code) if meridian_id else None

        if append:
            if image_path:
                caption = self._fit_html_caption(text)
                is_gif = image_path.lower().endswith(".gif")
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
            else:
                sent_message = await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
            await self.storage.add_bot_message(chat_id, sent_message.message_id, "meridian")
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except BadRequest as e:
                if "message is not modified" not in str(e).lower():
                    logger.debug("Could not clear old meridian keyboard: %s", e)
            except Exception as e:
                logger.debug("Could not clear old meridian keyboard: %s", e)
            return

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
            args = self._extract_command_args(update, context)
            if args:
                try:
                    limit = int(args[0])
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


    async def _handle_progress(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /progress command (admin only)."""
        chat_id = update.effective_chat.id

        if chat_id not in self.admin_ids:
            return

        if not update.message:
            logger.warning("progress called without message")
            return

        try:
            limit = 30
            args = self._extract_command_args(update, context)
            if args:
                try:
                    limit = max(1, min(int(args[0]), 100))
                except ValueError:
                    await update.message.reply_text(self._get_admin_text("progress_usage"))
                    return

            users = await self.storage.get_all_users()
            users.sort(key=lambda item: (not item.is_active, item.language, item.chat_id))

            route = self.meridians_manager.get_recommended_path_meridians()
            route_ids = [meridian.get("id") for meridian in route]
            route_total = len(route_ids)

            lines = [f"🧭 Users progress ({min(len(users), limit)}/{len(users)}):"]
            for user in users[:limit]:
                enabled_modes = []
                if user.principles_enabled:
                    enabled_modes.append("Yama/Niyama")
                if user.meridians_enabled:
                    enabled_modes.append("Meridians")

                current_meridian = (
                    self.meridians_manager.get_meridian_by_id(user.current_meridian_id)
                    if user.current_meridian_id
                    else None
                )
                current_name = (
                    self._localized_meridian_name(current_meridian, user.language)
                    if current_meridian
                    else "-"
                )

                point_progress = "-"
                if current_meridian:
                    point_total = len(current_meridian.get("points", []))
                    if user.current_point_index >= 0:
                        point_progress = f"{user.current_point_index + 1}/{point_total}"
                    else:
                        point_progress = f"intro/{point_total}"

                completed_count = len([item for item in user.completed_meridians if item in route_ids])
                if not route_total:
                    completed_count = len(user.completed_meridians)

                secret_tasks = user.secret_tasks or {}
                secret_progress = (
                    ", ".join(f"{task}:{status}" for task, status in secret_tasks.items())
                    if secret_tasks
                    else "-"
                )
                active_status = "active" if user.is_active else "paused"
                modes_text = ", ".join(enabled_modes) if enabled_modes else "-"
                route_text = f"{completed_count}/{route_total}" if route_total else str(completed_count)

                lines.append(
                    f"\n{user.chat_id} | {active_status} | {user.language} | {modes_text}"
                    f"\n  path: {user.meridian_learning_mode or '-'}; current: {current_name}; point: {point_progress}; completed: {route_text}"
                    f"\n  secret: {secret_progress}"
                )

            text = "\n".join(lines)
            chunks = [text[index:index + 3900] for index in range(0, len(text), 3900)]
            for chunk in chunks:
                await update.message.reply_text(chunk)

        except Exception as e:
            logger.error(f"Error in progress handler: {e}")
            try:
                await update.message.reply_text("Error getting progress.")
            except Exception:
                logger.error(f"Could not send progress error to {chat_id}")


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
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("👥 Subscribers", callback_data="admin_subscribers")]])
            await update.message.reply_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error in admin handler: {e}")
            try:
                await update.message.reply_text("Error showing admin help.")
            except:
                logger.error(f"Could not send error message to {chat_id}")

    async def _handle_subscribers(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /subscribers (admin only): subscribed users with links to their Telegram profiles."""
        chat_id = update.effective_chat.id
        if chat_id not in self.admin_ids or not update.message:
            return
        await self._send_subscribers_list(chat_id, context)

    async def _handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Buttons under the /admin message."""
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat.id
        if chat_id not in self.admin_ids:
            return
        if query.data == "admin_subscribers":
            await self._send_subscribers_list(chat_id, context)

    async def _subscriber_chat(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        """The user's Telegram profile (name, username), or None when Telegram does not give it."""
        try:
            return await asyncio.wait_for(context.bot.get_chat(chat_id), timeout=20)
        except Exception as e:
            logger.debug(f"Could not get chat {chat_id}: {e}")
            return None

    def _subscriber_line(self, number: int, user: User, chat) -> str:
        first = getattr(chat, "first_name", None)
        last = getattr(chat, "last_name", None)
        name = " ".join(part for part in (first, last) if part) or getattr(chat, "title", None) or f"id {user.chat_id}"
        username = getattr(chat, "username", None)
        # tg://user?id opens the profile even without a username
        href = f"https://t.me/{username}" if username else f"tg://user?id={user.chat_id}"
        handle = f" @{escape(username)}" if username else ""
        modes = []
        if user.principles_enabled:
            modes.append(f"🕊 {user.time_for_send}")
        if user.meridians_enabled:
            modes.append(f"☯️ {user.meridian_time_for_send}")
        details = " · ".join([f"<code>{user.chat_id}</code>", user.language, escape(user.timezone)] + (modes or ["no reminders"]))
        return f'{number}. <a href="{href}">{escape(name)}</a>{handle}\n    {details}'

    async def _send_subscribers_list(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send the admin the list of active subscribers, split to fit Telegram's message limit."""
        try:
            users = await self.storage.get_all_users()
            active = [u for u in users if u.is_active]
            inactive = len(users) - len(active)
            semaphore = asyncio.Semaphore(10)

            async def profile(user: User):
                async with semaphore:
                    return await self._subscriber_chat(context, user.chat_id)

            chats = await asyncio.gather(*(profile(u) for u in active))
            header = f"👥 <b>Subscribers: {len(active)}</b>" + (f" · unsubscribed: {inactive}" if inactive else "")
            lines = [self._subscriber_line(i, u, c) for i, (u, c) in enumerate(zip(active, chats), 1)]
            if not lines:
                lines = ["Nobody is subscribed yet."]
            chunks, current = [], header
            for line in lines:
                if len(current) + len(line) + 2 > 3800:
                    chunks.append(current)
                    current = line
                else:
                    current += "\n\n" + line
            chunks.append(current)
            for chunk in chunks:
                await context.bot.send_message(chat_id, chunk, parse_mode='HTML', disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Error sending subscribers list: {e}")
            try:
                await context.bot.send_message(chat_id, "Error getting the subscribers list.")
            except Exception:
                logger.error(f"Could not send subscribers error to {chat_id}")
