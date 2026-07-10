# roomspot-monitor

Monitors [Roomspot](https://www.roomspot.nl) for special-offer listings
(`isExtraAanbod == true`) and sends a Telegram alert for every new one.

## How it works

- A GitHub Actions workflow polls the Roomspot portal every 5 minutes
  (`python roomspot_monitor.py --once`).
- New listings are diffed against `seen.json`, which the workflow commits
  back to the repo after each run.
- The very first run records a baseline without alerting.

## Setup

Set two repository Actions secrets:

| Secret | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Chat/user ID the alerts go to |

Without them, the script prints alerts to stdout instead of sending.

## Run locally

```sh
python3 roomspot_monitor.py --once   # single poll
python3 roomspot_monitor.py          # loop every 5 minutes
```
