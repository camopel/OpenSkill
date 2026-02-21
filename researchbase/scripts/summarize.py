"""
summarize.py — Paper summarization for ResearchBase.

Uses LiteLLM proxy (localhost:4000) to generate structured summaries of papers.
Extracts techniques, benchmarks, and datasets from summaries.
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

from db import (
    get_chunks_for_paper,
    get_connection,
    get_paper,
    init_db,
    insert_benchmark,
    insert_technique,
    search_papers,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LITELLM_URL = "http://localhost:4000/v1/chat/completions"
MODEL = "claude-sonnet-4-6"
RATE_LIMIT_SEC = 2  # light rate limit for Bedrock
MAX_TEXT_CHARS = 60000  # max chars to send to LLM (leave room for prompt)

_last_call_time = 0.0

# ---------------------------------------------------------------------------
# LLM Interaction
# ---------------------------------------------------------------------------

SUMMARY_PROMPT = """You are a research paper analyst. Given the full text of an academic paper, produce a structured JSON summary.

Return ONLY a valid JSON object with exactly these fields:
{
  "problem": "What problem does this paper address? (1-2 sentences)",
  "approach": "Key method/technique (2-3 sentences)",
  "key_insight": "The novel contribution in 1 sentence",
  "results": "Main quantitative results + datasets used",
  "limitations": "Known weaknesses or gaps",
  "techniques": ["technique1", "technique2"],
  "datasets": ["dataset1", "dataset2"],
  "metrics": {"metric_name": value, ...}
}

