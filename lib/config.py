"""Central config. Reads secrets from environment (GitHub Actions secrets in prod, .env locally)."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

OPENSEA_API_KEY = os.environ.get("OPENSEA_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# Usernames to look for in holders of new collections (script 1).
TARGET_HOLDER_USERNAMES = ["Samyb_NFT", "TMA420", "mrdestroyer", "Paschamo"]

# Wallets to monitor for whale activity (script 2). Label is shown in the Telegram alert.
WHALE_WALLETS: dict[str, str] = {
    "SAMY":         "0x9723cc792c32dca2744690f99103d095ea149e82",
    "TMA":          "0xdbd47f66aa2f00b3db03397f260ce9728298c495",
    "mrDestroyer":  "0x6de8bdd19cd76b89ea2eb1ab6d9b245433652ef9",
    "DustDegenTony":"0x7288968b6047bb6a386d92ff58934d8df18bf7e5",
    "DT1":          "0xbff8b65222b51acdc6a0ba21d31e5a31fb0c716f",
    "DT2":          "0x3e7fe21664993a4736ef827dab3eaa3c194f3a7e",
    "DT3":          "0x88f556c6911d57c3970b4f9ad2a8a14263b6fffa",
    "TMAvault":     "0x71d13056cb985d985ae0f1877818b91d9c4cbd05",
    "Paschamo":     "0xf06bed3f0dad7932d8d00fe48c36751f5c10be23",
    "Bernoluti":    "0x266b0fad82daeafbcfdf95b3c71b8c43dc5c3039",
    "Dynamite":     "0x40723465ae65a3b6c689c37112fc1f2b3476aec2",
}

# Whale alert threshold: alert when a tracked wallet buys this many NFTs from one collection within the lookback window.
WHALE_NFT_THRESHOLD = 5

# Mint tracker alert threshold: alert when a new collection has at least this many mints.
MINT_COUNT_THRESHOLD = 100

# How far back to scan for activity each run, in minutes. Should match cron interval (or slightly more for overlap).
LOOKBACK_MINUTES = 20

# Paths
ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(exist_ok=True)


def require_secrets(*names: str) -> None:
    """Fail fast if a required secret isn't set."""
    missing = [n for n in names if not os.environ.get(n, "").strip()]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
