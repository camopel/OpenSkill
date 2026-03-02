# OpenSkill

Open-source skills for [OpenClaw](https://github.com/openclaw/openclaw) agents.

Published on [ClawHub](https://clawhub.com) as `@camopel/*`.

## Skills

| Skill | Description | ClawHub |
|-------|-------------|---------|
| [ddgs-search](./ddgs-search/) | Free multi-engine web search (Google, Bing, DuckDuckGo, Brave, Yandex, Yahoo) + arXiv API. No API keys. | `@camopel/ddgs-search` |
| [finviz-crawler](./finviz-crawler/) | Continuous financial news crawler daemon with SQLite storage, auto-cleanup, and query tool. | `@camopel/finviz-crawler` |
| [arxivkb](./arxivkb/) | arXiv paper crawler with semantic search (FAISS) and optional LLM summarization. Local embeddings. | `@camopel/arxivkb` |
| [claw-guard](./claw-guard/) | System-level watchdog for OpenClaw gateway restarts and sub-agent task PIDs. Auto-reverts config on failed restarts. | — |

## Install

### From ClawHub
```bash
clawhub install @camopel/ddgs-search
clawhub install @camopel/finviz-crawler
clawhub install @camopel/arxivkb
```

### From source
```bash
git clone https://github.com/camopel/OpenSkill.git
# Each skill has its own install script:
bash OpenSkill/ddgs-search/scripts/install.sh
bash OpenSkill/clawguard/scripts/install.sh
```

## Requirements

- Python 3.8+ (`ddgs-search`) or Python 3.10+ (all others)
- macOS or Linux
- Per-skill dependencies handled by each skill's installer

## License

MIT — [LICENSE](./LICENSE)
