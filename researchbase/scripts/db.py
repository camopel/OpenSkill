"""
db.py — SQLite (WAL mode) schema + CRUD operations for ResearchBase.

Manages papers, chunks, techniques, benchmarks, repos, and their relationships.
Uses SQLite WAL mode for concurrent readers + single writer without locking.
Array columns (authors, categories, etc.) are stored as JSON text.
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Resolve config
_SCRIPT_DIR = Path(__file__).parent
_CONFIG_PATH = _SCRIPT_DIR / "config.json"

def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)

def _resolve_path(p: str) -> str:
    return str(Path(p).expanduser())


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def _db_path() -> str:
    """Resolve database path from config."""
    cfg = _load_config()
    p = _resolve_path(cfg["db_path"])
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def get_connection(read_only: bool = False) -> sqlite3.Connection:
    """Return a SQLite connection with WAL mode enabled.

    read_only is accepted for API compatibility but SQLite WAL handles
    concurrent readers natively, so it's effectively ignored.
    """
    conn = sqlite3.connect(_db_path(), timeout=30)
    conn.row_factory = None  # tuples (default)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    if read_only:
        conn.execute("PRAGMA query_only=ON")
    return conn


def close_connection() -> None:
    """No-op for API compatibility. Connections are opened/closed per-call."""
    pass


# ---------------------------------------------------------------------------
# JSON helpers for array columns
# ---------------------------------------------------------------------------

def _to_json(val) -> Optional[str]:
    """Convert a Python list/None to a JSON string for storage."""
    if val is None:
        return None
    if isinstance(val, list):
        return json.dumps(val)
    if isinstance(val, str):
        return val
    return json.dumps(val)


def _from_json(val) -> Optional[list]:
    """Parse a JSON string back to a Python list."""
    if val is None:
        return None
    if isinstance(val, list):
        return val
    try:
        result = json.loads(val)
        return result if isinstance(result, list) else [result]
    except (json.JSONDecodeError, TypeError):
        return None


_PAPER_ARRAY_COLS = {"authors", "categories", "techniques"}
_REPO_ARRAY_COLS = {"languages", "frameworks"}
_ALL_ARRAY_COLS = _PAPER_ARRAY_COLS | _REPO_ARRAY_COLS


def _parse_row_arrays(d: dict, array_cols: set[str] | None = None) -> dict:
    """Parse JSON array columns in a row dict back to Python lists."""
    if array_cols is None:
        array_cols = _ALL_ARRAY_COLS
    for col in array_cols:
        if col in d:
            d[col] = _from_json(d[col])
    return d


def _cursor_to_dicts(cur: sqlite3.Cursor, array_cols: set[str] | None = None) -> list[dict]:
    """Convert cursor results to list of dicts, parsing JSON array columns."""
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    results = []
    for r in rows:
        d = dict(zip(cols, r))
        if array_cols is not None:
            _parse_row_arrays(d, array_cols)
        results.append(d)
    return results


def _cursor_to_dict(cur: sqlite3.Cursor, array_cols: set[str] | None = None) -> Optional[dict]:
    """Convert single cursor result to dict, parsing JSON array columns."""
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    d = dict(zip(cols, row))
    if array_cols is not None:
        _parse_row_arrays(d, array_cols)
    return d


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arxiv_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    authors TEXT,
    abstract TEXT,
    categories TEXT,
    published TEXT,
    updated TEXT,
    pdf_path TEXT,
    full_text_path TEXT,
    summary TEXT,
    techniques TEXT,
    status TEXT DEFAULT 'new',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER REFERENCES papers(id),
    section TEXT,
    chunk_index INTEGER,
    text TEXT NOT NULL,
    token_count INTEGER,
    faiss_id INTEGER,
    embedding_model TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS techniques (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    category TEXT,
    description TEXT,
    first_paper_id INTEGER REFERENCES papers(id),
    status TEXT DEFAULT 'promising',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS benchmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER REFERENCES papers(id),
    technique_id INTEGER REFERENCES techniques(id),
    dataset TEXT,
    metric TEXT,
    value REAL,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS repos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    paper_id INTEGER REFERENCES papers(id),
    stars INTEGER,
    last_commit TEXT,
    languages TEXT,
    frameworks TEXT,
    status TEXT DEFAULT 'discovered',
    clone_path TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS paper_techniques (
    paper_id INTEGER REFERENCES papers(id),
    technique_id INTEGER REFERENCES techniques(id),
    PRIMARY KEY (paper_id, technique_id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_paper_id ON chunks(paper_id);
CREATE INDEX IF NOT EXISTS idx_chunks_faiss_id ON chunks(faiss_id);
CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status);
CREATE INDEX IF NOT EXISTS idx_papers_published ON papers(published);
CREATE INDEX IF NOT EXISTS idx_benchmarks_paper_id ON benchmarks(paper_id);
CREATE INDEX IF NOT EXISTS idx_benchmarks_technique_id ON benchmarks(technique_id);
CREATE INDEX IF NOT EXISTS idx_repos_paper_id ON repos(paper_id);
"""


