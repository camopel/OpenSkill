#!/usr/bin/env python3
"""
cli.py — ResearchBase CLI entry point.

Usage:
    rb search "query"              — Semantic search across papers
    rb ingest --days 7             — Crawl and ingest recent papers
    rb ingest --arxiv 2401.12345   — Ingest a specific paper
    rb paper 2401.12345            — Show paper details
    rb stats                       — Show index stats
    rb list                        — List papers
    rb summarize <arxiv_id>        — Summarize a paper with LLM
    rb summarize --all             — Summarize all indexed papers
    rb repos                       — List discovered GitHub repos
    rb repos <arxiv_id>            — Discover repos for a paper
    rb gaps                        — Show research gap analysis
    rb compare "a" "b"             — Compare techniques
    rb technique "name"            — Technique details
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure scripts directory is in path
sys.path.insert(0, str(Path(__file__).parent))

from db import get_paper, get_stats, init_db, search_papers
from faiss_index import get_index_size, load_index
from ingest import crawl_and_ingest, ingest_single
from summarize import format_paper_summary, summarize_all, summarize_paper
from repos import discover_repos_for_paper, discover_repos_all, list_repos, format_repos
from gaps import analyze_gaps, format_gaps


def cmd_search(args):
    """Execute a semantic search."""
    init_db()
    from search import format_results, search
    results = search(
        args.query,
        top_k=args.top_k,
        precise=args.precise,
        embedding_backend=args.backend,
    )
    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(format_results(results))


def cmd_ingest(args):
    """Run the ingestion pipeline."""
    if args.arxiv:
        result = ingest_single(
            args.arxiv,
            embed=not args.no_embed,
            embedding_backend=args.backend,
            dry_run=args.dry_run,
        )
    else:
        result = crawl_and_ingest(
            days_back=args.days,
            max_results=args.max_results,
            embed=not args.no_embed,
            embedding_backend=args.backend,
            dry_run=args.dry_run,
        )
    print(json.dumps(result, indent=2, default=str))


def cmd_paper(args):
    """Show paper details."""
    init_db()
    print(format_paper_summary(args.arxiv_id))


def cmd_stats(args):
    """Show index statistics."""
    init_db()
    stats = get_stats()

    try:
        load_index()
        faiss_size = get_index_size()
    except Exception:
        faiss_size = "N/A"

    print(f"\n{'='*40}")
    print(f"  ResearchBase Statistics")
    print(f"{'='*40}")
    print(f"  Papers:      {stats.get('papers', 0)}")
    print(f"  Chunks:      {stats.get('chunks', 0)}")
    print(f"  Techniques:  {stats.get('techniques', 0)}")
    print(f"  Benchmarks:  {stats.get('benchmarks', 0)}")
    print(f"  Repos:       {stats.get('repos', 0)}")
    print(f"  FAISS index: {faiss_size} vectors")
    print(f"{'='*40}\n")


def cmd_summarize(args):
    """Summarize papers with LLM."""
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
        print("Error: provide an arxiv_id or use --all")
        sys.exit(1)


def cmd_repos(args):
    """Discover or list GitHub repositories."""
    init_db()
    if args.list:
        repos = list_repos(limit=args.limit)
        print(format_repos(repos))
    elif args.all:
        result = discover_repos_all(status=args.status, limit=args.limit)
        print(json.dumps(result, indent=2))
    elif args.arxiv_id:
        repos = discover_repos_for_paper(args.arxiv_id)
        if repos:
            for r in repos:
                print(f"  {r['url']}  ({r.get('source', '?')}, ⭐{r.get('stars', 0)})")
        else:
            print("No repos found.")
    else:
        # Default: list repos
        repos = list_repos(limit=args.limit)
        print(format_repos(repos))


def cmd_gaps(args):
    """Show research gap analysis."""
    init_db()
    gaps = analyze_gaps()
    if args.json:
        print(json.dumps(gaps, indent=2, default=str))
    else:
        print(format_gaps(gaps))


def cmd_compare(args):
    """Compare techniques."""
    init_db()
    from db import get_connection
    conn = get_connection()

    lines = [f"\n{'='*60}", "  Technique Comparison", f"{'='*60}"]
    for tech_name in args.techniques:
        row = conn.execute(
            """SELECT t.name, t.status, t.category, COUNT(pt.paper_id) as papers
               FROM techniques t
               LEFT JOIN paper_techniques pt ON t.id = pt.technique_id
               WHERE t.name ILIKE ?
               GROUP BY t.id, t.name, t.status, t.category""",
            [f"%{tech_name}%"],
        ).fetchone()
        if row:
            lines.append(f"\n  {row[0]}")
            lines.append(f"    Status:   {row[1]}")
            lines.append(f"    Category: {row[2] or 'N/A'}")
            lines.append(f"    Papers:   {row[3]}")

            # Benchmarks
            benchmarks = conn.execute(
                """SELECT b.dataset, b.metric, b.value
                   FROM benchmarks b
                   JOIN techniques t ON b.technique_id = t.id
                   WHERE t.name ILIKE ?
                   ORDER BY b.dataset, b.metric""",
                [f"%{tech_name}%"],
            ).fetchall()
            if benchmarks:
                lines.append("    Benchmarks:")
                for ds, metric, val in benchmarks:
                    lines.append(f"      {ds}: {metric}={val}")
        else:
            lines.append(f"\n  '{tech_name}' — not found")

    lines.append(f"\n{'='*60}")
    print("\n".join(lines))


def cmd_technique(args):
    """Show technique details."""
    init_db()
    from db import get_connection
    conn = get_connection()

    row = conn.execute(
        """SELECT t.*, COUNT(pt.paper_id) as paper_count
           FROM techniques t
           LEFT JOIN paper_techniques pt ON t.id = pt.technique_id
           WHERE t.name ILIKE ?
           GROUP BY t.id, t.name, t.category, t.description, t.first_paper_id, t.status, t.created_at""",
        [f"%{args.name}%"],
    ).fetchone()

    if not row:
        print(f"Technique '{args.name}' not found.")
        return

    cols = [d[0] for d in conn.description]
    tech = dict(zip(cols, row))

    print(f"\n{'='*40}")
    print(f"  Technique: {tech['name']}")
    print(f"{'='*40}")
    print(f"  Status:   {tech.get('status', '?')}")
    print(f"  Category: {tech.get('category') or 'N/A'}")
    print(f"  Papers:   {tech.get('paper_count', 0)}")

    if tech.get("description"):
        print(f"  Description: {tech['description']}")

    # Show related papers
    papers = conn.execute(
        """SELECT p.arxiv_id, p.title
           FROM papers p
           JOIN paper_techniques pt ON p.id = pt.paper_id
           JOIN techniques t ON pt.technique_id = t.id
           WHERE t.name ILIKE ?
           LIMIT 10""",
        [f"%{args.name}%"],
    ).fetchall()
    if papers:
        print(f"\n  Related Papers:")
        for aid, title in papers:
            print(f"    • {aid}: {title[:50]}")

    print(f"{'='*40}\n")


def cmd_list(args):
    """List papers in the database."""
    init_db()
    papers = search_papers(query=args.query, status=args.status, limit=args.limit)
    if not papers:
        print("No papers found.")
        return

    for p in papers:
        status = p.get("status", "?")
        published = p.get("published", "N/A")
        print(f"  [{status:12s}] {p['arxiv_id']:16s} {published}  {p['title'][:60]}")
    print(f"\n  Total: {len(papers)} papers")


def main():
    parser = argparse.ArgumentParser(
        prog="rb",
        description="ResearchBase — AI Research Paper Index",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # search
    p_search = subparsers.add_parser("search", help="Semantic search")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--top-k", type=int, default=10)
    p_search.add_argument("--precise", action="store_true", help="Use reranker")
    p_search.add_argument("--backend", choices=["titan", "jina"])
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest papers")
    p_ingest.add_argument("--days", type=int, default=7)
    p_ingest.add_argument("--max-results", type=int, default=100)
    p_ingest.add_argument("--arxiv", type=str, help="Specific arXiv ID")
    p_ingest.add_argument("--backend", choices=["titan", "jina"])
    p_ingest.add_argument("--no-embed", action="store_true")
    p_ingest.add_argument("--dry-run", action="store_true")
    p_ingest.set_defaults(func=cmd_ingest)

    # paper
    p_paper = subparsers.add_parser("paper", help="Show paper details")
    p_paper.add_argument("arxiv_id", help="arXiv paper ID")
    p_paper.set_defaults(func=cmd_paper)

    # stats
    p_stats = subparsers.add_parser("stats", help="Show index stats")
    p_stats.set_defaults(func=cmd_stats)

    # list
    p_list = subparsers.add_parser("list", help="List papers")
    p_list.add_argument("--query", type=str, help="Filter by title/abstract")
    p_list.add_argument("--status", type=str, help="Filter by status")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list)

    # summarize
    p_sum = subparsers.add_parser("summarize", help="Summarize papers with LLM")
    p_sum.add_argument("arxiv_id", nargs="?", help="arXiv paper ID")
    p_sum.add_argument("--all", action="store_true", help="Summarize all papers")
    p_sum.add_argument("--status", default="indexed", help="Filter by status (default: indexed)")
    p_sum.add_argument("--force", action="store_true", help="Re-summarize")
    p_sum.add_argument("--limit", type=int, default=0, help="Max papers (0=unlimited)")
    p_sum.set_defaults(func=cmd_summarize)

    # repos
    p_repos = subparsers.add_parser("repos", help="Discover/list GitHub repos")
    p_repos.add_argument("arxiv_id", nargs="?", help="arXiv paper ID")
    p_repos.add_argument("--all", action="store_true", help="Discover repos for all papers")
    p_repos.add_argument("--list", action="store_true", help="List known repos")
    p_repos.add_argument("--status", default="indexed", help="Filter by paper status")
    p_repos.add_argument("--limit", type=int, default=50)
    p_repos.set_defaults(func=cmd_repos)

    # gaps
    p_gaps = subparsers.add_parser("gaps", help="Research gap analysis")
    p_gaps.add_argument("--json", action="store_true")
    p_gaps.set_defaults(func=cmd_gaps)

    # compare
    p_compare = subparsers.add_parser("compare", help="Compare techniques")
    p_compare.add_argument("techniques", nargs="+", help="Technique names")
    p_compare.set_defaults(func=cmd_compare)

    # technique
    p_tech = subparsers.add_parser("technique", help="Technique details")
    p_tech.add_argument("name", help="Technique name")
    p_tech.set_defaults(func=cmd_technique)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
