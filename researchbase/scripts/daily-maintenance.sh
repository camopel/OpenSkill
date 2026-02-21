#!/bin/bash
# ResearchBase daily maintenance script
# Runs ingest + summarize
set -euo pipefail

LOGDIR="$HOME/Downloads/ResearchBase/logs"
mkdir -p "$LOGDIR"

LOGFILE="$LOGDIR/daily-$(date +%Y%m%d-%H%M%S).log"
LOCKFILE="$HOME/Downloads/ResearchBase/.ingest.lock"

exec > "$LOGFILE" 2>&1

echo "===== ResearchBase Daily Maintenance ====="
echo "Started: $(date)"
echo ""

# Acquire lock — skip if another pipeline (HomeHub) is already running
exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "Another ingest pipeline is running (lock held). Skipping."
    exit 0
fi
echo "$$" >&9

# Release lock on exit
cleanup() { flock -u 9; rm -f "$LOCKFILE"; }
trap cleanup EXIT

# Activate venv
source "$HOME/Workspace/.venv/bin/activate"

# Step 1: Ingest recent papers
echo "--- Step 1: Ingesting recent papers ---"
python "$HOME/.openclaw/workspace/skills/researchbase/scripts/cli.py" ingest || true
echo ""

# Step 2: Summarize any un-summarized papers
echo "--- Step 2: Summarizing indexed papers ---"
python "$HOME/.openclaw/workspace/skills/researchbase/scripts/cli.py" summarize --all --status indexed || true
echo ""

# Step 3: Show stats
echo "--- Final Stats ---"
python "$HOME/.openclaw/workspace/skills/researchbase/scripts/cli.py" stats || true
echo ""

echo "Finished: $(date)"
echo "===== Done ====="
