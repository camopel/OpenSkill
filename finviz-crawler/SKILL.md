---
name: finviz-crawler
description: Continuous financial news crawler for finviz.com with SQLite storage, article extraction, and query tool. Use when monitoring financial markets, building news digests, or needing a local financial news database. Runs as a systemd daemon bound to OpenClaw gateway.
---

# finviz-crawler

Continuous financial news crawler + query tool. Crawls finviz.com headlines, fetches article content via Crawl4AI + RSS, stores in SQLite + markdown files on disk.

## Install

```bash
pip install crawl4ai feedparser
crawl4ai-setup  # installs Playwright browsers
```

## Architecture

**Crawler daemon** (`finviz_crawler.py`) — continuous background service:
- Crawls finviz.com/news.ashx headlines every 5 minutes
- Fetches full article content via Crawl4AI (Playwright) or RSS (paywalled sites)
- SQLite for metadata, `.md` files for article content
- Bot/paywall detection, per-domain rate limiting, user-agent rotation
- Clean shutdown on SIGTERM/SIGINT

**Query tool** (`finviz_query.py`) — read-only DB queries:
- Filter by time window, get stats, export titles
- Used by cron jobs for automated summarization

## Usage

### Run the crawler
```bash
# Default: ~/Downloads/Finviz/
python3 scripts/finviz_crawler.py

# Custom paths
python3 scripts/finviz_crawler.py --db /path/to/finviz.db --articles-dir /path/to/articles/ --sleep 300
```

### Query articles
```bash
# Last 24 hours
python3 scripts/finviz_query.py --hours 24

# Titles only (for LLM summarization)
python3 scripts/finviz_query.py --hours 12 --titles-only

# With full article content
python3 scripts/finviz_query.py --hours 12 --with-content

# DB stats
python3 scripts/finviz_query.py --stats
```

### Systemd service (optional)

Create `~/.config/systemd/user/finviz-crawler.service`:
```ini
[Unit]
Description=Finviz News Crawler
BindsTo=openclaw-gateway.service
After=openclaw-gateway.service
PartOf=openclaw-gateway.service

[Service]
ExecStart=/path/to/venv/bin/python3 /path/to/scripts/finviz_crawler.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
```

## Cron Integration

Pair with an OpenClaw cron job for automated morning digests:
```
Schedule: 0 6 * * * (6 AM daily)
Task: Query last 24h articles → LLM summarize → deliver to Matrix/Telegram
```

## Data Layout

```
~/Downloads/Finviz/
├── finviz.db          # SQLite metadata (titles, URLs, timestamps, hashes)
└── articles/          # Full article content as .md files
    ├── reuters_fed_holds_rates.md
    ├── yahoo_nvidia_earnings.md
    └── ...
```
