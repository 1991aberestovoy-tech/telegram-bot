import logging
import os
from html import escape
from urllib.parse import quote_plus
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
import httpx

# ─── Настройки ───────────────────────────────────────────────────────────────

def load_local_env(path: str = ".env") -> None:
    """Loads simple KEY=VALUE pairs from a local .env file."""
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()
TOKEN = os.environ["BOT_TOKEN"]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Open Library API ─────────────────────────────────────────────────────────
SEARCH_URL = "https://openlibrary.org/search.json"
BOOK_URL   = "https://openlibrary.org"
SEARCH_FIELDS = (
    "key,title,author_name,first_publish_year,subject,isbn,cover_i,"
    "number_of_pages_median,ia,public_scan_b,has_fulltext,ebook_access,"
    "availability"
)

async def search_books(query: str, limit: int = 5) -> list[dict]:
    """Ищет книги через Open Library API."""
    params = {"q": query, "limit": limit, "fields": SEARCH_FIELDS}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(SEARCH_URL, params=params)
        r.raise_for_status()
        data = r.json()
    return data.get("docs", [])

def get_read_url(book: dict):
    """Возвращает открытую ссылку для чтения, если она есть."""
    availability = book.get("availability") or {}
    ia_ids = book.get("ia", [])
    identifier = availability.get("identifier")

    if availability.get("is_readable") and identifier:
        return f"https://archive.org/details/{identifier}/mode/2up"

    if book.get("public_scan_b") and ia_ids:
        return f"https://archive.org/details/{ia_ids[0]}/mode/2up"

    if book.get("ebook_access") == "public" and ia_ids:
        return f"https://archive.org/details/{ia_ids[0]}/mode/2up"

    return None

def get_open_library_url(book: dict):
    key = book.get("key", "")
    return f"{BOOK_URL}{key}" if key else None

def join_book_values(values, fallback: str = "—", limit=None) -> str:
    if not values:
        return fallback

    if isinstance(values, list):
        selected_values = values[:limit] if limit else values
        text = ", ".join(str(value) for value in selected_values if value)
        return text or fallback

    return str(values)

def build_sources(book: dict) -> list[tuple[str, str]]:
    """Собирает полезные внешние источники по книге."""
    title = book.get("title", "")
    authors = join_book_values(book.get("author_name"), "")
    search_query = quote_plus(" ".join(str(part) for part in [title, authors] if part))
    sources: list[tuple[str, str]] = []

    read_url = get_read_url(book)
    if read_url:
        sources.append(("Читать бесплатно", read_url))

    open_library_url = get_open_library_url(book)
    if open_library_url:
        sources.append(("Open Library", open_library_url))

    ia_ids = book.get("ia", [])
    if ia_ids:
        sources.append(("Internet Archive", f"https://archive.org/details/{ia_ids[0]}"))

    isbns = book.get("isbn", [])
    if isbns:
        sources.append(("ISBN Search", f"https://isbnsearch.org/isbn/{isbns[0]}"))

    if search_query:
        sources.append(("Google Books", f"https://books.google.com/books?q={search_query}"))
        sources.append(("WorldCat", f"https://search.worldcat.org/search?q={search_query}"))

    unique_sources = []
    seen_urls = set()
    for label, url in sources:
        if url in seen_urls:
            continue
        unique_sources.append((label, url))
        seen_urls.add(url)

    return unique_sources

def format_book(book: dict, index: int) -> str:
    """Форматирует одну книгу для вывода."""
    title   = escape(str(book.get("title", "Без названия")))
    authors = escape(join_book_values(book.get("author_name"), "Автор неизвестен"))
    year    = escape(str(book.get("first_publish_year", "—")))
    pages   = escape(str(book.get("number_of_pages_median", "—")))
    genres  = escape(join_book_values(book.get("subject"), limit=3))
    read_url = get_read_url(book)

    lines = [
        f"📚 <b>{index}. {title}</b>",
    ]

    if read_url:
        lines.append(f'✅ <b>Читать бесплатно:</b> <a href="{read_url}">открыть книгу</a>')
    else:
        lines.append("ℹ️ Открытой ссылки для чтения не нашел")

    lines.extend([
        f"✍️ Автор: {authors}",
        f"📅 Год: {year}",
        f"📄 Страниц: {pages}",
        f"🏷 Жанры: {genres}",
    ])

    return "\n".join(lines)

def build_results_keyboard(books: list[dict], result_id: str) -> InlineKeyboardMarkup:
    keyboard = []

    for index, book in enumerate(books):
        number = index + 1
        read_url = get_read_url(book)
        fallback_url = get_open_library_url(book)

        row = []
        if read_url:
            row.append(InlineKeyboardButton(f"📖 Читать {number}", url=read_url))
        elif fallback_url:
            row.append(InlineKeyboardButton(f"🔎 Карточка {number}", url=fallback_url))

        row.append(InlineKeyboardButton(f"🌐 Источники {number}", callback_data=f"sources:{result_id}:{index}"))
        keyboard.append(row)

    return InlineKeyboardMarkup(keyboard)

