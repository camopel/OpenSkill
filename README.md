# OpenSkill

Open-source skills for [OpenClaw](https://github.com/openclaw/openclaw) agents. Installable via [ClawHub](https://clawhub.com).

## Skills

| Skill | Description | Status |
|-------|-------------|--------|
| [ddgs-search](./ddgs-search/) | Free multi-engine web search (Google, Bing, DuckDuckGo, Brave, Yandex, Yahoo, Wikipedia) + arXiv API. No API keys. | ✅ Ready |
| [finviz-crawler](./finviz-crawler/) | Continuous financial news crawler daemon with SQLite storage, auto-cleanup, and query tool. | ✅ Ready |

## Install

```bash
# Via ClawHub
clawhub install ddgs-search
clawhub install finviz-crawler

# Or clone and copy
git clone https://github.com/camopel/OpenSkill.git
cp -r OpenSkill/ddgs-search ~/.openclaw/workspace/skills/
cp -r OpenSkill/finviz-crawler ~/.openclaw/workspace/skills/

# Then install dependencies
python3 ~/.openclaw/workspace/skills/ddgs-search/scripts/install.py
python3 ~/.openclaw/workspace/skills/finviz-crawler/scripts/install.py
```

## Requirements

- [OpenClaw](https://github.com/openclaw/openclaw) agent
- Python 3.10+
- Per-skill dependencies handled by each skill's `install.py`

## License

MIT
