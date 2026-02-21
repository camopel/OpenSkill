#!/usr/bin/env python3
"""
Cross-platform install script for finviz-crawler.
Works on macOS, Linux, and Windows (Python 3.10+).
"""
import subprocess
import sys
import shutil
import os


def run(cmd, check=True):
    print(f"  → {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def pip_install(packages):
    """Install packages using pip, preferring --user on non-venv systems."""
    pip_cmd = [sys.executable, "-m", "pip", "install"]
    # Use --user if not in a venv (avoids permission errors on system Python)
    if not (hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)):
        pip_cmd.append("--user")
    pip_cmd.extend(packages)
    result = run(pip_cmd, check=False)
    if result.returncode != 0:
        print(f"  ⚠️  pip install failed, retrying without --user...")
        run([sys.executable, "-m", "pip", "install"] + packages)


def main():
    print("🔧 Installing finviz-crawler dependencies...\n")

    # 1. Check Python version
    v = sys.version_info
    print(f"Python: {v.major}.{v.minor}.{v.micro}")
    if v < (3, 10):
        print("❌ Python 3.10+ required")
        sys.exit(1)
    print(f"  ✅ Python {v.major}.{v.minor}\n")

    # 2. Install Python packages
    print("Installing Python packages...")
    pip_install(["crawl4ai", "feedparser"])

    # 3. Install Playwright browsers (required by crawl4ai)
    print("\nInstalling Playwright browsers (used by crawl4ai)...")
    # crawl4ai ships its own setup command
    result = run([sys.executable, "-m", "crawl4ai.install"], check=False)
    if result.returncode != 0:
        # Fallback: try crawl4ai-setup CLI
        crawl4ai_setup = shutil.which("crawl4ai-setup")
        if crawl4ai_setup:
            run([crawl4ai_setup], check=False)
        else:
            # Last resort: install playwright directly
            print("  Falling back to playwright install...")
            run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)

    # 4. Create default data directory
    data_dir = os.path.expanduser("~/Downloads/Finviz")
    articles_dir = os.path.join(data_dir, "articles")
    os.makedirs(articles_dir, exist_ok=True)
    print(f"\n  📁 Data directory: {data_dir}")
    print(f"  📁 Articles directory: {articles_dir}")

    # 5. Verify
    print("\n🔍 Verifying installation...")
    errors = []

    try:
        import crawl4ai  # noqa: F401
        print("  ✅ crawl4ai")
    except ImportError:
        errors.append("crawl4ai")
        print("  ❌ crawl4ai")

    try:
        import feedparser  # noqa: F401
        print("  ✅ feedparser")
    except ImportError:
        errors.append("feedparser")
        print("  ❌ feedparser")

    try:
        from zoneinfo import ZoneInfo  # noqa: F401
        print("  ✅ zoneinfo")
    except ImportError:
        errors.append("zoneinfo (Python 3.9+ required)")
        print("  ❌ zoneinfo")

    # Quick test of the query script (no deps beyond stdlib)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    query_script = os.path.join(script_dir, "finviz_query.py")
    if os.path.exists(query_script):
        result = run([sys.executable, query_script, "--stats"], check=False)
        if result.returncode == 0:
            print("  ✅ query script")
        else:
            print("  ⚠️  query script (no data yet — normal for fresh install)")

    if errors:
        print(f"\n❌ Missing: {', '.join(errors)}")
        print("   Try: pip install " + " ".join(errors))
        sys.exit(1)
    else:
        print("\n✅ All dependencies installed!")
        print(f"\nRun the crawler:")
        print(f"  python3 {os.path.join(script_dir, 'finviz_crawler.py')}")
        print(f"\nQuery articles:")
        print(f"  python3 {query_script} --hours 24")


if __name__ == "__main__":
    main()
