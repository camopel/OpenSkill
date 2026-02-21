# OpenSkill

Open-source skills for [OpenClaw](https://github.com/openclaw/openclaw) agents. Installable via [ClawHub](https://clawhub.com).

## Skills

| Skill | Description | Status |
|-------|-------------|--------|
| [ddgs-search](./ddgs-search/) | Free multi-engine web search (Google, Bing, DuckDuckGo, Brave, Yandex, Yahoo, Wikipedia) + arXiv API. No API keys. | ✅ Ready |
| [finviz-crawler](./finviz-crawler/) | Continuous financial news crawler daemon with SQLite storage and query tool. | ✅ Ready |
| [researchbase](./researchbase/) | Academic paper pipeline — arXiv crawl, PDF extraction, chunking, embedding, FAISS search, LLM summarization, gap analysis. | 🚧 WIP |

## Install

```bash
# Via ClawHub
clawhub install ddgs-search
clawhub install finviz-crawler

# Or clone directly
git clone https://github.com/camopel/OpenSkill.git
cp -r OpenSkill/ddgs-search ~/.openclaw/workspace/skills/
```

## Requirements

- [OpenClaw](https://github.com/openclaw/openclaw) agent
- Python 3.10+
- Per-skill dependencies listed in each SKILL.md

## License

MIT
