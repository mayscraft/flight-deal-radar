# Flight Deal Radar — MVP

Daily pipeline: collect cached SIN airfares → append price history → ping
Telegram when a fare beats a hand-set target → publish a departure-board
dashboard. Built to the MVP brief; the full statistical engine layers on later.

## One-time setup (~20 minutes of human work)

### 1. Travelpayouts token
1. Sign up at travelpayouts.com (free, affiliate program).
2. Copy your API token from Profile → API access.

### 2. Telegram bot
1. In Telegram, message **@BotFather** → `/newbot` → follow prompts → copy the bot token.
2. Message your new bot anything (this opens the chat).
3. Get your chat ID: open
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   in a browser and copy `"chat":{"id": ...}`.

### 3. GitHub
1. Create a new repo and push this folder to it.
2. Repo → Settings → Secrets and variables → Actions → add three secrets:
   - `TRAVELPAYOUTS_TOKEN`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. Repo → Settings → Pages → Source: *Deploy from a branch* → branch `main`,
   folder `/docs`. Your dashboard will be at
   `https://<username>.github.io/<repo>/`.

### 4. First run
Actions tab → **Daily collect & alert** → *Run workflow*. A green run means:
fares collected, `data/history.jsonl` growing, dashboard live, and a Telegram
ping if anything already beats a target.

From then on it runs itself daily at 03:00 SGT. A separate watchdog at
09:00 SGT warns you on Telegram if the pipeline has been silent for 48h.

## Tuning
- `targets.yaml` — the product's brain. Edit target prices or add routes
  (new routes also need a city name in `alerter.py`'s CITY map and
  `docs/index.html`'s CITY map).
- Dedupe window and price tolerance: top of `alerter.py`.
- Months scanned ahead: `MONTHS_AHEAD` in `collector.py`.

## Files
```
collector.py                 daily fare collection → history.jsonl + latest.json
alerter.py                   target comparison → Telegram, with 72h dedupe
targets.yaml                 hand-set "good deal" prices (SGD, return)
.github/workflows/collect.yml   daily 03:00 SGT run + data commit
.github/workflows/watchdog.yml  heartbeat check, 09:00 SGT
docs/index.html              departure-board dashboard (GitHub Pages)
data/history.jsonl           append-only price history — seed data for the full engine
```

## Known limits (by design, for the MVP)
- Prices are **cached** (Travelpayouts/Aviasales data), not live — every alert
  says so and links to Google Flights for confirmation.
- No statistical scoring yet; targets.yaml is the judgment layer.
- SIN departures only. Multi-origin arbitrage, z-score tiers, SerpAPI
  verification and the full deal explorer live in the v1 build brief.
