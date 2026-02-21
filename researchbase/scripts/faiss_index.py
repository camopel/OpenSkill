"""
faiss_index.py — FAISS index manager for ResearchBase.

Uses IndexFlatIP (inner product on normalised vectors = cosine similarity).
Supports GPU acceleration via faiss-gpu.
"""

import json
import os
from pathlib import Path
from typing import Optional

import faiss
import numpy as np

_SCRIPT_DIR = Path(__file__).parent
_CONFIG_PATH = _SCRIPT_DIR / "config.json"

def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)

def _resolve_path(p: str) -> str:
    return str(Path(p).expanduser())


# ---------------------------------------------------------------------------
# Index paths
# ---------------------------------------------------------------------------

def _faiss_dir() -> str:
    cfg = _load_config()
    d = os.path.join(_resolve_path(cfg["data_dir"]), "faiss")
    os.makedirs(d, exist_ok=True)
    return d

def _index_path() -> str:
    return os.path.join(_faiss_dir(), "researchbase.faiss")

def _id_map_path() -> str:
    return os.path.join(_faiss_dir(), "id_map.npy")


# ---------------------------------------------------------------------------
# Index manager
# ---------------------------------------------------------------------------

_index: Optional[faiss.Index] = None
_gpu_res: Optional[faiss.StandardGpuResources] = None
_id_map: list[int] = []  # Maps FAISS position → chunk_id


def _get_dimensions() -> int:
    return _load_config()["embedding"].get("dimensions", 1024)


def _try_gpu(index: faiss.Index) -> faiss.Index:
    """
    Attempt GPU acceleration for the FAISS index.
    
    Currently disabled due to CUDA kernel compatibility issues
    (faiss-gpu compiled for different CUDA arch). CPU IndexFlatIP is fast
    enough for <1M vectors.
    """
    # GPU disabled — faiss-gpu has CUDA arch mismatch. CPU is fine for our scale.
    return index


def load_index() -> faiss.Index:
    """Load the FAISS index from disk, or create a new one."""
    global _index, _id_map
    idx_path = _index_path()
    map_path = _id_map_path()

    if os.path.exists(idx_path):
        cpu_index = faiss.read_index(idx_path)
        _index = _try_gpu(cpu_index)
        if os.path.exists(map_path):
            _id_map = np.load(map_path).tolist()
        else:
            _id_map = list(range(cpu_index.ntotal))
        print(f"[faiss] Loaded index with {_index.ntotal} vectors")
    else:
        dim = _get_dimensions()
        cpu_index = faiss.IndexFlatIP(dim)
        _index = _try_gpu(cpu_index)
        _id_map = []
        print(f"[faiss] Created new {dim}-d IndexFlatIP")

    return _index


def get_index() -> faiss.Index:
    """Get the current index, loading if necessary."""
    global _index
    if _index is None:
        load_index()
    return _index


def save_index() -> None:
    """Persist the FAISS index and id map to disk."""
    global _index, _id_map
    if _index is None:
        return

    # Convert GPU index back to CPU for saving
    try:
        cpu_index = faiss.index_gpu_to_cpu(_index)
    except Exception:
        cpu_index = _index

    faiss.write_index(cpu_index, _index_path())
    np.save(_id_map_path(), np.array(_id_map, dtype=np.int64))
    print(f"[faiss] Saved index ({cpu_index.ntotal} vectors) to {_index_path()}")


def add_vectors(vectors: np.ndarray, chunk_ids: list[int]) -> list[int]:
    """
    Add vectors to the index.
    
    Args:
        vectors: (N, dim) float32 array of normalised vectors.
        chunk_ids: List of corresponding chunk database IDs.
    
    Returns:
        List of FAISS position IDs assigned to each vector.
    """
    global _id_map
    index = get_index()
    assert vectors.ndim == 2, f"Expected 2D array, got {vectors.ndim}D"
    assert vectors.shape[0] == len(chunk_ids), "vectors and chunk_ids length mismatch"

    start_id = index.ntotal
    index.add(vectors.astype(np.float32))
    faiss_ids = list(range(start_id, start_id + len(chunk_ids)))
    _id_map.extend(chunk_ids)

    return faiss_ids


def search(query_vector: np.ndarray, top_k: int = 50) -> list[dict]:
    """
    Search the index for similar vectors.
    
    Args:
        query_vector: (dim,) or (1, dim) float32 normalised query vector.
        top_k: Number of results to return.
    
    Returns:
        List of dicts with 'faiss_id', 'chunk_id', 'score'.
    """
    index = get_index()
    if index.ntotal == 0:
        return []

    if query_vector.ndim == 1:
        query_vector = query_vector.reshape(1, -1)

    actual_k = min(top_k, index.ntotal)
    scores, indices = index.search(query_vector.astype(np.float32), actual_k)

    results = []
    for i in range(actual_k):
        faiss_id = int(indices[0][i])
        if faiss_id < 0:
            continue
        chunk_id = _id_map[faiss_id] if faiss_id < len(_id_map) else faiss_id
        results.append({
            "faiss_id": faiss_id,
            "chunk_id": chunk_id,
            "score": float(scores[0][i]),
        })
    return results


def get_index_size() -> int:
    """Return the number of vectors in the index."""
    index = get_index()
    return index.ntotal


def reset_index() -> None:
    """Delete the index files and reset in-memory state."""
    global _index, _id_map
    _index = None
    _id_map = []
    for p in [_index_path(), _id_map_path()]:
        if os.path.exists(p):
            os.remove(p)
    print("[faiss] Index reset.")


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    dim = _get_dimensions()

    # Fresh index
    reset_index()
    load_index()
    print(f"[faiss] Index size: {get_index_size()}")

    # Add some random vectors
    rng = np.random.default_rng(42)
    vecs = rng.standard_normal((10, dim)).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs = vecs / norms
    chunk_ids = list(range(100, 110))

    faiss_ids = add_vectors(vecs, chunk_ids)
    print(f"[faiss] Added 10 vectors, faiss_ids={faiss_ids}")
    print(f"[faiss] Index size: {get_index_size()}")

    # Search
    query = vecs[0]
    results = search(query, top_k=3)
    print(f"[faiss] Search results: {results}")
    assert results[0]["chunk_id"] == 100, "First result should be the query itself"
    assert results[0]["score"] > 0.99, "Self-similarity should be ~1.0"

    # Save and reload
    save_index()
    _index = None
    _id_map = []
    load_index()
    print(f"[faiss] After reload, size: {get_index_size()}")
    results2 = search(query, top_k=3)
    assert results2[0]["chunk_id"] == results[0]["chunk_id"]

    # Cleanup
    reset_index()
    print("[faiss] All tests passed ✓")
