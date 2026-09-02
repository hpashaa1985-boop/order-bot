import asyncio
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import (
    BotCommand,
    BotCommandScopeChat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_USERNAME = "Tuffc1k"

# Реквизиты для оплаты картой
PAYMENT_CARD = os.environ.get("PAYMENT_CARD", "УКАЖИТЕ_НОМЕР_КАРТЫ")
PAYMENT_CARD_NAME = os.environ.get("PAYMENT_CARD_NAME", "")
PAYMENT_CARD_BANK = os.environ.get("PAYMENT_CARD_BANK", "")
PAYMENT_COMMENT_HINT = os.environ.get(
    "PAYMENT_COMMENT_HINT",
    "В комментарии к переводу укажите ваш @username",
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Хранилище (в памяти) ───
ADMIN_ID_STORAGE = {"admin": None}
BLOCKED_USERS = set()
ACTIVE_CHATS = set()
USER_LANG = {}
ADMIN_REPLY_TARGET = {}
LAST_ORDER_TOTAL = {}
PENDING_PAY_INPUT = {}
PENDING_PAYMENTS = {}

# ─── Состояния ───
(
    STEP_LANG,
    STEP_PREPAY_INFO,
    STEP_BOT_TYPE,
    STEP_MENU,
    STEP_PAYMENTS,
    STEP_DATABASE,
    STEP_ADMIN_PANEL,
    STEP_CONFIRM,
    STEP_FIX_SELECT,
    STEP_DESCRIPTION,
) = range(10)

# ─── Переводы ───
TEXTS = {
    "ru": {
        "lang_name": "🇷🇺 Русский",
        "choose_lang": "🌐 Выберите язык / Choose language / Оберіть мову:",
        "prepay_info": (
            "⚠️ <b>Важная информация о работе</b>\n\n"
            "🔹 Работа производится <b>только по предоплате</b>.\n"
            "🔹 Без предоплаты заказ в работу не берётся.\n"
            "🔹 Вы всегда можете <b>потребовать предоплату назад</b>, "
            "если разработка ещё не начата или вас что-то не устраивает.\n\n"
            "Нажмите «Продолжить», чтобы оформить заказ."
        ),
        "btn_prepay_continue": "▶️ Продолжить",
        "btn_prepay_cancel": "❌ Отмена",
        "hello_admin": (
            "👑 Привет, админ!\n\n"
            "Внизу — быстрое меню.\n"
            "Команды:\n"
            "/reply ID текст — ответить\n"
            "/pay ID сумма — запросить оплату\n"
            "/block ID, /unblock ID, /blocked\n"
            "/end ID — завершить чат\n"
            "/stopreply — перестать отвечать"
        ),
        "your_order": "📝 <b>Ваш заказ:</b>",
        "total": "💰 <b>Итого:",
        "correct": "✅ Всё верно?",
        "btn_continue": "✅ Продолжить",
        "btn_fix": "✏️ Исправить",
        "btn_cancel": "❌ Отмена (сбросит все выборы)",
        "cancelled": "❌ Все выбранные действия отменены.\nЗаново: /start",
        "fix_what": "✏️ Что исправить?",
        "fix_item": "Исправляем пункт",
        "write_desc": "✍️ Напишите подробное описание бота (ТЗ).\nПосле отправки ждите ответа здесь, в боте.",
        "order_sent": "✅ <b>Заказ отправлен!</b>",
        "description": "📝 <b>Описание:</b>",
        "auto_wait": (
            "🕐 <b>Спасибо за заказ!</b>\n"
            "Ваша заявка получена. Ожидайте ответа разработчика. "
            "Можете писать сюда дополнения — они дойдут до разработчика."
        ),
        "btn_pay": "💳 Оплатить",
        "btn_i_paid": "✅ Я оплатил",
        "pay_details": (
            "💳 <b>Оплата по карте</b>\n\n"
            "Сумма к оплате: <b>{amount}₴</b>\n\n"
            "🏦 Банк: <b>{bank}</b>\n"
            "👤 Получатель: <b>{name}</b>\n"
            "💳 Карта:\n<code>{card}</code>\n\n"
            "📌 {hint}\n\n"
            "1) Скопируйте номер карты\n"
            "2) Переведите точную сумму <b>{amount}₴</b>\n"
            "3) Нажмите «✅ Я оплатил»"
        ),
        "pay_request_client": (
            "💳 <b>Разработчик выставил счёт</b>\n"
            "Сумма: <b>{amount}₴</b>\n\n"
            "Нажмите «Оплатить», чтобы получить номер карты."
        ),
        "i_paid_client": (
            "✅ Заявка об оплате отправлена разработчику.\n"
            "Ожидайте подтверждения."
        ),
        "i_paid_admin": (
            "💰 <b>Клиент сообщает об оплате</b>\n"
            "Клиент: @{username}\n"
            "ID: <code>{uid}</code>\n"
            "Сумма: <b>{amount}₴</b>\n\n"
            "Проверьте поступление и подтвердите."
        ),
        "pay_confirmed_client": "✅ <b>Оплата подтверждена!</b>\nСпасибо, разработчик скоро продолжит работу.",
        "sent_to_dev": "📨 Отправлено разработчику",
        "blocked_msg": "🚫 Вы заблокированы разработчиком.",
        "chat_ended_client": "🔒 Разработчик завершил чат. Для нового обращения — /start",
        "order_rejected_client": "❌ К сожалению, ваш заказ был отменён разработчиком.\nДля нового обращения — /start",
        "kb_new_order": "🆕 Новый заказ",
        "kb_change_lang": "🌐 Сменить язык",
        "kb_help": "ℹ️ Помощь",
        "help_text": (
            "Бот для заказа Telegram-ботов.\n"
            "• 🆕 Новый заказ\n"
            "• 🌐 Сменить язык\n"
            "• Напишите сообщение — оно уйдёт разработчику\n\n"
            "⚠️ Работа только по предоплате."
        ),
        "questions": [
            "🤖 Тип бота",
            "📋 Тип меню",
            "💳 Оплата в вашем боте",
            "🗄 База данных",
            "🔧 Админ-панель",
        ],
        "tip": "<i>Нажмите кнопку с номером варианта ⬇️</i>",
    },
    "en": {
        "lang_name": "🇬🇧 English",
        "choose_lang": "🌐 Выберите язык / Choose language / Оберіть мову:",
        "prepay_info": (
            "⚠️ <b>Important</b>\n\n"
            "🔹 Work is done <b>only after prepayment</b>.\n"
            "🔹 Without prepayment the order is not taken.\n"
            "🔹 You can always <b>request a refund</b> if work has not started.\n\n"
            "Press Continue to place an order."
        ),
        "btn_prepay_continue": "▶️ Continue",
        "btn_prepay_cancel": "❌ Cancel",
        "hello_admin": "👑 Hi, admin!",
        "your_order": "📝 <b>Your order:</b>",
        "total": "💰 <b>Total:",
        "correct": "✅ Is everything correct?",
        "btn_continue": "✅ Continue",
        "btn_fix": "✏️ Edit",
        "btn_cancel": "❌ Cancel (reset all)",
        "cancelled": "❌ Cancelled.\nStart again: /start",
        "fix_what": "✏️ What to edit?",
        "fix_item": "Editing item",
        "write_desc": "✍️ Write a detailed bot description.",
        "order_sent": "✅ <b>Order sent!</b>",
        "description": "📝 <b>Description:</b>",
        "auto_wait": "🕐 <b>Thanks!</b>\nWait for the developer reply.",
        "btn_pay": "💳 Pay",
        "btn_i_paid": "✅ I paid",
        "pay_details": (
            "💳 <b>Card payment</b>\n\n"
            "Amount: <b>{amount}₴</b>\n\n"
            "🏦 Bank: <b>{bank}</b>\n"
            "👤 Name: <b>{name}</b>\n"
            "💳 Card:\n<code>{card}</code>\n\n"
            "📌 {hint}\n\n"
            "1) Copy the card number\n"
            "2) Transfer exactly <b>{amount}₴</b>\n"
            "3) Press «✅ I paid»"
        ),
        "pay_request_client": (
            "💳 <b>Developer issued an invoice</b>\n"
            "Amount: <b>{amount}₴</b>\n\n"
            "Press Pay to get the card number."
        ),
        "i_paid_client": "✅ Payment report sent. Please wait for confirmation.",
        "i_paid_admin": (
            "💰 <b>Client says they paid</b>\n"
            "Client: @{username}\nID: <code>{uid}</code>\nAmount: <b>{amount}₴</b>"
        ),
        "pay_confirmed_client": "✅ <b>Payment confirmed!</b>\nThank you!",
        "sent_to_dev": "📨 Sent to developer",
        "blocked_msg": "🚫 You are blocked.",
        "chat_ended_client": "🔒 Chat ended. /start for a new request",
        "order_rejected_client": "❌ Your order was cancelled.\n/start for a new one",
        "kb_new_order": "🆕 New order",
        "kb_change_lang": "🌐 Change language",
        "kb_help": "ℹ️ Help",
        "help_text": "Order Telegram bots here. Prepayment only.",
        "questions": [
            "🤖 Bot type",
            "📋 Menu type",
            "💳 Payments in your bot",
            "🗄 Database",
            "🔧 Admin panel",
        ],
        "tip": "<i>Tap the button with the option number ⬇️</i>",
    },
    "uk": {
        "lang_name": "🇺🇦 Українська",
        "choose_lang": "🌐 Виберіть мову / Choose language / Выберите язык:",
        "prepay_info": (
            "⚠️ <b>Важлива інформація</b>\n\n"
            "🔹 Робота лише <b>за передоплатою</b>.\n"
            "🔹 Без передоплати замовлення не береться.\n"
            "🔹 Ви завжди можете <b>вимагати передоплату назад</b>, якщо роботу ще не почато.\n\n"
            "Натисніть «Продовжити»."
        ),
        "btn_prepay_continue": "▶️ Продовжити",
        "btn_prepay_cancel": "❌ Скасувати",
        "hello_admin": "👑 Привіт, адмін!",
        "your_order": "📝 <b>Ваше замовлення:</b>",
        "total": "💰 <b>Разом:",
        "correct": "✅ Все вірно?",
        "btn_continue": "✅ Продовжити",
        "btn_fix": "✏️ Виправити",
        "btn_cancel": "❌ Скасувати",
        "cancelled": "❌ Скасовано.\nЗаново: /start",
        "fix_what": "✏️ Що виправити?",
        "fix_item": "Виправляємо пункт",
        "write_desc": "✍️ Напишіть детальний опис бота.",
        "order_sent": "✅ <b>Замовлення відправлено!</b>",
        "description": "📝 <b>Опис:</b>",
        "auto_wait": "🕐 <b>Дякуємо!</b>\nОчікуйте відповіді розробника.",
        "btn_pay": "💳 Оплатити",
        "btn_i_paid": "✅ Я оплатив",
        "pay_details": (
            "💳 <b>Оплата на картку</b>\n\n"
            "Сума: <b>{amount}₴</b>\n\n"
            "🏦 Банк: <b>{bank}</b>\n"
            "👤 Отримувач: <b>{name}</b>\n"
            "💳 Картка:\n<code>{card}</code>\n\n"
            "📌 {hint}\n\n"
            "1) Скопіюйте номер картки\n"
            "2) Перекажіть рівно <b>{amount}₴</b>\n"
            "3) Натисніть «✅ Я оплатив»"
        ),
        "pay_request_client": (
            "💳 <b>Розробник виставив рахунок</b>\n"
            "Сума: <b>{amount}₴</b>\n\n"
            "Натисніть «Оплатити», щоб отримати номер картки."
        ),
        "i_paid_client": "✅ Заявку про оплату надіслано. Чекайте підтвердження.",
        "i_paid_admin": (
            "💰 <b>Клієнт повідомляє про оплату</b>\n"
            "Клієнт: @{username}\nID: <code>{uid}</code>\nСума: <b>{amount}₴</b>"
        ),
        "pay_confirmed_client": "✅ <b>Оплату підтверджено!</b>\nДякуємо!",
        "sent_to_dev": "📨 Відправлено розробнику",
        "blocked_msg": "🚫 Вас заблоковано.",
        "chat_ended_client": "🔒 Чат завершено. /start — нове звернення",
        "order_rejected_client": "❌ Замовлення скасовано.\n/start — нове",
        "kb_new_order": "🆕 Нове замовлення",
        "kb_change_lang": "🌐 Змінити мову",
        "kb_help": "ℹ️ Допомога",
        "help_text": "Бот для замовлення Telegram-ботів. Лише передоплата.",
        "questions": [
            "🤖 Тип бота",
            "📋 Тип меню",
            "💳 Оплата у вашому боті",
            "🗄 База даних",
            "🔧 Адмін-панель",
        ],
        "tip": "<i>Натисніть кнопку з номером варіанта ⬇️</i>",
    },
}

# ─── Варианты с понятными описаниями ───
BOT_TYPES = {
    "simple": {
        "ru": "Простой бот", "en": "Simple bot", "uk": "Простий бот",
        "desc_ru": "обычные команды и ответы, без мини-сайта внутри Telegram",
        "desc_en": "normal commands and replies, no mini-app inside Telegram",
        "desc_uk": "звичайні команди і відповіді, без міні-сайту в Telegram",
        "price": 100,
    },
    "webapp": {
        "ru": "Бот с WebApp", "en": "Bot with WebApp", "uk": "Бот з WebApp",
        "desc_ru": "открывается мини-сайт внутри Telegram (каталог, форма, игра)",
        "desc_en": "opens a mini-website inside Telegram (catalog, form, game)",
        "desc_uk": "відкривається міні-сайт у Telegram (каталог, форма, гра)",
        "price": 400,
    },
    "inline": {
        "ru": "Бот с инлайн-режимом", "en": "Inline-mode bot", "uk": "Бот з інлайн-режимом",
        "desc_ru": "можно вызывать через @имя_бота в любом чате",
        "desc_en": "can be used via @bot_name in any chat",
        "desc_uk": "можна викликати через @імʼя_бота в будь-якому чаті",
        "price": 200,
    },
}

MENU_OPTIONS = {
    "no_menu": {
        "ru": "Без меню", "en": "No menu", "uk": "Без меню",
        "desc_ru": "пользователь пишет команды вручную, кнопок почти нет",
        "desc_en": "user types commands manually, almost no buttons",
        "desc_uk": "користувач пише команди вручну, кнопок майже немає",
        "price": 0,
    },
    "reply_menu": {
        "ru": "Reply-меню", "en": "Reply menu", "uk": "Reply-меню",
        "desc_ru": "кнопки внизу экрана, как обычная клавиатура телефона",
        "desc_en": "buttons at the bottom, like a phone keyboard",
        "desc_uk": "кнопки внизу екрана, як звичайна клавіатура",
        "price": 40,
    },
    "inline_menu": {
        "ru": "Inline-меню", "en": "Inline menu", "uk": "Inline-меню",
        "desc_ru": "кнопки прямо под сообщениями бота",
        "desc_en": "buttons right under the bot messages",
        "desc_uk": "кнопки прямо під повідомленнями бота",
        "price": 60,
    },
    "both_menu": {
        "ru": "Оба типа", "en": "Both types", "uk": "Обидва типи",
        "desc_ru": "и клавиатура внизу, и кнопки под сообщениями",
        "desc_en": "both bottom keyboard and buttons under messages",
        "desc_uk": "і клавіатура внизу, і кнопки під повідомленнями",
        "price": 80,
    },
}

PAYMENT_OPTIONS = {
    "no_pay": {
        "ru": "Без оплаты", "en": "No payments", "uk": "Без оплати",
        "desc_ru": "в боте нельзя ничего купить/оплатить",
        "desc_en": "users cannot pay for anything inside the bot",
        "desc_uk": "у боті неможна нічого купити/оплатити",
        "price": 0,
    },
    "stars_pay": {
        "ru": "Telegram Stars", "en": "Telegram Stars", "uk": "Telegram Stars",
        "desc_ru": "оплата звёздами Telegram прямо в мессенджере",
        "desc_en": "pay with Telegram Stars inside the messenger",
        "desc_uk": "оплата зірками Telegram прямо в месенджері",
        "price": 100,
    },
    "external_pay": {
        "ru": "Внешняя оплата", "en": "External payments", "uk": "Зовнішня оплата",
        "desc_ru": "оплата картой/реквизитами (гривны, банк)",
        "desc_en": "card/bank payment (real money)",
        "desc_uk": "оплата карткою/реквізитами (гривні, банк)",
        "price": 200,
    },
}

DATABASE_OPTIONS = {
    "no_db": {
        "ru": "Без БД", "en": "No DB", "uk": "Без БД",
        "desc_ru": "бот ничего не запоминает после перезапуска",
        "desc_en": "bot forgets data after restart",
        "desc_uk": "бот нічого не памʼятає після перезапуску",
        "price": 0,
    },
    "sqlite": {
        "ru": "SQLite", "en": "SQLite", "uk": "SQLite",
        "desc_ru": "простая база: пользователи, заказы, небольшие данные",
        "desc_en": "simple database: users, orders, small data",
        "desc_uk": "проста база: користувачі, замовлення, невеликі дані",
        "price": 60,
    },
    "postgres": {
        "ru": "PostgreSQL", "en": "PostgreSQL", "uk": "PostgreSQL",
        "desc_ru": "большая надёжная база для серьёзного проекта",
        "desc_en": "large reliable database for serious projects",
        "desc_uk": "велика надійна база для серйозного проєкту",
        "price": 140,
    },
}

ADMIN_PANEL_OPTIONS = {
    "no_admin": {
        "ru": "Без админки", "en": "No admin", "uk": "Без адмінки",
        "desc_ru": "управлять ботом можно только через код/разработчика",
        "desc_en": "manage only via code/developer",
        "desc_uk": "керувати ботом лише через код/розробника",
        "price": 0,
    },
    "basic_admin": {
        "ru": "Базовая админка", "en": "Basic admin", "uk": "Базова адмінка",
        "desc_ru": "простые команды админа: статистика, рассылка",
        "desc_en": "simple admin tools: stats, broadcast",
        "desc_uk": "прості команди адміна: статистика, розсилка",
        "price": 100,
    },
    "advanced_admin": {
        "ru": "Расширенная админка", "en": "Advanced admin", "uk": "Розширена адмінка",
        "desc_ru": "удобное управление: пользователи, контент, настройки",
        "desc_en": "full control: users, content, settings",
        "desc_uk": "зручне керування: користувачі, контент, налаштування",
        "price": 200,
    },
}

STEP_KEYS = ["bot_type", "menu", "payments", "database", "admin_panel"]
STEP_OPTIONS = [BOT_TYPES, MENU_OPTIONS, PAYMENT_OPTIONS, DATABASE_OPTIONS, ADMIN_PANEL_OPTIONS]

NUM_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


# ─── Health check ───
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()
    def log_message(self, *a):
        return


def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), HealthCheckHandler).serve_forever()


