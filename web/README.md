# 🛠 Admin Panel — `/admin`

Панель администратора веб-сайта (FastAPI + Jinja2). Вход restricted для
Telegram-админов из списка: **никнейм + постоянный пароль**.

English summary at the end of this file.

---

## Где что лежит

| Файл | Назначение |
|---|---|
| `web/routes/admin.py` | Все маршруты панели: login/logout, dashboard, список админов, выдача/ротация паролей, CRUD статей |
| `web/auth.py` | Сессии (подписанные cookie), `require_admin()` |
| `web/passwords.py` | Генерация и PBKDF2-хэширование постоянных паролей, `AdminPasswordStore` |
| `web/manage.py` | CLI: админы и пароли (`add-admin`, `gen-passwords`, …) |
| `web/admins.json` | Список никнеймов админов (секретом не является) |
| `web/admin_passwords.json` | **СЕКРЕТ**: хэши паролей. В `.gitignore`, chmod 0600 |
| `web/templates/admin/` | `login.html`, `dashboard.html`, `admins.html`, `password_shown.html`, `article_form.html`, `base_admin.html` |

---

## Как устроен вход

1. Открываете `/admin/login`, вводите **Telegram-никнейм** из списка админов
   и **постоянный пароль**.
2. Никнейм проверяется по `ADMIN_USERNAMES` (env) + `web/admins.json`.
3. Пароль сверяется с PBKDF2-HMAC-SHA256-хэшем из
   `web/admin_passwords.json` (240 000 итераций, сравнение за
   постоянное время).
4. При успехе ставится подписанная session-cookie (`gigs_session`,
   HttpOnly, SameSite=Lax, срок — неделя).

⚠️ Один только никнейм больше не пускает — пароль обязателен.

---

## Постоянные пароли: генерация

Пароль генерируется **один раз**, показывается **один раз** (таблица в CLI
или страница `/admin/admins/<ник>/rotate`), после чего на диске остаётся
только хэш. Восстановить забытый пароль невозможно — только перевыпустить.

### CLI (из корня проекта)

```bash
python -m web.manage list-admins                       # кто есть и у кого нет пароля
python -m web.manage gen-passwords                     # выпустить пароли ВСЕМ админам списка
                                                       # (у кого уже есть — не трогаем)
python -m web.manage gen-passwords --all               # перевыпустить и существующим
python -m web.manage gen-passwords --rotate            # то же, что --all (с предупреждением)
python -m web.manage gen-passwords --length 20         # длина (мин. 8, по умолчанию 16)

python -m web.manage gen-password --for tehnokrat   # одному админу
python -m web.manage gen-password --for tehnokrat --rotate
python -m web.manage set-password --for tehnokrat     # ввести свой пароль вручную (min 8)

python -m web.manage add-admin tehnokrat              # добавить в список + сразу выдать пароль
python -m web.manage remove-admin tehnokrat           # убрать из списка + удалить хэш
```

(Команды `--for` принимают ник без `@`, регистр не важен.)

### Из панели (нужен активный логин админа)

- `/admin/admins` — таблица «ник → состояние пароля» + форма ротации;
- кнопка **Перевыпустить пароль** вызывает
  `POST /admin/admins/<username>/rotate` и показывает новый пароль один раз
  (страница отдаётся с `Cache-Control: no-store`).

### Что происходит при добавлении нового админа

Добавили ник в `web/admins.json` или через env `ADMIN_USERNAMES`?
Он появится в списке, но войти не сможет, пока у него нет пароля —
панель входа подскажет команду:

```bash
python -m web.manage gen-password --for <новый_ник>
# или разом всем:
python -m web.manage gen-passwords
```

На дашборде до тех пор висит баннер «админы без пароля».

---

## Безопасность / эксплуатация

- **Алфавит паролей** исключает похожие символы (`O0oIl1`) и пунктуацию —
  пароль удобно продиктовать/переслать и набрать.
- Хранится только `{kdf, iterations, salt_hex, hash_hex}`; plaintext нигде
  не логируется и не сохраняется.
- `web/admin_passwords.json` и `web/.secret_key` — секреты, не коммитить
  (добавлены в `.gitignore`); права `0600` ставятся автоматически.
- Утрата файла хэшей = потеря всех паролей: перегенерируйте
  `gen-passwords --all` и сообщите новые админам.
- Ротация мгновенно отключает старый пароль (сессии при этом живут до конца
  срока cookie — при компрометации удалите ещё и `web/.secret_key`, чтобы
  сбросить подписи сессий).
- `next`-редирект после логина ограничен путями, начинающимися с `/admin`.

## Быстрый старт с нуля

```bash
pip install -r requirements-web.txt
python -m web.manage init-db
python -m web.manage add-admin your_telegram_username   # покажет пароль ОДИН раз
python -m web.manage runserver --reload                 # http://127.0.0.1:8000/admin
```

---

## English (short version)

The admin panel at `/admin` logs in with a Telegram nickname from the admin
list **plus a permanent password**. Passwords are generated per admin via
`python -m web.manage gen-passwords` (or one-off with `gen-password --for
<nick> [--rotate]`, or from the UI at `/admin/admins`), shown exactly once,
and stored only as PBKDF2 hashes in `web/admin_passwords.json` (git-ignored,
chmod 600). A lost password cannot be recovered — rotate it. Nickname alone
no longer grants access.
