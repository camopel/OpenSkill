#!/usr/bin/env python3
"""
finviz-query — Read from the crawler's SQLite DB + article files for summarization.
Used by cron jobs. SQLite has metadata, article content is on disk as .md files.

Usage:
    python3 finviz_query.py --hours 12              # last 12h by publish_at
    python3 finviz_query.py --hours 168             # last 7 days
    python3 finviz_query.py --hours 12 --titles-only # compact headline list
    python3 finviz_query.py --stats                  # DB + disk stats
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB = os.path.expanduser("~/Downloads/Finviz/finviz.db")
DEFAULT_ARTICLES_DIR = os.path.expanduser("~/Downloads/Finviz/articles")


def get_conn(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        print(json.dumps({"error": f"Database not found: {db_path}"}))
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def query_recent(conn: sqlite3.Connection, articles_dir: str,
                 hours: float | None = None, since: str | None = None,
                 include_content: bool = False) -> list[dict]:
    if since:
        cutoff = since
    elif hours:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    else:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()

    rows = conn.execute(
        """SELECT title, url, domain, source, publish_at, article_path,
                  fetched_at, crawled_at, status, retry_count
           FROM articles
           WHERE publish_at >= ? AND status = 'done'
           ORDER BY publish_at DESC""",
        (cutoff,),
    ).fetchall()

    results = []
    for r in rows:
        item = dict(r)
        if include_content and item.get("article_path"):
            fpath = os.path.join(articles_dir, item["article_path"])
            if os.path.exists(fpath):
                with open(fpath, "r", errors="replace") as f:
                    item["content"] = f.read()
            else:
                item["content"] = None
        results.append(item)

    return results


def db_stats(conn: sqlite3.Connection, articles_dir: str) -> dict:
    stats = {}
    for status in ("done", "pending", "failed"):
        stats[status] = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE status=?", (status,)
        ).fetchone()[0]
    stats["total"] = sum(stats.values())

    stats["oldest"] = conn.execute("SELECT MIN(publish_at) FROM articles").fetchone()[0]
    stats["newest"] = conn.execute("SELECT MAX(publish_at) FROM articles").fetchone()[0]

    last_24h = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE publish_at >= ?",
        ((datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),),
    ).fetchone()[0]
    stats["last_24h"] = last_24h

    # Disk stats
    articles_path = Path(articles_dir)
    if articles_path.exists():
        files = list(articles_path.glob("*.md"))
        stats["articles_on_disk"] = len(files)
        stats["total_size_mb"] = round(sum(f.stat().st_size for f in files) / 1048576, 2)
    else:
        stats["articles_on_disk"] = 0
        stats["total_size_mb"] = 0

    return stats


def main():
    parser = argparse.ArgumentParser(description="Query finviz crawler DB")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--articles-dir", default=DEFAULT_ARTICLES_DIR)
    parser.add_argument("--hours", type=float, default=12,
                        help="Articles published in last N hours (default: 12)")
    parser.add_argument("--since", help="Articles since ISO date (overrides --hours)")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--titles-only", action="store_true")
    parser.add_argument("--with-content", action="store_true",
                        help="Include article content from disk")
    args = parser.parse_args()

    conn = get_conn(args.db)

    if args.stats:
        print(json.dumps(db_stats(conn, args.articles_dir), indent=2))
        return

    articles = query_recent(
        conn, args.articles_dir,
        hours=args.hours, since=args.since,
        include_content=args.with_content,
    )

    if args.titles_only:
        for a in articles:
            pub = a.get("publish_at", "")[:16]
            print(f"[{pub}] {a['title']}  ({a.get('domain', '')})")
    else:
        output = {
            "query": {"hours": args.hours, "since": args.since},
            "count": len(articles),
            "articles": articles,
        }
        print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