# ─── Утилиты ───
def is_admin(user) -> bool:
    return bool(user and user.username and user.username.lower() == ADMIN_USERNAME.lower())


def get_lang(context, user_id=None) -> str:
    if user_id and user_id in USER_LANG:
        return USER_LANG[user_id]
    return context.user_data.get("lang", "ru")


def lang_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(TEXTS["ru"]["lang_name"], callback_data="lang_ru")],
        [InlineKeyboardButton(TEXTS["en"]["lang_name"], callback_data="lang_en")],
        [InlineKeyboardButton(TEXTS["uk"]["lang_name"], callback_data="lang_uk")],
    ])


def prepay_keyboard(lang: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(TEXTS[lang]["btn_prepay_continue"], callback_data="prepay_ok")],
        [InlineKeyboardButton(TEXTS[lang]["btn_prepay_cancel"], callback_data="prepay_cancel")],
    ])


def get_step_keyboard(step_index: int, lang: str) -> InlineKeyboardMarkup:
    options = STEP_OPTIONS[step_index]
    buttons = []
    for i, (k, v) in enumerate(options.items(), start=1):
        buttons.append([
            InlineKeyboardButton(
                f"{i}. {v[lang]} — {v['price']}₴",
                callback_data=f"choice_{step_index}_{k}",
            )
        ])
    return InlineKeyboardMarkup(buttons)


