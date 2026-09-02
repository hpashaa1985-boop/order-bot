import asyncio
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

(
    STEP_BOT_TYPE,
    STEP_MENU,
    STEP_PAYMENTS,
    STEP_DATABASE,
    STEP_ADMIN_PANEL,
    STEP_CONFIRM,
    STEP_FIX_SELECT,
    STEP_DESCRIPTION,
) = range(8)

BOT_TYPES = {
    "simple": {"label": "Простой бот", "price": 500},
    "webapp": {"label": "Бот с WebApp", "price": 2000},
    "inline": {"label": "Бот с инлайн-режимом", "price": 1000},
}
MENU_OPTIONS = {
    "no_menu": {"label": "Без меню", "price": 0},
    "reply_menu": {"label": "Reply-меню", "price": 200},
    "inline_menu": {"label": "Inline-меню", "price": 300},
    "both_menu": {"label": "Оба типа", "price": 400},
}
PAYMENT_OPTIONS = {
    "no_pay": {"label": "Без оплаты", "price": 0},
    "stars_pay": {"label": "Telegram Stars", "price": 500},
    "external_pay": {"label": "Внешняя оплата", "price": 1000},
}
DATABASE_OPTIONS = {
    "no_db": {"label": "Без БД", "price": 0},
    "sqlite": {"label": "SQLite", "price": 300},
    "postgres": {"label": "PostgreSQL", "price": 700},
}
ADMIN_PANEL_OPTIONS = {
    "no_admin": {"label": "Без админки", "price": 0},
    "basic_admin": {"label": "Базовая админка", "price": 500},
    "advanced_admin": {"label": "Расширенная админка", "price": 1000},
}

STEPS_CONFIG = [
    ("bot_type", "🤖 Тип бота:", BOT_TYPES),
    ("menu", "📋 Тип меню:", MENU_OPTIONS),
    ("payments", "💳 Нужна оплата?", PAYMENT_OPTIONS),
    ("database", "🗄 Нужна база данных?", DATABASE_OPTIONS),
    ("admin_panel", "🔧 Нужна админ-панель?", ADMIN_PANEL_OPTIONS),
]

ADMIN_ID_STORAGE = {"admin": None}


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return


def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), HealthCheckHandler).serve_forever()


def get_step_keyboard(step_index: int) -> InlineKeyboardMarkup:
    _, _, options = STEPS_CONFIG[step_index]
    buttons = [
        [
            InlineKeyboardButton(
                f"{v['label']} (+{v['price']}₽)",
                callback_data=f"choice_{step_index}_{k}",
            )
        ]
        for k, v in options.items()
    ]
    return InlineKeyboardMarkup(buttons)


def build_summary(user_data: dict):
    total = 0
    lines = ["📝 <b>Ваш заказ:</b>\n"]
    for i, (key, _, opts) in enumerate(STEPS_CONFIG):
        val = user_data.get(key)
        if val in opts:
            lines.append(f" {i + 1}. {opts[val]['label']} — {opts[val]['price']}₽")
            total += opts[val]["price"]
    lines.append(f"\n💰 <b>Итого: {total}₽</b>")
    return "\n".join(lines), total


def confirm_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Продолжить", callback_data="confirm_continue")],
            [InlineKeyboardButton("✏️ Исправить", callback_data="confirm_fix")],
            [
                InlineKeyboardButton(
                    "❌ Отмена (сбросит все выборы)",
                    callback_data="confirm_cancel",
                )
            ],
        ]
    )


async def start(update: Update, context):
    user = update.effective_user
    if user.username and user.username.lower() == ADMIN_USERNAME.lower():
        ADMIN_ID_STORAGE["admin"] = user.id
        await update.message.reply_text(
            "👑 Привет, админ! Заказы будут приходить сюда.\n"
            "Ответ клиенту: /reply ID текст"
        )
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(
        "👋 Привет! Оформим заказ на бота.\n\n"
        f"<b>Шаг 1:</b>\n{STEPS_CONFIG[0][1]}",
        reply_markup=get_step_keyboard(0),
        parse_mode="HTML",
    )
    return STEP_BOT_TYPE


