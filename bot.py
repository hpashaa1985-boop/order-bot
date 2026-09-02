import asyncio
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
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
# Токен провайдера для оплаты (получить у @BotFather -> Payments)
PAYMENT_PROVIDER_TOKEN = os.environ.get("PAYMENT_PROVIDER_TOKEN", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Состояния ───
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
        "hello_admin": "👑 Привет, админ! Уведомления о заказах будут приходить сюда.\nОтвет клиенту: /reply ID текст",
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
        "wait_answer": "⏳ Напишите сюда, если нужно что-то добавить. Ждите ответа.",
        "btn_pay": "💳 Оплатить заказ",
        "pay_title": "Оплата заказа бота",
        "pay_desc": "Оплата разработки Telegram-бота",
        "pay_label": "Заказ бота",
        "pay_success": "✅ Оплата прошла успешно! Спасибо! Разработчик скоро свяжется с вами.",
        "reply_from_dev": "💬",
        "sent_to_dev": "📨 Отправлено разработчику",
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
        "hello_admin": "👑 Hi, admin! Order notifications will come here.\nReply to a client: /reply ID text",
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
        "write_desc": "✍️ Write a detailed bot description (spec).\nAfter sending, wait for a reply here in the bot.",
        "order_sent": "✅ <b>Order sent!</b>",
        "description": "📝 <b>Description:</b>",
        "wait_answer": "⏳ Write here if you want to add something. Wait for a reply.",
        "btn_pay": "💳 Pay for order",
        "pay_title": "Bot order payment",
        "pay_desc": "Payment for Telegram bot development",
        "pay_label": "Bot order",
        "pay_success": "✅ Payment successful! Thank you! The developer will contact you soon.",
        "reply_from_dev": "💬",
        "sent_to_dev": "📨 Sent to developer",
        "questions": [
            "🤖 Bot type:",
            "📋 Menu type:",
            "💳 Do you need payments in the bot?",
            "🗄 Need a database?",
            "🔧 Need an admin panel?",
        ],
    },
    "uk": {
        "lang_name": "🇺🇦 Українська",
        "choose_lang": "🌐 Виберіть мову / Choose language / Выберите язык:",
        "hello_admin": "👑 Привіт, адмін! Сповіщення про замовлення будуть приходити сюди.\nВідповідь клієнту: /reply ID текст",
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
        "write_desc": "✍️ Напишіть детальний опис бота (ТЗ).\nПісля відправки очікуйте відповіді тут, у боті.",
        "order_sent": "✅ <b>Замовлення відправлено!</b>",
        "description": "📝 <b>Опис:</b>",
        "wait_answer": "⏳ Напишіть сюди, якщо треба щось додати. Очікуйте відповіді.",
        "btn_pay": "💳 Оплатити замовлення",
        "pay_title": "Оплата замовлення бота",
        "pay_desc": "Оплата розробки Telegram-бота",
        "pay_label": "Замовлення бота",
        "pay_success": "✅ Оплата пройшла успішно! Дякуємо! Розробник скоро зв'яжеться з вами.",
        "reply_from_dev": "💬",
        "sent_to_dev": "📨 Відправлено розробнику",
        "questions": [
            "🤖 Тип бота:",
            "📋 Тип меню:",
            "💳 Чи потрібна оплата у вашому боті?",
            "🗄 Чи потрібна база даних?",
            "🔧 Чи потрібна адмін-панель?",
        ],
    },
}

