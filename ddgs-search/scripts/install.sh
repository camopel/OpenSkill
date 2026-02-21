#!/usr/bin/env bash
# Install ddgs-search dependencies
set -e

echo "Installing ddgs CLI..."
pip install --user ddgs 2>/dev/null || pip install ddgs

# Verify
if command -v ddgs &>/dev/null; then
    echo "✅ ddgs installed: $(which ddgs)"
else
    echo "⚠️  ddgs installed but not in PATH. Add ~/.local/bin to PATH:"
    echo '  export PATH="$HOME/.local/bin:$PATH"'
fi

# Quick test
echo "Testing search..."
python3 "$(dirname "$0")/search.py" -q "test" -m 1 -b duckduckgo && echo "✅ Search works" || echo "❌ Search failed"
