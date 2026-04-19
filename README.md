# Telegram Book Bot

Бот ищет книги через Open Library и отвечает в Telegram.

## Railway

1. Создай новый проект в Railway.
2. Выбери Deploy from GitHub repo.
3. Подключи репозиторий `1991aberestovoy-tech/telegram-bot`.
4. В Variables добавь переменную `BOT_TOKEN` со значением токена от BotFather.
5. Нажми Deploy.

Railway возьмет команду запуска из `Procfile`:

```text
worker: python book_bot.py
```