# ─── Варианты (labels на 3-х языках, цены в гривнах) ───
BOT_TYPES = {
    "simple":  {"ru": "Простой бот",        "en": "Simple bot",         "uk": "Простий бот",         "price": 500},
    "webapp":  {"ru": "Бот с WebApp",       "en": "Bot with WebApp",    "uk": "Бот з WebApp",        "price": 2000},
    "inline":  {"ru": "Бот с инлайн-режимом","en": "Inline-mode bot",   "uk": "Бот з інлайн-режимом","price": 1000},
}
MENU_OPTIONS = {
    "no_menu":     {"ru": "Без меню",       "en": "No menu",       "uk": "Без меню",       "price": 0},
    "reply_menu":  {"ru": "Reply-меню",     "en": "Reply menu",    "uk": "Reply-меню",     "price": 200},
    "inline_menu": {"ru": "Inline-меню",    "en": "Inline menu",   "uk": "Inline-меню",    "price": 300},
    "both_menu":   {"ru": "Оба типа",       "en": "Both types",    "uk": "Обидва типи",    "price": 400},
}
PAYMENT_OPTIONS = {
    "no_pay":       {"ru": "Без оплаты",         "en": "No payments",         "uk": "Без оплати",           "price": 0},
    "stars_pay":    {"ru": "Telegram Stars",     "en": "Telegram Stars",      "uk": "Telegram Stars",       "price": 500},
    "external_pay": {"ru": "Внешняя оплата",     "en": "External payments",   "uk": "Зовнішня оплата",      "price": 1000},
}
DATABASE_OPTIONS = {
    "no_db":    {"ru": "Без БД",       "en": "No DB",       "uk": "Без БД",        "price": 0},
    "sqlite":   {"ru": "SQLite",       "en": "SQLite",      "uk": "SQLite",        "price": 300},
    "postgres": {"ru": "PostgreSQL",   "en": "PostgreSQL",  "uk": "PostgreSQL",    "price": 700},
}
ADMIN_PANEL_OPTIONS = {
    "no_admin":       {"ru": "Без админки",        "en": "No admin",        "uk": "Без адмінки",         "price": 0},
    "basic_admin":    {"ru": "Базовая админка",    "en": "Basic admin",     "uk": "Базова адмінка",      "price": 500},
    "advanced_admin": {"ru": "Расширенная админка","en": "Advanced admin",  "uk": "Розширена адмінка",   "price": 1000},
}

STEP_KEYS = ["bot_type", "menu", "payments", "database", "admin_panel"]
STEP_OPTIONS = [BOT_TYPES, MENU_OPTIONS, PAYMENT_OPTIONS, DATABASE_OPTIONS, ADMIN_PANEL_OPTIONS]

ADMIN_ID_STORAGE = {"admin": None}


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
def get_lang(context) -> str:
    return context.user_data.get("lang", "ru")


def t(context, key: str):
    return TEXTS[get_lang(context)][key]


def lang_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(TEXTS["ru"]["lang_name"], callback_data="lang_ru")],
        [InlineKeyboardButton(TEXTS["en"]["lang_name"], callback_data="lang_en")],
        [InlineKeyboardButton(TEXTS["uk"]["lang_name"], callback_data="lang_uk")],
    ])


def get_step_keyboard(step_index: int, lang: str) -> InlineKeyboardMarkup:
    options = STEP_OPTIONS[step_index]
    buttons = [
        [InlineKeyboardButton(
            f"{v[lang]} (+{v['price']}₴)",
            callback_data=f"choice_{step_index}_{k}",
        )]
        for k, v in options.items()
    ]
    return InlineKeyboardMarkup(buttons)


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


