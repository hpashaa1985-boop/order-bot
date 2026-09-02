import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)
import config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ─── Состояния диалога ───
(
    STEP_BOT_TYPE,
    STEP_MENU,
    STEP_PAYMENTS,
    STEP_DATABASE,
    STEP_ADMIN_PANEL,
    STEP_CONFIRM,
    STEP_FIX_SELECT,
    STEP_DESCRIPTION,
    STEP_ADMIN_REPLY
) = range(9)

# ─── Варианты и цены ───
BOT_TYPES = {
    "simple": {"label": "Простой бот (без мини-приложения)", "price": 500},
    "webapp": {"label": "Бот с мини-приложением (WebApp)", "price": 2000},
    "inline": {"label": "Бот с инлайн-режимом", "price": 1000},
}

MENU_OPTIONS = {
    "no_menu": {"label": "Без меню", "price": 0},
    "reply_menu": {"label": "Reply-меню (кнопки внизу)", "price": 200},
    "inline_menu": {"label": "Inline-меню (кнопки в сообщении)", "price": 300},
    "both_menu": {"label": "Оба типа меню", "price": 400},
}

PAYMENT_OPTIONS = {
    "no_pay": {"label": "Без оплаты", "price": 0},
    "stars_pay": {"label": "Оплата через Telegram Stars", "price": 500},
    "external_pay": {"label": "Внешняя платёжная система", "price": 1000},
}

DATABASE_OPTIONS = {
    "no_db": {"label": "Без базы данных", "price": 0},
    "sqlite": {"label": "SQLite (лёгкая БД)", "price": 300},
    "postgres": {"label": "PostgreSQL (серьёзная БД)", "price": 700},
}

ADMIN_PANEL_OPTIONS = {
    "no_admin": {"label": "Без админ-панели", "price": 0},
    "basic_admin": {"label": "Базовая админ-панель", "price": 500},
    "advanced_admin": {"label": "Расширенная админ-панель", "price": 1000},
}

STEPS_CONFIG = [
    ("bot_type", "🤖 Выберите тип бота:", BOT_TYPES),
    ("menu", "📋 Выберите тип меню:", MENU_OPTIONS),
    ("payments", "💳 Нужна ли оплата в боте?", PAYMENT_OPTIONS),
    ("database", "🗄 Нужна ли база данных?", DATABASE_OPTIONS),
    ("admin_panel", "🔧 Нужна ли админ-панель?", ADMIN_PANEL_OPTIONS),
]

ADMIN_ID_STORAGE = {}

# ─── Вспомогательные функции ───

