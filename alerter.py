"""Flight Deal Radar — MVP alerter.

Reads data/latest.json, compares each route's cheapest fare against
targets.yaml, and sends a Telegram alert for any fare at or below target —
unless a similar alert (same route + travel month, price within 5%) was
already sent in the last 72 hours (tracked in data/alerted.json).

Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import json
import os
import sys
import datetime as dt
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LATEST = DATA / "latest.json"
ALERTED = DATA / "alerted.json"

DEDUPE_HOURS = 72
PRICE_TOLERANCE = 0.05

CITY = {
    "TPE": "Taipei", "NRT": "Tokyo Narita", "HND": "Tokyo Haneda",
    "KIX": "Osaka", "ICN": "Seoul", "HKG": "Hong Kong", "DPS": "Bali",
    "HAN": "Hanoi", "DAD": "Da Nang", "CNX": "Chiang Mai", "MNL": "Manila",
    "CMB": "Colombo", "MLE": "Maldives", "PER": "Perth", "SYD": "Sydney",
}
AIRLINE = {
    "TR": "Scoot", "SQ": "Singapore Airlines", "3K": "Jetstar", "GK": "Jetstar",
    "AK": "AirAsia", "D7": "AirAsia X", "QZ": "AirAsia", "FD": "Thai AirAsia",
    "CI": "China Airlines", "BR": "EVA Air", "IT": "Tigerair Taiwan",
    "VJ": "VietJet", "VZ": "Thai Vietjet", "VN": "Vietnam Airlines",
    "CX": "Cathay", "MH": "Malaysia Airlines", "OD": "Batik Air", "ID": "Batik Air",
    "TG": "Thai Airways", "SL": "Thai Lion", "PR": "PAL", "5J": "Cebu Pacific",
    "UL": "SriLankan", "QF": "Qantas", "JQ": "Jetstar", "NH": "ANA", "JL": "JAL",
    "KE": "Korean Air", "OZ": "Asiana", "TW": "T'way Air", "7C": "Jeju Air",
    "LJ": "Jin Air", "BX": "Air Busan", "MU": "China Eastern", "MF": "Xiamen Air",
    "NX": "Air Macau", "AI": "Air India", "MM": "Peach", "GA": "Garuda",
    "BI": "Royal Brunei", "ZG": "ZIPAIR",
}
MONTH_NAME = ["", "January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]


def month_label(travel_month: str) -> str:
    y, m = travel_month.split("-")
    return f"{MONTH_NAME[int(m)]} {y}"


def deep_link(origin: str, dest: str, travel_month: str) -> str:
    q = f"Flights to {dest} from {origin} in {month_label(travel_month)}"
    return "https://www.google.com/travel/flights?q=" + quote(q)


def load_alerted() -> list[dict]:
    if ALERTED.exists():
        with open(ALERTED) as f:
            return json.load(f)
    return []


def recently_alerted(history: list[dict], route: dict, now: dt.datetime) -> bool:
    cutoff = now - dt.timedelta(hours=DEDUPE_HOURS)
    for a in history:
        if (a["destination"] == route["destination"]
                and a["travel_month"] == route["travel_month"]
                and dt.datetime.fromisoformat(a["sent_at"]) >= cutoff
                and abs(a["price_sgd"] - route["price_sgd"]) <= PRICE_TOLERANCE * a["price_sgd"]):
            return True
    return False


def send_telegram(token: str, chat_id: str, text: str) -> None:
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text,
              "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=30,
    )
    r.raise_for_status()


def main() -> int:
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not tg_token or not chat_id:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set", file=sys.stderr)
        return 1
    if not LATEST.exists():
        print("data/latest.json missing — run collector first", file=sys.stderr)
        return 1

    with open(LATEST) as f:
        snapshot = json.load(f)

    now = dt.datetime.now(dt.timezone.utc)
    alerted = load_alerted()
    sent = 0

    for route in snapshot["routes"]:
        price, target = route["price_sgd"], route["target_sgd"]
        if price is None or price > target:
            continue
        if recently_alerted(alerted, route, now):
            print(f"  skip (deduped): {route['destination']} S${price}")
            continue

        dest = route["destination"]
        city = CITY.get(dest, dest)
        link = deep_link(route["origin"], dest, route["travel_month"])
        code = route.get("airline")
        airline = AIRLINE.get(code, code) or "—"
        transfers = route.get("transfers")
        if transfers == 0:
            stops = "nonstop"
        elif transfers is None:
            stops = "stops n/a"
        else:
            stops = f"{transfers} stop(s)"
        text = (
            f"🛫 <b>{dest} {city} — S${price} return</b> (target: S${target})\n"
            f"Travel: {month_label(route['travel_month'])} · {airline} · {stops}\n"
            f"⚠️ Cached price — confirm live:\n{link}"
        )
        send_telegram(tg_token, chat_id, text)
        alerted.append({
            "destination": dest,
            "travel_month": route["travel_month"],
            "price_sgd": price,
            "sent_at": now.isoformat(timespec="seconds"),
        })
        sent += 1
        print(f"  alert sent: {dest} S${price} (target S${target})")

    # Prune dedupe memory older than 14 days to keep the file tiny.
    cutoff = now - dt.timedelta(days=14)
    alerted = [a for a in alerted
               if dt.datetime.fromisoformat(a["sent_at"]) >= cutoff]
    with open(ALERTED, "w") as f:
        json.dump(alerted, f, indent=1)

    print(f"Done: {sent} alert(s) sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
