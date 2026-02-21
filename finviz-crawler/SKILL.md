---
name: finviz-crawler
description: Continuous financial news crawler for finviz.com with SQLite storage, article extraction, and query tool. Use when monitoring financial markets, building news digests, or needing a local financial news database. Runs as a background daemon or systemd service.
metadata: {"openclaw":{"requires":{"bins":["python3"]}}}
---

# finviz-crawler

## Why This Skill?

📰 **Your own financial news database** — most finance skills just wrap an API for one-shot queries. This skill runs continuously, building a local archive of every headline and article from Finviz. Query your history anytime — no API limits, no missing data.

🆓 **No API key, no subscription** — scrapes finviz.com directly using Crawl4AI + RSS. Bloomberg, Reuters, Yahoo Finance, CNBC articles extracted automatically. Zero cost.

🤖 **Built for AI summarization** — the query tool outputs clean text/JSON optimized for LLM digests. Pair with an OpenClaw cron job for automated morning briefings, evening wrap-ups, or weekly investment summaries.

💾 **Auto-cleanup** — configurable expiry automatically deletes old articles from both the database and disk. Set `--expiry-days 30` to keep a month of history, or `0` to keep everything forever.

🔄 **Daemon architecture** — runs as a background service that starts/stops with OpenClaw. No manual intervention needed after setup. Works with systemd (Linux) and launchd (macOS).

## Install

```bash
python3 scripts/install.py
```

Works on **macOS, Linux, and Windows**. Installs Python packages (`crawl4ai`, `feedparser`), sets up Playwright browsers, creates data directories, and verifies everything.

### Manual install
```bash
pip install crawl4ai feedparser
crawl4ai-setup  # or: python -m playwright install chromium
```

## Usage

### Run the crawler
```bash
# Default: ~/Downloads/Finviz/, 7-day expiry
python3 scripts/finviz_crawler.py

# Custom paths and settings
python3 scripts/finviz_crawler.py --db /path/to/finviz.db --articles-dir /path/to/articles/

# Keep 30 days of articles
python3 scripts/finviz_crawler.py --expiry-days 30

# Never auto-delete (keep everything)
python3 scripts/finviz_crawler.py --expiry-days 0

# Custom crawl interval (default: 300s)
python3 scripts/finviz_crawler.py --sleep 600
```

### Query articles
```bash
# Last 24 hours of headlines
python3 scripts/finviz_query.py --hours 24

# Titles only (compact, good for LLM summarization)
python3 scripts/finviz_query.py --hours 12 --titles-only

# With full article content
python3 scripts/finviz_query.py --hours 12 --with-content

# Database stats
python3 scripts/finviz_query.py --stats
```

### Configuration

| Setting | CLI flag | Env var | Default |
|---------|----------|---------|---------|
| Database path | `--db` | — | `~/Downloads/Finviz/finviz.db` |
| Articles directory | `--articles-dir` | — | `~/Downloads/Finviz/articles/` |
| Crawl interval | `--sleep` | — | `300` (5 min) |
| Article expiry | `--expiry-days` | `FINVIZ_EXPIRY_DAYS` | `7` days |
| Timezone | — | `FINVIZ_TZ` or `TZ` | System default |

## Architecture

**Crawler daemon** (`finviz_crawler.py`):
- Crawls finviz.com/news.ashx headlines every 5 minutes
- Fetches article content via Crawl4AI (Playwright) or RSS (paywalled sites)
- Bot/paywall detection rejects garbage content
- Per-domain rate limiting, user-agent rotation
- Deduplicates via SHA-256 title hash
- Auto-expires old articles (configurable)
- Clean shutdown on SIGTERM/SIGINT

**Query tool** (`finviz_query.py`):
- Read-only SQLite queries (no HTTP, stdlib only)
- Filter by time window, export titles or full content
- Designed for LLM summarization pipelines

## Run as a service (optional)

### systemd (Linux)
```ini
[Unit]
Description=Finviz News Crawler

[Service]
ExecStart=python3 /path/to/scripts/finviz_crawler.py --expiry-days 30
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
```

### launchd (macOS)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.finviz.crawler</string>
    <key>ProgramArguments</key>
    <array>
        <string>python3</string>
        <string>/path/to/scripts/finviz_crawler.py</string>
        <string>--expiry-days</string>
        <string>30</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
</dict>
</plist>
```

## Data layout
```
~/Downloads/Finviz/
├── finviz.db          # SQLite: metadata, URLs, timestamps, hashes
└── articles/          # Full article content as .md files
```

## Cron integration

Pair with an OpenClaw cron job for automated digests:
```
Schedule: 0 6 * * * (6 AM daily)
Task: Query last 24h → LLM summarize → deliver to Matrix/Telegram/Discord
```
