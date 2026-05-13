"""Script 2: For each tracked wallet, count NFT purchases per collection in the lookback window. Alert if >= threshold."""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import opensea, state, telegram
from lib.config import WHALE_WALLETS, WHALE_NFT_THRESHOLD, LOOKBACK_MINUTES, require_secrets
from lib.telegram import esc

STATE_KEY = "whale_tracker"


def main():
    require_secrets("OPENSEA_API_KEY")

    if not WHALE_WALLETS:
        print("[whale] No wallets configured in WHALE_WALLETS. Edit lib/config.py to add some.")
        return

    st = state.load(STATE_KEY)
    seen_keys: set[str] = set(st.get("seen_keys") or [])

    now = datetime.now(timezone.utc)
    after_unix = int(now.timestamp() - (LOOKBACK_MINUTES * 60))

    alerts = 0
    for label, address in WHALE_WALLETS.items():
        address = (address or "").lower()
        if not address.startswith("0x"):
            print(f"[whale] skipping {label}: invalid address {address!r}")
            continue

        try:
            events = opensea.events_by_account(address, event_type="sale", after_unix=after_unix, limit=50)
        except opensea.OpenSeaError as e:
            print(f"[whale] {label} events failed: {e}")
            continue

        # Count purchases per collection (only events where this address is the buyer).
        purchases_by_collection: dict[str, int] = {}
        for ev in events:
            buyer = (ev.get("buyer") or "").lower()
            if buyer != address:
                continue
            nft = ev.get("nft") or {}
            slug = nft.get("collection") or nft.get("collection_slug")
            if not slug:
                continue
            purchases_by_collection[slug] = purchases_by_collection.get(slug, 0) + 1

        for slug, count in purchases_by_collection.items():
            if count < WHALE_NFT_THRESHOLD:
                continue
            # Dedup key: address + collection + day. One alert per wallet per collection per day.
            day = now.strftime("%Y-%m-%d")
            key = f"{address}:{slug}:{day}"
            if key in seen_keys:
                continue

            opensea_url = f"https://opensea.io/collection/{slug}"
            wallet_url = f"https://opensea.io/{address}"
            msg = (
                f"🐳 <b>Whale move:</b> {esc(label)}\n"
                f"• Bought <b>{count}</b> NFTs from <a href=\"{esc(opensea_url)}\">{esc(slug)}</a> "
                f"(last {LOOKBACK_MINUTES} min)\n"
                f"• Wallet: <a href=\"{esc(wallet_url)}\">{esc(address)}</a>"
            )
            telegram.send(msg)
            seen_keys.add(key)
            alerts += 1

        time.sleep(1)

    # Trim state.
    if len(seen_keys) > 2000:
        seen_keys = set(list(seen_keys)[-1000:])

    state.save(STATE_KEY, {
        "seen_keys": sorted(seen_keys),
        "last_run": now.isoformat(),
    })
    print(f"[whale] done. alerts sent: {alerts}")


if __name__ == "__main__":
    main()