def get_step_keyboard(step_index: int) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для определённого шага."""
    _, _, options = STEPS_CONFIG[step_index]
    buttons = []
    for key, val in options.items():
        price_text = f" (+{val['price']}₽)" if val["price"] > 0 else " (бесплатно)"
        buttons.append([InlineKeyboardButton(
            text=val["label"] + price_text,
            callback_data=f"choice_{step_index}_{key}"
        )])
    return InlineKeyboardMarkup(buttons)


def build_summary(user_data: dict) -> str:
    """Собирает итоговую сводку заказа."""
    total = 0
    lines = ["📝 <b>Ваш заказ:</b>\n"]

    for i, (data_key, question, options) in enumerate(STEPS_CONFIG):
        chosen_key = user_data.get(data_key)
        if chosen_key and chosen_key in options:
            opt = options[chosen_key]
            lines.append(f"  {i+1}. {question.split(' ', 1)[0]} {opt['label']} — "
                         f"{opt['price']}₽")
            total += opt["price"]

    lines.append(f"\n💰 <b>Итого: {total}₽</b>")
    return "\n".join(lines), total


def fix_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    """Клавиатура для выбора, какой пункт исправить."""
    buttons = []
    for i, (data_key, question, options) in enumerate(STEPS_CONFIG):
        chosen_key = user_data.get(data_key)
        if chosen_key and chosen_key in options:
            label = options[chosen_key]["label"]
            buttons.append([InlineKeyboardButton(
                text=f"{i+1}. {label} ✏️",
                callback_data=f"fix_{i}"
            )])
    buttons.append([InlineKeyboardButton("⬅️ Назад к сводке", callback_data="back_to_summary")])
    return InlineKeyboardMarkup(buttons)


# ─── Обработчики ───

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — начало."""
    user = update.effective_user

    # Автоматическое определение админа
    if user.username and user.username.lower() == config.ADMIN_USERNAME.lower():
        ADMIN_ID_STORAGE["admin"] = user.id
        config.ADMIN_ID = user.id
        await update.message.reply_text(
            "👑 Привет, админ! Ты зарегистрирован.\n"
            "Когда клиент оставит заказ, ты получишь уведомление.\n"
            "Чтобы ответить клиенту: /reply <user_id> <текст>"
        )
        return ConversationHandler.END

    # Обычный пользователь
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Привет! Я помогу оформить заказ на разработку Telegram-бота.\n\n"
        "Сейчас зададим несколько вопросов, чтобы определить стоимость.\n"
        "Поехали! 🚀",
    )

    _, question, _ = STEPS_CONFIG[0]
    await update.message.reply_text(
        text=f"<b>Вопрос 1/{len(STEPS_CONFIG)}</b>\n{question}",
        reply_markup=get_step_keyboard(0),
        parse_mode="HTML"
    )
    return STEP_BOT_TYPE


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора на любом шаге."""
    query = update.callback_query
    await query.answer()

    data = query.data  # choice_0_simple, choice_1_no_menu и т.д.
    parts = data.split("_", 2)  # ["choice", "0", "simple"]
    step_index = int(parts[1])
    chosen_key = parts[2]

    # Сохраняем выбор
    data_key = STEPS_CONFIG[step_index][0]
    context.user_data[data_key] = chosen_key

    next_step = step_index + 1

    if next_step < len(STEPS_CONFIG):
        # Следующий вопрос
        _, question, _ = STEPS_CONFIG[next_step]
        await query.edit_message_text(
            text=f"<b>Вопрос {next_step+1}/{len(STEPS_CONFIG)}</b>\n{question}",
            reply_markup=get_step_keyboard(next_step),
            parse_mode="HTML"
        )
        return STEP_BOT_TYPE + next_step
    else:
        # Все вопросы заданы → показываем сводку
        return await show_summary(query, context)


async def show_summary(query_or_update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает сводку заказа."""
    summary, total = build_summary(context.user_data)
    context.user_data["total"] = total

    confirm_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Продолжить", callback_data="confirm_continue")],
        [InlineKeyboardButton("✏️ Исправить", callback_data="confirm_fix")],
        [InlineKeyboardButton("❌ Отмена (все выбранные данные будут удалены!)",
                               callback_data="confirm_cancel")],
    ])

    text = summary + "\n\n⬇️ Выберите действие:"

    if hasattr(query_or_update, "edit_message_text"):
        await query_or_update.edit_message_text(
            text=text, reply_markup=confirm_buttons, parse_mode="HTML"
        )
    else:
        await query_or_update.reply_text(
            text=text, reply_markup=confirm_buttons, parse_mode="HTML"
        )
    return STEP_CONFIRM


async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок: продолжить / исправить / отмена."""
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_cancel":
        context.user_data.clear()
        await query.edit_message_text(
            "❌ Заказ отменён. Все ранее выбранные данные удалены.\n"
            "Чтобы начать заново — /start"
        )
        return ConversationHandler.END

    elif query.data == "confirm_fix":
        await query.edit_message_text(
            "✏️ Какой пункт хотите исправить?",
            reply_markup=fix_keyboard(context.user_data)
        )
        return STEP_FIX_SELECT

    elif query.data == "confirm_continue":
        await query.edit_message_text(
            "✍️ Отлично! Теперь напишите <b>подробное описание</b> вашего бота:\n\n"
            "• Что бот должен делать?\n"
            "• Какие команды нужны?\n"
            "• Есть ли примеры / ссылки?\n\n"
            "Отправьте текстовое сообщение 👇",
            parse_mode="HTML"
        )
        return STEP_DESCRIPTION


async def handle_fix_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь выбрал пункт для исправления."""
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_summary":
        return await show_summary(query, context)

    # fix_0, fix_1 ...
    step_index = int(query.data.split("_")[1])
    _, question, _ = STEPS_CONFIG[step_index]

    # Сохраняем какой шаг исправляем, чтоб потом вернуться
    context.user_data["fixing_step"] = step_index

    await query.edit_message_text(
        text=f"✏️ <b>Исправление пункта {step_index+1}</b>\n{question}",
        reply_markup=get_step_keyboard(step_index),
        parse_mode="HTML"
    )
    return STEP_FIX_SELECT


