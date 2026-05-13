"""Script 3: Track new collections' mint counts. Alert when a collection's total_supply reaches the threshold."""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import opensea, state, telegram
from lib.config import MINT_COUNT_THRESHOLD, require_secrets
from lib.telegram import esc

STATE_KEY = "mint_tracker"


def supply_of(meta: dict, stats: dict) -> int:
    """Best-effort: read mint/supply count from collection metadata or stats."""
    for key in ("total_supply", "supply"):
        v = meta.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    total = (stats or {}).get("total", {}) or {}
    for key in ("num_owners", "sales"):
        v = total.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    return 0


def main():
    require_secrets("OPENSEA_API_KEY")

    st = state.load(STATE_KEY)
    alerted: set[str] = set(st.get("alerted_slugs") or [])
    is_first_run = not alerted  # No prior state means first run.

    now = datetime.now(timezone.utc)

    collections = opensea.list_collections(order_by="created_date", limit=100)
    print(f"[mint] scanning {len(collections)} recent collections")

    # On the first run, seed alerted set with anything already above threshold so we
    # don't fire on pre-existing collections — only on ones that cross threshold AFTER we start watching.
    if is_first_run:
        seeded = 0
        for c in collections:
            slug = c.get("collection") or c.get("slug")
            if slug:
                alerted.add(slug)
                seeded += 1
        state.save(STATE_KEY, {"alerted_slugs": sorted(alerted), "last_run": now.isoformat()})
        print(f"[mint] first run: seeded {seeded} slugs, no alerts sent.")
        return

    alerts = 0
    for c in collections:
        slug = c.get("collection") or c.get("slug")
        if not slug or slug in alerted:
            continue

        try:
            meta = opensea.collection(slug)
            stats = opensea.collection_stats(slug)
        except opensea.OpenSeaError as e:
            print(f"[mint] {slug} fetch failed: {e}")
            continue

        supply = supply_of(meta, stats)
        if supply < MINT_COUNT_THRESHOLD:
            continue

        name = meta.get("name") or slug
        opensea_url = f"https://opensea.io/collection/{slug}"
        twitter = meta.get("twitter_username")
        x_line = f"\n• X: <a href=\"https://x.com/{esc(twitter)}\">{esc(twitter)}</a>" if twitter else ""

        msg = (
            f"⛏️ <b>Mint threshold hit:</b> <a href=\"{esc(opensea_url)}\">{esc(name)}</a>\n"
            f"• Mints: <b>{supply}</b> (threshold {MINT_COUNT_THRESHOLD})"
            f"{x_line}\n"
            f"• OpenSea: <a href=\"{esc(opensea_url)}\">{esc(opensea_url)}</a>"
        )
        try:
            telegram.send(msg)
        except telegram.TelegramAuthError:
            print("[mint] Aborting: Telegram auth failed.")
            state.save(STATE_KEY, {"alerted_slugs": sorted(alerted), "last_run": now.isoformat()})
            return
        alerted.add(slug)
        alerts += 1
        time.sleep(1)

    if len(alerted) > 5000:
        alerted = set(list(alerted)[-3000:])

    state.save(STATE_KEY, {
        "alerted_slugs": sorted(alerted),
        "last_run": now.isoformat(),
    })
    print(f"[mint] done. alerts sent: {alerts}")


if __name__ == "__main__":
    main()
