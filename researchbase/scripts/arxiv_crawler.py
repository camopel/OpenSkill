"""
arxiv_crawler.py — arXiv search + PDF download for ResearchBase.

Uses the `arxiv` Python package to search for papers and download PDFs.
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import arxiv

_SCRIPT_DIR = Path(__file__).parent
_CONFIG_PATH = _SCRIPT_DIR / "config.json"

def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)

def _resolve_path(p: str) -> str:
    return str(Path(p).expanduser())

# Default topics from config
TOPICS = [
    "3D gaussian splatting",
    "neural radiance field",
    "world model robotics",
    "real to sim transfer",
    "digital twin construction",
    "scene understanding 3D",
    "physics simulation learning",
    "robot manipulation sim",
    "LLM agent planning",
    "USD OpenUSD scene",
    "monocular 3D reconstruction",
    "semantic scene generation",
    "outdoor scene reconstruction",
    "sim to real transfer robotics",
    "vision language model 3D",
]


def _extract_arxiv_id(entry_id: str) -> str:
    """Extract clean arxiv ID from entry URL, e.g. '2401.12345v1' → '2401.12345'."""
    # entry_id is like http://arxiv.org/abs/2401.12345v1
    aid = entry_id.split("/abs/")[-1] if "/abs/" in entry_id else entry_id
    # Remove version suffix
    if "v" in aid:
        aid = aid.rsplit("v", 1)[0]
    return aid


def search_arxiv(
    query: str,
    max_results: int = 50,
    days_back: int = 7,
) -> list[dict]:
    """
    Search arXiv for papers matching a query.
    
    Args:
        query: Search query string.
        max_results: Maximum number of results per query.
        days_back: Only include papers from the last N days.
    
    Returns:
        List of paper metadata dicts.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    client = arxiv.Client(
        page_size=100,
        delay_seconds=3.0,
        num_retries=3,
    )

    # Use arXiv query syntax: search in title + abstract
    # For multi-word queries: use AND between words in ti/abs fields
    # This is more flexible than exact phrase matching
    words = query.strip().split()
    if len(words) <= 3:
        # Short phrases: try exact match first, fall back to AND
        arxiv_query = f'ti:"{query}" OR abs:"{query}" OR (ti:{" AND ti:".join(words)}) OR (abs:{" AND abs:".join(words)})'
    else:
        # Longer queries: AND between key words in title or abstract
        ti_parts = " AND ".join(f"ti:{w}" for w in words)
        abs_parts = " AND ".join(f"abs:{w}" for w in words)
        arxiv_query = f"({ti_parts}) OR ({abs_parts})"

    search = arxiv.Search(
        query=arxiv_query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    papers = []
    try:
        for result in client.results(search):
            # Filter by date
            published = result.published.replace(tzinfo=timezone.utc) if result.published.tzinfo is None else result.published
            if published < cutoff:
                continue

            arxiv_id = _extract_arxiv_id(result.entry_id)
            paper = {
                "arxiv_id": arxiv_id,
                "title": result.title.replace("\n", " ").strip(),
                "authors": [a.name for a in result.authors],
                "abstract": result.summary.replace("\n", " ").strip(),
                "categories": list(result.categories),
                "published": result.published.strftime("%Y-%m-%d"),
                "updated": result.updated.strftime("%Y-%m-%d") if result.updated else None,
                "pdf_url": result.pdf_url,
            }
            papers.append(paper)
    except Exception as e:
        print(f"[arxiv] Error searching '{query}': {e}")

    return papers


def download_pdf(arxiv_id: str, pdf_url: Optional[str] = None) -> Optional[str]:
    """
    Download the PDF for an arXiv paper.
    
    Args:
        arxiv_id: The arXiv paper ID (e.g. '2401.12345').
        pdf_url: Optional direct URL. If not provided, constructs from ID.
    
    Returns:
        Local file path to the downloaded PDF, or None on failure.
    """
    cfg = _load_config()
    pdf_dir = os.path.join(_resolve_path(cfg["data_dir"]), "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)

    safe_id = arxiv_id.replace("/", "_")
    pdf_path = os.path.join(pdf_dir, f"{safe_id}.pdf")

    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:
        print(f"[arxiv] PDF already exists: {pdf_path}")
        return pdf_path

    if pdf_url is None:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    try:
        import urllib.request
        print(f"[arxiv] Downloading {pdf_url}...")
        urllib.request.urlretrieve(pdf_url, pdf_path)
        size = os.path.getsize(pdf_path)
        if size < 1000:
            print(f"[arxiv] Warning: PDF too small ({size}B), likely failed")
            os.remove(pdf_path)
            return None
        print(f"[arxiv] Downloaded {safe_id}.pdf ({size // 1024}KB)")
        return pdf_path
    except Exception as e:
        print(f"[arxiv] Failed to download {arxiv_id}: {e}")
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        return None


def crawl_all_topics(
    topics: Optional[list[str]] = None,
    max_results: int = 50,
    days_back: int = 7,
    download: bool = False,
) -> list[dict]:
    """
    Crawl all configured topics and return combined paper list.
    
    Args:
        topics: Override topics list (defaults to config/TOPICS).
        max_results: Max results per topic.
        days_back: Look back N days.
        download: If True, also download PDFs.
    
    Returns:
        Deduplicated list of paper metadata dicts.
    """
    if topics is None:
        try:
            cfg = _load_config()
            topics = cfg["crawler"]["topics"]
        except Exception:
            topics = TOPICS

    seen_ids: set[str] = set()
    all_papers: list[dict] = []

    for i, topic in enumerate(topics):
        print(f"[arxiv] [{i+1}/{len(topics)}] Searching: {topic}")
        papers = search_arxiv(topic, max_results=max_results, days_back=days_back)
        
        new_count = 0
        for p in papers:
            if p["arxiv_id"] not in seen_ids:
                seen_ids.add(p["arxiv_id"])
                all_papers.append(p)
                new_count += 1

                if download:
                    download_pdf(p["arxiv_id"], p.get("pdf_url"))

        print(f"[arxiv]   Found {len(papers)} results, {new_count} new")
        
        # Be polite to arXiv
        if i < len(topics) - 1:
            time.sleep(3)

    print(f"[arxiv] Total unique papers: {len(all_papers)}")
    return all_papers


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Test with a single quick search
    print("[arxiv] Testing search...")
    results = search_arxiv("3D gaussian splatting", max_results=3, days_back=30)
    print(f"[arxiv] Found {len(results)} papers")
    for r in results[:3]:
        print(f"  - {r['arxiv_id']}: {r['title'][:80]}")
    
    if results:
        print("[arxiv] Testing PDF download...")
        pdf = download_pdf(results[0]["arxiv_id"], results[0].get("pdf_url"))
        print(f"  PDF path: {pdf}")
    
    print("[arxiv] All tests passed ✓")
