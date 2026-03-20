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

## 📁 Структура проекта

```py
Gigs_Archive/
├── config.py
├── .env                                # Secrets (token, IDs)
├── .env.example                        # Example of sructure of envfle
├── gigs_archive.db                     # The DB
├── LICENSE
├── main.py                             # Entry point (run this)
├── README.md
├── requirements.txt                    # Requirements for running bot
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