def init_db() -> None:
    """Create all tables if they don't exist."""
    conn = get_connection()
    try:
        for stmt in _SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
        print("[db] Schema initialised.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Papers CRUD
# ---------------------------------------------------------------------------

def insert_paper(
    arxiv_id: str,
    title: str,
    authors: list[str] | None = None,
    abstract: str | None = None,
    categories: list[str] | None = None,
    published: str | None = None,
    updated: str | None = None,
    pdf_path: str | None = None,
    status: str = "new",
) -> int:
    """Insert a paper. Returns the paper id. Skips if arxiv_id already exists."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM papers WHERE arxiv_id = ?", [arxiv_id]
        ).fetchone()
        if existing:
            return existing[0]

        conn.execute(
            """INSERT INTO papers (arxiv_id, title, authors, abstract, categories,
                                   published, updated, pdf_path, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [arxiv_id, title, _to_json(authors), abstract, _to_json(categories),
             published, updated, pdf_path, status],
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM papers WHERE arxiv_id = ?", [arxiv_id]
        ).fetchone()
        return row[0]
    finally:
        conn.close()


def get_paper(arxiv_id: str) -> Optional[dict]:
    """Fetch a paper by arxiv_id."""
    conn = get_connection(read_only=True)
    try:
        cur = conn.execute(
            "SELECT * FROM papers WHERE arxiv_id = ?", [arxiv_id]
        )
        return _cursor_to_dict(cur, _PAPER_ARRAY_COLS)
    finally:
        conn.close()


def search_papers(
    query: str | None = None,
    category: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search papers by title/abstract text, category, or status."""
    conn = get_connection(read_only=True)
    try:
        conditions = []
        params: list[Any] = []

        if query:
            conditions.append("(title LIKE ? COLLATE NOCASE OR abstract LIKE ? COLLATE NOCASE)")
            params.extend([f"%{query}%", f"%{query}%"])
        if category:
            # categories is a JSON array stored as text, use LIKE on the JSON string
            conditions.append("categories LIKE ?")
            params.append(f'%"{category}"%')
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT * FROM papers {where} ORDER BY published DESC LIMIT ?"
        params.append(limit)

        cur = conn.execute(sql, params)
        return _cursor_to_dicts(cur, _PAPER_ARRAY_COLS)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Chunks CRUD
# ---------------------------------------------------------------------------

def insert_chunk(
    paper_id: int,
    section: str,
    chunk_index: int,
    text: str,
    token_count: int,
    faiss_id: int | None = None,
    embedding_model: str | None = None,
) -> int:
    """Insert a text chunk. Returns chunk id."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO chunks (paper_id, section, chunk_index, text,
                                   token_count, faiss_id, embedding_model)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [paper_id, section, chunk_index, text, token_count, faiss_id,
             embedding_model],
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_chunk_faiss_id(chunk_id: int, faiss_id: int) -> None:
    """Set the faiss_id for a chunk after indexing."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE chunks SET faiss_id = ? WHERE id = ?", [faiss_id, chunk_id]
        )
        conn.commit()
    finally:
        conn.close()


def get_chunks_for_paper(paper_id: int) -> list[dict]:
    """Return all chunks for a given paper, ordered by chunk_index."""
    conn = get_connection(read_only=True)
    try:
        cur = conn.execute(
            "SELECT * FROM chunks WHERE paper_id = ? ORDER BY chunk_index",
            [paper_id],
        )
        return _cursor_to_dicts(cur)
    finally:
        conn.close()


def get_chunk_by_faiss_id(faiss_id: int) -> Optional[dict]:
    """Look up a chunk by its FAISS index id."""
    conn = get_connection(read_only=True)
    try:
        cur = conn.execute(
            "SELECT c.*, p.arxiv_id, p.title as paper_title, p.authors "
            "FROM chunks c JOIN papers p ON c.paper_id = p.id "
            "WHERE c.faiss_id = ?",
            [faiss_id],
        )
        d = _cursor_to_dict(cur)
        if d:
            d["authors"] = _from_json(d.get("authors"))
        return d
    finally:
        conn.close()


def get_chunks_by_faiss_ids(faiss_ids: list[int]) -> list[dict]:
    """Look up multiple chunks by FAISS index ids."""
    if not faiss_ids:
        return []
    conn = get_connection(read_only=True)
    try:
        placeholders = ", ".join(["?"] * len(faiss_ids))
        cur = conn.execute(
            f"SELECT c.*, p.arxiv_id, p.title as paper_title, p.authors "
            f"FROM chunks c JOIN papers p ON c.paper_id = p.id "
            f"WHERE c.faiss_id IN ({placeholders})",
            faiss_ids,
        )
        results = _cursor_to_dicts(cur)
        for d in results:
            d["authors"] = _from_json(d.get("authors"))
        return results
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Techniques & Benchmarks
# ---------------------------------------------------------------------------

def insert_technique(
    name: str,
    category: str | None = None,
    description: str | None = None,
    first_paper_id: int | None = None,
    status: str = "promising",
    conn=None,
) -> int:
    """Insert a technique (upsert by name). Returns technique id."""
    _own_conn = conn is None
    if _own_conn:
        conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM techniques WHERE name = ?", [name]
        ).fetchone()
        if existing:
            return existing[0]
        conn.execute(
            """INSERT INTO techniques (name, category, description, first_paper_id, status)
               VALUES (?, ?, ?, ?, ?)""",
            [name, category, description, first_paper_id, status],
        )
        conn.commit()
        row = conn.execute("SELECT id FROM techniques WHERE name = ?", [name]).fetchone()
        return row[0]
    finally:
        if _own_conn:
            conn.close()


def insert_benchmark(
    paper_id: int,
    technique_id: int,
    dataset: str,
    metric: str,
    value: float,
    notes: str | None = None,
    conn=None,
) -> int:
    """Insert a benchmark result."""
    _own_conn = conn is None
    if _own_conn:
        conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO benchmarks (paper_id, technique_id, dataset, metric, value, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [paper_id, technique_id, dataset, metric, value, notes],
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        if _own_conn:
            conn.close()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_stats() -> dict:
    """Return counts of all entities."""
    conn = get_connection(read_only=True)
    try:
        stats = {}
        for table in ["papers", "chunks", "techniques", "benchmarks", "repos"]:
            try:
                row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
                stats[table] = row[0]
            except Exception:
                stats[table] = 0
        return stats
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    stats = get_stats()
    print(f"[db] Stats: {stats}")

    # Quick insert/retrieve test
    pid = insert_paper(
        arxiv_id="test.0000",
        title="Test Paper",
        authors=["Alice", "Bob"],
        abstract="A test abstract.",
        categories=["cs.CV"],
        published="2024-01-01",
    )
    print(f"[db] Inserted test paper id={pid}")

    paper = get_paper("test.0000")
    print(f"[db] Retrieved: {paper['title']}")
    assert paper["authors"] == ["Alice", "Bob"], f"Authors mismatch: {paper['authors']}"
    assert paper["categories"] == ["cs.CV"], f"Categories mismatch: {paper['categories']}"
    print(f"[db] Authors (list): {paper['authors']}")
    print(f"[db] Categories (list): {paper['categories']}")

    cid = insert_chunk(pid, "abstract", 0, "A test abstract.", 5)
    print(f"[db] Inserted chunk id={cid}")

    chunks = get_chunks_for_paper(pid)
    print(f"[db] Chunks for paper: {len(chunks)}")

    # Test search_papers
    found = search_papers(query="Test", category="cs.CV", limit=5)
    print(f"[db] search_papers found: {len(found)}")
    assert len(found) >= 1, "search_papers failed"

    # Clean up test data
    conn = get_connection()
    conn.execute("DELETE FROM chunks WHERE paper_id = ?", [pid])
    conn.execute("DELETE FROM papers WHERE arxiv_id = 'test.0000'")
    conn.commit()
    conn.close()

    stats = get_stats()
    print(f"[db] Final stats: {stats}")
    print("[db] All tests passed ✓")
