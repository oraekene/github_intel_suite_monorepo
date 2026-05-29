#!/usr/bin/env bash
# ============================================================
#  GitHub Intelligence Suite — TUI Launcher (Linux / macOS)
#  Usage:
#    ./launcher.sh              # interactive menu
#    ./launcher.sh extract      # full extraction
#    ./launcher.sh view stats   # quick view
#    ./launcher.sh pia          # run PIA pipeline
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment if present
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "  [WARN] No .venv found. Using system Python. Run setup.sh first."
fi

python3 launcher.py "$@"
