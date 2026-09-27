# 🎭 Gigs Archive — Telegram Bot for Event Posters

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![aiogram](https://img.shields.io/badge/aiogram-3.x-green.svg)](https://docs.aiogram.dev)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Гиги Архив** — это Telegram-бот для публикации афиш мероприятий. 
Пользователи отправляют постеры, модераторы проверяют, и одобренные события публикуются в канале.

## ✨ Возможности

### Для пользователей
- 📸 **Отправка афиш** — просто отправьте фото с описанием
- 🔒 **Анонимность** — выберите, показывать имя или нет
- 📅 **Удобный выбор даты** — календарь для выбора даты события
- 📊 **Статистика** — отслеживайте свои публикации
- 🗓️ **Еженедельная подборка** — получайт>е дайджест событий по пятницам
- 🔔 **Подписка** — автоматическая рассылка подборки в DM

### Для модераторов
- ✅ **Двухэтапная модерация** — одобрение → финализация описания
- 📋 **Список ожидающих** — `/pending` показывает все афиши в очереди
- 📊 **Статистика модератора** — `/mystats` показывает вашу активность
- 🔗 **Быстрые ссылки** — переход к сообщению в чате модерации
- ✏️ **Редактирование** — модератор может улучшить описание перед публикацией

### Технические особенности
- 🌐 **i18n поддержка** — локализация через JSON файлы
- 💾 **SQLite база** — легковесное хранение данных
- 🤖 **Asyncio scheduler** — автоматические рассылки по расписанию
- 📝 **Логирование** — подробные логи для отладки
- 🔄 **FSM состояния** — правильная обработка многошаговых сценариев

## 🚀 Быстрый старт

### Требования
- Python 3.11+
- Telegram Bot Token (от [@BotFather](https://t.me/BotFather))
- SQLite (встроен в Python)

### Установка

```bash
# 1. Клонируйте репозиторий
git clone https://github.com/yourusername/Gigs_Archive.git
cd Gigs_Archive

# 2. Создайте виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. Установите зависимости
pip install -r requirements.txt

# 4. Настройте переменные окружения
cp .env.example .env
# Отредактируйте .env и добавьте ваш BOT_TOKEN

```

### Запуск
```bash
python main.py
```

## 📋 Команды бота

### Основные команды
| Команда | Описание |
|---------|----------|
| `/start` | 🚀 Запустить бота |
| `/help` | 📚 Показать справку |
| `/poster` | 📸 Отправить новую афишу |
| `/stats` | 📊 Ваша статистика публикаций |
| `/summary` | 🗓️ Еженедельная подборка событий |
| `/cancel` | ❌ Отменить текущее действие |
| `/sub_on` | ✅ Подписаться на рассылку по пятницам |
| `/sub_off` | ❌ Отписаться от рассылки |

### Команды модератора
| Команда | Описание |
|---------|----------|
| `/pending` | ⏳ Показать афиши на модерации |
| `/mystats` | 📊 Статистика модератора |

## 🌐 Web Site (Gigs Archive Website)

Сайт на **FastAPI + Jinja2 + SQLite** — публичная витрина афиш и статей
(интервью/рецензии) с админ-панелью. Сайт работает **независимо от бота**:
общая база SQLite, но отдельные таблицы (`web_articles`) и свой запуск.

### Требования

- Python 3.11+
- Зависимости из `requirements-web.txt` (ставятся отдельно от бота)

### Установка и запуск (изолированно от бота)

```bash
# 1. Отдельное виртуальное окружение для сайта (не смешивать с ботом)
python3 -m venv .venv-web
source .venv-web/bin/activate   # Linux/Mac
# .venv-web\Scripts\activate    # Windows

# 2. Зависимости только для сайта
pip install -r requirements-web.txt

# 3. Инициализация таблиц сайта в общей БД (создаст gigs_archive.db, если его нет)
python -m web.manage init-db

# 4. Добавьте себя в админы сайта (Telegram-username, без @)
python -m web.manage add-admin your_telegram_username

# 5. (Опционально) демо-контент — статья + пример афиши
python -m web.manage seed-demo

# 6. Запуск dev-сервера
python -m web.manage runserver                  # http://127.0.0.1:8000
python -m web.manage runserver --reload         # с авто-перезагрузкой (разработка)
python -m web.manage runserver --host 0.0.0.0 --port 8080   # доступ извне
```

Открыть: `http://127.0.0.1:8000` — главная; `/posters`, `/articles`;
админка — `/admin` (вход по Telegram-username из списка админов).

### Конфигурация (переменные окружения / `.env`)

Сайт читает тот же `.env`, что и бот, но **может работать вообще без него** —
у всех веб-переменных безопасные значения по умолчанию:

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DATABASE_PATH` | `gigs_archive.db` | Общая SQLite-база (тот же файл, что у бота) |
| `SECRET_KEY` | авто-генерация | Подпись сессий; при первом запуске сохраняется в `web/.secret_key` |
| `ADMIN_USERNAMES` | пусто | Доп. список админов через запятую (см. также `web/admins.json`) |
| `SITE_TITLE` | `Gigs Archive` | Название сайта |
| `TELEGRAM_CHANNEL` | `Gigs_archive` | Ссылка на канал в шапке/подвале |
| `POSTER_IMAGE_URL_TEMPLATE` | пусто | Шаблон URL картинок афиш, напр. `https://raw.example.org/photos/{chat_id}_{message_id}.jpg` |
| `POSTERS_DIR` | `web_static/posters` | Папка локальных импортированных афиш |
| `BOT_TOKEN`, `MAIN_CHANNEL_ID` | пусто | Нужны **только** импортеру афиш из Telegram |

### Импорт афиш из Telegram (опционально)

Скачивает фото одобренных постеров (по `file_id` из общей БД) в `web_static/posters/`:

```bash
python -m web.importer             # импорт всех афиш без картинки
python -m web.importer --limit 20  # только первые 20
python -m web.importer --force     # перезагрузить даже уже импортированные
```

Требует `BOT_TOKEN` в `.env`. Безопасно запускать повторно и параллельно с ботом.

### Администрирование

```bash
python -m web.manage list-admins            # кто может входить в /admin
python -m web.manage remove-admin username  # удалить из web/admins.json
```

Модель прав: **ADMIN** (username в `ADMIN_USERNAMES` или `web/admins.json`) —
создание/редактирование/публикация статей; **USER** — все остальные, только чтение
публичной части. Сессии — подписанные cookie (`itsdangerous`), срок 7 дней.

### Продакшен-запуск

```bash
uvicorn web.app:app --host 0.0.0.0 --port 8000 --workers 2
```

Пример systemd-unit:

```ini
[Unit]
Description=Gigs Archive Web
After=network.target

[Service]
WorkingDirectory=/opt/Gigs_Archive
ExecStart=/opt/Gigs_Archive/.venv-web/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Health-check: `GET /healthz` (статус БД). Документация API намеренно отключена
(`docs_url=None`).

### Проверка

```bash
# Синтаксис
python -m py_compile web/*.py web/routes/*.py

# Приложение собирается и стартует
python -c "from web.app import app; print('✅ OK')"
```

## 📁 Структура проекта

```py
Gigs_Archive/
├── config.py
├── .env                                # Secrets (token, IDs)
├── .env.example                        # Example of sructure of envfle
├── gigs_archive.db                     # The DB
├── LICENSE
├── main.py                             # Entry point (run this) — Telegram bot
├── README.md
├── requirements.txt                    # Requirements for running bot
├── requirements-web.txt                # Requirements for running web site
├── bot                                 # Telegram bot logic
│   ├── handlers.py                     # User handlers
│   ├── __init__.py
│   ├── keyboards.py                    # All inline keyboards
│   ├── moderator_handlers.py           # Moderator handlers
│   ├── moderator_states.py             # States of FSM for moderator flow
│   ├── states.py                       # States of FSM for user flow
│   └── summary_handlers.py             # Summary handlers (separate file 'couse of a lot of logic)
├── db
│   ├── add_columns.py                  # 
│   ├── add_indexes.py                  # } Helpers for creation columns and indexes in old type db
│   ├── add_moderation_columns.py       # 
│   ├── crud.py                         # DB operations (create, read, update)
│   ├── __init__.py
│   └── models.py                       # SQLAlchemy tables (User, Poster)
├── locales
│   └── ru.json                         # Punch-lines collected there
├── web                                 # Web site (FastAPI, runs independently of the bot)
│   ├── app.py                          # App factory + /healthz
│   ├── config.py                       # Web settings (env with safe defaults)
│   ├── database.py                     # SQLAlchemy models (User, Poster, Article)
│   ├── auth.py                         # Admin session cookie / privilege check
│   ├── manage.py                       # Admin CLI (init-db, add-admin, runserver…)
│   ├── importer.py                     # Telegram → web poster image importer
│   ├── posters.py / helpers.py         # URL/format helpers, markdown renderer
│   ├── routes/                         # public.py (site), admin.py (/admin CRUD)
│   └── templates/                      # Jinja2 templates (public + admin)
├── web_static                          # Static assets; posters/ — imported images
└── utils                               # Helpers
    ├── scheduler.py
    ├── helpers.py                      # Formatting, date helpers, logger
    ├── i18n.py                         # Localization
    └── __init__.py
```
```py 
# RU
├── config.py # Конфигурация бота
├── .env # Секреты (токен, ID)
├── .env.example # Пример .env файла
├── gigs_archive.db # База данных SQLite
├── main.py # Точка входа
├── README.md # Документация
├── requirements.txt # Зависимости Python
├── bot/ # Логика бота
│ ├── handlers.py # Обработчики пользователей
│ ├── keyboards.py # Inline клавиатуры
│ ├── moderator_handlers.py # Обработчики модераторов
│ ├── moderator_states.py # FSM состояния модерации
│ ├── states.py # FSM состояния пользователей
│ ├── summary_handlers.py # Еженедельные подборки
│ └── helpers/
│ └── scheduler.py # Планировщик задач
├── db/ # База данных
│ ├── models.py # SQLAlchemy модели
│ ├── crud.py # CRUD операции
│ └── add_*.py # Миграции БД
├── locales/ # Локализация
│ └── ru.json # Русские переводы
└── utils/ # Утилиты
├── helpers.py # Форматирование, ссылки
├── i18n.py # Интернационализация
└── logger.py # Настройка логирования
```

## ⚙️ Конфигурация

### Переменные окружения (.env)

```env
# Telegram Bot
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Channels & Chats
MAIN_CHANNEL_ID=-1001234567890
TEST_CHANNEL_ID=-1009876543210
MODERATION_CHAT_ID=-1001112223334

# Admins (comma-separated Telegram IDs)
ADMIN_IDS=123456789,987654321

# Database
DATABASE_PATH=./gigs_archive.db

# Debug Mode (true/false)
DEBUG_MODE=false
```

## 🔄 Миграции базы данных
Если вы обновляете существующую базу, выполните миграции:

```bash
# Добавить новые колонки
python db/add_columns.py
python db/add_moderation_columns.py
python db/add_indexes.py
```

## 📊 Мониторинг
Проверка логов

```bash
# В реальном времени
tail -f bot.log

# Последние 100 строк
tail -n 100 bot.log
```

## Проверка статуса
```bash
# Если используете systemd
sudo systemctl status gigs-archive

# Просмотр логов systemd
sudo journalctl -u gigs-archive -f
```

## 🛠️ Разработка
Запуск в режиме отладки
```py
# В .env установите:
DEBUG_MODE=true
```
```bash
# Запустите бота
python main.py
```

## Тестирование команд

```bash
# Проверка синтаксиса
python -m py_compile main.py bot/*.py

# Тест импортов
python -c "from main import main; print('✅ OK')"
```

## 📝 Лицензия
MIT License — см. файл [LICENSE](LICENSE) для деталей.
## 🤝 Поддержка
Вопросы: @tehnokratgod
Канал: @Gigs_archive
Бот: @Gigs_archive_bot
Баги: Создайте issue в репозитории или обратитесь к @tehnokratgod

#### Создано с ❤️ для организаторов событий