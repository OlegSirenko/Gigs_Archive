# Gigs_Archive

```
Gigs_Archive/
├── main.py              # Entry point (run this)
├── config.py            # Settings from .env
├── .env                 # Secrets (token, IDs)
├── requirements.txt     # Dependencies
│
├── db/                  # Database layer
│   ├── models.py        # SQLAlchemy tables (User, Poster)
│   └── crud.py          # DB operations (create, read, update)
│
├── bot/                 # Telegram bot logic
│   ├── handlers.py      # All routers (commands, poster, moderation)
│   ├── keyboards.py     # All inline keyboards
│   └── states.py        # FSM states for poster flow
│
├── services/            # Business logic
│   ├── summary.py       # Weekly summary generation
│   └── notifications.py # User notifications (approve/decline)
│
└── utils/               # Helpers
    └── helpers.py       # Formatting, date helpers, logger
```