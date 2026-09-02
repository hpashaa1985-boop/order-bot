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
    LabeledPrice,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_USERNAME = "Tuffc1k"
PAYMENT_PROVIDER_TOKEN = os.environ.get("PAYMENT_PROVIDER_TOKEN", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Хранилище (в памяти) ───
ADMIN_ID_STORAGE = {"admin": None}
BLOCKED_USERS = set()
ACTIVE_CHATS = set()          # клиенты, у которых идёт чат
USER_LANG = {}
ADMIN_REPLY_TARGET = {}       # admin_id -> client_id (кому сейчас отвечает админ)

# ─── Состояния диалога заказа ───
(
    STEP_LANG,
    STEP_BOT_TYPE,
    STEP_MENU,
    STEP_PAYMENTS,
    STEP_DATABASE,
    STEP_ADMIN_PANEL,
    STEP_CONFIRM,
    STEP_FIX_SELECT,
    STEP_DESCRIPTION,
) = range(9)

# ─── Переводы ───
TEXTS = {
    "ru": {
        "lang_name": "🇷🇺 Русский",
        "choose_lang": "🌐 Выберите язык / Choose language / Оберіть мову:",
        "hello_admin": (
            "👑 Привет, админ!\n\n"
            "Внизу — быстрое меню.\n"
            "Также команды:\n"
            "/reply ID текст — ответить\n"
            "/block ID, /unblock ID, /blocked\n"
            "/end ID — завершить чат\n"
            "/stopreply — перестать отвечать клиенту"
        ),
        "start_msg": "👋 Привет! Давайте оформим заказ на бота.\n\n<b>Шаг 1:</b>\n",
        "step": "Шаг",
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
        "auto_wait": "🕐 <b>Спасибо за заказ!</b>\nВаша заявка получена. Ожидайте ответа разработчика — обычно в течение нескольких часов. Можете писать сюда любые дополнения — они дойдут до разработчика.",
        "btn_pay": "💳 Оплатить заказ",
        "pay_title": "Оплата заказа бота",
        "pay_desc": "Оплата разработки Telegram-бота",
        "pay_label": "Заказ бота",
        "pay_success": "✅ Оплата прошла успешно! Спасибо!",
        "sent_to_dev": "📨 Отправлено разработчику",
        "blocked_msg": "🚫 Вы заблокированы разработчиком.",
        "chat_ended_client": "🔒 Разработчик завершил чат. Для нового обращения — /start",
        "order_rejected_client": "❌ К сожалению, ваш заказ был отменён разработчиком.\nДля нового обращения — /start",
        # быстрые кнопки клиента
        "kb_new_order": "🆕 Новый заказ",
        "kb_change_lang": "🌐 Сменить язык",
        "kb_help": "ℹ️ Помощь",
        "help_text": "Это бот для заказа Telegram-ботов.\n• 🆕 Новый заказ — оформить заказ\n• 🌐 Сменить язык — переключить язык\n• Просто напишите — сообщение уйдёт разработчику",
        "questions": [
            "🤖 Тип бота:",
            "📋 Тип меню:",
            "💳 Нужна оплата в вашем боте?",
            "🗄 Нужна база данных?",
            "🔧 Нужна админ-панель?",
        ],
    },
    "en": {
        "lang_name": "🇬🇧 English",
        "choose_lang": "🌐 Выберите язык / Choose language / Оберіть мову:",
        "hello_admin": "👑 Hi, admin!",
        "start_msg": "👋 Hi! Let's create a bot order.\n\n<b>Step 1:</b>\n",
        "step": "Step",
        "your_order": "📝 <b>Your order:</b>",
        "total": "💰 <b>Total:",
        "correct": "✅ Is everything correct?",
        "btn_continue": "✅ Continue",
        "btn_fix": "✏️ Edit",
        "btn_cancel": "❌ Cancel (reset all)",
        "cancelled": "❌ All actions cancelled.\nStart again: /start",
        "fix_what": "✏️ What to edit?",
        "fix_item": "Editing item",
        "write_desc": "✍️ Write a detailed bot description.\nWait for a reply here in the bot.",
        "order_sent": "✅ <b>Order sent!</b>",
        "description": "📝 <b>Description:</b>",
        "auto_wait": "🕐 <b>Thanks for your order!</b>\nYour request is received. Wait for the developer's reply — usually within a few hours. You can send additional messages here.",
        "btn_pay": "💳 Pay for order",
        "pay_title": "Bot order payment",
        "pay_desc": "Payment for Telegram bot development",
        "pay_label": "Bot order",
        "pay_success": "✅ Payment successful! Thank you!",
        "sent_to_dev": "📨 Sent to developer",
        "blocked_msg": "🚫 You are blocked by the developer.",
        "chat_ended_client": "🔒 Developer ended the chat. To start a new one — /start",
        "order_rejected_client": "❌ Unfortunately, your order has been cancelled by the developer.\nStart a new one — /start",
        "kb_new_order": "🆕 New order",
        "kb_change_lang": "🌐 Change language",
        "kb_help": "ℹ️ Help",
        "help_text": "This is a bot for ordering Telegram bots.\n• 🆕 New order — place order\n• 🌐 Change language\n• Just type — your message goes to developer",
        "questions": [
            "🤖 Bot type:",
            "📋 Menu type:",
            "💳 Payments in your bot?",
            "🗄 Need a database?",
            "🔧 Need an admin panel?",
        ],
    },
    "uk": {
        "lang_name": "🇺🇦 Українська",
        "choose_lang": "🌐 Виберіть мову / Choose language / Выберите язык:",
        "hello_admin": "👑 Привіт, адмін!",
        "start_msg": "👋 Привіт! Оформимо замовлення на бота.\n\n<b>Крок 1:</b>\n",
        "step": "Крок",
        "your_order": "📝 <b>Ваше замовлення:</b>",
        "total": "💰 <b>Разом:",
        "correct": "✅ Все вірно?",
        "btn_continue": "✅ Продовжити",
        "btn_fix": "✏️ Виправити",
        "btn_cancel": "❌ Скасувати (скине всі вибори)",
        "cancelled": "❌ Всі дії скасовано.\nЗаново: /start",
        "fix_what": "✏️ Що виправити?",
        "fix_item": "Виправляємо пункт",
        "write_desc": "✍️ Напишіть детальний опис бота.\nОчікуйте відповіді тут, у боті.",
        "order_sent": "✅ <b>Замовлення відправлено!</b>",
        "description": "📝 <b>Опис:</b>",
        "auto_wait": "🕐 <b>Дякуємо за замовлення!</b>\nВашу заявку отримано. Очікуйте відповіді розробника — зазвичай протягом кількох годин. Можете надсилати сюди будь-які доповнення.",
        "btn_pay": "💳 Оплатити замовлення",
        "pay_title": "Оплата замовлення бота",
        "pay_desc": "Оплата розробки Telegram-бота",
        "pay_label": "Замовлення бота",
        "pay_success": "✅ Оплата пройшла успішно! Дякуємо!",
        "sent_to_dev": "📨 Відправлено розробнику",
        "blocked_msg": "🚫 Вас заблокував розробник.",
        "chat_ended_client": "🔒 Розробник завершив чат. Для нового звернення — /start",
        "order_rejected_client": "❌ На жаль, ваше замовлення було скасовано розробником.\nДля нового звернення — /start",
        "kb_new_order": "🆕 Нове замовлення",
        "kb_change_lang": "🌐 Змінити мову",
        "kb_help": "ℹ️ Допомога",
        "help_text": "Це бот для замовлення Telegram-ботів.\n• 🆕 Нове замовлення\n• 🌐 Змінити мову\n• Просто напишіть — повідомлення піде розробнику",
        "questions": [
            "🤖 Тип бота:",
            "📋 Тип меню:",
            "💳 Чи потрібна оплата у вашому боті?",
            "🗄 Чи потрібна база даних?",
            "🔧 Чи потрібна адмін-панель?",
        ],
    },
}

# ─── Варианты с описанием ───
BOT_TYPES = {
    "simple":  {"ru": "Простой бот",         "en": "Simple bot",        "uk": "Простий бот",
                "desc_ru": "Обычный бот с командами (без визуальных приложений)",
                "desc_en": "Regular command-based bot (no visual apps)",
                "desc_uk": "Звичайний бот з командами (без візуальних додатків)",
                "price": 200},
    "webapp":  {"ru": "Бот с WebApp",        "en": "Bot with WebApp",   "uk": "Бот з WebApp",
                "desc_ru": "Открывается мини-приложение внутри Telegram (сайт, каталог, игра)",
                "desc_en": "Opens a mini-app inside Telegram (site, catalog, game)",
                "desc_uk": "Відкриває міні-додаток усередині Telegram (сайт, каталог, гра)",
                "price": 800},
    "inline":  {"ru": "Бот с инлайн-режимом","en": "Inline-mode bot",   "uk": "Бот з інлайн-режимом",
                "desc_ru": "Можно вызывать через @имябота в любом чате",
                "desc_en": "Can be called via @botname in any chat",
                "desc_uk": "Можна викликати через @імябота у будь-якому чаті",
                "price": 400},
}
MENU_OPTIONS = {
    "no_menu":     {"ru": "Без меню",   "en": "No menu",     "uk": "Без меню",
                    "desc_ru": "Управление только командами",
                    "desc_en": "Command-only",
                    "desc_uk": "Керування лише командами",
                    "price": 0},
    "reply_menu":  {"ru": "Reply-меню", "en": "Reply menu",  "uk": "Reply-меню",
                    "desc_ru": "Кнопки внизу экрана (как клавиатура)",
                    "desc_en": "Buttons at the bottom of the screen",
                    "desc_uk": "Кнопки внизу екрана (як клавіатура)",
                    "price": 80},
    "inline_menu": {"ru": "Inline-меню","en": "Inline menu", "uk": "Inline-меню",
                    "desc_ru": "Кнопки прямо под сообщениями бота",
                    "desc_en": "Buttons right under bot messages",
                    "desc_uk": "Кнопки прямо під повідомленнями бота",
                    "price": 120},
    "both_menu":   {"ru": "Оба типа",   "en": "Both types",  "uk": "Обидва типи",
                    "desc_ru": "И клавиатура снизу, и кнопки под сообщениями",
                    "desc_en": "Both keyboard and inline buttons",
                    "desc_uk": "І клавіатура знизу, і кнопки під повідомленнями",
                    "price": 160},
}
PAYMENT_OPTIONS = {
    "no_pay":       {"ru": "Без оплаты",     "en": "No payments",       "uk": "Без оплати",
                     "desc_ru": "Бот бесплатный для пользователей",
                     "desc_en": "Bot is free to use",
                     "desc_uk": "Бот безкоштовний для користувачів",
                     "price": 0},
    "stars_pay":    {"ru": "Telegram Stars", "en": "Telegram Stars",    "uk": "Telegram Stars",
                     "desc_ru": "Оплата встроенной валютой Telegram (⭐)",
                     "desc_en": "Payments via built-in Telegram Stars (⭐)",
                     "desc_uk": "Оплата вбудованою валютою Telegram (⭐)",
                     "price": 200},
    "external_pay": {"ru": "Внешняя оплата", "en": "External payments", "uk": "Зовнішня оплата",
                     "desc_ru": "LiqPay / Stripe / карты — реальные деньги",
                     "desc_en": "LiqPay / Stripe / cards — real money",
                     "desc_uk": "LiqPay / Stripe / карти — реальні гроші",
                     "price": 400},
}
DATABASE_OPTIONS = {
    "no_db":    {"ru": "Без БД",     "en": "No DB",      "uk": "Без БД",
                 "desc_ru": "Бот ничего не запоминает после перезапуска",
                 "desc_en": "Bot forgets everything on restart",
                 "desc_uk": "Бот нічого не пам'ятає після перезапуску",
                 "price": 0},
    "sqlite":   {"ru": "SQLite",     "en": "SQLite",     "uk": "SQLite",
                 "desc_ru": "Лёгкая БД в файле — для малых проектов",
                 "desc_en": "Lightweight file DB — for small projects",
                 "desc_uk": "Легка БД у файлі — для малих проектів",
                 "price": 120},
    "postgres": {"ru": "PostgreSQL", "en": "PostgreSQL", "uk": "PostgreSQL",
                 "desc_ru": "Мощная БД — для крупных ботов",
                 "desc_en": "Powerful DB — for large bots",
                 "desc_uk": "Потужна БД — для великих ботів",
                 "price": 280},
}
ADMIN_PANEL_OPTIONS = {
    "no_admin":       {"ru": "Без админки",         "en": "No admin",       "uk": "Без адмінки",
                       "desc_ru": "У бота не будет управления",
                       "desc_en": "No management panel",
                       "desc_uk": "Керування не буде",
                       "price": 0},
    "basic_admin":    {"ru": "Базовая админка",     "en": "Basic admin",    "uk": "Базова адмінка",
                       "desc_ru": "Статистика, рассылка, простые действия",
                       "desc_en": "Stats, broadcast, simple actions",
                       "desc_uk": "Статистика, розсилка, прості дії",
                       "price": 200},
    "advanced_admin": {"ru": "Расширенная админка", "en": "Advanced admin", "uk": "Розширена адмінка",
                       "desc_ru": "Управление всем: пользователи, товары, настройки",
                       "desc_en": "Full control: users, products, settings",
                       "desc_uk": "Керування усім: користувачі, товари, налаштування",
                       "price": 400},
}

STEP_KEYS = ["bot_type", "menu", "payments", "database", "admin_panel"]
STEP_OPTIONS = [BOT_TYPES, MENU_OPTIONS, PAYMENT_OPTIONS, DATABASE_OPTIONS, ADMIN_PANEL_OPTIONS]


# ─── Health check для Render ───
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()
    def log_message(self, *a): return


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


def get_step_keyboard(step_index: int, lang: str) -> InlineKeyboardMarkup:
    options = STEP_OPTIONS[step_index]
    buttons = []
    for k, v in options.items():
        label = f"{v[lang]} — {v['price']}₴"
        buttons.append([InlineKeyboardButton(label, callback_data=f"choice_{step_index}_{k}")])
    return InlineKeyboardMarkup(buttons)


def get_step_text(step_index: int, lang: str) -> str:
    """Текст вопроса + описание всех вариантов."""
    header = TEXTS[lang]["questions"][step_index]
    options = STEP_OPTIONS[step_index]
    lines = [f"<b>{header}</b>\n"]
    desc_key = f"desc_{lang}"
    for v in options.values():
        lines.append(f"• <b>{v[lang]}</b> — {v[desc_key]}  <i>({v['price']}₴)</i>")
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
    """Кнопки под сообщением от клиента."""
    rows = [
        [
            InlineKeyboardButton("💬 Ответить", callback_data=f"reply_{client_id}"),
            InlineKeyboardButton("🔒 Завершить чат", callback_data=f"endchat_{client_id}"),
        ],
        [
            InlineKeyboardButton("❌ Отклонить заказ", callback_data=f"reject_{client_id}"),
        ],
    ]
    if is_blocked:
        rows.append([InlineKeyboardButton("✅ Разблокировать", callback_data=f"unblock_{client_id}")])
    else:
        rows.append([InlineKeyboardButton("🚫 Заблокировать", callback_data=f"block_{client_id}")])
    return InlineKeyboardMarkup(rows)


def client_reply_kb(lang: str):
    """Reply-клавиатура для клиента (быстрые кнопки внизу)."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(TEXTS[lang]["kb_new_order"])],
            [KeyboardButton(TEXTS[lang]["kb_change_lang"]), KeyboardButton(TEXTS[lang]["kb_help"])],
        ],
        resize_keyboard=True,
    )


def admin_reply_kb():
    """Reply-клавиатура для админа."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🚫 Заблокированные"), KeyboardButton("❌ Стоп-ответ")],
            [KeyboardButton("ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


async def set_admin_commands(app: Application, admin_id: int):
    """Устанавливает slash-меню команд для админа."""
    cmds = [
        BotCommand("start", "Меню"),
        BotCommand("reply", "Ответ клиенту: /reply ID текст"),
        BotCommand("block", "Заблокировать: /block ID"),
        BotCommand("unblock", "Разблокировать: /unblock ID"),
        BotCommand("blocked", "Список заблокированных"),
        BotCommand("end", "Завершить чат: /end ID"),
        BotCommand("stopreply", "Перестать отвечать"),
    ]
    try:
        await app.bot.set_my_commands(cmds, scope=BotCommandScopeChat(chat_id=admin_id))
    except Exception as e:
        logger.error("set_admin_commands: %s", e)


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
    await update.message.reply_text(
        TEXTS["ru"]["choose_lang"],
        reply_markup=lang_keyboard(),
    )
    return STEP_LANG


async def handle_lang(update: Update, context):
    query = update.callback_query
    await query.answer()
    lang = query.data.split("_")[1]
    context.user_data["lang"] = lang
    USER_LANG[query.from_user.id] = lang

    # показать вопрос 1 с описаниями
    await query.edit_message_text(
        get_step_text(0, lang),
        reply_markup=get_step_keyboard(0, lang),
        parse_mode="HTML",
    )
    # прислать reply-клавиатуру
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="👇",
        reply_markup=client_reply_kb(lang),
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
        btns = [
            [InlineKeyboardButton(
                f"{i + 1}. {TEXTS[lang]['questions'][i]}",
                callback_data=f"fix_{i}",
            )]
            for i in range(len(STEP_KEYS))
        ]
        await query.edit_message_text(
            TEXTS[lang]["fix_what"],
            reply_markup=InlineKeyboardMarkup(btns),
        )
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

    pay_kb = None
    if PAYMENT_PROVIDER_TOKEN:
        pay_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(TEXTS[lang]["btn_pay"], callback_data=f"pay_{total}")
        ]])

    # итоговое сообщение клиенту
    await update.message.reply_text(
        f"{TEXTS[lang]['order_sent']}\n\n{summary}\n\n"
        f"{TEXTS[lang]['description']}\n{desc}",
        parse_mode="HTML",
        reply_markup=pay_kb,
    )
    # автоответ
    await update.message.reply_text(TEXTS[lang]["auto_wait"], parse_mode="HTML",
                                    reply_markup=client_reply_kb(lang))

    ACTIVE_CHATS.add(user.id)

    admin_id = ADMIN_ID_STORAGE.get("admin")
    if admin_id:
        try:
            await context.bot.send_message(
                admin_id,
                f"🔔 <b>НОВЫЙ ЗАКАЗ!</b>\n"
                f"🌐 Язык клиента: <b>{TEXTS[lang]['lang_name']}</b>\n"
                f"Клиент: @{user.username or 'нет'}\n"
                f"ID: <code>{user.id}</code>\n\n"
                f"{summary}\n\n"
                f"📝 ТЗ: {desc}",
                parse_mode="HTML",
                reply_markup=admin_order_keyboard(user.id, is_blocked=(user.id in BLOCKED_USERS)),
            )
        except Exception as e:
            logger.error("admin notify: %s", e)

    return ConversationHandler.END


