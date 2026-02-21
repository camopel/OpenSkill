---
name: ddgs-search
description: Free multi-engine web search via ddgs CLI (DuckDuckGo, Google, Bing, Brave, Yandex, Yahoo, Wikipedia) + arXiv API search. No API keys required. Use when user needs web search, research paper discovery, or when other skills need a search backend. Drop-in replacement for web-search-plus.
metadata: {"openclaw":{"requires":{"bins":["ddgs","python3"]}}}
---

# ddgs-search

Free multi-engine web search + arXiv paper search. Zero API keys, zero cost.

## Install

```bash
bash scripts/install.sh
# or manually:
pip install ddgs
```

## Web Search

```bash
# Google (default)
python3 scripts/search.py -q "your query" -m 5

# Other engines
python3 scripts/search.py -q "your query" -b bing
python3 scripts/search.py -q "your query" -b duckduckgo
python3 scripts/search.py -q "your query" -b brave
python3 scripts/search.py -q "your query" -b yandex
python3 scripts/search.py -q "your query" -b yahoo
python3 scripts/search.py -q "your query" -b wikipedia
```

Output (web-search-plus compatible JSON):
```json
{
  "provider": "ddgs",
  "results": [
    {"title": "...", "url": "...", "snippet": "...", "published_date": "..."}
  ]
}
```

## arXiv Search

```bash
# Search by topic
python3 scripts/arxiv_search.py -q "3D gaussian splatting" -m 10

# Field-specific search
python3 scripts/arxiv_search.py -q "ti:transformer AND cat:cs.CV" -m 5

# Sort by relevance
python3 scripts/arxiv_search.py -q "reinforcement learning" --sort-by relevance
```

Returns authors, categories, abstracts — same JSON format.

## Direct CLI

```bash
ddgs text -q "query" -m 5 -b google
ddgs text -q "query" -m 10 -b bing -o /tmp/results.json
```

## Integration

Set `WEB_SEARCH_PLUS_PATH` to use as a search backend for other skills:
```bash
export WEB_SEARCH_PLUS_PATH="path/to/ddgs-search/scripts/search.py"
```
