"""
gaps.py — Gap analysis for ResearchBase.

Identifies under-researched areas, deprecated techniques, and coverage gaps.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from db import get_connection, init_db

_SCRIPT_DIR = Path(__file__).parent
_CONFIG_PATH = _SCRIPT_DIR / "config.json"


def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)


def analyze_gaps() -> dict:
    """
    Analyze research gaps across the indexed papers.
    
    Returns a dict with:
    - topic_coverage: papers per tracked topic
    - under_researched: topics with few papers
    - technique_stats: technique paper counts
    - deprecated: deprecated/superseded techniques
    - no_code: papers without discovered repos
    - stale: topics with no recent papers
    """
    conn = get_connection()
    config = _load_config()
    tracked_topics = config.get("crawler", {}).get("topics", [])

    result = {
        "topic_coverage": [],
        "under_researched": [],
        "technique_stats": [],
        "deprecated_techniques": [],
        "no_code_papers": [],
        "no_summary_papers": [],
    }

    # 1. Topic coverage — match papers to tracked topics by keyword overlap
    for topic in tracked_topics:
        keywords = topic.lower().split()
        # Build ILIKE conditions
        conditions = " OR ".join(
            f"(lower(title) LIKE '%{kw}%' OR lower(abstract) LIKE '%{kw}%')"
            for kw in keywords if len(kw) > 3
        )
        if not conditions:
            conditions = f"lower(title) LIKE '%{topic.lower()}%'"

        try:
            count = conn.execute(
                f"SELECT COUNT(*) FROM papers WHERE {conditions}"
            ).fetchone()[0]
        except Exception:
            count = 0

        result["topic_coverage"].append({"topic": topic, "papers": count})

    # Sort by paper count ascending to highlight gaps
    result["topic_coverage"].sort(key=lambda x: x["papers"])

    # Under-researched = topics with ≤2 papers
    result["under_researched"] = [
        t for t in result["topic_coverage"] if t["papers"] <= 2
    ]

    # 2. Technique stats — papers per technique
    try:
        rows = conn.execute(
            """SELECT t.name, t.status, t.category, COUNT(pt.paper_id) as paper_count
               FROM techniques t
               LEFT JOIN paper_techniques pt ON t.id = pt.technique_id
               GROUP BY t.id, t.name, t.status, t.category
               ORDER BY paper_count DESC"""
        ).fetchall()
        cols = [d[0] for d in conn.description]
        result["technique_stats"] = [dict(zip(cols, r)) for r in rows]
    except Exception:
        pass

    # 3. Deprecated/superseded techniques
    try:
        rows = conn.execute(
            "SELECT name, status, category FROM techniques WHERE status IN ('deprecated', 'superseded')"
        ).fetchall()
        result["deprecated_techniques"] = [
            {"name": r[0], "status": r[1], "category": r[2]} for r in rows
        ]
    except Exception:
        pass

    # 4. Papers without repos (no code available)
    try:
        rows = conn.execute(
            """SELECT p.arxiv_id, p.title
               FROM papers p
               LEFT JOIN repos r ON p.id = r.paper_id
               WHERE r.id IS NULL AND p.status IN ('indexed', 'summarized')
               LIMIT 20"""
        ).fetchall()
        result["no_code_papers"] = [
            {"arxiv_id": r[0], "title": r[1]} for r in rows
        ]
    except Exception:
        pass

    # 5. Papers without summaries
    try:
        rows = conn.execute(
            """SELECT arxiv_id, title FROM papers
               WHERE summary IS NULL AND status = 'indexed'
               LIMIT 20"""
        ).fetchall()
        result["no_summary_papers"] = [
            {"arxiv_id": r[0], "title": r[1]} for r in rows
        ]
    except Exception:
        pass

    return result


def format_gaps(gaps: dict) -> str:
    """Format gap analysis as readable text."""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append("  ResearchBase — Gap Analysis")
    lines.append(f"{'='*60}")

    # Topic coverage
    lines.append(f"\n📊 Topic Coverage:")
    lines.append(f"{'─'*40}")
    for t in gaps.get("topic_coverage", []):
        bar = "█" * min(t["papers"], 30)
        lines.append(f"  {t['topic']:40s} {t['papers']:3d} {bar}")

    # Under-researched
    under = gaps.get("under_researched", [])
    if under:
        lines.append(f"\n⚠️  Under-Researched Topics ({len(under)}):")
        lines.append(f"{'─'*40}")
        for t in under:
            lines.append(f"  • {t['topic']} ({t['papers']} papers)")

    # Technique stats
    tech_stats = gaps.get("technique_stats", [])
    if tech_stats:
        lines.append(f"\n🔧 Techniques by Paper Count:")
        lines.append(f"{'─'*40}")
        for t in tech_stats[:20]:
            status_icon = "🏆" if t.get("status") == "sota" else "📈" if t.get("status") == "promising" else "📊"
            lines.append(f"  {status_icon} {t['name']:35s} {t['paper_count']:3d} papers ({t.get('status', '?')})")

    # Deprecated
    deprecated = gaps.get("deprecated_techniques", [])
    if deprecated:
        lines.append(f"\n🚫 Deprecated/Superseded Techniques:")
        lines.append(f"{'─'*40}")
        for t in deprecated:
            lines.append(f"  • {t['name']} ({t['status']})")

    # No code
    no_code = gaps.get("no_code_papers", [])
    if no_code:
        lines.append(f"\n📭 Papers Without Repos ({len(no_code)}):")
        lines.append(f"{'─'*40}")
        for p in no_code[:10]:
            lines.append(f"  • {p['arxiv_id']:16s} {p['title'][:50]}")

    # No summary
    no_summary = gaps.get("no_summary_papers", [])
    if no_summary:
        lines.append(f"\n📝 Papers Awaiting Summarization ({len(no_summary)}):")
        lines.append(f"{'─'*40}")
        for p in no_summary[:10]:
            lines.append(f"  • {p['arxiv_id']:16s} {p['title'][:50]}")

    lines.append(f"\n{'='*60}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="ResearchBase gap analysis")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    init_db()
    gaps = analyze_gaps()

    if args.json:
        print(json.dumps(gaps, indent=2, default=str))
    else:
        print(format_gaps(gaps))


if __name__ == "__main__":
    main()
