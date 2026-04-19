import logging
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
import httpx

# ─── Настройки ───────────────────────────────────────────────────────────────
TOKEN = os.environ["BOT_TOKEN"]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Open Library API ─────────────────────────────────────────────────────────
SEARCH_URL = "https://openlibrary.org/search.json"
BOOK_URL   = "https://openlibrary.org"

async def search_books(query: str, limit: int = 5) -> list[dict]:
    """Ищет книги через Open Library API."""
    params = {"q": query, "limit": limit, "fields": "key,title,author_name,first_publish_year,subject,isbn,cover_i,number_of_pages_median"}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(SEARCH_URL, params=params)
        r.raise_for_status()
        data = r.json()
    return data.get("docs", [])

def format_book(book: dict, index: int) -> str:
    """Форматирует одну книгу для вывода."""
    title   = book.get("title", "Без названия")
    authors = ", ".join(book.get("author_name", ["Автор неизвестен"]))
    year    = book.get("first_publish_year", "—")
    pages   = book.get("number_of_pages_median", "—")
    subjects = book.get("subject", [])
    genres  = ", ".join(subjects[:3]) if subjects else "—"
    key     = book.get("key", "")
    link    = f"https://openlibrary.org{key}" if key else ""

    lines = [
        f"📚 *{index}. {title}*",
        f"✍️ Автор: {authors}",
        f"📅 Год: {year}",
        f"📄 Страниц: {pages}",
        f"🏷 Жанры: {genres}",
    ]
    if link:
        lines.append(f"🔗 [Открыть на Open Library]({link})")
    return "\n".join(lines)

# ─── Handlers ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Привет! Я бот для поиска книг 📚\n\n"
        "Просто напиши название книги, автора или тему — и я найду информацию!\n\n"
        "📌 *Команды:*\n"
        "/start — приветствие\n"
        "/help  — помощь\n"
        "/top   — популярные книги\n\n"
        "🔍 Например: `Мастер и Маргарита` или `Python programming`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Как пользоваться ботом:*\n\n"
        "• Напиши название книги на любом языке\n"
        "• Или имя автора: `Толстой`\n"
        "• Или тему: `machine learning`\n\n"
        "Бот ищет через базу *Open Library* (7+ млн книг) 🌍"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    queries = ["Harry Potter", "Lord of the Rings", "1984 Orwell"]
    keyboard = [
        [InlineKeyboardButton("⚡ Гарри Поттер",      callback_data="search:Harry Potter")],
        [InlineKeyboardButton("💍 Властелин колец",   callback_data="search:Lord of the Rings")],
        [InlineKeyboardButton("👁 1984 (Оруэлл)",     callback_data="search:1984 Orwell")],
        [InlineKeyboardButton("🐉 Игра Престолов",    callback_data="search:Game of Thrones")],
        [InlineKeyboardButton("🤖 Python для начинающих", callback_data="search:Python programming beginners")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔥 *Популярные запросы* — выбери или напиши свой:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if not query:
        return

    msg = await update.message.reply_text(f"🔍 Ищу *{query}*...", parse_mode="Markdown")

    try:
        books = await search_books(query)
    except Exception as e:
        logger.error(f"Ошибка API: {e}")
        await msg.edit_text("❌ Ошибка при поиске. Попробуй позже.")
        return

    if not books:
        await msg.edit_text(
            f"😔 По запросу *{query}* ничего не найдено.\n\nПопробуй другой запрос.",
            parse_mode="Markdown"
        )
        return

    results = [f"📋 *Результаты по запросу:* _{query}_\n"]
    for i, book in enumerate(books, 1):
        results.append(format_book(book, i))
        results.append("─" * 30)

    results.append("💡 _Данные: Open Library_")
    full_text = "\n".join(results)

    # Telegram ограничивает сообщения до 4096 символов
    if len(full_text) > 4000:
        full_text = full_text[:4000] + "\n...\n_(текст обрезан)_"

    await msg.edit_text(full_text, parse_mode="Markdown", disable_web_page_preview=True)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("search:"):
        search_term = query.data[len("search:"):]
        # Имитируем текстовый запрос
        context.user_data["cb_query"] = search_term
        wait_msg = await query.message.reply_text(f"🔍 Ищу *{search_term}*...", parse_mode="Markdown")

        try:
            books = await search_books(search_term)
        except Exception as e:
            await wait_msg.edit_text("❌ Ошибка при поиске.")
            return

        if not books:
            await wait_msg.edit_text(f"😔 Ничего не найдено по *{search_term}*.", parse_mode="Markdown")
            return

        results = [f"📋 *Результаты:* _{search_term}_\n"]
        for i, book in enumerate(books, 1):
            results.append(format_book(book, i))
            results.append("─" * 30)
        results.append("💡 _Данные: Open Library_")

        full_text = "\n".join(results)
        if len(full_text) > 4000:
            full_text = full_text[:4000] + "\n...\n_(текст обрезан)_"

        await wait_msg.edit_text(full_text, parse_mode="Markdown", disable_web_page_preview=True)

# ─── Запуск ───────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("top",   cmd_top))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
