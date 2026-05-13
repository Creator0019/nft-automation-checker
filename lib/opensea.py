"""OpenSea API v2 client. Docs: https://docs.opensea.io/reference/api-overview"""
import time
import requests
from .config import OPENSEA_API_KEY

BASE = "https://api.opensea.io/api/v2"
DEFAULT_CHAIN = "ethereum"


class OpenSeaError(Exception):
    pass


def _headers() -> dict:
    h = {"accept": "application/json"}
    if OPENSEA_API_KEY:
        h["x-api-key"] = OPENSEA_API_KEY
    return h


def _get(path: str, params: dict | None = None, retries: int = 3) -> dict:
    url = f"{BASE}{path}"
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_headers(), params=params or {}, timeout=20)
            if r.status_code == 429:
                # Rate limited — exponential backoff.
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 404:
                return {}
            if not r.ok:
                last_err = f"{r.status_code}: {r.text[:200]}"
                time.sleep(1)
                continue
            return r.json()
        except requests.RequestException as e:
            last_err = str(e)
            time.sleep(1)
    raise OpenSeaError(f"GET {path} failed after {retries} attempts: {last_err}")


def list_collections(order_by: str = "created_date", limit: int = 100, chain: str = DEFAULT_CHAIN) -> list[dict]:
    """List collections sorted by created_date desc (newest first)."""
    data = _get("/collections", {"order_by": order_by, "limit": limit, "chain": chain})
    return data.get("collections", []) or []


def collection_stats(slug: str) -> dict:
    """Returns total volume, floor price, sales, etc."""
    return _get(f"/collections/{slug}/stats")


def collection(slug: str) -> dict:
    """Returns metadata (twitter, discord, description, contract list, total_supply, etc.)."""
    return _get(f"/collections/{slug}")


def collection_nfts(slug: str, limit: int = 50, next_cursor: str | None = None) -> dict:
    """Returns NFTs in a collection. Used to derive holder addresses."""
    params = {"limit": min(limit, 50)}
    if next_cursor:
        params["next"] = next_cursor
    return _get(f"/collection/{slug}/nfts", params)


def account(address_or_username: str) -> dict:
    """Fetch an OpenSea account profile. Accepts either a 0x address or a username."""
    return _get(f"/accounts/{address_or_username}")


def events_by_account(address: str, event_type: str = "sale", after_unix: int | None = None,
                      chain: str = DEFAULT_CHAIN, limit: int = 50) -> list[dict]:
    """Fetch recent events for a wallet. event_type: sale | transfer | order | cancel | redemption."""
    params = {"event_type": event_type, "limit": min(limit, 50), "chain": chain}
    if after_unix:
        params["after"] = after_unix
    data = _get(f"/events/accounts/{address}", params)
    return data.get("asset_events", []) or []


def resolve_username_to_address(username: str) -> str | None:
    """Look up an OpenSea username and return the 0x address. Returns None if not found."""
    data = account(username)
    addr = data.get("address")
    return addr.lower() if addr else None


def collection_holders(slug: str, max_nfts: int = 500) -> dict[str, int]:
    """Walk a collection's NFTs and aggregate owner address → count. Capped at max_nfts to limit API usage."""
    holders: dict[str, int] = {}
    cursor = None
    fetched = 0
    while fetched < max_nfts:
        data = collection_nfts(slug, limit=50, next_cursor=cursor)
        nfts = data.get("nfts", []) or []
        if not nfts:
            break
        for nft in nfts:
            owners = nft.get("owners") or []
            for o in owners:
                addr = (o.get("address") or "").lower()
                if addr:
                    holders[addr] = holders.get(addr, 0) + int(o.get("quantity", 1) or 1)
        fetched += len(nfts)
        cursor = data.get("next")
        if not cursor:
            break
    return holders