def format_sources(book: dict, index: int) -> str:
    title = escape(str(book.get("title", "Без названия")))
    sources = build_sources(book)

    if not sources:
        return f"🌐 <b>Источники для {index}. {title}</b>\n\nПока не нашел надежных ссылок."

    lines = [f"🌐 <b>Источники для {index}. {title}</b>"]
    for number, (label, url) in enumerate(sources, 1):
        lines.append(f'{number}. <a href="{url}">{escape(label)}</a>')

    return "\n".join(lines)

async def send_search_results(message, context: ContextTypes.DEFAULT_TYPE, search_term: str):
    wait_msg = await message.reply_text(f"🔍 Ищу <b>{escape(search_term)}</b>...", parse_mode="HTML")

    try:
        books = await search_books(search_term)
    except Exception as e:
        logger.error(f"Ошибка API: {e}")
        await wait_msg.edit_text("❌ Ошибка при поиске. Попробуй позже.")
        return

    if not books:
        await wait_msg.edit_text(
            f"😔 По запросу <b>{escape(search_term)}</b> ничего не найдено.\n\nПопробуй другой запрос.",
            parse_mode="HTML"
        )
        return

    result_counter = context.user_data.get("result_counter", 0) + 1
    result_id = str(result_counter)
    context.user_data["result_counter"] = result_counter

    result_sets = context.user_data.setdefault("result_sets", {})
    result_sets[result_id] = books
    for old_result_id in list(result_sets.keys())[:-10]:
        result_sets.pop(old_result_id, None)

    results = [f"📋 <b>Результаты:</b> {escape(search_term)}\n"]
    for i, book in enumerate(books, 1):
        results.append(format_book(book, i))
        results.append("─" * 24)

    results.append("💡 Данные: Open Library")
    full_text = "\n".join(results)

    if len(full_text) > 4000:
        full_text = full_text[:4000] + "\n...\n(текст обрезан)"

    await wait_msg.edit_text(
        full_text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=build_results_keyboard(books, result_id),
    )

# ─── Handlers ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Привет! Я бот для поиска книг 📚\n\n"
        "Просто напиши название книги, автора или тему — и я найду информацию!\n\n"
        "📌 <b>Команды:</b>\n"
        "/start — приветствие\n"
        "/help  — помощь\n"
        "/top   — популярные книги\n\n"
        "🔍 Например: <code>Мастер и Маргарита</code> или <code>Python programming</code>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "• Напиши название книги на любом языке\n"
        "• Или имя автора: <code>Толстой</code>\n"
        "• Или тему: <code>machine learning</code>\n\n"
        "Если книга есть в открытом доступе, я сначала дам кнопку для чтения.\n"
        "Кнопка «Источники» покажет Open Library, Internet Archive, Google Books, WorldCat и ISBN Search."
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⚡ Гарри Поттер",      callback_data="search:Harry Potter")],
        [InlineKeyboardButton("💍 Властелин колец",   callback_data="search:Lord of the Rings")],
        [InlineKeyboardButton("👁 1984 (Оруэлл)",     callback_data="search:1984 Orwell")],
        [InlineKeyboardButton("🐉 Игра Престолов",    callback_data="search:Game of Thrones")],
        [InlineKeyboardButton("🤖 Python для начинающих", callback_data="search:Python programming beginners")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔥 <b>Популярные запросы</b> — выбери или напиши свой:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if not query:
        return

    await send_search_results(update.message, context, query)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback = update.callback_query
    await callback.answer()

    if callback.data.startswith("search:"):
        search_term = callback.data[len("search:"):]
        await send_search_results(callback.message, context, search_term)
        return

    if callback.data.startswith("sources:"):
        _, result_id, book_index_text = callback.data.split(":", 2)
        book_index = int(book_index_text)
        books = context.user_data.get("result_sets", {}).get(result_id, [])

        if book_index >= len(books):
            await callback.message.reply_text("Источники устарели. Повтори поиск еще раз.")
            return

        book = books[book_index]
        keyboard = []
        read_url = get_read_url(book)
        if read_url:
            keyboard.append([InlineKeyboardButton("📖 Читать бесплатно", url=read_url)])

        open_library_url = get_open_library_url(book)
        if open_library_url:
            keyboard.append([InlineKeyboardButton("🔎 Карточка Open Library", url=open_library_url)])

        await callback.message.reply_text(
            format_sources(book, book_index + 1),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
        )

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
