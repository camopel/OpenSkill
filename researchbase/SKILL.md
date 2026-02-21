---
name: researchbase
description: "Academic paper research pipeline: arXiv crawl → PDF extraction → chunking → embedding (Amazon Titan V2) → FAISS semantic search → LLM summarization → gap analysis. Full CLI (`rb`) for search, ingest, summarize, compare. Use for academic research monitoring, paper discovery, literature review, or building a personal research knowledge base."
---

# ResearchBase

> ⚠️ **WIP** — This skill requires AWS Bedrock (Titan V2 embeddings) and an LLM endpoint (Claude via LiteLLM). Contributions to add alternative embedding backends (OpenAI, local models) are welcome.

Full academic research pipeline: crawl → index → search → summarize → analyze.

## Install

```bash
pip install arxiv faiss-cpu boto3 pdfplumber tiktoken
cp scripts/config.example.json scripts/config.json
# Edit config.json with your topics and AWS region
```

Add `rb` to your PATH:
```bash
ln -s $(pwd)/rb ~/.local/bin/rb
```

## Usage

### CLI (`rb`)

```bash
# Ingest recent papers (crawl arXiv → download PDFs → chunk → embed → index)
rb ingest --days 7

# Search papers semantically
rb search "3D gaussian splatting real-time rendering"

# Summarize papers with LLM
rb summarize --all --status indexed --limit 50

# View paper details
rb paper 2401.12345

# Index statistics
rb stats

# Gap analysis
rb gaps
```

### Pipeline

```
arXiv API → PDF download → text extraction (pdfplumber)
    → chunking (800 tokens, 100 overlap)
    → embedding (Amazon Titan V2, 1024-dim)
    → FAISS IndexFlatIP (cosine similarity)
    → SQLite metadata (WAL mode)

Summarization: Claude Sonnet via LiteLLM → structured JSON summaries
Gap analysis: cross-reference techniques and benchmarks across papers
```

### Daily Automation

```bash
# Run as a cron job or OpenClaw cron
bash scripts/daily-maintenance.sh
```

The maintenance script handles lock files to prevent concurrent runs.

## Configuration

Edit `scripts/config.json`:
- `data_dir` — where SQLite, FAISS index, and PDFs are stored
- `embedding.aws_region` — Bedrock region for Titan V2
- `crawler.topics` — arXiv search topics to monitor
- `chunking.max_tokens` — chunk size for embedding

## Data Layout

```
~/Downloads/ResearchBase/
├── sqlite/researchbase.db    # Paper metadata, chunks, summaries
├── faiss/researchbase.faiss  # Vector index (persisted)
├── faiss/id_map.npy          # FAISS position → chunk_id mapping
├── pdfs/                     # Downloaded paper PDFs
└── logs/                     # Pipeline logs
```

## Requirements

- **Embeddings**: AWS Bedrock (Amazon Titan V2) — requires AWS credentials
- **Summarization**: LLM endpoint at `http://localhost:4000` (LiteLLM proxy recommended)
- **Search**: FAISS (CPU sufficient for <1M vectors)

## TODO

- [ ] Alternative embedding backends (OpenAI, Ollama, sentence-transformers)
- [ ] Configurable LLM endpoint (not just LiteLLM)
- [ ] Web UI (currently part of HomeHub, needs extraction)
