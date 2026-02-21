"""
ingest.py — Ingestion orchestrator for ResearchBase.

Pipeline: crawl arXiv → download PDFs → extract text → chunk → embed → store in SQLite + FAISS.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

# Add scripts dir to path for local imports
sys.path.insert(0, str(Path(__file__).parent))

from arxiv_crawler import crawl_all_topics, download_pdf, search_arxiv
from db import get_connection, init_db, insert_chunk, insert_paper, update_chunk_faiss_id, get_paper, close_connection
from embed import embed_batch
from faiss_index import add_vectors, get_index_size, load_index, save_index
from pdf_processor import process_pdf

_SCRIPT_DIR = Path(__file__).parent
_CONFIG_PATH = _SCRIPT_DIR / "config.json"

def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)


def ingest_paper(
    paper_meta: dict,
    download: bool = True,
    embed: bool = True,
    embedding_backend: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """
    Ingest a single paper: download PDF, extract text, chunk, embed, store.
    
    Args:
        paper_meta: Dict with arxiv_id, title, authors, abstract, etc.
        download: Whether to download the PDF.
        embed: Whether to generate embeddings.
        embedding_backend: Override embedding backend ('titan' or 'jina').
        dry_run: If True, only print what would happen without writing.
    
    Returns:
        Summary dict with counts.
    """
    arxiv_id = paper_meta["arxiv_id"]
    result = {"arxiv_id": arxiv_id, "chunks": 0, "embedded": 0, "status": "ok"}

    if dry_run:
        print(f"[ingest] [DRY RUN] Would ingest {arxiv_id}: {paper_meta['title'][:60]}")
        return result

    # 1. Insert paper into DB
    paper_id = insert_paper(
        arxiv_id=arxiv_id,
        title=paper_meta["title"],
        authors=paper_meta.get("authors"),
        abstract=paper_meta.get("abstract"),
        categories=paper_meta.get("categories"),
        published=paper_meta.get("published"),
        updated=paper_meta.get("updated"),
        pdf_path=paper_meta.get("pdf_path"),
        status="ingesting",
    )

    # 2. Download PDF
    pdf_path = paper_meta.get("pdf_path")
    if download and not pdf_path:
        pdf_path = download_pdf(arxiv_id, paper_meta.get("pdf_url"))
        if pdf_path:
            conn = get_connection()
            conn.execute("UPDATE papers SET pdf_path = ? WHERE id = ?", [pdf_path, paper_id])
            conn.commit()
            conn.close()

    # 3. Extract + chunk
    chunks = []
    if pdf_path:
        chunks = process_pdf(pdf_path)
    
    if not chunks and paper_meta.get("abstract"):
        # Fallback: use abstract as a single chunk
        chunks = [{
            "section": "Abstract",
            "text": paper_meta["abstract"],
            "token_count": len(paper_meta["abstract"].split()),
            "chunk_index": 0,
        }]

    # 4. Store chunks in DB
    chunk_ids = []
    chunk_texts = []
    for chunk in chunks:
        cid = insert_chunk(
            paper_id=paper_id,
            section=chunk["section"],
            chunk_index=chunk["chunk_index"],
            text=chunk["text"],
            token_count=chunk["token_count"],
        )
        chunk_ids.append(cid)
        chunk_texts.append(chunk["text"])
    result["chunks"] = len(chunk_ids)

    # 5. Embed + add to FAISS
    if embed and chunk_texts:
        try:
            import numpy as np
            vectors = embed_batch(chunk_texts, backend=embedding_backend)
            faiss_ids = add_vectors(vectors, chunk_ids)
            
            # Update chunks with faiss_id and model info in a single connection
            model_name = embedding_backend or _load_config()["embedding"].get("primary", "titan")
            conn = get_connection()
            for cid, fid in zip(chunk_ids, faiss_ids):
                conn.execute(
                    "UPDATE chunks SET faiss_id = ?, embedding_model = ? WHERE id = ?",
                    [fid, model_name, cid],
                )
            conn.commit()
            conn.close()
            result["embedded"] = len(faiss_ids)
        except Exception as e:
            print(f"[ingest] Embedding failed for {arxiv_id}: {e}")
            result["status"] = "partial"

    # 6. Update paper status
    conn = get_connection()
    status = "indexed" if result["embedded"] > 0 else "chunked" if result["chunks"] > 0 else "metadata_only"
    conn.execute("UPDATE papers SET status = ?, updated_at = current_timestamp WHERE id = ?",
                 [status, paper_id])
    conn.commit()
    conn.close()

    print(f"[ingest] {arxiv_id}: {result['chunks']} chunks, {result['embedded']} embedded → {status}")
    return result


def crawl_and_ingest(
    topics: Optional[list[str]] = None,
    days_back: int = 7,
    max_results: int = 500,
    embed: bool = True,
    embedding_backend: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """
    Full pipeline: crawl all topics, then ingest each paper.
    
    Returns:
        Summary dict with total counts.
    """
    init_db()
    if not dry_run:
        load_index()

    print(f"[ingest] Starting crawl (days_back={days_back}, max_results={max_results})")
    papers = crawl_all_topics(
        topics=topics,
        max_results=max_results,
        days_back=days_back,
        download=False,  # We download in ingest_paper
    )

    # Filter already-ingested
    new_papers = []
    for p in papers:
        existing = get_paper(p["arxiv_id"])
        if existing and existing.get("status") in ("indexed", "chunked"):
            continue
        new_papers.append(p)

    print(f"[ingest] {len(new_papers)} new papers to ingest (of {len(papers)} found)")

    summary = {"total_found": len(papers), "new": len(new_papers), "ingested": 0,
               "chunks": 0, "embedded": 0, "errors": 0}

    for i, paper in enumerate(new_papers):
        print(f"\n[ingest] [{i+1}/{len(new_papers)}] {paper['arxiv_id']}: {paper['title'][:60]}")
        try:
            result = ingest_paper(
                paper, download=True, embed=embed,
                embedding_backend=embedding_backend, dry_run=dry_run,
            )
            summary["ingested"] += 1
            summary["chunks"] += result["chunks"]
            summary["embedded"] += result["embedded"]
        except Exception as e:
            print(f"[ingest] Error: {e}")
            summary["errors"] += 1

        # Small delay between papers
        if i < len(new_papers) - 1:
            time.sleep(1)

    # Save FAISS index
    if not dry_run and summary["embedded"] > 0:
        save_index()

    print(f"\n[ingest] Done! {summary}")
    return summary


def ingest_single(
    arxiv_id: str,
    embed: bool = True,
    embedding_backend: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Ingest a single paper by arXiv ID."""
    init_db()
    if not dry_run:
        load_index()

    # Search for the paper
    papers = search_arxiv(arxiv_id, max_results=1, days_back=365 * 5)
    if not papers:
        # Try direct metadata fetch
        papers = [{"arxiv_id": arxiv_id, "title": f"Paper {arxiv_id}", "abstract": None}]

    result = ingest_paper(
        papers[0], download=True, embed=embed,
        embedding_backend=embedding_backend, dry_run=dry_run,
    )

    if not dry_run and result["embedded"] > 0:
        save_index()

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ResearchBase ingestion pipeline")
    parser.add_argument("--days", type=int, default=7, help="Days to look back")
    parser.add_argument("--max-results", type=int, default=50, help="Max results per topic")
    parser.add_argument("--arxiv", type=str, help="Ingest a specific arXiv paper ID")
    parser.add_argument("--backend", type=str, choices=["titan", "jina"], help="Embedding backend")
    parser.add_argument("--no-embed", action="store_true", help="Skip embedding")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no writes)")
    args = parser.parse_args()

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

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