Rules:
- "techniques" should be specific method names (e.g., "3D Gaussian Splatting", "NeRF", "PPO"), not generic terms
- "datasets" should be specific benchmark datasets (e.g., "ShapeNet", "ScanNet", "KITTI")
- "metrics" should map metric names to numeric values when available (e.g., {"PSNR": 30.5, "SSIM": 0.95})
- If a field has no relevant info, use an empty string, empty list, or empty object as appropriate
- Return ONLY the JSON, no markdown fences, no explanation"""


def _rate_limit():
    """Enforce rate limiting between LLM calls."""
    global _last_call_time
    now = time.time()
    elapsed = now - _last_call_time
    if elapsed < RATE_LIMIT_SEC:
        wait = RATE_LIMIT_SEC - elapsed
        print(f"[summarize] Rate limiting: waiting {wait:.1f}s")
        time.sleep(wait)
    _last_call_time = time.time()


def _call_llm(paper_text: str, title: str) -> Optional[dict]:
    """Call LiteLLM proxy to summarize a paper. Returns parsed JSON or None."""
    _rate_limit()

    # Truncate text if too long
    if len(paper_text) > MAX_TEXT_CHARS:
        paper_text = paper_text[:MAX_TEXT_CHARS] + "\n\n[... truncated ...]"

    user_msg = f"Paper title: {title}\n\nFull text:\n{paper_text}"

    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
    }).encode("utf-8")

    req = urllib.request.Request(
        LITELLM_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()

        # Strip markdown fences if present
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*\n?", "", content)
            content = re.sub(r"\n?```\s*$", "", content)

        return json.loads(content)
    except urllib.error.URLError as e:
        print(f"[summarize] LLM call failed: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"[summarize] Failed to parse LLM response as JSON: {e}")
        if 'content' in dir():
            print(f"[summarize] Raw response: {content[:500]}")
        return None
    except Exception as e:
        print(f"[summarize] Unexpected error: {e}")
        return None


# ---------------------------------------------------------------------------
# Paper Text Assembly
# ---------------------------------------------------------------------------

def _assemble_paper_text(paper: dict) -> str:
    """Assemble full paper text from chunks, falling back to abstract."""
    chunks = get_chunks_for_paper(paper["id"])
    if chunks:
        # Sort by chunk_index and concatenate
        chunks.sort(key=lambda c: c.get("chunk_index", 0))
        parts = []
        current_section = None
        for c in chunks:
            section = c.get("section", "")
            if section != current_section:
                parts.append(f"\n## {section}\n")
                current_section = section
            parts.append(c["text"])
        return "\n".join(parts)
    elif paper.get("abstract"):
        return f"Abstract:\n{paper['abstract']}"
    else:
        return ""


# ---------------------------------------------------------------------------
# Technique & Benchmark Extraction
# ---------------------------------------------------------------------------

def _extract_techniques_and_benchmarks(paper_id: int, summary: dict, conn=None):
    """Parse structured summary to populate techniques, benchmarks, and junction tables."""
    _own_conn = conn is None
    if _own_conn:
        conn = get_connection()

    # Extract techniques
    techniques = summary.get("techniques", [])
    technique_ids = []
    for tech_name in techniques:
        if not tech_name or not isinstance(tech_name, str):
            continue
        tech_name = tech_name.strip()
        if len(tech_name) < 2 or len(tech_name) > 200:
            continue

        tech_id = insert_technique(
            name=tech_name,
            first_paper_id=paper_id,
            status="promising",
            conn=conn,
        )
        technique_ids.append(tech_id)

        # Link paper to technique
        try:
            conn.execute(
                "INSERT INTO paper_techniques (paper_id, technique_id) VALUES (?, ?)",
                [paper_id, tech_id],
            )
        except Exception:
            pass  # Already linked

    # Extract benchmarks from metrics
    metrics = summary.get("metrics", {})
    datasets = summary.get("datasets", [])

    if metrics and technique_ids:
        primary_tech_id = technique_ids[0]
        dataset_name = datasets[0] if datasets else "unknown"

        for metric_name, value in metrics.items():
            if not isinstance(value, (int, float)):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    continue

            insert_benchmark(
                paper_id=paper_id,
                technique_id=primary_tech_id,
                dataset=dataset_name,
                metric=metric_name,
                value=value,
                conn=conn,
            )

    # Check if results mention SOTA — upgrade technique status
    results_text = (summary.get("results", "") or "").lower()
    sota_indicators = ["state-of-the-art", "sota", "best", "outperform", "surpass"]
    if any(ind in results_text for ind in sota_indicators):
        for tech_id in technique_ids:
            conn.execute(
                "UPDATE techniques SET status = 'sota' WHERE id = ? AND status != 'sota'",
                [tech_id],
            )

    print(f"[summarize] Extracted {len(technique_ids)} techniques, {len(metrics)} benchmarks")

    if _own_conn:
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Main Summarization
# ---------------------------------------------------------------------------

def summarize_paper(arxiv_id: str, force: bool = False) -> Optional[dict]:
    """
    Summarize a single paper using the LLM.
    
    Returns the structured summary dict, or None on failure.
    """
    paper = get_paper(arxiv_id)
    if not paper:
        print(f"[summarize] Paper {arxiv_id} not found in database.")
        return None

    # Skip if already summarized (unless forced)
    if paper.get("summary") and not force:
        print(f"[summarize] Paper {arxiv_id} already summarized. Use --force to re-summarize.")
        return json.loads(paper["summary"])

    # Assemble text
    text = _assemble_paper_text(paper)
    if not text:
        print(f"[summarize] No text available for {arxiv_id}")
        return None

    print(f"[summarize] Summarizing {arxiv_id}: {paper['title'][:60]}...")
    print(f"[summarize] Text length: {len(text)} chars")

    summary = _call_llm(text, paper["title"])
    if not summary:
        return None

    # Validate expected fields
    expected_fields = ["problem", "approach", "key_insight", "results", "limitations",
                       "techniques", "datasets", "metrics"]
    for field in expected_fields:
        if field not in summary:
            summary[field] = "" if field in ("problem", "approach", "key_insight", "results", "limitations") else []
    if "metrics" not in summary or not isinstance(summary["metrics"], dict):
        summary["metrics"] = {}

    # Store summary in DB
    conn = get_connection()
    summary_json = json.dumps(summary)
    conn.execute(
        "UPDATE papers SET summary = ?, status = 'summarized', updated_at = current_timestamp WHERE arxiv_id = ?",
        [summary_json, arxiv_id],
    )

    # Extract techniques and benchmarks (reuse same connection to avoid lock)
    _extract_techniques_and_benchmarks(paper["id"], summary, conn=conn)

    conn.commit()
    conn.close()

    print(f"[summarize] ✓ Summarized {arxiv_id}")
    return summary


def summarize_all(status: str = "indexed", force: bool = False, limit: int = 0) -> dict:
    """
    Summarize all papers with the given status.
    limit=0 means unlimited.
    
    Returns summary stats.
    """
    conn = get_connection()

    limit_clause = f"LIMIT {limit}" if limit > 0 else ""

    if force:
        rows = conn.execute(
            f"SELECT arxiv_id FROM papers WHERE status = ? {limit_clause}",
            [status],
        ).fetchall()
    else:
        # Only papers not yet summarized
        rows = conn.execute(
            f"SELECT arxiv_id FROM papers WHERE status = ? AND summary IS NULL {limit_clause}",
            [status],
        ).fetchall()

    if not rows:
        # Also get 'summarized' papers that might need re-summarizing
        if not force:
            print(f"[summarize] No un-summarized papers with status '{status}'")
            return {"total": 0, "success": 0, "failed": 0}

    arxiv_ids = [r[0] for r in rows]
    print(f"[summarize] Found {len(arxiv_ids)} papers to summarize")

    stats = {"total": len(arxiv_ids), "success": 0, "failed": 0}

    for i, aid in enumerate(arxiv_ids):
        print(f"\n[summarize] [{i+1}/{len(arxiv_ids)}] {aid}")
        result = summarize_paper(aid, force=force)
        if result:
            stats["success"] += 1
        else:
            stats["failed"] += 1

    print(f"\n[summarize] Done! {stats}")
    return stats


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def format_paper_summary(arxiv_id: str) -> str:
    """Format a paper's metadata and summary as readable text."""
    paper = get_paper(arxiv_id)
    if not paper:
        return f"Paper {arxiv_id} not found in database."

    lines = []
    lines.append(f"{'='*60}")
    lines.append(f"Title: {paper['title']}")
    lines.append(f"arXiv: {paper['arxiv_id']}")
    lines.append(f"Published: {paper.get('published', 'N/A')}")
    lines.append(f"Updated: {paper.get('updated', 'N/A')}")
    lines.append(f"Status: {paper.get('status', 'N/A')}")

    if paper.get("authors"):
        authors = paper["authors"]
        if len(authors) <= 5:
            lines.append(f"Authors: {', '.join(authors)}")
        else:
            lines.append(f"Authors: {', '.join(authors[:5])} et al. ({len(authors)} total)")

    if paper.get("categories"):
        lines.append(f"Categories: {', '.join(paper['categories'])}")

    if paper.get("abstract"):
        lines.append(f"\nAbstract:")
        lines.append(paper["abstract"])

    # Show structured summary if available
    if paper.get("summary"):
        try:
            summary = json.loads(paper["summary"])
            lines.append(f"\n{'─'*40}")
            lines.append("LLM Summary:")
            lines.append(f"  Problem:     {summary.get('problem', 'N/A')}")
            lines.append(f"  Approach:    {summary.get('approach', 'N/A')}")
            lines.append(f"  Key Insight: {summary.get('key_insight', 'N/A')}")
            lines.append(f"  Results:     {summary.get('results', 'N/A')}")
            lines.append(f"  Limitations: {summary.get('limitations', 'N/A')}")
            if summary.get("techniques"):
                lines.append(f"  Techniques:  {', '.join(summary['techniques'])}")
            if summary.get("datasets"):
                lines.append(f"  Datasets:    {', '.join(summary['datasets'])}")
            if summary.get("metrics"):
                metrics_str = ", ".join(f"{k}={v}" for k, v in summary["metrics"].items())
                lines.append(f"  Metrics:     {metrics_str}")
        except json.JSONDecodeError:
            lines.append(f"\nSummary: {paper['summary']}")

    if paper.get("techniques"):
        lines.append(f"\nTechniques: {', '.join(paper['techniques'])}")

    # Chunk stats
    chunks = get_chunks_for_paper(paper["id"])
    if chunks:
        sections = set(c["section"] for c in chunks)
        total_tokens = sum(c.get("token_count", 0) for c in chunks)
        lines.append(f"\nIndexed: {len(chunks)} chunks, ~{total_tokens} tokens")
        lines.append(f"Sections: {', '.join(sorted(sections))}")

    if paper.get("pdf_path"):
        lines.append(f"PDF: {paper['pdf_path']}")

    lines.append(f"{'='*60}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Summarize papers using LLM")
    parser.add_argument("arxiv_id", nargs="?", help="arXiv paper ID to summarize")
    parser.add_argument("--all", action="store_true", help="Summarize all papers")
    parser.add_argument("--status", default="indexed", help="Filter by paper status (default: indexed)")
    parser.add_argument("--force", action="store_true", help="Re-summarize even if summary exists")
    parser.add_argument("--limit", type=int, default=100, help="Max papers to summarize")
    args = parser.parse_args()

    init_db()

    if args.all:
        result = summarize_all(status=args.status, force=args.force, limit=args.limit)
        print(json.dumps(result, indent=2))
    elif args.arxiv_id:
        summary = summarize_paper(args.arxiv_id, force=args.force)
        if summary:
            print(json.dumps(summary, indent=2))
        else:
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
