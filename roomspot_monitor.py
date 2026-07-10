#!/usr/bin/env python3
"""Roomspot special-offer monitor.

Polls the Roomspot portal for listings flagged isExtraAanbod == true,
diffs them against a local seen.json state file, and sends a Telegram
alert for every listing that wasn't there before.

If TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set, alerts are printed
to stdout instead of sent.

Usage:
    python roomspot_monitor.py --once          # single poll (CI mode)
    python roomspot_monitor.py                 # poll forever every 5 min
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://www.roomspot.nl/portal/object/frontend/getallobjects/format/json"
STATE_FILE = Path(__file__).parent / "seen.json"
POLL_INTERVAL = 300  # seconds, loop mode only
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) roomspot-monitor/1.0"


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}", flush=True)


def fetch_objects() -> list:
    req = urllib.request.Request(API_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    # The portal wraps the listing array in a "result" key; tolerate both shapes.
    objects = payload.get("result", payload) if isinstance(payload, dict) else payload
    if not isinstance(objects, list):
        raise ValueError(f"Unexpected API response shape: {type(objects).__name__}")
    return objects


def special_offers(objects: list) -> dict:
    """Return {listing_id: listing} for every isExtraAanbod listing."""
    offers = {}
    for obj in objects:
        if not isinstance(obj, dict) or not obj.get("isExtraAanbod"):
            continue
        listing_id = str(obj.get("id") or obj.get("dwellingID") or obj.get("urlKey"))
        offers[listing_id] = obj
    return offers


def listing_url(obj: dict) -> str:
    url_key = obj.get("urlKey")
    if url_key:
        return f"https://www.roomspot.nl/aanbod/te-huur/details/{url_key}"
    return "https://www.roomspot.nl/aanbod/te-huur"


def describe(obj: dict) -> str:
    street = obj.get("street") or obj.get("address") or "Unknown address"
    number = obj.get("houseNumber") or ""
    city = (obj.get("city") or {}).get("name") if isinstance(obj.get("city"), dict) else obj.get("city")
    price = obj.get("totalRent") or obj.get("netRent") or obj.get("price")
    parts = [f"{street} {number}".strip()]
    if city:
        parts.append(str(city))
    if price:
        parts.append(f"EUR {price}")
    return " | ".join(parts)


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log(f"[dry-run] Telegram not configured, would send: {text}")
        return False
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=30) as resp:
        ok = json.load(resp).get("ok", False)
    if not ok:
        log("Telegram API returned ok=false")
    return ok


def load_state() -> set | None:
    if not STATE_FILE.exists():
        return None
    return set(json.loads(STATE_FILE.read_text()).get("ids", []))


def save_state(ids: set) -> None:
    STATE_FILE.write_text(
        json.dumps(
            {"ids": sorted(ids), "updated": datetime.now(timezone.utc).isoformat(timespec="seconds")},
            indent=2,
        )
        + "\n"
    )


def poll() -> None:
    offers = special_offers(fetch_objects())
    seen = load_state()

    if seen is None:
        # First ever run: record what's live now, don't alert on it.
        save_state(set(offers))
        log(f"Baseline: {len(offers)} special offer(s) currently live")
        return

    new_ids = set(offers) - seen
    for listing_id in sorted(new_ids):
        obj = offers[listing_id]
        send_telegram(f"New Roomspot special offer!\n{describe(obj)}\n{listing_url(obj)}")

    save_state(seen | set(offers))
    log(f"Checked: {len(offers)} live, {len(new_ids)} new")


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor Roomspot special offers")
    parser.add_argument("--once", action="store_true", help="poll once and exit (for CI)")
    args = parser.parse_args()

    if args.once:
        poll()
        return 0

    while True:
        try:
            poll()
        except Exception as exc:  # keep the loop alive on transient errors
            log(f"Poll failed: {exc}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