def confirm_keyboard(lang: str, total: int):
    buttons = [
        [InlineKeyboardButton(TEXTS[lang]["btn_continue"], callback_data="confirm_continue")],
        [InlineKeyboardButton(TEXTS[lang]["btn_fix"], callback_data="confirm_fix")],
        [InlineKeyboardButton(TEXTS[lang]["btn_cancel"], callback_data="confirm_cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


# ─── Handlers ───
async def start(update: Update, context):
    user = update.effective_user
    if user.username and user.username.lower() == ADMIN_USERNAME.lower():
        ADMIN_ID_STORAGE["admin"] = user.id
        await update.message.reply_text(TEXTS["ru"]["hello_admin"])
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

    await query.edit_message_text(
        TEXTS[lang]["start_msg"] + TEXTS[lang]["questions"][0],
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
            f"<b>{TEXTS[lang]['step']} {step + 2}:</b>\n{TEXTS[lang]['questions'][step + 1]}",
            reply_markup=get_step_keyboard(step + 1, lang),
            parse_mode="HTML",
        )
        return STEP_BOT_TYPE + step + 1

    summary, total = build_summary(context.user_data, lang)
    await query.edit_message_text(
        summary + "\n\n" + TEXTS[lang]["correct"],
        reply_markup=confirm_keyboard(lang, total),
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
        f"{TEXTS[lang]['fix_item']} {step + 1}:\n{TEXTS[lang]['questions'][step]}",
        reply_markup=get_step_keyboard(step, lang),
    )
    return STEP_FIX_SELECT


async def handle_fix_choice(update: Update, context):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)

    parts = query.data.split("_", 2)
    step = int(parts[1])
    context.user_data[STEP_KEYS[step]] = parts[2]

    summary, total = build_summary(context.user_data, lang)
    await query.edit_message_text(
        summary + "\n\n" + TEXTS[lang]["correct"],
        reply_markup=confirm_keyboard(lang, total),
        parse_mode="HTML",
    )
    return STEP_CONFIRM


async def handle_description(update: Update, context):
    desc = update.message.text
    lang = get_lang(context)
    summary, total = build_summary(context.user_data, lang)
    user = update.effective_user

    # Кнопка оплаты (если провайдер задан)
    pay_kb = None
    if PAYMENT_PROVIDER_TOKEN:
        pay_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(TEXTS[lang]["btn_pay"], callback_data=f"pay_{total}")
        ]])

    await update.message.reply_text(
        f"{TEXTS[lang]['order_sent']}\n\n{summary}\n\n"
        f"{TEXTS[lang]['description']}\n{desc}\n\n"
        f"{TEXTS[lang]['wait_answer']}",
        parse_mode="HTML",
        reply_markup=pay_kb,
    )

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
                f"📝 ТЗ: {desc}\n\n"
                f"<code>/reply {user.id} ваш текст</code>",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("admin notify error: %s", e)

    return ConversationHandler.END


# ─── Оплата ───
async def handle_pay(update: Update, context):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)

    if not PAYMENT_PROVIDER_TOKEN:
        await query.message.reply_text("⚠️ Оплата пока не настроена. Свяжитесь с разработчиком.")
        return

    total = int(query.data.split("_")[1])

    prices = [LabeledPrice(label=TEXTS[lang]["pay_label"], amount=total * 100)]  # копейки

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
    lang = get_lang(context)
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
            logger.error("payment notify error: %s", e)


# ─── Ответ админа ───
async def admin_reply(update: Update, context):
    user = update.effective_user
    if not user.username or user.username.lower() != ADMIN_USERNAME.lower():
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Формат: /reply ID текст")
        return

    try:
        target_id = int(context.args[0])
        text = " ".join(context.args[1:])
        await context.bot.send_message(target_id, text)
        await update.message.reply_text("✅ Отправлено")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def relay_to_admin(update: Update, context):
    user = update.effective_user
    admin_id = ADMIN_ID_STORAGE.get("admin")
    if not admin_id or user.id == admin_id:
        return

    try:
        await context.bot.send_message(
            admin_id,
            f"💬 От @{user.username or 'нет'} | ID <code>{user.id}</code>\n\n"
            f"{update.message.text}\n\n"
            f"<code>/reply {user.id} текст</code>",
            parse_mode="HTML",
        )
        lang = get_lang(context)
        await update.message.reply_text(TEXTS[lang]["sent_to_dev"])
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
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("reply", admin_reply))
    app.add_handler(CallbackQueryHandler(handle_pay, pattern=r"^pay_"))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_to_admin))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
