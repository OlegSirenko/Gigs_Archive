# web/telegram_images.py
from web.config import settings

def get_bot_api_image_url(photo_file_id: str) -> str | None:
    """Официальный способ получить ссылку через Bot API."""
    if not photo_file_id or not settings.secret_key:
        return None
    try:
        import requests
        url = f"https://api.telegram.org/bot{settings.secret_key}/getFile"
        response = requests.get(url, params={"file_id": photo_file_id}, timeout=5)
        data = response.json()
        if data.get("ok"):
            file_path = data["result"]["file_path"]
            return f"https://api.telegram.org/file/bot{settings.secret_key}/{file_path}"
        return None
    except Exception as e:
        print(f"!!! [BOT API ERROR] {e}")
        return None

def get_poster_image_url(poster) -> str | None:
    """Возвращает URL прокси для картинки."""
    if not poster or not hasattr(poster, 'photo_file_id') or not poster.photo_file_id:
        return None
    return f"/api/poster-image/{poster.id}"