async def handle_choice(update: Update, context):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_", 2)
    step = int(parts[1])
    context.user_data[STEPS_CONFIG[step][0]] = parts[2]

    if step + 1 < len(STEPS_CONFIG):
        await query.edit_message_text(
            f"<b>Шаг {step + 2}:</b>\n{STEPS_CONFIG[step + 1][1]}",
            reply_markup=get_step_keyboard(step + 1),
            parse_mode="HTML",
        )
        return STEP_BOT_TYPE + step + 1

    summary, _ = build_summary(context.user_data)
    await query.edit_message_text(
        summary + "\n\n✅ Всё верно?",
        reply_markup=confirm_keyboard(),
        parse_mode="HTML",
    )
    return STEP_CONFIRM


async def handle_confirm(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_continue":
        await query.edit_message_text(
            "✍️ Напишите подробное описание бота (ТЗ).\n"
            "После отправки ждите ответа здесь, в боте."
        )
        return STEP_DESCRIPTION

    if query.data == "confirm_fix":
        btns = [
            [
                InlineKeyboardButton(
                    f"{i + 1}. {STEPS_CONFIG[i][1]}",
                    callback_data=f"fix_{i}",
                )
            ]
            for i in range(len(STEPS_CONFIG))
        ]
        await query.edit_message_text(
            "✏️ Что исправить?",
            reply_markup=InlineKeyboardMarkup(btns),
        )
        return STEP_FIX_SELECT

    context.user_data.clear()
    await query.edit_message_text(
        "❌ Все выбранные действия отменены.\nЗаново: /start"
    )
    return ConversationHandler.END


async def handle_fix_select(update: Update, context):
    query = update.callback_query
    await query.answer()
    step = int(query.data.split("_")[1])
    await query.edit_message_text(
        f"Исправляем пункт {step + 1}:\n{STEPS_CONFIG[step][1]}",
        reply_markup=get_step_keyboard(step),
    )
    return STEP_FIX_SELECT


async def handle_fix_choice(update: Update, context):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_", 2)
    step = int(parts[1])
    context.user_data[STEPS_CONFIG[step][0]] = parts[2]

    summary, _ = build_summary(context.user_data)
    await query.edit_message_text(
        summary + "\n\n✅ Всё верно?",
        reply_markup=confirm_keyboard(),
        parse_mode="HTML",
    )
    return STEP_CONFIRM


async def handle_description(update: Update, context):
    desc = update.message.text
    summary, _ = build_summary(context.user_data)
    user = update.effective_user

    await update.message.reply_text(
        f"✅ <b>Заказ отправлен!</b>\n\n{summary}\n\n"
        f"📝 <b>Описание:</b>\n{desc}\n\n"
        "⏳ Напишите сюда, если нужно что-то добавить. Ждите ответа.",
        parse_mode="HTML",
    )

    admin_id = ADMIN_ID_STORAGE.get("admin")
    if admin_id:
        try:
            await context.bot.send_message(
                admin_id,
                "🔔 <b>НОВЫЙ ЗАКАЗ!</b>\n"
                f"Клиент: @{user.username or 'нет'}\n"
                f"ID: <code>{user.id}</code>\n\n"
                f"{summary}\n\n"
                f"📝 ТЗ: {desc}\n\n"
                f"<code>/reply {user.id} ваш текст</code>",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("admin notify error: %s", e)
    else:
        logger.warning("Admin has not pressed /start yet")

    return ConversationHandler.END


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
        await context.bot.send_message(
            target_id,
            f"💬 <b>Ответ от разработчика:</b>\n\n{text}",
            parse_mode="HTML",
        )
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
        await update.message.reply_text("📨 Отправлено разработчику")
    except Exception as e:
        logger.error("relay error: %s", e)


def main():
    if not TOKEN:
        raise SystemExit("BOT_TOKEN is not set in Environment")

    # фикс для новых Python (event loop)
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    threading.Thread(target=run_health_check, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_to_admin))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
