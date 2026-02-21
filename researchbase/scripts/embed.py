"""
embed.py — Embedding pipeline for ResearchBase.

Uses Amazon Titan Text Embeddings V2 via Bedrock.
All outputs are 1024-dimensional normalised float32 vectors.
Retries up to 10 times with exponential backoff on transient failures.
"""

import json
import time
from pathlib import Path

import numpy as np

_SCRIPT_DIR = Path(__file__).parent
_CONFIG_PATH = _SCRIPT_DIR / "config.json"

MAX_RETRIES = 10
BASE_DELAY = 1.0  # seconds


def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Titan V2 backend
# ---------------------------------------------------------------------------

_bedrock_client = None


def _get_bedrock_client():
    """Lazy-init Bedrock Runtime client."""
    global _bedrock_client
    if _bedrock_client is None:
        import boto3
        cfg = _load_config()["embedding"]
        _bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=cfg.get("aws_region", "us-east-1"),
        )
    return _bedrock_client


def _embed_titan(text: str) -> np.ndarray:
    """Embed a single text using Amazon Titan V2 with retry logic."""
    cfg = _load_config()["embedding"]
    client = _get_bedrock_client()
    body = json.dumps({
        "inputText": text[:8192],
        "dimensions": cfg.get("dimensions", 1024),
        "normalize": True,
    })

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.invoke_model(
                modelId=cfg.get("titan_model_id", "amazon.titan-embed-text-v2:0"),
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(resp["body"].read())
            return np.array(result["embedding"], dtype=np.float32)
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                delay = min(BASE_DELAY * (2 ** (attempt - 1)), 60)
                print(f"[embed] Attempt {attempt}/{MAX_RETRIES} failed: {e}. Retrying in {delay:.0f}s...")
                time.sleep(delay)
            else:
                print(f"[embed] All {MAX_RETRIES} attempts failed.")

    raise RuntimeError(f"Titan embedding failed after {MAX_RETRIES} retries: {last_error}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def embed_text(text: str, **_kwargs) -> np.ndarray:
    """Embed a single document text. Returns a 1024-d float32 vector."""
    return _embed_titan(text)


def embed_batch(texts: list[str], **_kwargs) -> np.ndarray:
    """Embed a batch of document texts. Returns (N, 1024) float32 array."""
    if not texts:
        return np.zeros((0, 1024), dtype=np.float32)
    embeddings = [_embed_titan(t) for t in texts]
    return np.stack(embeddings)


def embed_query(query: str, **_kwargs) -> np.ndarray:
    """Embed a search query. Returns a 1024-d float32 vector."""
    return _embed_titan(query)


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("[embed] Testing Titan backend...")
    vec = embed_text("Hello world, this is a test.")
    print(f"  shape={vec.shape}, norm={np.linalg.norm(vec):.4f}")

    vec_q = embed_query("What is gaussian splatting?")
    print(f"  query shape={vec_q.shape}")

    vecs = embed_batch(["text one", "text two", "text three"])
    print(f"  batch shape={vecs.shape}")

    print("[embed] Done ✓")