def get_step_text(step_index: int, lang: str) -> str:
    """Вопрос + понятное описание рядом с каждым вариантом."""
    header = TEXTS[lang]["questions"][step_index]
    options = STEP_OPTIONS[step_index]
    desc_key = f"desc_{lang}"

    lines = [f"<b>Шаг {step_index + 1}/5 — {header}</b>\n"]
    for i, v in enumerate(options.values(), start=1):
        emoji = NUM_EMOJI[i - 1]
        lines.append(
            f"{emoji} <b>{v[lang]} — {v['price']}₴</b>\n"
            f"    └ {v[desc_key]}\n"
        )
    lines.append(TEXTS[lang]["tip"])
    return "\n".join(lines)


def build_summary(user_data: dict, lang: str):
    total = 0
    lines = [TEXTS[lang]["your_order"] + "\n"]
    for i, key in enumerate(STEP_KEYS):
        val = user_data.get(key)
        opts = STEP_OPTIONS[i]
        if val in opts:
            lines.append(f" {i + 1}. {opts[val][lang]} — {opts[val]['price']}₴")
            total += opts[val]["price"]
    lines.append(f"\n{TEXTS[lang]['total']} {total}₴</b>")
    return "\n".join(lines), total


def confirm_keyboard(lang: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(TEXTS[lang]["btn_continue"], callback_data="confirm_continue")],
        [InlineKeyboardButton(TEXTS[lang]["btn_fix"], callback_data="confirm_fix")],
        [InlineKeyboardButton(TEXTS[lang]["btn_cancel"], callback_data="confirm_cancel")],
    ])


