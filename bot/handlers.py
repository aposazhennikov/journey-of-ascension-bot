"""Command handlers for yoga bot."""

import asyncio
import logging
import re
from html import escape
from pathlib import Path
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
    fit_html_caption,
    get_principle_image_path,
    get_meridian_image_path,
    localized_point_name
)


logger = logging.getLogger(__name__)

MERIDIAN_POINTS_PAGE_SIZE = 7
MERIDIAN_SELECTION_PAGE_SIZE = 7
CUN_MEASUREMENT_IMAGE_PATH = Path(__file__).resolve().parent.parent / "images" / "meridians" / "cun_measurement.png"


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
                          'Choose weekdays when the bot should not send daily practice reminders.\n'
                          '\n'
                          'Leave everything unselected if you want a daily rhythm.',
        'setup_complete': '🎉 <b>Your practice rhythm is ready.</b>\n'
                          '\n'
                          '📋 <b>What is active now:</b>\n'
                          '🕐 Time: {time}\n'
                          '🌍 Time Zone: {timezone}\n'
                          '📅 Quiet Days: {skip_days}\n'
                          '\n'
                          'Open /menu whenever you want to explore the lists, change the rhythm, or continue '
                          'meridian practice.',
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
        'sending_test': '🧪 Sending a reminder check...',
        'menu_about': 'ℹ️ About the bot',
        'menu_feedback': '💌 Feedback and ideas',
        'menu_stop': '⏹ Stop bot',
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
                              'Choose weekdays when the bot should not send daily practice reminders.\n'
                              '\n'
                              'Leave everything unselected if you want a daily rhythm.',
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
                                    'longer, gently massage it, and breathe through it with attention.\n'
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
        'feature_announcement': '☯️ <b>New in Journey of Ascension: meridian practice</b>\n'
                                '\n'
                                'You can now study Chinese meridians inside the bot: choose a channel, open '
                                'each point with its image, and move through the practice at your own pace.\n'
                                '\n'
                                'The daily reminder does not rush you forward. It simply brings you back to '
                                'the current focus so attention can become steadier.\n'
                                '\n'
                                'Open /menu and choose <b>Meridians</b>.',
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
                          'Выберите дни недели, когда бот не должен присылать ежедневные напоминания по '
                          'практике.\n'
                          '\n'
                          'Если хотите ежедневный ритм, оставьте дни невыбранными.',
        'setup_complete': '🎉 <b>Ритм практики настроен.</b>\n'
                          '\n'
                          '📋 <b>Что сейчас активно:</b>\n'
                          '🕐 Время: {time}\n'
                          '🌍 Часовой пояс: {timezone}\n'
                          '📅 Дни тишины: {skip_days}\n'
                          '\n'
                          'Открывайте /menu, когда захотите посмотреть списки, изменить ритм или продолжить '
                          'практику меридианов.',
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
        'sending_test': '🧪 Проверяю отправку напоминания...',
        'menu_about': 'ℹ️ О боте',
        'menu_feedback': '💌 Отзывы и идеи',
        'menu_stop': '⏹ Остановить бота',
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
                              'Выберите дни недели, когда бот не должен присылать ежедневные напоминания по '
                              'практике.\n'
                              '\n'
                              'Если хотите ежедневный ритм, оставьте дни невыбранными.',
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
                                    'дольше, мягко помассируйте и представляйте вдох и выдох через неё.\n'
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
        'feature_announcement': '☯️ <b>Новое в Journey of Ascension: практика меридианов</b>\n'
                                '\n'
                                'Теперь внутри бота можно изучать китайские меридианы: выбирать канал, '
                                'открывать каждую точку с изображением и двигаться по практике в своём '
                                'темпе.\n'
                                '\n'
                                'Ежедневное напоминание не торопит вас дальше. Оно просто возвращает к '
                                'текущему фокусу, чтобы внимание становилось устойчивее.\n'
                                '\n'
                                'Откройте /menu и выберите <b>Меридианы</b>.',
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
        'setup_complete': '🎉 <b>Amaliyot ritmingiz tayyor.</b>\n'
                          '\n'
                          '📋 <b>Hozir nimalar faol:</b>\n'
                          '🕐 Vaqt: {time}\n'
                          '🌍 Vaqt mintaqasi: {timezone}\n'
                          '📅 Sokin kunlar: {skip_days}\n'
                          '\n'
                          "/menu ni ochib, ro'yxatlarni ko'rishingiz, ritmni o'zgartirishingiz yoki meridian "
                          'amaliyotini davom ettirishingiz mumkin.',
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
        'sending_test': '🧪 Eslatma tekshiruvi yuborilmoqda...',
        'menu_about': 'ℹ️ Bot haqida',
        'menu_feedback': '💌 Fikr va takliflar',
        'menu_stop': "⏹ Botni to'xtatish",
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
                                    'uzoqroq turing, yengil massaj qiling va shu nuqta orqali nafas '
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
        'feature_announcement': "☯️ <b>Journey of Ascension'da yangilik: meridian amaliyoti</b>\n"
                                '\n'
                                "Endi bot ichida Xitoy meridianlarini o'rganish mumkin: kanalni tanlang, har "
                                "bir nuqtani rasmi bilan oching va amaliyotda o'z ritmingizda yuring.\n"
                                '\n'
                                'Kundalik eslatma sizni shoshiltirmaydi. U faqat joriy fokusga qaytaradi, '
                                "shunda diqqat asta-sekin barqarorroq bo'ladi.\n"
                                '\n'
                                "/menu ni oching va <b>Meridianlar</b> bo'limini tanlang.",
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
        'setup_complete': '🎉 <b>Тәжірибе ырғағы дайын.</b>\n'
                          '\n'
                          '📋 <b>Қазір не белсенді:</b>\n'
                          '🕐 Уақыт: {time}\n'
                          '🌍 Уақыт белдеуі: {timezone}\n'
                          '📅 Тыныш күндер: {skip_days}\n'
                          '\n'
                          '/menu ашып, тізімдерді көре аласыз, ырғақты өзгерте аласыз немесе меридиан '
                          'тәжірибесін жалғастыра аласыз.',
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
        'sending_test': '🧪 Еске салу тексеруі жіберіліп жатыр...',
        'menu_about': 'ℹ️ Бот туралы',
        'menu_feedback': '💌 Пікірлер мен ұсыныстар',
        'menu_stop': '⏹ Ботты тоқтату',
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
                                    'ұзағырақ болыңыз, жеңіл уқалаңыз және сол нүкте арқылы тыныс алуды '
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
        'feature_announcement': '☯️ <b>Journey of Ascension ішіндегі жаңалық: меридиан тәжірибесі</b>\n'
                                '\n'
                                'Енді бот ішінде қытай меридиандарын зерттеуге болады: арнаны таңдаңыз, әр '
                                'нүктені суретімен ашыңыз және тәжірибеде өз ырғағыңызбен жүріңіз.\n'
                                '\n'
                                'Күнделікті еске салу сізді асықтырмайды. Ол тек ағымдағы фокусқа қайтарады, '
                                'сонда зейін біртіндеп тұрақтанады.\n'
                                '\n'
                                '/menu ашып, <b>Меридиандар</b> бөлімін таңдаңыз.',
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
        "• broadcast <message> - Send message to all users\n"
        "• broadcast meridians_announcement - Send localized meridians announcement\n\n"
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
            "Practice starts with noticing where your strength goes during an ordinary day. Energy is not an abstract word here: it is attention, vitality, steadiness, and the ability to act without draining yourself.\n\n"
            "<b>Yama and Niyama</b> are the foundation. They help stop the leaks: harsh speech, conflict, hurry, excess, self-harm, resentment, and automatic reactions. <b>Ahimsa</b>, for example, is not only about not hurting others; it is also about not spending force on damaging yourself and then paying for recovery.\n\n"
            "<b>Meridians</b> bring the same work into the body. You learn to feel channels of Qi through attention, breath, touch, warmth, pressure, and quiet areas. If a point is hard to feel, it is not a failure; it is a place that asks for more patient practice.\n\n"
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
            "Choose the time when the bot should send your daily <b>Yama/Niyama</b> principle.\n\n"
            "Format: HH:MM, for example 08:00 or 20:30."
        ),
        "time_step_meridians": (
            "⏰ <b>Step 2/3: Reminder Time</b>\n\n"
            "Choose the time when the bot should send your daily <b>meridian</b> focus.\n\n"
            "Format: HH:MM, for example 08:00 or 20:30."
        ),
        "time_step_both": (
            "⏰ <b>Step 2/4: Reminder Time</b>\n\n"
            "First choose the time for your daily <b>Yama/Niyama</b> principle. The meridian reminder time comes next.\n\n"
            "Format: HH:MM, for example 08:00 or 20:30."
        ),
        "continue_setup": "Continue",
        "menu": "📋 <b>Journey of Ascension</b>",
        "menu_principles": "🧘🏻✨ Yama/Niyama",
        "menu_meridians": "☯️ Meridians",
        "menu_modes": "🧭 My Path",
        "menu_stop": "⏹ Stop bot",
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
            "Choose weekdays when the bot should not send daily practice reminders.\n\n"
            "Leave everything unselected if you want a daily rhythm."
        ),
        "principles_menu": (
            "🕊️ <b>Yama/Niyama</b>\n\n"
            "These are the first two limbs of classical yoga. They are not a list of nice ideas; they are a training of how not to waste energy through speech, habits, reactions, desires, and inner disorder.\n\n"
            "<b>Yama</b> works with your contact with the world: non-harm, truthfulness, non-stealing, moderation, and non-possessiveness. It teaches you to stop losing force in conflict, pressure, comparison, and grabbing.\n\n"
            "<b>Niyama</b> works with your inner ground: purity, contentment, discipline, self-study, and surrender of the fruits of action. It gathers attention back into a cleaner rhythm.\n\n"
            "The daily principle is only the accent of the day. It does not mean you practise Ahimsa today and forget it tomorrow. We keep all principles in life at once; each day one of them comes closer to the surface.\n\n"
            "Open one principle for today or view the full list."
        ),
        "principles_random": "Random principle",
        "principles_all": "All principles",
        "principles_back": "🔙 Back to Yama/Niyama",
        "principles_empty": "The principles did not open right now. Please return to Yama/Niyama or try again from /menu.",
        "change_modes": "🧭 My Path",
        "change_meridian_time": "☯️ Meridian Time",
        "mode_menu": (
            "🧭 <b>My Path</b>\n\n"
            "Choose which practice you want to return to each day.\n\n"
            "<b>Yama/Niyama</b> is the foundation: less inner noise, fewer energy leaks, more honesty in action.\n\n"
            "<b>Meridians</b> are the body layer: points, channels, Qi flow, and the habit of patiently including places that are hard to feel at first.\n\n"
            "You can begin with one direction or keep both active together."
        ),
        "mode_principles_only": "Yama/Niyama foundation",
        "mode_meridians_only": "Meridian study",
        "mode_both": "Both directions",
        "mode_saved": "✅ <b>Your path has been updated.</b>",
        "meridian_time_step": "☯️ <b>Meridian Reminder Time</b>\n\nEnter time in HH:MM format, for example 20:00.",
        "meridian_time_setup_step": (
            "☯️ <b>Step 3/4: Meridian Reminder Time</b>\n\n"
            "Now choose when the bot should return you to the current meridian or point. This can be a different time from the Yama/Niyama principle.\n\n"
            "Format: HH:MM, for example 20:00."
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
            "<b>2.</b> If the point is hard to feel, treat it as not yet open for practice. Stay longer, gently massage it, and imagine breathing in and out through this place.\n\n"
            "<b>3.</b> Do not force a result. A quiet, steady sensation is enough.\n\n"
            "When you move to the next point, keep the previous ones in the background and add the new point to the same line of attention."
        ),
        "meridians_menu": (
            "☯️ <b>Meridians</b>\n\n"
            "<b>Why study meridians?</b>\n\n"
            "In Chinese tradition, meridians are the channels through which Qi moves. For practice, this is not a theory to believe in blindly. It is a way to observe the body: where sensation is clear, where the line breaks, where a point feels warm, tense, empty, or silent.\n\n"
            "<b>What you train:</b> attention, breath, and gentle touch. A point that does not answer at first can be treated as closed for now: stay longer, massage it lightly, breathe through it with attention, and wait until the sensation becomes steadier.\n\n"
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
            "☯️ <b>New in Journey of Ascension: meridian practice</b>\n\n"
            "You can now study Chinese meridians inside the bot: choose a channel, open each point with its image, and move through the practice at your own pace.\n\n"
            "The daily reminder does not rush you forward. It simply brings you back to the current focus so attention can become steadier.\n\n"
            "Open /menu and choose <b>Meridians</b>."
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
            "🎉 <b>Your practice rhythm is ready.</b>\n\n"
            "📋 <b>What is active now:</b>\n"
            "🕐 Time: {time}\n"
            "🌍 Time Zone: {timezone}\n"
            "📅 Quiet Days: {skip_days}\n\n"
            "Open /menu whenever you want to explore the lists, change the rhythm, or continue meridian practice."
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
            "Практика начинается с простого наблюдения: куда в течение дня уходит моя сила? Энергия здесь не абстрактное слово. Это внимание, живость, устойчивость и способность действовать, не опустошая себя.\n\n"
            "<b>Яма и Нияма</b> — фундамент. Они помогают закрывать утечки: резкую речь, конфликт, спешку, излишества, вред себе, обиду и автоматические реакции. <b>Ахимса</b>, например, не только про «не вредить другим»; это ещё и про то, чтобы не тратить силу на разрушение себя, а потом не платить энергией за восстановление.\n\n"
            "<b>Меридианы</b> переносят эту же работу в тело. Вы учитесь чувствовать каналы Ци через внимание, дыхание, касание, тепло, давление и тихие зоны. Если точка почти не ощущается, это не ошибка; это место, которому нужно больше терпеливой практики.\n\n"
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
            "Укажите время, когда бот будет присылать ежедневный принцип <b>Ямы/Ниямы</b>.\n\n"
            "Формат: ЧЧ:ММ, например 08:00 или 20:30."
        ),
        "time_step_meridians": (
            "⏰ <b>Шаг 2/3: Время отправки</b>\n\n"
            "Укажите время, когда бот будет присылать ежедневный фокус по <b>меридианам</b>.\n\n"
            "Формат: ЧЧ:ММ, например 08:00 или 20:30."
        ),
        "time_step_both": (
            "⏰ <b>Шаг 2/4: Время отправки</b>\n\n"
            "Сначала укажите время для ежедневного принципа <b>Ямы/Ниямы</b>. Время меридианов выберем следующим шагом.\n\n"
            "Формат: ЧЧ:ММ, например 08:00 или 20:30."
        ),
        "continue_setup": "Продолжить",
        "menu": "📋 <b>Journey of Ascension</b>",
        "menu_principles": "🧘🏻✨ Яма/Нияма",
        "menu_meridians": "☯️ Меридианы",
        "menu_modes": "🧭 Мой путь",
        "menu_stop": "⏹ Остановить бота",
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
            "Выберите дни недели, когда бот не должен присылать ежедневные напоминания по практике.\n\n"
            "Если хотите ежедневный ритм, оставьте дни невыбранными."
        ),
        "principles_menu": (
            "🕊️ <b>Яма/Нияма</b>\n\n"
            "Это первые две ступени классической йоги. Не список красивых идей, а тренировка того, как не расходовать энергию через речь, привычки, реакции, желания и внутренний беспорядок.\n\n"
            "<b>Яма</b> работает с вашим контактом с миром: ненасилие, правдивость, неприсвоение чужого, умеренность и нестяжательство. Она учит не терять силу в конфликте, давлении, сравнении и хватании лишнего.\n\n"
            "<b>Нияма</b> работает с внутренней опорой: чистота, удовлетворённость, дисциплина, самоизучение и посвящение плодов практики высшему. Она собирает внимание в более чистый ритм.\n\n"
            "Принцип дня — это только акцент. Это не значит, что сегодня мы практикуем Ахимсу, а завтра забываем о ней. Мы держим все принципы в жизни одновременно; просто каждый день один из них выходит ближе к поверхности.\n\n"
            "Откройте принцип дня или посмотрите весь список."
        ),
        "principles_random": "Случайный принцип",
        "principles_all": "Все принципы",
        "principles_back": "🔙 К Яме/Нияме",
        "principles_empty": "Сейчас принципы не открылись. Вернитесь к Яме/Нияме или попробуйте снова из /menu.",
        "change_modes": "🧭 Мой путь",
        "change_meridian_time": "☯️ Время меридианов",
        "mode_menu": (
            "🧭 <b>Мой путь</b>\n\n"
            "Выберите, к какой практике вы хотите возвращаться каждый день.\n\n"
            "<b>Яма/Нияма</b> — фундамент: меньше внутреннего шума, меньше утечек энергии, больше честности в поступках.\n\n"
            "<b>Меридианы</b> — телесный слой: точки, каналы, течение Ци и навык спокойно включать в внимание места, которые сначала почти не ощущаются.\n\n"
            "Можно начать с одного направления или оставить активными оба."
        ),
        "mode_principles_only": "Фундамент Ямы/Ниямы",
        "mode_meridians_only": "Изучение меридианов",
        "mode_both": "Оба направления",
        "mode_saved": "✅ <b>Ваш путь обновлён.</b>",
        "meridian_time_step": "☯️ <b>Время напоминания по меридианам</b>\n\nВведите время в формате ЧЧ:ММ, например 20:00.",
        "meridian_time_setup_step": (
            "☯️ <b>Шаг 3/4: Время меридианов</b>\n\n"
            "Теперь выберите, когда бот будет возвращать вас к текущему меридиану или точке. Это время может отличаться от времени принципа Ямы/Ниямы.\n\n"
            "Формат: ЧЧ:ММ, например 20:00."
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
            "<b>2.</b> Если точка почти не ощущается, считайте её пока закрытой для практики. Побудьте с ней дольше, мягко помассируйте и представляйте вдох и выдох через это место.\n\n"
            "<b>3.</b> Не выжимайте результат. Достаточно тихого устойчивого ощущения.\n\n"
            "Когда переходите к следующей точке, не бросайте предыдущие: удерживайте их фоном и добавляйте новую в ту же линию внимания."
        ),
        "meridians_menu": (
            "☯️ <b>Меридианы</b>\n\n"
            "<b>Зачем изучать меридианы?</b>\n\n"
            "В китайской традиции меридианы — это каналы, по которым движется Ци. Для практики это не теория, в которую нужно слепо верить. Это способ наблюдать тело: где ощущение ясное, где линия обрывается, где точка тёплая, напряжённая, пустая или молчит.\n\n"
            "<b>Что мы тренируем:</b> внимание, дыхание и мягкое касание. Если точка сначала не отвечает, можно считать её пока закрытой для практики: задержитесь дольше, легко помассируйте, подышите через неё вниманием и дождитесь более устойчивого ощущения.\n\n"
            "<b>Как двигаться:</b> каждая новая точка добавляется к предыдущим. Сначала почувствуйте первую. Потом удерживайте её фоном и добавляйте вторую. Постепенно меридиан становится одной живой линией, а не набором отдельных точек.\n\n"
            "<b>Выберите путь:</b> маршрут бота подойдёт, если хочется спокойной последовательности с самого начала. Свободный выбор — если конкретный меридиан уже тянет ваше внимание.\n\n"
            "<b>Перед точками:</b> откройте справку по <b>цуням</b>. Она помогает найти область, а точное место уточняется пальцами, дыханием и вниманием.\n\n"
            "Это практика самонаблюдения и внутренней дисциплины. Она не заменяет медицинскую диагностику и лечение."
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
            "☯️ <b>Новое в Journey of Ascension: практика меридианов</b>\n\n"
            "Теперь внутри бота можно изучать китайские меридианы: выбирать канал, открывать каждую точку с изображением и двигаться по практике в своём темпе.\n\n"
            "Ежедневное напоминание не торопит вас дальше. Оно просто возвращает к текущему фокусу, чтобы внимание становилось устойчивее.\n\n"
            "Откройте /menu и выберите <b>Меридианы</b>."
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
            "🎉 <b>Ритм практики настроен.</b>\n\n"
            "📋 <b>Что сейчас активно:</b>\n"
            "🕐 Время: {time}\n"
            "🌍 Часовой пояс: {timezone}\n"
            "📅 Дни тишины: {skip_days}\n\n"
            "Открывайте /menu, когда захотите посмотреть списки, изменить ритм или продолжить практику меридианов."
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
            "Amaliyot oddiy kuzatishdan boshlanadi: kun davomida kuchim qayerga ketmoqda? Bu yerda energiya mavhum so'z emas. Bu diqqat, hayotiylik, barqarorlik va o'zingizni bo'shatib yubormasdan harakat qilish qobiliyatidir.\n\n"
            "<b>Yama va Niyama</b> poydevor. Ular energiya oqib ketadigan joylarni yopishga yordam beradi: keskin so'z, ziddiyat, shoshilish, ortiqchalik, o'zingizga zarar, xafagarchilik va avtomatik reaksiyalar. <b>Ahimsa</b>, masalan, faqat boshqalarga zarar yetkazmaslik emas; u o'zingizni yemirmaslik va keyin tiklanishga yana kuch sarflamaslikdan ham boshlanadi.\n\n"
            "<b>Meridianlar</b> shu ishni tanaga olib kiradi. Siz Qi kanallarini diqqat, nafas, teginish, iliqlik, bosim va sokin joylar orqali sezishni o'rganasiz. Agar nuqta deyarli sezilmasa, bu xato emas; bu ko'proq sabrli amaliyot so'rayotgan joy.\n\n"
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
            "Bot kundalik <b>Yama/Niyama</b> tamoyilini qachon yuborishini tanlang.\n\n"
            "Format: HH:MM, masalan 08:00 yoki 20:30."
        ),
        "time_step_meridians": (
            "⏰ <b>2/3-qadam: Yuborish vaqti</b>\n\n"
            "Bot kundalik <b>meridian</b> fokusini qachon yuborishini tanlang.\n\n"
            "Format: HH:MM, masalan 08:00 yoki 20:30."
        ),
        "time_step_both": (
            "⏰ <b>2/4-qadam: Yuborish vaqti</b>\n\n"
            "Avval kundalik <b>Yama/Niyama</b> tamoyili vaqtini tanlang. Meridian eslatmasi vaqtini keyingi qadamda tanlaymiz.\n\n"
            "Format: HH:MM, masalan 08:00 yoki 20:30."
        ),
        "continue_setup": "Davom etish",
        "menu": "📋 <b>Journey of Ascension</b>",
        "menu_principles": "🧘🏻✨ Yama/Niyama",
        "menu_meridians": "☯️ Meridianlar",
        "menu_modes": "🧭 Mening yo'lim",
        "menu_stop": "⏹ Botni to'xtatish",
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
            "Bot kundalik amaliyot eslatmalarini yubormaydigan hafta kunlarini tanlang.\n\n"
            "Har kuni ritm kerak bo'lsa, kunlarni tanlamang."
        ),
        "principles_menu": (
            "🕊️ <b>Yama/Niyama</b>\n\n"
            "Bular klassik yoganing birinchi ikki pog'onasi. Bu chiroyli fikrlar ro'yxati emas, balki energiyani so'z, odat, reaksiya, istak va ichki tartibsizlik orqali behuda sarflamaslik mashqidir.\n\n"
            "<b>Yama</b> dunyo bilan munosabatda ishlaydi: zarar yetkazmaslik, rostgo'ylik, o'g'irlamaslik, mo'tadillik va ortiqcha egalik qilmaslik. U kuchni ziddiyat, bosim, taqqoslash va ortiqcha narsaga yopishishda yo'qotmaslikni o'rgatadi.\n\n"
            "<b>Niyama</b> ichki tayanch bilan ishlaydi: poklik, qanoat, intizom, o'zini o'rganish va amaliyot mevasini oliy maqsadga bag'ishlash. U diqqatni tozaroq ritmga yig'adi.\n\n"
            "Kun tamoyili faqat urg'u. Bu bugun Ahimsani mashq qilib, ertaga uni unutamiz degani emas. Biz barcha tamoyillarni hayotda birga ushlab turamiz; har kuni bittasi yuzaga yaqinroq chiqadi.\n\n"
            "Bugungi tamoyilni oching yoki to'liq ro'yxatni ko'ring."
        ),
        "principles_random": "Tasodifiy tamoyil",
        "principles_all": "Barcha tamoyillar",
        "principles_back": "🔙 Yama/Niyamaga qaytish",
        "principles_empty": "Hozir tamoyillar ochilmadi. Yama/Niyamaga qayting yoki /menu dan qayta urinib ko'ring.",
        "change_modes": "🧭 Mening yo'lim",
        "change_meridian_time": "☯️ Meridian vaqti",
        "mode_menu": (
            "🧭 <b>Mening yo'lim</b>\n\n"
            "Har kuni qaysi amaliyotga qaytishni xohlayotganingizni tanlang.\n\n"
            "<b>Yama/Niyama</b> poydevor: ichki shovqin kamroq, energiya yo'qotish kamroq, harakatlarda ko'proq halollik.\n\n"
            "<b>Meridianlar</b> tana qatlami: nuqtalar, kanallar, Qi oqimi va avval noaniq sezilgan joylarni sabr bilan diqqatga qo'shish ko'nikmasi.\n\n"
            "Bitta yo'nalishdan boshlashingiz yoki ikkalasini ham faol qoldirishingiz mumkin."
        ),
        "mode_principles_only": "Yama/Niyama poydevori",
        "mode_meridians_only": "Meridianlarni o'rganish",
        "mode_both": "Ikkala yo'nalish",
        "mode_saved": "✅ <b>Yo'lingiz yangilandi.</b>",
        "meridian_time_step": "☯️ <b>Meridian eslatma vaqti</b>\n\nVaqtni HH:MM formatida kiriting, masalan 20:00.",
        "meridian_time_setup_step": (
            "☯️ <b>3/4-qadam: Meridian eslatma vaqti</b>\n\n"
            "Endi bot sizni joriy meridian yoki nuqtaga qachon qaytarishini tanlang. Bu vaqt Yama/Niyama tamoyili vaqtidan farq qilishi mumkin.\n\n"
            "Format: HH:MM, masalan 20:00."
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
            "<b>2.</b> Agar nuqta deyarli sezilmasa, uni amaliyot uchun hali ochilmagan deb qabul qiling. Uzoqroq turing, yengil massaj qiling va shu joy orqali nafas olayotganingizni tasavvur qiling.\n\n"
            "<b>3.</b> Natijani majburlamang. Sokin va barqaror sezgi yetarli.\n\n"
            "Keyingi nuqtaga o'tganda oldingilarni fon sifatida sezib, yangi nuqtani shu diqqat chizig'iga qo'shing."
        ),
        "meridians_menu": (
            "☯️ <b>Meridianlar</b>\n\n"
            "<b>Meridianlarni nima uchun o'rganamiz?</b>\n\n"
            "Xitoy an'anasida meridianlar Qi harakat qiladigan kanallar deb tasvirlanadi. Amaliyot uchun bu ko'r-ko'rona ishoniladigan nazariya emas. Bu tanani kuzatish usuli: qayerda sezgi ravshan, qayerda chiziq uziladi, qaysi nuqta iliq, tarang, bo'sh yoki jim.\n\n"
            "<b>Nimani mashq qilamiz:</b> diqqat, nafas va yumshoq teginish. Agar nuqta boshida javob bermasa, uni hozircha amaliyot uchun yopiq deb qabul qiling: uzoqroq turing, yengil massaj qiling, shu joy orqali diqqat bilan nafas oling va sezgi barqarorroq bo'lishini kuting.\n\n"
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
            "☯️ <b>Journey of Ascension'da yangilik: meridian amaliyoti</b>\n\n"
            "Endi bot ichida Xitoy meridianlarini o'rganish mumkin: kanalni tanlang, har bir nuqtani rasmi bilan oching va amaliyotda o'z ritmingizda yuring.\n\n"
            "Kundalik eslatma sizni shoshiltirmaydi. U faqat joriy fokusga qaytaradi, shunda diqqat asta-sekin barqarorroq bo'ladi.\n\n"
            "/menu ni oching va <b>Meridianlar</b> bo'limini tanlang."
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
            "🎉 <b>Amaliyot ritmingiz tayyor.</b>\n\n"
            "📋 <b>Hozir nimalar faol:</b>\n"
            "🕐 Vaqt: {time}\n"
            "🌍 Vaqt mintaqasi: {timezone}\n"
            "📅 Sokin kunlar: {skip_days}\n\n"
            "/menu ni ochib, ro'yxatlarni ko'rishingiz, ritmni o'zgartirishingiz yoki meridian amaliyotini davom ettirishingiz mumkin."
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
            "Тәжірибе бір адал сұрақтан басталады: күн ішінде энергиям қайда кетіп жатыр? Ол шашыраса, зейін шулайды, реакциялар өткірленеді, қарапайым әрекеттің өзі көбірек күш алады. Энергия жиналса, дене тынышырақ, ал санада кеңістік көбейеді.\n\n"
            "<b>Яма мен Нияма</b> — негіз. Бұл құрғақ моральдық ұран емес; олар күшті сөз, әдет, қақтығыс, өзіңізге зиян, асығыстық және бейсаналы реакциялар арқылы шашпауға көмектеседі. <b>Ахимса</b>, мысалы, энергияны зиянға жұмсамаудан басталады — өзіңізге зиян келтіруді де қоса.\n\n"
            "<b>Меридиандар</b> тәжірибені денеге әкеледі. Сіз Ци арналарын зейін, тыныс және сезім арқылы бақылауды үйренесіз: кей нүктелер тез жауап береді, ал кейбіріне жұмсақ жанасу мен көбірек уақыт керек.\n\n"
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
            "Бот күнделікті <b>Яма/Нияма</b> қағидасын қашан жіберетінін таңдаңыз.\n\n"
            "Формат: HH:MM, мысалы 08:00 немесе 20:30."
        ),
        "time_step_meridians": (
            "⏰ <b>2/3-қадам: Жіберу уақыты</b>\n\n"
            "Бот күнделікті <b>меридиан</b> фокусын қашан жіберетінін таңдаңыз.\n\n"
            "Формат: HH:MM, мысалы 08:00 немесе 20:30."
        ),
        "time_step_both": (
            "⏰ <b>2/4-қадам: Жіберу уақыты</b>\n\n"
            "Алдымен күнделікті <b>Яма/Нияма</b> қағидасының уақытын таңдаңыз. Меридиан еске салуының уақытын келесі қадамда таңдаймыз.\n\n"
            "Формат: HH:MM, мысалы 08:00 немесе 20:30."
        ),
        "continue_setup": "Жалғастыру",
        "menu": "📋 <b>Journey of Ascension</b>",
        "menu_principles": "🧘🏻✨ Яма/Нияма",
        "menu_meridians": "☯️ Меридиандар",
        "menu_modes": "🧭 Менің жолым",
        "menu_stop": "⏹ Ботты тоқтату",
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
            "Бот күнделікті тәжірибе еске салуларын жібермейтін апта күндерін таңдаңыз.\n\n"
            "Күн сайынғы ырғақ керек болса, күндерді таңдамаңыз."
        ),
        "principles_menu": (
            "🕊️ <b>Яма/Нияма</b>\n\n"
            "Бұл классикалық йоганың алғашқы екі сатысы және тәжірибенің адамгершілік негізі.\n\n"
            "<b>Яма</b> әлеммен қарым-қатынаста энергияны сақтайды: зиян келтірмеу, шыншылдық, ұрламау, ұстамдылық және дүниеқоңыздықтан арылу.\n\n"
            "<b>Нияма</b> энергияны іште жинайды: тазалық, қанағат, тәртіп, өзін-өзі зерттеу және тәжірибе жемісін жоғары мақсатқа арнау.\n\n"
            "Күн қағидасы қалған қағидалардың орнына келмейді; ол бақылауға арналған екпін ғана. Біз олардың бәрін өмірге біртіндеп енгіземіз, ал әр күні біреуі анығырақ көрінеді.\n\n"
            "Бүгінгі қағиданы ашыңыз немесе толық тізімді көріңіз."
        ),
        "principles_random": "Кездейсоқ қағида",
        "principles_all": "Барлық қағидалар",
        "principles_back": "🔙 Яма/Ниямаға қайту",
        "principles_empty": "Қазір қағидалар ашылмады. Яма/Ниямаға оралыңыз немесе /menu арқылы қайта көріңіз.",
        "change_modes": "🧭 Менің жолым",
        "change_meridian_time": "☯️ Меридиан уақыты",
        "mode_menu": (
            "🧭 <b>Менің жолым</b>\n\n"
            "Күн сайын қай тәжірибеге қайта оралғыңыз келетінін таңдаңыз.\n\n"
            "<b>Яма/Нияма</b> — негіз: ішкі шу азаяды, энергия шығыны азаяды, әрекетте адалдық көбейеді.\n\n"
            "<b>Меридиандар</b> — дене қабаты: нүктелер, арналар, Ци ағымы және бастапқыда көмескі сезілетін жерлерді сабырмен зейінге қосу дағдысы.\n\n"
            "Бір бағыттан бастауға немесе екеуін де белсенді қалдыруға болады."
        ),
        "mode_principles_only": "Яма/Нияма негізі",
        "mode_meridians_only": "Меридиандарды зерттеу",
        "mode_both": "Екі бағыт та",
        "mode_saved": "✅ <b>Жолыңыз жаңартылды.</b>",
        "meridian_time_step": "☯️ <b>Меридиан еске салу уақыты</b>\n\nУақытты HH:MM форматында енгізіңіз, мысалы 20:00.",
        "meridian_time_setup_step": (
            "☯️ <b>3/4-қадам: Меридиан еске салу уақыты</b>\n\n"
            "Енді бот сізді ағымдағы меридианға немесе нүктеге қашан қайтаратынын таңдаңыз. Бұл уақыт Яма/Нияма қағидасының уақытынан бөлек болуы мүмкін.\n\n"
            "Формат: HH:MM, мысалы 20:00."
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
            "<b>2.</b> Егер нүкте әрең сезілсе, оны тәжірибе үшін әзірге ашылмаған деп қабылдаңыз. Ұзағырақ болыңыз, жеңіл уқалаңыз және сол жер арқылы тыныс алуды елестетіңіз.\n\n"
            "<b>3.</b> Нәтижені күштемеңіз. Тыныш әрі тұрақты сезім жеткілікті.\n\n"
            "Келесі нүктеге өткенде алдыңғыларды фонда сезіп, жаңа нүктені сол зейін сызығына қосыңыз."
        ),
        "meridians_menu": (
            "☯️ <b>Меридиандар</b>\n\n"
            "<b>Меридиандарды не үшін зерттейміз?</b>\n\n"
            "Қытай дәстүрінде меридиандар Ци қозғалатын жолдар ретінде сипатталады. Тәжірибеде бұл өте нақты болады: дене зейінге қай жерде жауап беретінін, қай жерде кернеу барын және қай жерде сезім әлі әлсіз екенін байқайсыз.\n\n"
            "<b>Бұл қалай көмектеседі:</b> зейін, тыныс және жұмсақ жанасу нүктеге сезімталдықты біртіндеп қайтарады. Аймақ жылырақ, анық әрі арнаның жалпы сызығына оңайырақ қосылатын болады.\n\n"
            "<b>Қалай зерттеу:</b> тыныш реттілік керек болса бот бағытын таңдаңыз, қай меридианды зерттегіңіз келетінін білсеңіз еркін таңдауды таңдаңыз.\n\n"
            "<b>Нүктелерден бұрын:</b> <b>цунь</b> нұсқаулығын ашыңыз. Ол денеңіздегі керек аймаққа жақындауға көмектеседі; нүктені саусақ, тыныс және зейін арқылы нақтылайсыз.\n\n"
            "Бұл өзін бақылау тәжірибесі. Ол дәрігерді, диагнозды немесе емді алмастырмайды."
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
            "Бұл бот тәжірибені күннің ішіне енгізгісі келетін адамға арналған: ол бәрі өтіп кеткен соң кешке ғана еске түспесін.\n\n"
            "Бұл жерде энергия — байқауға болатын нәрсе: зейін, тұрақтылық, тіршілік күші, өзіңізді сарқымай әрекет ету қабілеті. Энергия қақтығысқа, асығыстыққа, ренішке, артықтыққа немесе өзіңізге көңіл бөлмеуге кетсе, бүкіл күн ауырлайды.\n\n"
            "<b>Яма/Нияма</b> бұл ағуларды мінез-құлық, сөз, ой, тәртіп және өзіңізге адалдық арқылы жабуға көмектеседі.\n\n"
            "<b>Меридиандар</b> жұмысты денеге әкеледі: арналар, нүктелер, Ци ағымы, жабық аймақтар, тыныс, жанасу және сабырлы зейін.\n\n"
            "Бот күн ішінде тәжірибе жібін жоғалтпауға көмектеседі: керек сәтте фокусқа қайтарады және келесі шағын қадамды көрсетеді."
        ),
        "feature_announcement": (
            "☯️ <b>Journey of Ascension ішіндегі жаңалық: меридиан тәжірибесі</b>\n\n"
            "Енді бот ішінде қытай меридиандарын зерттеуге болады: арнаны таңдаңыз, әр нүктені суретімен ашыңыз және тәжірибеде өз ырғағыңызбен жүріңіз.\n\n"
            "Күнделікті еске салу сізді асықтырмайды. Ол тек ағымдағы фокусқа қайтарады, сонда зейін біртіндеп тұрақтанады.\n\n"
            "/menu ашып, <b>Меридиандар</b> бөлімін таңдаңыз."
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
            "🎉 <b>Тәжірибе ырғағы дайын.</b>\n\n"
            "📋 <b>Қазір не белсенді:</b>\n"
            "🕐 Уақыт: {time}\n"
            "🌍 Уақыт белдеуі: {timezone}\n"
            "📅 Тыныш күндер: {skip_days}\n\n"
            "/menu ашып, тізімдерді көре аласыз, ырғақты өзгерте аласыз немесе меридиан тәжірибесін жалғастыра аласыз."
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
            "Choose weekdays when the bot should not send daily practice reminders.\n\n"
            "Leave everything unselected if you want a daily rhythm."
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
            "Выберите дни недели, когда бот не должен присылать ежедневные напоминания по практике.\n\n"
            "Если хотите ежедневный ритм, оставьте дни невыбранными."
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

for _language, _updates in LIVE_TEXT_OVERRIDES.items():
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
        self.application.add_handler(CallbackQueryHandler(self._handle_stop_feedback_skip_callback, pattern="^stop_feedback_skip$"))
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
                                keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
                                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')
                            else:
                                await self._edit_message_text_safe(query, self._get_text("setup_error", language), parse_mode='HTML')
                    else:
                        # Handle new registration
                        self.user_states[chat_id]["timezone"] = timezone_str
                        self.user_states[chat_id]["step"] = "time"

                        confirmation = self._get_text("timezone_saved", language)
                        time_msg = self._get_time_step_text(language, self.user_states[chat_id])

                        combined_msg = f"{confirmation}\n\n{time_msg}"

                        await self._edit_message_text_safe(query, combined_msg, parse_mode='HTML')
                else:
                    await self._edit_message_text_safe(query, self._get_text("invalid_timezone", language), parse_mode='HTML')

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
                                confirmation = "✅ Skip days cleared - daily messages enabled"
                            elif language == "ru":
                                confirmation = "✅ Дни пропуска очищены - включены ежедневные сообщения"
                            elif language == "uz":
                                confirmation = "✅ O'tkazib yuborish kunlari tozalandi - kundalik xabarlar yoqildi"
                            elif language == "kz":
                                confirmation = "✅ Өткізіп жіберу күндері тазаланды - күнделікті хабарлар қосылды"

                        text = f"{escape(confirmation)}\n\n{self._text_html('menu', language)}"
                        keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)

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
                keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
                logger.debug(f"Final setup message for user {chat_id} in language {language}: {text[:150]}...")

                await self._edit_message_text_safe(query, text, reply_markup=keyboard, parse_mode='HTML')
                # Store the final message ID
                await self.storage.add_bot_message(chat_id, query.message.message_id, "setup_complete")
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

            user = await self.storage.get_user(chat_id)
            if user and not user.is_active and step != "stop_feedback":
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
            meridian_time_msg = self._get_text("meridian_time_setup_step", language)
            combined_msg = f"{escape(confirmation)}\n\n{meridian_time_msg}"

            if message_id:
                await self._edit_bot_message_text_safe(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=combined_msg,
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(combined_msg, parse_mode='HTML')
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
            keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)

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
                "en": "Current selection" if current else "Selected days to skip",
                "ru": "Текущий выбор" if current else "Выбранные дни для пропуска",
                "uz": "Joriy tanlov" if current else "O'tkazib yuborish uchun tanlangan kunlar",
                "kz": "Ағымдағы таңдау" if current else "Өткізіп жіберу үшін таңдалған күндер",
            }.get(language, "Selected days to skip")
            return f"🔸 <b>{label}:</b> {escape(self._format_skip_days(skip_days, language))}"

        empty = {
            "en": "No days selected — messages will be sent daily",
            "ru": "Дни не выбраны — сообщения будут отправляться ежедневно",
            "uz": "Kunlar tanlanmagan — xabarlar har kuni yuboriladi",
            "kz": "Күндер таңдалмаған — хабарлар күн сайын жіберіледі",
        }.get(language, "No days selected — messages will be sent daily")
        return f"🔸 <b>{empty}</b>"

    def _format_setup_complete(self, user, language: str, skip_days_display: str) -> str:
        """Format setup summary according to the selected practice modes."""
        labels = {
            "en": {
                "done": "🎉 <b>Your practice rhythm is ready.</b>",
                "settings": "📋 <b>What is active now:</b>",
                "mode": "🧭 Practice:",
                "principles": "Yama/Niyama",
                "meridians": "Meridians",
                "both": "Yama/Niyama + Meridians",
                "time": "🕐 Time:",
                "principle_time": "🕐 Yama/Niyama time:",
                "meridian_time": "☯️ Meridian time:",
                "timezone": "🌍 Time zone:",
                "skip": "📅 Quiet days:",
                "next_principles": "Each day you receive one principle as the point of attention. The other principles are not paused; we simply choose one doorway for observing thought, speech, and action today.",
                "next_meridians": "At the chosen time you return to the current meridian or point. You move through points only when you press the buttons, so the pace stays yours.",
                "next_both": "The rhythm now has two layers: an ethical focus for the day and meridian observation. The other principles are not paused; the daily card is simply the doorway for today's attention. Keep it gentle, regular, and honest.",
                "hint": "Open /menu whenever you want to explore the lists, change the rhythm, or continue meridian practice.",
            },
            "ru": {
                "done": "🎉 <b>Ритм практики настроен.</b>",
                "settings": "📋 <b>Что сейчас активно:</b>",
                "mode": "🧭 Практика:",
                "principles": "Яма/Нияма",
                "meridians": "Меридианы",
                "both": "Яма/Нияма + Меридианы",
                "time": "🕐 Время:",
                "principle_time": "🕐 Время Ямы/Ниямы:",
                "meridian_time": "☯️ Время меридианов:",
                "timezone": "🌍 Часовой пояс:",
                "skip": "📅 Дни тишины:",
                "next_principles": "Каждый день вы получаете один принцип как точку внимания. Остальные принципы не выключаются: мы просто выбираем, через что сегодня наблюдать мысли, речь и поступки.",
                "next_meridians": "В выбранное время вы возвращаетесь к текущему меридиану или точке. Дальше по точкам вы идёте только кнопками, поэтому темп остаётся вашим.",
                "next_both": "Ритм собран в два слоя: нравственный фокус дня и наблюдение меридианов. Остальные принципы не выключаются; карточка дня просто задаёт вход для сегодняшнего внимания. Держите практику мягкой, регулярной и честной.",
                "hint": "Открывайте /menu, когда захотите посмотреть списки, изменить ритм или продолжить практику меридианов.",
            },
            "uz": {
                "done": "🎉 <b>Amaliyot ritmingiz tayyor.</b>",
                "settings": "📋 <b>Hozir nimalar faol:</b>",
                "mode": "🧭 Amaliyot:",
                "principles": "Yama/Niyama",
                "meridians": "Meridianlar",
                "both": "Yama/Niyama + Meridianlar",
                "time": "🕐 Vaqt:",
                "principle_time": "🕐 Yama/Niyama vaqti:",
                "meridian_time": "☯️ Meridian vaqti:",
                "timezone": "🌍 Vaqt mintaqasi:",
                "skip": "📅 Sokin kunlar:",
                "next_principles": "Har kuni bitta tamoyil diqqat markazida bo'ladi. Boshqa tamoyillar to'xtamaydi; bugun fikr, so'z va harakatni shu eshik orqali kuzatamiz.",
                "next_meridians": "Tanlangan vaqtda joriy meridian yoki nuqtaga qaytasiz. Nuqtalar bo'ylab faqat tugmalar orqali o'tasiz, shuning uchun sur'at sizniki bo'lib qoladi.",
                "next_both": "Endi ritm ikki qatlamdan iborat: kunning axloqiy fokusi va meridianlarni kuzatish. Boshqa tamoyillar to'xtamaydi; kun kartasi bugungi diqqat uchun eshik bo'ladi. Amaliyot yumshoq, muntazam va halol bo'lsin.",
                "hint": "/menu ni ochib, ro'yxatlarni ko'rishingiz, ritmni o'zgartirishingiz yoki meridian amaliyotini davom ettirishingiz mumkin.",
            },
            "kz": {
                "done": "🎉 <b>Тәжірибе ырғағы дайын.</b>",
                "settings": "📋 <b>Қазір не белсенді:</b>",
                "mode": "🧭 Тәжірибе:",
                "principles": "Яма/Нияма",
                "meridians": "Меридиандар",
                "both": "Яма/Нияма + Меридиандар",
                "time": "🕐 Уақыт:",
                "principle_time": "🕐 Яма/Нияма уақыты:",
                "meridian_time": "☯️ Меридиан уақыты:",
                "timezone": "🌍 Уақыт белдеуі:",
                "skip": "📅 Тыныш күндер:",
                "next_principles": "Күн сайын бір қағида зейіннің ортасында болады. Қалған қағидалар тоқтамайды; бүгін ой, сөз және әрекетті осы есік арқылы бақылаймыз.",
                "next_meridians": "Таңдалған уақытта ағымдағы меридианға немесе нүктеге қайта ораласыз. Нүктелер бойынша тек батырмалармен өтесіз, сондықтан қарқын өзіңізде қалады.",
                "next_both": "Ырғақ енді екі қабаттан тұрады: күннің этикалық фокусы және меридиандарды бақылау. Қалған қағидалар тоқтамайды; күн картасы бүгінгі зейінге кіретін есік болады. Тәжірибе жұмсақ, тұрақты және шынайы болсын.",
                "hint": "/menu ашып, тізімдерді көре аласыз, ырғақты өзгерте аласыз немесе меридиан тәжірибесін жалғастыра аласыз.",
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

        lines.extend(["", next_text, "", labels["hint"]])
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
            [InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")]
        ])

    def _create_principle_detail_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create keyboard for a selected Yama/Niyama principle card."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(self._get_text("principles_random", language), callback_data="principles_random"),
                InlineKeyboardButton(self._get_text("principles_all", language), callback_data="principles_all")
            ],
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

    def _create_registration_modes_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """Create initial practice mode keyboard for new-user onboarding."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(self._get_text("mode_meridians_only", language), callback_data="intro_mode_meridians")],
            [InlineKeyboardButton(self._get_text("mode_principles_only", language), callback_data="intro_mode_principles")],
            [InlineKeyboardButton(self._get_text("mode_both", language), callback_data="intro_mode_both")],
        ])

    def _create_meridians_menu_keyboard(self, language: str, user: Optional[User] = None) -> InlineKeyboardMarkup:
        """Create compact meridians section keyboard."""
        keyboard = []
        if user and user.meridians_enabled and user.current_meridian_id:
            keyboard.append([InlineKeyboardButton(self._get_text("current_meridian", language), callback_data="meridian_current")])
        keyboard.extend([
            [InlineKeyboardButton(self._get_text("meridian_change_path", language), callback_data="meridian_path")],
            [InlineKeyboardButton(self._get_text("meridian_measurements", language), callback_data="meridian_measurements")],
            [InlineKeyboardButton(self._get_text("back_to_menu", language), callback_data="menu_main")]
        ])
        return InlineKeyboardMarkup(keyboard)

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
                    InlineKeyboardButton(self._get_text("meridian_point_help", language), callback_data="meridian_point_help")
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
                InlineKeyboardButton(self._get_text("meridian_point_help", language), callback_data="meridian_point_help")
            ],
        ])
        if point_index is not None and points_count is not None and point_index >= points_count - 1:
            keyboard.append([InlineKeyboardButton(self._get_text("complete_meridian", language), callback_data="meridian_complete")])
        keyboard.append([InlineKeyboardButton(self._get_text("meridian_back", language), callback_data="meridian_main")])
        return InlineKeyboardMarkup(keyboard)

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
                    callback_data=f"meridian_point:{index}"
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
                keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
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

            await query.answer()
            if not user or not user.is_active:
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
                if CUN_MEASUREMENT_IMAGE_PATH.exists():
                    try:
                        with open(CUN_MEASUREMENT_IMAGE_PATH, "rb") as photo:
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
                        self._create_meridian_practice_keyboard(language, at_intro=True),
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
                    self._create_meridian_practice_keyboard(language, at_intro=True),
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
                    self._create_meridian_practice_keyboard(language, point_index=user.current_point_index, points_count=len(points)),
                    language,
                    meridian.get("id"),
                    point_code
                )
                return

            if action == "complete":
                if points and user.current_point_index < len(points) - 1:
                    user.current_point_index = max(0, user.current_point_index)
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

                if user.current_meridian_id and user.current_meridian_id not in user.completed_meridians:
                    user.completed_meridians.append(user.current_meridian_id)

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
                    keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)

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
                    keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)

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
            keyboard = self._create_main_menu_keyboard_for_user(chat_id, language)
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
