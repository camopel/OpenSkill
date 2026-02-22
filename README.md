# OpenSkill

Open-source skills for [OpenClaw](https://github.com/camopel/openclaw) agents.

## Skills

| Skill | Description |
|-------|-------------|
| [ddgs-search](./ddgs-search/) | Free multi-engine web search (Google, Bing, DuckDuckGo, Brave, Yandex, Yahoo) + arXiv API. No API keys. |
| [finviz-crawler](./finviz-crawler/) | Continuous financial news crawler daemon with SQLite storage, auto-cleanup, and query tool. |
| [arxivkb](./arxivkb/) | arXiv paper crawler with semantic search (FAISS) and optional LLM summarization. Local embeddings. |

## PrivateApp Integration

These skills power apps in [PrivateApp](https://github.com/camopel/PrivateApp) — a personal PWA dashboard that runs on your home server.

| Skill | PrivateApp App |
|-------|-------------|
| finviz-crawler | 📰 Market News — financial headlines and article reader |
| arxivkb | 🔬 ArXiv — research paper search and topic browser |

Install the skills, then PrivateApp auto-detects their data and shows the app in the Market tab.

## Install

```bash
# Clone the repo
git clone https://github.com/camopel/OpenSkill.git

# Install a skill
python3 OpenSkill/ddgs-search/scripts/install.py
python3 OpenSkill/finviz-crawler/scripts/install.py
python3 OpenSkill/arxivkb/scripts/install.py
```

Each skill's `install.py` handles cross-platform dependency installation (macOS and Linux), data directory creation, and optional background service setup.

## Requirements

- Python 3.8+ (`ddgs-search`) or Python 3.10+ (all others)
- macOS or Linux
- Per-skill dependencies handled automatically by each skill's `install.py`

### Hardware Requirements

| Skill | RAM | Disk | Notes |
|-------|-----|------|-------|
| **ddgs-search** | Any | Minimal | Web search only, no local models |
| **finviz-crawler** | 512MB+ | ~1GB per 10K articles | SQLite + markdown files |
| **arxivkb** | **2GB+** | **500MB+ base** | Embedding model loaded in RAM during search |

#### ArXivKB Embedding Models

| Model | RAM | Disk | Notes |
|-------|-----|------|-------|
| `nomic-embed-text` (via Ollama, default) | ~300MB | 270MB | Requires [Ollama](https://ollama.ai) |
| `all-MiniLM-L6-v2` | ~300MB | 80MB | Pure Python, no Ollama needed |
| `BAAI/bge-large-en-v1.5` | ~2.5GB | 1.3GB | 4GB+ RAM recommended |

## License

MIT — [LICENSE](./LICENSE)
