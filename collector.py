"""Flight Deal Radar — MVP collector.

Pulls the cheapest cached return fare per departure month for each route in
targets.yaml (SIN -> destination) from the Travelpayouts Data API, appends
every observation to data/history.jsonl (append-only, never rewritten), and
writes data/latest.json (today's cheapest fare per route) for the dashboard
and alerter.

Env: TRAVELPAYOUTS_TOKEN
"""

import json
import os
import sys
import datetime as dt
from pathlib import Path

import requests
import yaml

API = "https://api.travelpayouts.com/aviasales/v3/grouped_prices"
ORIGIN = "SIN"
CURRENCY = "sgd"
MONTHS_AHEAD = 6

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
HISTORY = DATA / "history.jsonl"
LATEST = DATA / "latest.json"
HEARTBEAT = DATA / "heartbeat.log"


def load_targets() -> dict:
    with open(ROOT / "targets.yaml") as f:
        raw = yaml.safe_load(f)
    return {k: int(v) for k, v in raw.items()}


def month_list(n: int) -> list[str]:
    today = dt.date.today().replace(day=1)
    months = []
    y, m = today.year, today.month
    for _ in range(n):
        m += 1
        if m > 12:
            m, y = 1, y + 1
        months.append(f"{y:04d}-{m:02d}-01")
    return months


def fetch_route(token: str, dest: str) -> list[dict]:
    """Cheapest return fare per departure month for ORIGIN->dest."""
    params = {
        "origin": ORIGIN,
        "destination": dest,
        "group_by": "month",
        "currency": CURRENCY,
        "one_way": "false",
        "token": token,
    }
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    payload = r.json()
    if not payload.get("success", False):
        print(f"  ! API returned success=false for {dest}: {payload}", file=sys.stderr)
        return []

    wanted = set(m[:7] for m in month_list(MONTHS_AHEAD))
    observations = []
    collected_at = dt.date.today().isoformat()

    for month_key, item in (payload.get("data") or {}).items():
        month = str(month_key)[:7]
        if month not in wanted or not item:
            continue
        observations.append({
            "collected_at": collected_at,
            "origin": ORIGIN,
            "destination": dest,
            "travel_month": month,
            "price_sgd": item.get("price"),
            "native_price": item.get("price"),
            "native_currency": CURRENCY.upper(),
            "airline": item.get("airline"),
            "transfers": item.get("transfers"),
            "trip_type": "return",
            "source": "travelpayouts",
        })
    return observations


def main() -> int:
    token = os.environ.get("TRAVELPAYOUTS_TOKEN")
    if not token:
        print("TRAVELPAYOUTS_TOKEN is not set", file=sys.stderr)
        return 1

    targets = load_targets()
    DATA.mkdir(exist_ok=True)

    all_obs: list[dict] = []
    failures = 0
    for dest in targets:
        try:
            obs = fetch_route(token, dest)
            all_obs.extend(obs)
            print(f"  {ORIGIN}->{dest}: {len(obs)} months")
        except Exception as e:  # keep collecting other routes
            failures += 1
            print(f"  ! {ORIGIN}->{dest} failed: {e}", file=sys.stderr)

    # Append-only history. Never overwrite, never dedupe at write time.
    with open(HISTORY, "a") as f:
        for row in all_obs:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")

    # Latest snapshot: cheapest fare per route across observed months.
    latest = {}
    for row in all_obs:
        d = row["destination"]
        if row["price_sgd"] is None:
            continue
        if d not in latest or row["price_sgd"] < latest[d]["price_sgd"]:
            latest[d] = row
    # Every tracked route appears in the snapshot; price_sgd is null when the
    # API had no data today so the dashboard can show the gap instead of
    # silently dropping the route.
    snapshot = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "origin": ORIGIN,
        "routes": [
            {**latest[d], "target_sgd": targets[d]} if d in latest
            else {"origin": ORIGIN, "destination": d, "price_sgd": None,
                  "target_sgd": targets[d]}
            for d in sorted(targets)
        ],
    }
    with open(LATEST, "w") as f:
        json.dump(snapshot, f, indent=1)

    # Heartbeat.
    with open(HEARTBEAT, "a") as f:
        f.write(
            f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} "
            f"collected={len(all_obs)} routes_ok={len(targets) - failures}/{len(targets)}\n"
        )

    print(f"Done: {len(all_obs)} observations, {failures} route failures.")
    # Fail the run only if EVERYTHING failed (likely bad token).
    return 1 if (all_obs == [] and failures > 0) else 0


if __name__ == "__main__":
    sys.exit(main())
