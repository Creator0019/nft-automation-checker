"""Telegram sender. Messages use HTML formatting so links render as clickable."""
import html
import requests
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# Module-level circuit breaker: once Telegram returns a fatal auth error (401/403/404),
# stop trying for the rest of this run. No point retrying with the same bad token.
_FATAL = False


class TelegramAuthError(RuntimeError):
    pass


def send(text: str, disable_preview: bool = True) -> None:
    """Send a Telegram message. Raises TelegramAuthError on fatal auth failure so the calling script can stop early."""
    global _FATAL
    if _FATAL:
        raise TelegramAuthError("Telegram disabled for this run due to earlier auth failure.")
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
        if r.status_code in (401, 403, 404):
            _FATAL = True
            print(f"[telegram] FATAL auth/permission error {r.status_code}: {r.text[:300]}")
            print("[telegram] Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID secrets. Suppressing further sends this run.")
            raise TelegramAuthError(f"Telegram {r.status_code}: {r.text[:200]}")
        if r.status_code != 200:
            print(f"[telegram] send failed {r.status_code}: {r.text[:300]}")
    except requests.RequestException as e:
        print(f"[telegram] send error: {e}")


def esc(s: str | None) -> str:
    """Escape a value for safe inclusion in HTML-formatted Telegram message."""
    return html.escape(str(s) if s is not None else "")
