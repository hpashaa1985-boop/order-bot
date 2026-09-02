import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)
import config

# --- МИНИ ВЕБ-СЕРВЕР ДЛЯ RENDER (чтобы не отключали) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive")

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# --- ВЕСЬ ОСТАЛЬНОЙ ТВОЙ КОД БОТА ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

(STEP_BOT_TYPE, STEP_MENU, STEP_PAYMENTS, STEP_DATABASE, STEP_ADMIN_PANEL, 
 STEP_CONFIRM, STEP_FIX_SELECT, STEP_DESCRIPTION, STEP_ADMIN_REPLY) = range(9)

BOT_TYPES = {"simple": {"label": "Простой бот", "price": 500}, "webapp": {"label": "Бот с WebApp", "price": 2000}, "inline": {"label": "Бот с инлайн-режимом", "price": 1000}}
MENU_OPTIONS = {"no_menu": {"label": "Без меню", "price": 0}, "reply_menu": {"label": "Reply-меню", "price": 200}, "inline_menu": {"label": "Inline-меню", "price": 300}, "both_menu": {"label": "Оба типа", "price": 400}}
PAYMENT_OPTIONS = {"no_pay": {"label": "Без оплаты", "price": 0}, "stars_pay": {"label": "Telegram Stars", "price": 500}, "external_pay": {"label": "Внешняя оплата", "price": 1000}}
DATABASE_OPTIONS = {"no_db": {"label": "Без БД", "price": 0}, "sqlite": {"label": "SQLite", "price": 300}, "postgres": {"label": "PostgreSQL", "price": 700}}
ADMIN_PANEL_OPTIONS = {"no_admin": {"label": "Без админки", "price": 0}, "basic_admin": {"label": "Базовая админка", "price": 500}, "advanced_admin": {"label": "Расширенная админка", "price": 1000}}

STEPS_CONFIG = [("bot_type", "🤖 Тип бота:", BOT_TYPES), ("menu", "📋 Тип меню:", MENU_OPTIONS), ("payments", "💳 Нужна оплата?", PAYMENT_OPTIONS), ("database", "🗄 Нужна база данных?", DATABASE_OPTIONS), ("admin_panel", "🔧 Нужна админ-панель?", ADMIN_PANEL_OPTIONS)]
ADMIN_ID_STORAGE = {"admin": None}

def get_step_keyboard(step_index):
    _, _, options = STEPS_CONFIG[step_index]
    buttons = [[InlineKeyboardButton(text=f"{v['label']} (+{v['price']}₽)", callback_data=f"choice_{step_index}_{k}")] for k, v in options.items()]
    return InlineKeyboardMarkup(buttons)

def build_summary(user_data):
    total = 0
    lines = ["📝 <b>Ваш заказ:</b>\n"]
    for i, (key, ques, opts) in enumerate(STEPS_CONFIG):
        val = user_data.get(key)
        if val in opts:
            lines.append(f" {i+1}. {opts[val]['label']} — {opts[val]['price']}₽")
            total += opts[val]['price']
    lines.append(f"\n💰 <b>Итого: {total}₽</b>")
    return "\n".join(lines), total

async def start(update, context):
    user = update.effective_user
    if user.username and user.username.lower() == config.ADMIN_USERNAME.lower():
        ADMIN_ID_STORAGE["admin"] = user.id
        await update.message.reply_text("👑 Админ зарегистрирован! Отвечать: /reply ID текст")
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text("👋 Привет! Давай соберем твоего бота.\nВопрос 1:", reply_markup=get_step_keyboard(0), parse_mode="HTML")
    return STEP_BOT_TYPE

async def handle_choice(update, context):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    step = int(parts[1])
    context.user_data[STEPS_CONFIG[step][0]] = parts[2]
    if step + 1 < len(STEPS_CONFIG):
        await query.edit_message_text(f"Вопрос {step+2}:", reply_markup=get_step_keyboard(step+1))
        return STEP_BOT_TYPE + step + 1
    summary, _ = build_summary(context.user_data)
    await query.edit_message_text(summary + "\n\n✅ Всё верно?", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Продолжить", callback_data="confirm_continue")],
        [InlineKeyboardButton("✏️ Исправить", callback_data="confirm_fix")],
        [InlineKeyboardButton("❌ Отмена", callback_data="confirm_cancel")]
    ]), parse_mode="HTML")
    return STEP_CONFIRM

async def handle_confirm(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_continue":
        await query.edit_message_text("✍️ Напишите подробное ТЗ (описание):")
        return STEP_DESCRIPTION
    elif query.data == "confirm_fix":
        btns = [[InlineKeyboardButton(f"Пункт {i+1}", callback_data=f"fix_{i}")] for i in range(len(STEPS_CONFIG))]
        await query.edit_message_text("Что исправляем?", reply_markup=InlineKeyboardMarkup(btns))
        return STEP_FIX_SELECT
    context.user_data.clear()
    await query.edit_message_text("❌ Отменено. /start для нового заказа.")
    return ConversationHandler.END

async def handle_fix_select(update, context):
    query = update.callback_query
    await query.answer()
    step = int(query.data.split("_")[1])
    await query.edit_message_text(f"Исправляем пункт {step+1}:", reply_markup=get_step_keyboard(step))
    return STEP_FIX_SELECT

async def handle_description(update, context):
    desc = update.message.text
    summary, _ = build_summary(context.user_data)
    await update.message.reply_text("✅ Заказ отправлен! Ждите ответа.")
    admin_id = ADMIN_ID_STORAGE["admin"] or getattr(config, 'ADMIN_ID', None)
    if admin_id:
        await context.bot.send_message(admin_id, f"🔔 НОВЫЙ ЗАКАЗ!\nID: <code>{update.effective_user.id}</code>\n@{update.effective_user.username}\n\n{summary}\n\nТЗ: {desc}", parse_mode="HTML")
    return ConversationHandler.END

async def admin_reply(update, context):
    if update.effective_user.username.lower() != config.ADMIN_USERNAME.lower(): return
    if len(context.args) < 2: return
    try:
        await context.bot.send_message(chat_id=int(context.args[0]), text=f"💬 Ответ разработчика:\n\n{' '.join(context.args[1:])}")
        await update.message.reply_text("Отправлено!")
    except: await update.message.reply_text("Ошибка отправки.")

def main():
    # Запускаем веб-сервер в отдельном потоке
    threading.Thread(target=run_health_check, daemon=True).start()
    
    # Запускаем бота
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STEP_BOT_TYPE: [CallbackQueryHandler(handle_choice)],
            STEP_MENU: [CallbackQueryHandler(handle_choice)],
            STEP_PAYMENTS: [CallbackQueryHandler(handle_choice)],
            STEP_DATABASE: [CallbackQueryHandler(handle_choice)],
            STEP_ADMIN_PANEL: [CallbackQueryHandler(handle_choice)],
            STEP_CONFIRM: [CallbackQueryHandler(handle_confirm)],
            STEP_FIX_SELECT: [CallbackQueryHandler(handle_fix_select), CallbackQueryHandler(handle_choice, pattern=r"^choice_")],
            STEP_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description)],
        },
        fallbacks=[CommandHandler("start", start)]
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("reply", admin_reply))
    app.run_polling()

if __name__ == "__main__":
    main()
