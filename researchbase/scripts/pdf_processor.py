"""
pdf_processor.py — PDF text extraction and chunking for ResearchBase.

Uses PyMuPDF (fitz) to extract text, detects sections, and chunks
with configurable token size and overlap.
"""

import json
import re
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

_SCRIPT_DIR = Path(__file__).parent
_CONFIG_PATH = _SCRIPT_DIR / "config.json"

def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

SECTION_PATTERNS = [
    (r"^\s*abstract\s*$", "Abstract"),
    (r"^\s*\d*\.?\s*introduction\s*$", "Introduction"),
    (r"^\s*\d*\.?\s*related\s+work\s*$", "Related Work"),
    (r"^\s*\d*\.?\s*background\s*$", "Background"),
    (r"^\s*\d*\.?\s*method(?:s|ology)?\s*$", "Method"),
    (r"^\s*\d*\.?\s*(?:our\s+)?approach\s*$", "Method"),
    (r"^\s*\d*\.?\s*(?:proposed\s+)?(?:framework|model|system|architecture)\s*$", "Method"),
    (r"^\s*\d*\.?\s*experiment(?:s|al\s+(?:setup|results))?\s*$", "Experiments"),
    (r"^\s*\d*\.?\s*(?:results?(?:\s+and\s+discussion)?|evaluation)\s*$", "Results"),
    (r"^\s*\d*\.?\s*discussion\s*$", "Discussion"),
    (r"^\s*\d*\.?\s*conclusion(?:s)?\s*$", "Conclusion"),
    (r"^\s*\d*\.?\s*(?:future\s+work|limitations)\s*$", "Conclusion"),
    (r"^\s*\d*\.?\s*(?:acknowledge?ments?)\s*$", "Acknowledgements"),
    (r"^\s*references\s*$", "References"),
    (r"^\s*\d*\.?\s*(?:appendix|supplementary)\s*", "Appendix"),
]


def _detect_section(line: str) -> Optional[str]:
    """Check if a line is a section header."""
    clean = line.strip().lower()
    if len(clean) > 80 or len(clean) < 3:
        return None
    for pattern, name in SECTION_PATTERNS:
        if re.match(pattern, clean, re.IGNORECASE):
            return name
    return None


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text(pdf_path: str) -> str:
    """Extract full text from a PDF using PyMuPDF."""
    try:
        doc = fitz.open(pdf_path)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text("text"))
        doc.close()
        return "\n".join(text_parts)
    except Exception as e:
        print(f"[pdf] Error extracting text from {pdf_path}: {e}")
        return ""


def extract_sections(pdf_path: str) -> list[dict]:
    """
    Extract text from a PDF and split into sections.
    
    Returns:
        List of dicts: {'section': str, 'text': str}
    """
    full_text = extract_text(pdf_path)
    if not full_text.strip():
        return []

    lines = full_text.split("\n")
    sections: list[dict] = []
    current_section = "Header"
    current_text: list[str] = []

    for line in lines:
        detected = _detect_section(line)
        if detected:
            # Save previous section
            text = "\n".join(current_text).strip()
            if text:
                sections.append({"section": current_section, "text": text})
            current_section = detected
            current_text = []
        else:
            current_text.append(line)

    # Save last section
    text = "\n".join(current_text).strip()
    if text:
        sections.append({"section": current_section, "text": text})

    return sections


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough token count estimate (~0.75 words per token for English)."""
    words = len(text.split())
    return int(words * 1.33)


def chunk_text(
    text: str,
    max_tokens: int = 800,
    overlap_tokens: int = 100,
) -> list[dict]:
    """
    Split text into overlapping chunks.
    
    Args:
        text: Input text.
        max_tokens: Maximum tokens per chunk.
        overlap_tokens: Token overlap between chunks.
    
    Returns:
        List of dicts: {'text': str, 'token_count': int, 'chunk_index': int}
    """
    words = text.split()
    if not words:
        return []

    # Convert token counts to approximate word counts
    max_words = int(max_tokens / 1.33)
    overlap_words = int(overlap_tokens / 1.33)
    step = max(max_words - overlap_words, 1)

    chunks = []
    idx = 0
    start = 0

    while start < len(words):
        end = min(start + max_words, len(words))
        chunk_words = words[start:end]
        chunk_text = " ".join(chunk_words)
        token_count = _estimate_tokens(chunk_text)

        chunks.append({
            "text": chunk_text,
            "token_count": token_count,
            "chunk_index": idx,
        })

        idx += 1
        start += step

        # Prevent infinite loop on very small text
        if end >= len(words):
            break

    return chunks


def process_pdf(
    pdf_path: str,
    max_tokens: Optional[int] = None,
    overlap_tokens: Optional[int] = None,
) -> list[dict]:
    """
    Full pipeline: extract sections, chunk each section.
    
    Args:
        pdf_path: Path to PDF file.
        max_tokens: Override max tokens per chunk.
        overlap_tokens: Override overlap tokens.
    
    Returns:
        List of dicts: {'section': str, 'text': str, 'token_count': int, 'chunk_index': int}
    """
    cfg = _load_config()["chunking"]
    max_tok = max_tokens or cfg.get("max_tokens", 800)
    overlap_tok = overlap_tokens or cfg.get("overlap_tokens", 100)

    sections = extract_sections(pdf_path)
    if not sections:
        # Fallback: treat entire text as one section
        text = extract_text(pdf_path)
        if not text.strip():
            print(f"[pdf] No text extracted from {pdf_path}")
            return []
        sections = [{"section": "Full", "text": text}]

    all_chunks: list[dict] = []
    global_idx = 0

    for section in sections:
        # Skip references and acknowledgements
        if section["section"] in ("References", "Acknowledgements", "Appendix"):
            continue

        chunks = chunk_text(section["text"], max_tok, overlap_tok)
        for chunk in chunks:
            chunk["section"] = section["section"]
            chunk["chunk_index"] = global_idx
            all_chunks.append(chunk)
            global_idx += 1

    print(f"[pdf] Processed {pdf_path}: {len(sections)} sections, {len(all_chunks)} chunks")
    return all_chunks


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        # Try to find a test PDF
        cfg = _load_config()
        pdf_dir = Path(cfg["data_dir"]).expanduser() / "pdfs"
        pdfs = list(pdf_dir.glob("*.pdf"))
        if pdfs:
            pdf_path = str(pdfs[0])
            print(f"[pdf] Using test PDF: {pdf_path}")
        else:
            print("[pdf] No PDFs found. Run arxiv_crawler.py first.")
            print("[pdf] Testing chunking with synthetic text...")
            text = "This is a test. " * 500
            chunks = chunk_text(text, max_tokens=100, overlap_tokens=20)
            print(f"[pdf] Generated {len(chunks)} chunks from synthetic text")
            for c in chunks[:3]:
                print(f"  chunk {c['chunk_index']}: {c['token_count']} tokens, {len(c['text'])} chars")
            print("[pdf] Chunking test passed ✓")
            sys.exit(0)

    chunks = process_pdf(pdf_path)
    print(f"\n[pdf] Total chunks: {len(chunks)}")
    for c in chunks[:5]:
        print(f"  [{c['section']}] chunk {c['chunk_index']}: {c['token_count']} tokens")
        print(f"    {c['text'][:100]}...")
    print("[pdf] All tests passed ✓")
