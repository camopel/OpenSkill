---
name: finviz-crawler
description: Continuous financial news crawler for finviz.com with SQLite storage, article extraction, and query tool. Use when monitoring financial markets, building news digests, or needing a local financial news database. Runs as a background daemon or systemd service.
metadata: {"openclaw":{"requires":{"bins":["python3"]}}}
---

# finviz-crawler

Continuous financial news crawler + query tool. Crawls finviz.com headlines, fetches full article content, stores in SQLite + markdown files.

## Install

```bash
python3 scripts/install.py
```

The install script handles everything across **macOS, Linux, and Windows**:
- Installs Python packages (`crawl4ai`, `feedparser`)
- Sets up Playwright browsers (for article extraction)
- Creates data directories
- Verifies installation

### Manual install
```bash
pip install crawl4ai feedparser
crawl4ai-setup  # or: python -m playwright install chromium
```

## Usage

### Run the crawler
```bash
# Uses ~/Downloads/Finviz/ by default
python3 scripts/finviz_crawler.py

# Custom paths
python3 scripts/finviz_crawler.py --db /path/to/finviz.db --articles-dir /path/to/articles/

# Custom sleep interval between crawl cycles (default: 300s)
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

### Timezone

Timestamps use your system timezone by default. Override with:
```bash
FINVIZ_TZ=America/New_York python3 scripts/finviz_crawler.py
```

Priority: `FINVIZ_TZ` → `TZ` → `/etc/timezone` → UTC.

## Architecture

**Crawler daemon** (`finviz_crawler.py`):
- Crawls finviz.com/news.ashx headlines every 5 minutes
- Fetches article content via Crawl4AI (Playwright) or RSS (paywalled sites)
- Bot/paywall detection rejects garbage content
- Per-domain rate limiting, user-agent rotation
- Deduplicates via SHA-256 title hash
- Clean shutdown on SIGTERM/SIGINT

**Query tool** (`finviz_query.py`):
- Read-only SQLite queries (no HTTP, no dependencies beyond stdlib)
- Filter by time window, export titles or full content
- Used by cron jobs for automated summarization

## Run as a service (optional)

### systemd (Linux)
```ini
[Unit]
Description=Finviz News Crawler

[Service]
ExecStart=python3 /path/to/scripts/finviz_crawler.py
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
Task: Query last 24h → LLM summarize → deliver to Matrix/Telegram
```
