"""
repos.py — GitHub repo discovery for ResearchBase.

Uses Papers With Code API + regex fallback to find code repos for papers.
"""

import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from db import get_connection, get_paper, init_db, search_papers

# ---------------------------------------------------------------------------
# Papers With Code API
# ---------------------------------------------------------------------------

PWC_API_BASE = "https://paperswithcode.com/api/v1"
GITHUB_URL_RE = re.compile(r"github\.com/([\w.-]+/[\w.-]+)")


def _fetch_pwc_repos(arxiv_id: str) -> list[dict]:
    """Fetch repositories for a paper from Papers With Code API."""
    # PWC uses the short arxiv ID (without version)
    clean_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
    url = f"{PWC_API_BASE}/papers/{clean_id}/repositories/"

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        # Don't follow redirects — PWC redirects to HuggingFace for unknown papers
        import urllib.request as _ur

        class NoRedirectHandler(_ur.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = _ur.build_opener(NoRedirectHandler)
        resp = opener.open(req, timeout=15)
        if resp.status != 200:
            return []
        data = json.loads(resp.read().decode("utf-8"))

        repos = []
        results = data if isinstance(data, list) else data.get("results", [])
        for r in results:
            repo_url = r.get("url", "")
            if not repo_url:
                continue
            repos.append({
                "url": repo_url,
                "stars": r.get("stars", 0),
                "framework": r.get("framework", ""),
                "is_official": r.get("is_official", False),
            })
        return repos
    except urllib.error.HTTPError as e:
        if e.code in (302, 404):
            return []  # Paper not on PWC
        print(f"[repos] PWC API error for {arxiv_id}: {e}")
        return []
    except Exception as e:
        print(f"[repos] PWC API error for {arxiv_id}: {e}")
        return []


def _extract_github_urls_from_text(text: str) -> list[str]:
    """Extract GitHub URLs from paper text using regex."""
    if not text:
        return []
    matches = GITHUB_URL_RE.findall(text)
    urls = []
    seen = set()
    for match in matches:
        # Clean up trailing dots/slashes
        clean = match.rstrip("./")
        full_url = f"https://github.com/{clean}"
        if full_url not in seen:
            seen.add(full_url)
            urls.append(full_url)
    return urls


# ---------------------------------------------------------------------------
# Repo Storage
# ---------------------------------------------------------------------------

def _insert_repo(
    url: str,
    paper_id: int,
    stars: int = 0,
    frameworks: list[str] | None = None,
    status: str = "discovered",
) -> Optional[int]:
    """Insert a repo into the DB. Returns repo ID or None if duplicate."""
    conn = get_connection()
    existing = conn.execute("SELECT id FROM repos WHERE url = ?", [url]).fetchone()
    if existing:
        # Update star count if we have newer data
        if stars > 0:
            conn.execute("UPDATE repos SET stars = ? WHERE id = ?", [stars, existing[0]])
        return existing[0]

    conn.execute(
        """INSERT INTO repos (url, paper_id, stars, frameworks, status)
           VALUES (?, ?, ?, ?, ?)""",
        [url, paper_id, stars, frameworks or [], status],
    )
    row = conn.execute("SELECT id FROM repos WHERE url = ?", [url]).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Discovery Pipeline
# ---------------------------------------------------------------------------

def discover_repos_for_paper(arxiv_id: str) -> list[dict]:
    """
    Find repos for a paper: first try PWC API, then regex fallback on paper text.
    Returns list of discovered repos.
    """
    paper = get_paper(arxiv_id)
    if not paper:
        print(f"[repos] Paper {arxiv_id} not found")
        return []

    discovered = []

    # 1. Papers With Code API
    pwc_repos = _fetch_pwc_repos(arxiv_id)
    for r in pwc_repos:
        frameworks = [r["framework"]] if r.get("framework") else []
        status = "official" if r.get("is_official") else "discovered"
        repo_id = _insert_repo(
            url=r["url"],
            paper_id=paper["id"],
            stars=r.get("stars", 0),
            frameworks=frameworks,
            status=status,
        )
        if repo_id:
            discovered.append({"url": r["url"], "stars": r.get("stars", 0), "source": "pwc"})

    # 2. Regex fallback — check abstract and chunks
    from db import get_chunks_for_paper
    texts_to_check = []
    if paper.get("abstract"):
        texts_to_check.append(paper["abstract"])

    chunks = get_chunks_for_paper(paper["id"])
    for c in chunks[:5]:  # Check first 5 chunks (title page area)
        texts_to_check.append(c.get("text", ""))

    for text in texts_to_check:
        urls = _extract_github_urls_from_text(text)
        for url in urls:
            # Don't duplicate PWC findings
            if any(d["url"] == url for d in discovered):
                continue
            repo_id = _insert_repo(url=url, paper_id=paper["id"], status="discovered")
            if repo_id:
                discovered.append({"url": url, "stars": 0, "source": "text"})

    if discovered:
        print(f"[repos] Found {len(discovered)} repos for {arxiv_id}")
    return discovered


def discover_repos_all(status: str = "indexed", limit: int = 200) -> dict:
    """Discover repos for all papers with the given status."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT arxiv_id FROM papers WHERE status IN (?, 'summarized') LIMIT ?",
        [status, limit],
    ).fetchall()

    stats = {"total": len(rows), "found": 0, "repos": 0}
    for i, (arxiv_id,) in enumerate(rows):
        print(f"[repos] [{i+1}/{len(rows)}] {arxiv_id}")
        repos = discover_repos_for_paper(arxiv_id)
        if repos:
            stats["found"] += 1
            stats["repos"] += len(repos)
        # Be nice to PWC API
        time.sleep(1)

    print(f"\n[repos] Done! {stats}")
    return stats


def list_repos(limit: int = 50) -> list[dict]:
    """List all repos in the DB."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT r.*, p.arxiv_id, p.title as paper_title
           FROM repos r
           JOIN papers p ON r.paper_id = p.id
           ORDER BY r.stars DESC
           LIMIT ?""",
        [limit],
    ).fetchall()
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in rows]


def format_repos(repos: list[dict]) -> str:
    """Format repo list as readable text."""
    if not repos:
        return "No repos found."

    lines = [f"\n{'='*60}", "  GitHub Repositories", f"{'='*60}\n"]
    for r in repos:
        stars = r.get("stars", 0)
        star_str = f"⭐{stars}" if stars else ""
        status = r.get("status", "")
        lines.append(f"  {r['url']}")
        lines.append(f"    Paper: {r.get('paper_title', 'N/A')[:50]} ({r.get('arxiv_id', '?')})")
        fw = r.get("frameworks", [])
        fw_str = ", ".join(fw) if fw else ""
        meta = " | ".join(filter(None, [star_str, fw_str, status]))
        if meta:
            lines.append(f"    {meta}")
        lines.append("")

    lines.append(f"  Total: {len(repos)} repos")
    lines.append(f"{'='*60}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Discover GitHub repos for papers")
    parser.add_argument("arxiv_id", nargs="?", help="arXiv paper ID")
    parser.add_argument("--all", action="store_true", help="Discover repos for all papers")
    parser.add_argument("--list", action="store_true", help="List known repos")
    parser.add_argument("--status", default="indexed", help="Filter by paper status")
    parser.add_argument("--limit", type=int, default=50, help="Max results")
    args = parser.parse_args()

    init_db()

    if args.list:
        repos = list_repos(limit=args.limit)
        print(format_repos(repos))
    elif args.all:
        result = discover_repos_all(status=args.status, limit=args.limit)
        print(json.dumps(result, indent=2))
    elif args.arxiv_id:
        repos = discover_repos_for_paper(args.arxiv_id)
        print(json.dumps(repos, indent=2, default=str))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