def admin_order_keyboard(client_id: int, is_blocked: bool = False):
    rows = [
        [
            InlineKeyboardButton("💬 Ответить", callback_data=f"reply_{client_id}"),
            InlineKeyboardButton("💰 Потребовать оплату", callback_data=f"askpay_{client_id}"),
        ],
        [
            InlineKeyboardButton("🔒 Завершить чат", callback_data=f"endchat_{client_id}"),
            InlineKeyboardButton("❌ Отклонить заказ", callback_data=f"reject_{client_id}"),
        ],
    ]
    if is_blocked:
        rows.append([InlineKeyboardButton("✅ Разблокировать", callback_data=f"unblock_{client_id}")])
    else:
        rows.append([InlineKeyboardButton("🚫 Заблокировать", callback_data=f"block_{client_id}")])
    return InlineKeyboardMarkup(rows)


def pay_offer_keyboard(lang: str, amount: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(TEXTS[lang]["btn_pay"], callback_data=f"pay_{amount}")]
    ])


def pay_details_keyboard(lang: str, amount: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(TEXTS[lang]["btn_i_paid"], callback_data=f"ipaid_{amount}")],
    ])


def admin_confirm_pay_keyboard(client_id: int, amount: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"confirmpay_{client_id}_{amount}")],
        [InlineKeyboardButton("💬 Ответить", callback_data=f"reply_{client_id}")],
    ])


