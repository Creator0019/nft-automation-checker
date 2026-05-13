"""Script 1: Check OpenSea for newly created collections, alert with volume/floor/X link, and check target users in holders."""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import opensea, state, telegram
from lib.config import TARGET_HOLDER_USERNAMES, LOOKBACK_MINUTES, require_secrets
from lib.telegram import esc

STATE_KEY = "new_collections"


def resolve_targets(prev_map: dict) -> dict[str, str]:
    """Resolve target usernames → wallet address. Cache the result in state to avoid repeat lookups."""
    resolved = dict(prev_map or {})
    for username in TARGET_HOLDER_USERNAMES:
        if username in resolved and resolved[username]:
            continue
        try:
            addr = opensea.resolve_username_to_address(username)
        except opensea.OpenSeaError as e:
            print(f"[targets] failed to resolve {username}: {e}")
            continue
        if addr:
            resolved[username] = addr
            print(f"[targets] {username} -> {addr}")
        else:
            print(f"[targets] {username} not found")
    return resolved


def format_alert(c: dict, stats: dict, x_url: str | None, target_hits: dict[str, int]) -> str:
    slug = c.get("collection") or c.get("slug") or ""
    name = c.get("name") or slug
    opensea_url = f"https://opensea.io/collection/{slug}"

    s = (stats or {}).get("total", {}) or {}
    volume = s.get("volume")
    floor = s.get("floor_price")
    sales = s.get("sales")
    floor_sym = s.get("floor_price_symbol") or "ETH"

    lines = [
        f"🆕 <b>New collection:</b> <a href=\"{esc(opensea_url)}\">{esc(name)}</a>",
        f"• Volume: <b>{esc(volume)}</b> ETH",
        f"• Floor: <b>{esc(floor)}</b> {esc(floor_sym)}",
        f"• Sales: <b>{esc(sales)}</b>",
    ]
    if x_url:
        lines.append(f"• X: <a href=\"{esc(x_url)}\">{esc(x_url)}</a>")
    lines.append(f"• OpenSea: <a href=\"{esc(opensea_url)}\">{esc(opensea_url)}</a>")

    if target_hits:
        lines.append("")
        lines.append("👀 <b>Target holders found:</b>")
        for username, count in target_hits.items():
            lines.append(f"• {esc(username)}: <b>{count}</b> NFT(s)")

    return "\n".join(lines)


def main():
    require_secrets("OPENSEA_API_KEY")

    st = state.load(STATE_KEY)
    seen_slugs: set[str] = set(st.get("seen_slugs") or [])
    resolved_targets: dict[str, str] = resolve_targets(st.get("resolved_targets") or {})
    target_address_to_username = {v.lower(): k for k, v in resolved_targets.items() if v}

    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - (LOOKBACK_MINUTES * 60)

    collections = opensea.list_collections(order_by="created_date", limit=100)
    print(f"[new-collections] fetched {len(collections)} collections")

    new_alerts = 0
    for c in collections:
        slug = c.get("collection") or c.get("slug")
        if not slug or slug in seen_slugs:
            continue

        created = c.get("created_date")
        if created:
            try:
                ts = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
            except ValueError:
                ts = None
            if ts and ts < cutoff:
                # Older than our lookback window. Mark seen to avoid re-checking forever.
                seen_slugs.add(slug)
                continue

        try:
            stats = opensea.collection_stats(slug)
        except opensea.OpenSeaError as e:
            print(f"[stats] {slug} failed: {e}")
            stats = {}

        try:
            meta = opensea.collection(slug)
        except opensea.OpenSeaError as e:
            print(f"[meta] {slug} failed: {e}")
            meta = {}
        twitter = meta.get("twitter_username")
        x_url = f"https://x.com/{twitter}" if twitter else None

        target_hits: dict[str, int] = {}
        if target_address_to_username:
            try:
                holders = opensea.collection_holders(slug, max_nfts=300)
                for addr, count in holders.items():
                    if addr in target_address_to_username:
                        target_hits[target_address_to_username[addr]] = count
            except opensea.OpenSeaError as e:
                print(f"[holders] {slug} failed: {e}")

        msg = format_alert(c, stats, x_url, target_hits)
        telegram.send(msg)
        seen_slugs.add(slug)
        new_alerts += 1

        # Be gentle with rate limits.
        time.sleep(1)

    # Trim seen list so state doesn't grow forever.
    if len(seen_slugs) > 5000:
        seen_slugs = set(list(seen_slugs)[-3000:])

    state.save(STATE_KEY, {
        "seen_slugs": sorted(seen_slugs),
        "resolved_targets": resolved_targets,
        "last_run": now.isoformat(),
    })
    print(f"[new-collections] done. alerts sent: {new_alerts}")


if __name__ == "__main__":
    main()