# ─── Оплата ───
async def handle_pay(update: Update, context):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)

    if not PAYMENT_PROVIDER_TOKEN:
        await query.message.reply_text("⚠️ Оплата пока не настроена.")
        return

    total = int(query.data.split("_")[1])
    prices = [LabeledPrice(label=TEXTS[lang]["pay_label"], amount=total * 100)]

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=TEXTS[lang]["pay_title"],
        description=TEXTS[lang]["pay_desc"],
        payload=f"order_{query.from_user.id}",
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency="UAH",
        prices=prices,
    )


async def precheckout(update: Update, context):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, context):
    lang = get_lang(context, update.effective_user.id)
    await update.message.reply_text(TEXTS[lang]["pay_success"])

    admin_id = ADMIN_ID_STORAGE.get("admin")
    if admin_id:
        user = update.effective_user
        amount = update.message.successful_payment.total_amount / 100
        try:
            await context.bot.send_message(
                admin_id,
                f"💰 <b>ОПЛАТА ПОЛУЧЕНА!</b>\n"
                f"Клиент: @{user.username or 'нет'} (ID: <code>{user.id}</code>)\n"
                f"Сумма: <b>{amount}₴</b>",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("payment notify: %s", e)


# ─── Админские действия (кнопки под заказом) ───
async def handle_admin_action(update: Update, context):
    query = update.callback_query
    user = query.from_user

    if not is_admin(user):
        await query.answer("Нет доступа", show_alert=True)
        return

    action, client_id_str = query.data.split("_", 1)
    client_id = int(client_id_str)
    client_lang = USER_LANG.get(client_id, "ru")

    if action == "reply":
        ADMIN_REPLY_TARGET[user.id] = client_id
        ACTIVE_CHATS.add(client_id)
        await query.answer()
        await query.message.reply_text(
            f"✍️ Режим ответа: <code>{client_id}</code>\n"
            f"Пишите сообщения — они уходят клиенту.\n"
            f"Чтобы выйти — нажмите «❌ Стоп-ответ» или /stopreply\n"
            f"Чтобы завершить чат клиента — /end {client_id}",
            parse_mode="HTML",
        )

    elif action == "reject":
        ACTIVE_CHATS.discard(client_id)
        ADMIN_REPLY_TARGET.pop(user.id, None)
        try:
            await context.bot.send_message(client_id, TEXTS[client_lang]["order_rejected_client"])
        except Exception as e:
            logger.error(e)
        await query.answer("Заказ отклонён")
        await query.message.reply_text(f"❌ Заказ клиента <code>{client_id}</code> отменён. Клиент уведомлён.", parse_mode="HTML")

    elif action == "endchat":
        ACTIVE_CHATS.discard(client_id)
        if ADMIN_REPLY_TARGET.get(user.id) == client_id:
            ADMIN_REPLY_TARGET.pop(user.id, None)
        try:
            await context.bot.send_message(client_id, TEXTS[client_lang]["chat_ended_client"])
        except Exception as e:
            logger.error(e)
        await query.answer("Чат завершён")
        await query.message.reply_text(f"🔒 Чат с клиентом <code>{client_id}</code> завершён.", parse_mode="HTML")

    elif action == "block":
        BLOCKED_USERS.add(client_id)
        ACTIVE_CHATS.discard(client_id)
        if ADMIN_REPLY_TARGET.get(user.id) == client_id:
            ADMIN_REPLY_TARGET.pop(user.id, None)
        await query.answer("Заблокирован")
        await query.message.reply_text(f"🚫 Клиент <code>{client_id}</code> заблокирован.", parse_mode="HTML")

    elif action == "unblock":
        BLOCKED_USERS.discard(client_id)
        await query.answer("Разблокирован")
        await query.message.reply_text(f"✅ Клиент <code>{client_id}</code> разблокирован.", parse_mode="HTML")


# ─── Админские команды ───
async def admin_reply_cmd(update: Update, context):
    if not is_admin(update.effective_user):
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Формат: /reply ID текст")
        return
    try:
        target_id = int(context.args[0])
        if target_id in BLOCKED_USERS:
            await update.message.reply_text("⚠️ Пользователь заблокирован.")
            return
        text = " ".join(context.args[1:])
        await context.bot.send_message(target_id, text)
        ADMIN_REPLY_TARGET[update.effective_user.id] = target_id
        ACTIVE_CHATS.add(target_id)
        await update.message.reply_text(
            f"✅ Отправлено. Дальше можно просто писать в чат — уйдёт клиенту <code>{target_id}</code>.\n"
            f"«❌ Стоп-ответ» или /stopreply — чтобы выйти.",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def cmd_stop_reply(update: Update, context):
    if not is_admin(update.effective_user):
        return
    target = ADMIN_REPLY_TARGET.pop(update.effective_user.id, None)
    if target:
        await update.message.reply_text(f"✋ Больше не отвечаете клиенту <code>{target}</code>.", parse_mode="HTML")
    else:
        await update.message.reply_text("Вы никому не отвечали.")


async def cmd_block(update: Update, context):
    if not is_admin(update.effective_user):
        return
    if not context.args:
        await update.message.reply_text("Формат: /block ID")
        return
    try:
        uid = int(context.args[0])
        BLOCKED_USERS.add(uid)
        ACTIVE_CHATS.discard(uid)
        await update.message.reply_text(f"🚫 <code>{uid}</code> заблокирован.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def cmd_unblock(update: Update, context):
    if not is_admin(update.effective_user):
        return
    if not context.args:
        await update.message.reply_text("Формат: /unblock ID")
        return
    try:
        uid = int(context.args[0])
        BLOCKED_USERS.discard(uid)
        await update.message.reply_text(f"✅ <code>{uid}</code> разблокирован.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def cmd_blocked(update: Update, context):
    if not is_admin(update.effective_user):
        return
    if not BLOCKED_USERS:
        await update.message.reply_text("Никто не заблокирован.")
        return
    lines = ["🚫 <b>Заблокированные:</b>"]
    for uid in BLOCKED_USERS:
        lines.append(f"• <code>{uid}</code>  — /unblock {uid}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_end(update: Update, context):
    if not is_admin(update.effective_user):
        return
    if not context.args:
        await update.message.reply_text("Формат: /end ID")
        return
    try:
        uid = int(context.args[0])
        ACTIVE_CHATS.discard(uid)
        if ADMIN_REPLY_TARGET.get(update.effective_user.id) == uid:
            ADMIN_REPLY_TARGET.pop(update.effective_user.id, None)
        client_lang = USER_LANG.get(uid, "ru")
        try:
            await context.bot.send_message(uid, TEXTS[client_lang]["chat_ended_client"])
        except Exception:
            pass
        await update.message.reply_text(f"🔒 Чат с <code>{uid}</code> завершён.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# ─── Общий обработчик текста ───
async def text_router(update: Update, context):
    user = update.effective_user
    text = update.message.text or ""

    # === АДМИН ===
    if is_admin(user):
        # быстрые кнопки
        if text == "🚫 Заблокированные":
            return await cmd_blocked(update, context)
        if text == "❌ Стоп-ответ":
            return await cmd_stop_reply(update, context)
        if text == "ℹ️ Помощь":
            await update.message.reply_text(TEXTS["ru"]["hello_admin"])
            return

        # если админ сейчас в режиме ответа — пересылаем клиенту
        target = ADMIN_REPLY_TARGET.get(user.id)
        if target:
            if target in BLOCKED_USERS:
                await update.message.reply_text("⚠️ Клиент заблокирован. Разблокируйте или /stopreply")
                return
            try:
                await context.bot.send_message(target, text)
                await update.message.reply_text(f"✅ → <code>{target}</code>", parse_mode="HTML")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")
            return

        await update.message.reply_text("Нажмите «💬 Ответить» под сообщением клиента или /reply ID текст")
        return

    # === КЛИЕНТ ===
    if user.id in BLOCKED_USERS:
        return

    lang = get_lang(context, user.id)

    # быстрые кнопки клиента
    if text == TEXTS[lang]["kb_new_order"] or text in (TEXTS["ru"]["kb_new_order"], TEXTS["en"]["kb_new_order"], TEXTS["uk"]["kb_new_order"]):
        return await start(update, context)

    if text == TEXTS[lang]["kb_change_lang"] or text in (TEXTS["ru"]["kb_change_lang"], TEXTS["en"]["kb_change_lang"], TEXTS["uk"]["kb_change_lang"]):
        await update.message.reply_text(TEXTS["ru"]["choose_lang"], reply_markup=lang_keyboard())
        return

    if text == TEXTS[lang]["kb_help"] or text in (TEXTS["ru"]["kb_help"], TEXTS["en"]["kb_help"], TEXTS["uk"]["kb_help"]):
        await update.message.reply_text(TEXTS[lang]["help_text"], reply_markup=client_reply_kb(lang))
        return

    # обычное сообщение — пересылаем админу
    admin_id = ADMIN_ID_STORAGE.get("admin")
    if not admin_id:
        await update.message.reply_text(TEXTS[lang]["sent_to_dev"])
        return

    try:
        await context.bot.send_message(
            admin_id,
            f"💬 От @{user.username or 'нет'} | ID <code>{user.id}</code>\n"
            f"🌐 {TEXTS[lang]['lang_name']}\n\n"
            f"{text}",
            parse_mode="HTML",
            reply_markup=admin_order_keyboard(user.id, is_blocked=(user.id in BLOCKED_USERS)),
        )
        await update.message.reply_text(TEXTS[lang]["sent_to_dev"], reply_markup=client_reply_kb(lang))
    except Exception as e:
        logger.error("relay error: %s", e)


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
            STEP_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description)
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(conv)

    app.add_handler(CommandHandler("reply", admin_reply_cmd))
    app.add_handler(CommandHandler("stopreply", cmd_stop_reply))
    app.add_handler(CommandHandler("block", cmd_block))
    app.add_handler(CommandHandler("unblock", cmd_unblock))
    app.add_handler(CommandHandler("blocked", cmd_blocked))
    app.add_handler(CommandHandler("end", cmd_end))

    app.add_handler(CallbackQueryHandler(handle_pay, pattern=r"^pay_"))
    app.add_handler(CallbackQueryHandler(
        handle_admin_action, pattern=r"^(reply|reject|endchat|block|unblock)_"
    ))

    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