async def handle_fix_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка исправленного выбора."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_", 2)
    step_index = int(parts[1])
    chosen_key = parts[2]

    data_key = STEPS_CONFIG[step_index][0]
    context.user_data[data_key] = chosen_key

    # Возвращаемся к сводке
    return await show_summary(query, context)


async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем описание бота от пользователя."""
    description = update.message.text
    user = update.effective_user
    context.user_data["description"] = description

    summary, total = build_summary(context.user_data)

    # Уведомление клиенту
    await update.message.reply_text(
        "✅ <b>Заказ успешно отправлен!</b>\n\n"
        f"{summary}\n\n"
        f"📝 <b>Описание:</b>\n{description}\n\n"
        "⏳ Ожидайте ответа. Мы свяжемся с вами прямо здесь, в этом боте!",
        parse_mode="HTML"
    )

    # Уведомление админу
    admin_id = ADMIN_ID_STORAGE.get("admin") or config.ADMIN_ID
    if admin_id:
        admin_text = (
            "🔔 <b>НОВЫЙ ЗАКАЗ!</b>\n\n"
            f"👤 Клиент: @{user.username or 'нет username'}\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"Имя: {user.first_name} {user.last_name or ''}\n\n"
            f"{summary}\n\n"
            f"📝 <b>Описание:</b>\n{description}\n\n"
            f"💬 Чтобы ответить:\n"
            f"<code>/reply {user.id} Ваш ответ</code>"
        )
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление админу: {e}")

    return ConversationHandler.END


# ─── Админские команды ───

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ отвечает клиенту: /reply <user_id> <текст>"""
    user = update.effective_user

    # Проверка что это админ
    admin_id = ADMIN_ID_STORAGE.get("admin") or config.ADMIN_ID
    if user.id != admin_id:
        await update.message.reply_text("⛔ У вас нет доступа к этой команде.")
        return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "Использование:\n<code>/reply 123456789 Текст ответа</code>",
            parse_mode="HTML"
        )
        return

    try:
        target_user_id = int(args[0])
        reply_text = " ".join(args[1:])
    except ValueError:
        await update.message.reply_text("❌ Неверный user_id")
        return

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"💬 <b>Ответ от разработчика:</b>\n\n{reply_text}",
            parse_mode="HTML"
        )
        await update.message.reply_text(f"✅ Сообщение отправлено пользователю {target_user_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Если пользователь пишет вне диалога — пересылаем админу."""
    user = update.effective_user
    admin_id = ADMIN_ID_STORAGE.get("admin") or config.ADMIN_ID

    # Не пересылаем сообщения админа самому себе
    if user.id == admin_id:
        return

    if admin_id:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"💬 <b>Сообщение от клиента</b>\n"
                    f"👤 @{user.username or 'нет username'} | "
                    f"ID: <code>{user.id}</code>\n\n"
                    f"{update.message.text}\n\n"
                    f"Ответить: <code>/reply {user.id} текст</code>"
                ),
                parse_mode="HTML"
            )
            await update.message.reply_text(
                "📨 Ваше сообщение отправлено разработчику. Ожидайте ответа!"
            )
        except Exception as e:
            logging.error(f"Ошибка пересылки: {e}")


# ─── Главная функция ───

def main():
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # Диалог оформления заказа
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STEP_BOT_TYPE: [
                CallbackQueryHandler(handle_choice, pattern=r"^choice_\d+_.+$")
            ],
            STEP_MENU: [
                CallbackQueryHandler(handle_choice, pattern=r"^choice_\d+_.+$")
            ],
            STEP_PAYMENTS: [
                CallbackQueryHandler(handle_choice, pattern=r"^choice_\d+_.+$")
            ],
            STEP_DATABASE: [
                CallbackQueryHandler(handle_choice, pattern=r"^choice_\d+_.+$")
            ],
            STEP_ADMIN_PANEL: [
                CallbackQueryHandler(handle_choice, pattern=r"^choice_\d+_.+$")
            ],
            STEP_CONFIRM: [
                CallbackQueryHandler(handle_confirm, pattern=r"^confirm_.+$")
            ],
            STEP_FIX_SELECT: [
                CallbackQueryHandler(handle_fix_select, pattern=r"^(fix_\d+|back_to_summary)$"),
                CallbackQueryHandler(handle_fix_choice, pattern=r"^choice_\d+_.+$"),
            ],
            STEP_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description)
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("reply", admin_reply))

    # Все остальные текстовые сообщения → пересылка админу
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_user_message
    ))

    print("🤖 Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()