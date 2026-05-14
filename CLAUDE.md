# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A scheduled NFT monitoring bot that runs on GitHub Actions every 15 minutes. Three independent watchers (new-collection scanner with target-holder lookup, whale wallet tracker, mint threshold tracker) hit the OpenSea API v2 and push alerts to Telegram.

The bot is **stateless across runs** — state is persisted by committing `state/*.json` back to the repo at the end of every workflow run. There is no server, database, or external store. The repo *is* the database.

## Commands

```bash
# Local dev: set OPENSEA_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID in .env (see .env.example), then:
pip install -r requirements.txt
python scripts/new_collections.py
python scripts/whale_tracker.py
python scripts/mint_tracker.py

# Syntax check everything
python -m py_compile lib/*.py scripts/*.py

# Manually trigger the workflow on GitHub
# Actions tab → "Minter Monitor" → Run workflow
```

There are no tests, no linter, no build step.

## Architecture

### Workflow lifecycle (`.github/workflows/monitor.yml`)

Each run: checkout repo → install deps → run the three scripts in sequence (each `continue-on-error: true`) → stage `state/` → commit + push if anything changed. The commit step uses `git diff --cached --quiet` after `git add state/` so that **new untracked state files are detected** (a prior bug used `git diff` which only saw tracked files).

`concurrency: minter-monitor` prevents overlapping runs from race-conditioning the state commit.

**Cron schedule is `3,18,33,48 * * * *` (every 15 min, offset off the top of the hour).** Top-of-hour slots (:00 etc.) are the most congested on GitHub's scheduler; the offset reduces delay. Do not switch back to `*/15`.

**The bot's own state commits do NOT trigger workflow runs.** GitHub deliberately prevents `GITHUB_TOKEN`-authored commits from firing event triggers, so there is no risk of recursion. The schedule fires independently.

### State pattern

Every script follows the same shape:
1. `state.load("<key>")` → dict
2. Check `is_first_run = not seen_set` — if true, **silently seed** the seen set with the current API response and return without alerting. This avoids spamming the user with 100 alerts the first time the bot sees the world.
3. Otherwise: iterate fresh items, dedupe against `seen`, alert + add to `seen`.
4. `state.save("<key>", {...})` at the end.

When changing alert logic, preserve the first-run seed guard — without it, a state file deletion or fresh clone re-spams every existing item.

### Telegram circuit breaker (`lib/telegram.py`)

`send()` raises `TelegramAuthError` on 401/403/404 and sets a module-level `_FATAL` flag. All three scripts catch this in their alert loop and `return` early (after saving state). This was added after a 401 caused 100 retry failures in a single run.

### OpenSea client (`lib/opensea.py`)

- Centralized retry/backoff in `_get()`: handles 429 with exponential sleep, returns `{}` on 404, retries 3× on transient errors.
- `resolve_username_to_address()` is used once per run to map OpenSea usernames (e.g. `Samyb_NFT`) to 0x addresses. Results are cached in `state/new_collections.json` under `resolved_targets` so we don't re-lookup every run.
- `collection_holders(slug, max_nfts=300)` walks a collection's NFTs and aggregates owners. **This is the most expensive operation in the codebase** — capped at 300 NFTs to stay under OpenSea rate limits. If you add more target users or more new collections appear per cycle, this can push a run past the 10-min workflow timeout.

### Configuration (`lib/config.py`)

All tunables live here:
- `TARGET_HOLDER_USERNAMES` — who to look for in holders of new collections
- `WHALE_WALLETS` — `{label: 0xaddress}` map; label appears in alerts
- `WHALE_NFT_THRESHOLD` — purchases-per-collection in lookback window before alert
- `MINT_COUNT_THRESHOLD` — collection supply threshold for mint alerts
- `LOOKBACK_MINUTES` — should be ≥ cron interval (default 20 min for a 15-min cron, slight overlap is intentional)

Secrets come from env: `OPENSEA_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. `require_secrets(...)` fails fast at script start if a required one is missing.

## Things to know before changing code

- **The bot runs unattended on a schedule.** A bug doesn't crash a server you can restart — it crashes a cron job and silently stops alerts. Prefer `continue-on-error` over hard failures, and prefer "skip and log" over "raise" in the per-item loops.
- **`LOOKBACK_MINUTES` and the cron interval are coupled.** If you change the cron in `.github/workflows/monitor.yml`, also update `LOOKBACK_MINUTES` in `lib/config.py` to be slightly larger (so adjacent runs overlap and don't miss events at the boundary).
- **`continue-on-error: true` on each script step is deliberate.** A failure in one watcher should not block the others from running or block the state commit. Don't remove it.
- **State trimming**: each script caps its `seen_*` set at ~3000–5000 entries to prevent unbounded growth in the committed JSON.
- **First-run seed must remain silent.** If you add a new watcher, follow the same `is_first_run` pattern in the existing scripts.

## Free-tier budget

Private repo on GitHub Free = 2,000 Action minutes/month. Every-15-min schedule × ~1 min/run × 30 days ≈ 2,400–2,900 min, which is **over** the limit. Mitigations: make repo public (unlimited minutes), increase cron interval to 30 min, or set a $0 spending cap and accept end-of-month pauses.

## Scheduling reliability on free private repos

GitHub deprioritizes scheduled workflows on free-tier private repos. Cron firings are routinely delayed 30+ min and sometimes skipped entirely during high load. This is documented behavior, not a bug. If reliability matters, the user should either make the repo public (free, prioritized scheduling) or move to a paid plan. Don't waste time trying to "fix" missed cron runs by changing the workflow — the cause is not the YAML.

## Local push gotcha

The bot commits to `main` from inside the workflow (state updates as `minter-bot`). After any successful run, the remote `main` is ahead of the user's local clone. A naive `git push` will be rejected. The reliable flow when the user has uncommitted local changes:

```bash
git pull --rebase origin main
git push
```

This replays local commits on top of the bot's state commits. Because the bot only edits `state/*.json` and humans rarely touch those, conflicts are essentially impossible. Don't suggest a merge commit here — rebase keeps the history readable.
