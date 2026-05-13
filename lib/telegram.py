"""Telegram sender. Messages use HTML formatting so links render as clickable."""
import html
import requests
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send(text: str, disable_preview: bool = True) -> None:
    """Send a Telegram message. Silently logs and continues on failure so one bad send doesn't kill the run."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[telegram] Skipping send — bot token or chat id not configured.")
        print(text)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": disable_preview,
            },
            timeout=15,
        )
        if r.status_code != 200:
            print(f"[telegram] send failed {r.status_code}: {r.text[:300]}")
    except requests.RequestException as e:
        print(f"[telegram] send error: {e}")


def esc(s: str | None) -> str:
    """Escape a value for safe inclusion in HTML-formatted Telegram message."""
    return html.escape(str(s) if s is not None else "")
