"""
search.py — Semantic search pipeline for ResearchBase.

Query flow: embed query → FAISS top-K retrieve → enrich with metadata from SQLite → return.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from db import get_chunks_by_faiss_ids, get_connection, init_db
from embed import embed_query
from faiss_index import get_index_size, load_index, search as faiss_search

_SCRIPT_DIR = Path(__file__).parent
_CONFIG_PATH = _SCRIPT_DIR / "config.json"

def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)


def search(
    query: str,
    top_k: int = 10,
    precise: bool = False,
    embedding_backend: Optional[str] = None,
) -> list[dict]:
    """
    Semantic search over the ResearchBase index.
    
    Args:
        query: Natural language search query.
        top_k: Number of results to return.
        precise: If True, use Cohere reranker for better results (Phase 2).
        embedding_backend: Override embedding backend.
    
    Returns:
        List of result dicts with metadata and relevance scores.
    """
    cfg = _load_config()
    retrieve_k = cfg["search"].get("top_k_retrieve", 50)

    # Ensure index is loaded
    load_index()
    index_size = get_index_size()
    if index_size == 0:
        print("[search] Index is empty. Run 'rb ingest' first.")
        return []

    # Embed the query
    query_vec = embed_query(query, backend=embedding_backend)

    # FAISS retrieval
    raw_results = faiss_search(query_vec, top_k=retrieve_k)
    if not raw_results:
        return []

    # Enrich with metadata from SQLite
    faiss_ids = [r["faiss_id"] for r in raw_results]
    chunks = get_chunks_by_faiss_ids(faiss_ids)
    
    # Build lookup by faiss_id
    chunk_lookup = {}
    for chunk in chunks:
        fid = chunk.get("faiss_id")
        if fid is not None:
            chunk_lookup[fid] = chunk

    # Merge scores with metadata
    results = []
    for raw in raw_results:
        fid = raw["faiss_id"]
        chunk = chunk_lookup.get(fid)
        if chunk is None:
            continue

        result = {
            "score": raw["score"],
            "arxiv_id": chunk.get("arxiv_id", ""),
            "paper_title": chunk.get("paper_title", ""),
            "authors": chunk.get("authors", []),
            "section": chunk.get("section", ""),
            "chunk_index": chunk.get("chunk_index", 0),
            "text": chunk.get("text", "")[:500],  # Truncate for display
            "chunk_id": chunk.get("id"),
            "paper_id": chunk.get("paper_id"),
        }
        results.append(result)

    # Deduplicate: keep best chunk per paper
    seen_papers: dict[str, dict] = {}
    deduplicated = []
    for r in results:
        aid = r["arxiv_id"]
        if aid not in seen_papers:
            seen_papers[aid] = r
            deduplicated.append(r)
        elif r["score"] > seen_papers[aid]["score"]:
            # Replace with higher-scoring chunk
            deduplicated = [x for x in deduplicated if x["arxiv_id"] != aid]
            seen_papers[aid] = r
            deduplicated.append(r)

    # Sort by score descending
    deduplicated.sort(key=lambda x: x["score"], reverse=True)

    return deduplicated[:top_k]


def format_results(results: list[dict]) -> str:
    """Format search results for display."""
    if not results:
        return "No results found."

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"\n{'='*60}")
        lines.append(f"#{i}  [{r['score']:.4f}]  {r['paper_title']}")
        lines.append(f"    arXiv: {r['arxiv_id']}  |  Section: {r['section']}")
        if r.get("authors"):
            authors_str = ", ".join(r["authors"][:3])
            if len(r["authors"]) > 3:
                authors_str += f" et al. ({len(r['authors'])} authors)"
            lines.append(f"    Authors: {authors_str}")
        lines.append(f"    {r['text'][:300]}...")

    lines.append(f"\n{'='*60}")
    lines.append(f"Found {len(results)} results")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ResearchBase semantic search")
    parser.add_argument("query", type=str, help="Search query")
    parser.add_argument("--top-k", type=int, default=10, help="Number of results")
    parser.add_argument("--precise", action="store_true", help="Use reranker (Phase 2)")
    parser.add_argument("--backend", type=str, choices=["titan", "jina"], help="Embedding backend")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    init_db()
    results = search(args.query, top_k=args.top_k, precise=args.precise,
                     embedding_backend=args.backend)

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(format_results(results))


if __name__ == "__main__":
    main()
