"""Russian labels/filters for the public web site.

The site is Russian-first; only universally understood tokens stay in Latin
(Telegram, Admin, 404, page numbers).
"""

MONTHS_GENITIVE = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

WEEKDAYS = {
    0: "понедельник", 1: "вторник", 2: "среда", 3: "четверг",
    4: "пятница", 5: "суббота", 6: "воскресенье",
}

KIND_LABELS = {
    "article": "Статья",
    "interview": "Интервью",
    "review": "Репортаж",
}


def month_name(dt) -> str:
    """Full genitive month name, e.g. 'сентября'."""
    return MONTHS_GENITIVE[dt.month - 1]


SHORT_MONTHS = [
    "янв", "фев", "мар", "апр", "мая", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]


def short_month(dt) -> str:
    """Short nominative month for badges, e.g. 'окт'."""
    return SHORT_MONTHS[dt.month - 1]


def weekday_name(dt) -> str:
    return WEEKDAYS[dt.weekday()]


def ru_date(dt) -> str:
    """07 сентября 2026"""
    return f"{dt.day} {month_name(dt)} {dt.year}"


def ru_datetime(dt) -> str:
    """суббота, 07 сентября 2026, 20:00"""
    return (
        f"{weekday_name(dt)}, {dt.day:02d} {month_name(dt)} {dt.year}, "
        f"{dt:%H:%M}"
    )


def ru_date_short(dt) -> str:
    """07 сент — compact badge form."""
    return f"{dt.day:02d} {short_month(dt)}"


def kind_label(kind: str | None) -> str:
    return KIND_LABELS.get(kind or "", kind or "")