def client_reply_kb(lang: str):
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(TEXTS[lang]["kb_new_order"])],
            [KeyboardButton(TEXTS[lang]["kb_change_lang"]), KeyboardButton(TEXTS[lang]["kb_help"])],
        ],
        resize_keyboard=True,
    )


def admin_reply_kb():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🚫 Заблокированные"), KeyboardButton("❌ Стоп-ответ")],
            [KeyboardButton("ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


def format_pay_details(lang: str, amount: int) -> str:
    return TEXTS[lang]["pay_details"].format(
        amount=amount,
        bank=PAYMENT_CARD_BANK or "—",
        name=PAYMENT_CARD_NAME or "—",
        card=PAYMENT_CARD,
        hint=PAYMENT_COMMENT_HINT,
    )


async def set_admin_commands(app: Application, admin_id: int):
    cmds = [
        BotCommand("start", "Меню"),
        BotCommand("reply", "Ответ: /reply ID текст"),
        BotCommand("pay", "Счёт: /pay ID сумма"),
        BotCommand("block", "Бан: /block ID"),
        BotCommand("unblock", "Разбан: /unblock ID"),
        BotCommand("blocked", "Список банов"),
        BotCommand("end", "Закрыть чат: /end ID"),
        BotCommand("stopreply", "Стоп ответ"),
    ]
    try:
        await app.bot.set_my_commands(cmds, scope=BotCommandScopeChat(chat_id=admin_id))
    except Exception as e:
        logger.error("set_admin_commands: %s", e)


async def send_pay_request(context, client_id: int, amount: int):
    lang = USER_LANG.get(client_id, "ru")
    LAST_ORDER_TOTAL[client_id] = amount
    PENDING_PAYMENTS[client_id] = amount
    await context.bot.send_message(
        client_id,
        TEXTS[lang]["pay_request_client"].format(amount=amount),
        parse_mode="HTML",
        reply_markup=pay_offer_keyboard(lang, amount),
    )


# ─── Клиентские handlers ───
async def start(update: Update, context):
    user = update.effective_user
    if is_admin(user):
        ADMIN_ID_STORAGE["admin"] = user.id
        await set_admin_commands(context.application, user.id)
        await update.message.reply_text(TEXTS["ru"]["hello_admin"], reply_markup=admin_reply_kb())
        return ConversationHandler.END
    if user.id in BLOCKED_USERS:
        await update.message.reply_text(TEXTS[get_lang(context, user.id)]["blocked_msg"])
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text(TEXTS["ru"]["choose_lang"], reply_markup=lang_keyboard())
    return STEP_LANG


async def handle_lang(update: Update, context):
    query = update.callback_query
    await query.answer()
    lang = query.data.split("_")[1]
    context.user_data["lang"] = lang
    USER_LANG[query.from_user.id] = lang
    await query.edit_message_text(
        TEXTS[lang]["prepay_info"],
        reply_markup=prepay_keyboard(lang),
        parse_mode="HTML",
    )
    await context.bot.send_message(query.message.chat_id, "👇", reply_markup=client_reply_kb(lang))
    return STEP_PREPAY_INFO


async def handle_prepay(update: Update, context):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    if query.data == "prepay_cancel":
        context.user_data.clear()
        await query.edit_message_text(TEXTS[lang]["cancelled"])
        return ConversationHandler.END
    await query.edit_message_text(
        get_step_text(0, lang),
        reply_markup=get_step_keyboard(0, lang),
        parse_mode="HTML",
    )
    return STEP_BOT_TYPE


async def handle_choice(update: Update, context):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    parts = query.data.split("_", 2)
    step = int(parts[1])
    context.user_data[STEP_KEYS[step]] = parts[2]
    if step + 1 < len(STEP_KEYS):
        await query.edit_message_text(
            get_step_text(step + 1, lang),
            reply_markup=get_step_keyboard(step + 1, lang),
            parse_mode="HTML",
        )
        return STEP_BOT_TYPE + step + 1
    summary, _ = build_summary(context.user_data, lang)
    await query.edit_message_text(
        summary + "\n\n" + TEXTS[lang]["correct"],
        reply_markup=confirm_keyboard(lang),
        parse_mode="HTML",
    )
    return STEP_CONFIRM


async def handle_confirm(update: Update, context):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    if query.data == "confirm_continue":
        await query.edit_message_text(TEXTS[lang]["write_desc"])
        return STEP_DESCRIPTION
    if query.data == "confirm_fix":
        btns = [[InlineKeyboardButton(f"{i + 1}. {TEXTS[lang]['questions'][i]}", callback_data=f"fix_{i}")]
                for i in range(len(STEP_KEYS))]
        await query.edit_message_text(TEXTS[lang]["fix_what"], reply_markup=InlineKeyboardMarkup(btns))
        return STEP_FIX_SELECT
    context.user_data.clear()
    await query.edit_message_text(TEXTS[lang]["cancelled"])
    return ConversationHandler.END


async def handle_fix_select(update: Update, context):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    step = int(query.data.split("_")[1])
    await query.edit_message_text(
        f"{TEXTS[lang]['fix_item']} {step + 1}:\n\n" + get_step_text(step, lang),
        reply_markup=get_step_keyboard(step, lang),
        parse_mode="HTML",
    )
    return STEP_FIX_SELECT


async def handle_fix_choice(update: Update, context):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    parts = query.data.split("_", 2)
    step = int(parts[1])
    context.user_data[STEP_KEYS[step]] = parts[2]
    summary, _ = build_summary(context.user_data, lang)
    await query.edit_message_text(
        summary + "\n\n" + TEXTS[lang]["correct"],
        reply_markup=confirm_keyboard(lang),
        parse_mode="HTML",
    )
    return STEP_CONFIRM


async def handle_description(update: Update, context):
    user = update.effective_user
    if user.id in BLOCKED_USERS:
        return ConversationHandler.END
    desc = update.message.text
    lang = get_lang(context)
    summary, total = build_summary(context.user_data, lang)
    LAST_ORDER_TOTAL[user.id] = total
    PENDING_PAYMENTS[user.id] = total

    await update.message.reply_text(
        f"{TEXTS[lang]['order_sent']}\n\n{summary}\n\n{TEXTS[lang]['description']}\n{desc}",
        parse_mode="HTML",
        reply_markup=pay_offer_keyboard(lang, total),
    )
    await update.message.reply_text(
        TEXTS[lang]["auto_wait"], parse_mode="HTML", reply_markup=client_reply_kb(lang)
    )
    ACTIVE_CHATS.add(user.id)

    admin_id = ADMIN_ID_STORAGE.get("admin")
    if admin_id:
        try:
            await context.bot.send_message(
                admin_id,
                f"🔔 <b>НОВЫЙ ЗАКАЗ!</b>\n"
                f"🌐 {TEXTS[lang]['lang_name']}\n"
                f"Клиент: @{user.username or 'нет'}\n"
                f"ID: <code>{user.id}</code>\n\n{summary}\n\n📝 ТЗ: {desc}",
                parse_mode="HTML",
                reply_markup=admin_order_keyboard(user.id, user.id in BLOCKED_USERS),
            )
        except Exception as e:
            logger.error("admin notify: %s", e)
    return ConversationHandler.END


# ─── Оплата картой ───
async def handle_pay(update: Update, context):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context, query.from_user.id)
    amount = int(query.data.split("_")[1])
    PENDING_PAYMENTS[query.from_user.id] = amount
    await query.message.reply_text(
        format_pay_details(lang, amount),
        parse_mode="HTML",
        reply_markup=pay_details_keyboard(lang, amount),
    )


async def handle_i_paid(update: Update, context):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    lang = get_lang(context, user.id)
    amount = int(query.data.split("_")[1])
    PENDING_PAYMENTS[user.id] = amount

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await query.message.reply_text(TEXTS[lang]["i_paid_client"])

    admin_id = ADMIN_ID_STORAGE.get("admin")
    if admin_id:
        try:
            await context.bot.send_message(
                admin_id,
                TEXTS["ru"]["i_paid_admin"].format(
                    username=user.username or "нет",
                    uid=user.id,
                    amount=amount,
                ),
                parse_mode="HTML",
                reply_markup=admin_confirm_pay_keyboard(user.id, amount),
            )
        except Exception as e:
            logger.error("i_paid admin: %s", e)


async def handle_confirm_pay(update: Update, context):
    query = update.callback_query
    if not is_admin(query.from_user):
        await query.answer("Нет доступа", show_alert=True)
        return
    parts = query.data.split("_")
    client_id = int(parts[1])
    amount = int(parts[2])
    lang = USER_LANG.get(client_id, "ru")
    try:
        await context.bot.send_message(client_id, TEXTS[lang]["pay_confirmed_client"], parse_mode="HTML")
    except Exception as e:
        logger.error(e)
    await query.answer("Оплата подтверждена")
    await query.message.reply_text(
        f"✅ Оплата <b>{amount}₴</b> от <code>{client_id}</code> подтверждена.",
        parse_mode="HTML",
    )


async def handle_admin_action(update: Update, context):
    query = update.callback_query
    user = query.from_user
    if not is_admin(user):
        await query.answer("Нет доступа", show_alert=True)
        return

    action, rest = query.data.split("_", 1)
    client_id = int(rest)
    client_lang = USER_LANG.get(client_id, "ru")

    if action == "reply":
        ADMIN_REPLY_TARGET[user.id] = client_id
        ACTIVE_CHATS.add(client_id)
        await query.answer()
        await query.message.reply_text(
            f"✍️ Ответ для <code>{client_id}</code>\nПишите сообщения. Стоп — «❌ Стоп-ответ»",
            parse_mode="HTML",
        )
    elif action == "askpay":
        PENDING_PAY_INPUT[user.id] = client_id
        last = LAST_ORDER_TOTAL.get(client_id)
        hint = f"\nПоследняя сумма заказа: <b>{last}₴</b>" if last else ""
        await query.answer()
        await query.message.reply_text(
            f"💰 Сумма для <code>{client_id}</code> (числом):{hint}",
            parse_mode="HTML",
        )
    elif action == "reject":
        ACTIVE_CHATS.discard(client_id)
        ADMIN_REPLY_TARGET.pop(user.id, None)
        try:
            await context.bot.send_message(client_id, TEXTS[client_lang]["order_rejected_client"])
        except Exception:
            pass
        await query.answer("Отклонено")
        await query.message.reply_text(f"❌ Заказ <code>{client_id}</code> отклонён.", parse_mode="HTML")
    elif action == "endchat":
        ACTIVE_CHATS.discard(client_id)
        if ADMIN_REPLY_TARGET.get(user.id) == client_id:
            ADMIN_REPLY_TARGET.pop(user.id, None)
        try:
            await context.bot.send_message(client_id, TEXTS[client_lang]["chat_ended_client"])
        except Exception:
            pass
        await query.answer("Чат закрыт")
        await query.message.reply_text(f"🔒 Чат с <code>{client_id}</code> завершён.", parse_mode="HTML")
    elif action == "block":
        BLOCKED_USERS.add(client_id)
        ACTIVE_CHATS.discard(client_id)
        ADMIN_REPLY_TARGET.pop(user.id, None)
        await query.answer("Бан")
        await query.message.reply_text(f"🚫 <code>{client_id}</code> заблокирован.", parse_mode="HTML")
    elif action == "unblock":
        BLOCKED_USERS.discard(client_id)
        await query.answer("Разбан")
        await query.message.reply_text(f"✅ <code>{client_id}</code> разблокирован.", parse_mode="HTML")


# ─── Админские команды ───
async def admin_reply_cmd(update: Update, context):
    if not is_admin(update.effective_user):
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Формат: /reply ID текст")
        return
    try:
        target_id = int(context.args[0])
        text = " ".join(context.args[1:])
        await context.bot.send_message(target_id, text)
        ADMIN_REPLY_TARGET[update.effective_user.id] = target_id
        await update.message.reply_text(f"✅ Отправлено → <code>{target_id}</code>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def cmd_pay(update: Update, context):
    if not is_admin(update.effective_user):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Формат: /pay ID сумма")
        return
    try:
        target = int(context.args[0])
        amount = int(context.args[1])
        await send_pay_request(context, target, amount)
        await update.message.reply_text(f"✅ Счёт {amount}₴ → <code>{target}</code>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def cmd_stop_reply(update: Update, context):
    if not is_admin(update.effective_user):
        return
    t = ADMIN_REPLY_TARGET.pop(update.effective_user.id, None)
    await update.message.reply_text(f"✋ Стоп." + (f" Было: <code>{t}</code>" if t else ""), parse_mode="HTML")


async def cmd_block(update: Update, context):
    if not is_admin(update.effective_user) or not context.args:
        return
    uid = int(context.args[0])
    BLOCKED_USERS.add(uid)
    await update.message.reply_text(f"🚫 <code>{uid}</code>", parse_mode="HTML")


async def cmd_unblock(update: Update, context):
    if not is_admin(update.effective_user) or not context.args:
        return
    uid = int(context.args[0])
    BLOCKED_USERS.discard(uid)
    await update.message.reply_text(f"✅ <code>{uid}</code>", parse_mode="HTML")


async def cmd_blocked(update: Update, context):
    if not is_admin(update.effective_user):
        return
    if not BLOCKED_USERS:
        await update.message.reply_text("Пусто.")
        return
    await update.message.reply_text(
        "🚫 " + ", ".join(f"<code>{u}</code>" for u in BLOCKED_USERS), parse_mode="HTML"
    )


async def cmd_end(update: Update, context):
    if not is_admin(update.effective_user) or not context.args:
        return
    uid = int(context.args[0])
    ACTIVE_CHATS.discard(uid)
    ADMIN_REPLY_TARGET.pop(update.effective_user.id, None)
    try:
        await context.bot.send_message(uid, TEXTS[USER_LANG.get(uid, "ru")]["chat_ended_client"])
    except Exception:
        pass
    await update.message.reply_text(f"🔒 <code>{uid}</code>", parse_mode="HTML")


async def text_router(update: Update, context):
    user = update.effective_user
    text = update.message.text or ""

    if is_admin(user):
        if text == "🚫 Заблокированные":
            return await cmd_blocked(update, context)
        if text == "❌ Стоп-ответ":
            return await cmd_stop_reply(update, context)
        if text == "ℹ️ Помощь":
            await update.message.reply_text(TEXTS["ru"]["hello_admin"])
            return

        if user.id in PENDING_PAY_INPUT:
            target = PENDING_PAY_INPUT.pop(user.id)
            try:
                amount = int(text.strip())
                if amount <= 0:
                    raise ValueError()
                await send_pay_request(context, target, amount)
                await update.message.reply_text(
                    f"✅ Счёт <b>{amount}₴</b> → <code>{target}</code>", parse_mode="HTML"
                )
            except ValueError:
                PENDING_PAY_INPUT[user.id] = target
                await update.message.reply_text("Введите число, например 500")
            return

        target = ADMIN_REPLY_TARGET.get(user.id)
        if target:
            try:
                await context.bot.send_message(target, text)
                await update.message.reply_text(f"✅ → <code>{target}</code>", parse_mode="HTML")
            except Exception as e:
                await update.message.reply_text(f"❌ {e}")
            return

        await update.message.reply_text("Нажмите «💬 Ответить» под сообщением клиента")
        return

    if user.id in BLOCKED_USERS:
        return

    lang = get_lang(context, user.id)
    if text in (TEXTS["ru"]["kb_new_order"], TEXTS["en"]["kb_new_order"], TEXTS["uk"]["kb_new_order"]):
        return await start(update, context)
    if text in (TEXTS["ru"]["kb_change_lang"], TEXTS["en"]["kb_change_lang"], TEXTS["uk"]["kb_change_lang"]):
        await update.message.reply_text(TEXTS["ru"]["choose_lang"], reply_markup=lang_keyboard())
        return
    if text in (TEXTS["ru"]["kb_help"], TEXTS["en"]["kb_help"], TEXTS["uk"]["kb_help"]):
        await update.message.reply_text(TEXTS[lang]["help_text"], reply_markup=client_reply_kb(lang))
        return

    admin_id = ADMIN_ID_STORAGE.get("admin")
    if not admin_id:
        await update.message.reply_text(TEXTS[lang]["sent_to_dev"])
        return
    try:
        await context.bot.send_message(
            admin_id,
            f"💬 @{user.username or 'нет'} | <code>{user.id}</code>\n🌐 {TEXTS[lang]['lang_name']}\n\n{text}",
            parse_mode="HTML",
            reply_markup=admin_order_keyboard(user.id, user.id in BLOCKED_USERS),
        )
        await update.message.reply_text(TEXTS[lang]["sent_to_dev"], reply_markup=client_reply_kb(lang))
    except Exception as e:
        logger.error("relay: %s", e)


def main():
    if not TOKEN:
        raise SystemExit("BOT_TOKEN is not set")
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    threading.Thread(target=run_health_check, daemon=True).start()
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STEP_LANG: [CallbackQueryHandler(handle_lang, pattern=r"^lang_")],
            STEP_PREPAY_INFO: [CallbackQueryHandler(handle_prepay, pattern=r"^prepay_")],
            STEP_BOT_TYPE: [CallbackQueryHandler(handle_choice, pattern=r"^choice_")],
            STEP_MENU: [CallbackQueryHandler(handle_choice, pattern=r"^choice_")],
            STEP_PAYMENTS: [CallbackQueryHandler(handle_choice, pattern=r"^choice_")],
            STEP_DATABASE: [CallbackQueryHandler(handle_choice, pattern=r"^choice_")],
            STEP_ADMIN_PANEL: [CallbackQueryHandler(handle_choice, pattern=r"^choice_")],
            STEP_CONFIRM: [CallbackQueryHandler(handle_confirm, pattern=r"^confirm_")],
            STEP_FIX_SELECT: [
                CallbackQueryHandler(handle_fix_select, pattern=r"^fix_"),
                CallbackQueryHandler(handle_fix_choice, pattern=r"^choice_"),
            ],
            STEP_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("reply", admin_reply_cmd))
    app.add_handler(CommandHandler("pay", cmd_pay))
    app.add_handler(CommandHandler("stopreply", cmd_stop_reply))
    app.add_handler(CommandHandler("block", cmd_block))
    app.add_handler(CommandHandler("unblock", cmd_unblock))
    app.add_handler(CommandHandler("blocked", cmd_blocked))
    app.add_handler(CommandHandler("end", cmd_end))

    app.add_handler(CallbackQueryHandler(handle_pay, pattern=r"^pay_"))
    app.add_handler(CallbackQueryHandler(handle_i_paid, pattern=r"^ipaid_"))
    app.add_handler(CallbackQueryHandler(handle_confirm_pay, pattern=r"^confirmpay_"))
    app.add_handler(CallbackQueryHandler(
        handle_admin_action, pattern=r"^(reply|askpay|reject|endchat|block|unblock)_"
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
