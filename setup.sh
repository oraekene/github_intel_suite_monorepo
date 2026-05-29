#!/usr/bin/env bash
# ============================================================
#  GitHub Intelligence Suite — Setup (Linux / macOS)
#  Run once: bash setup.sh
# ============================================================
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   GitHub Intelligence Suite — Setup         ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

# 1. Check Python
if ! command -v python3 &>/dev/null; then
    echo "  [ERROR] python3 not found."
    echo "          Install it with:"
    echo "            Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "            macOS:         brew install python"
    exit 1
fi
PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
echo "  ✓ Python $PY_VER found."
echo ""

# 2. Virtual environment
if [ -d ".venv" ]; then
    echo "  ✓ Virtual environment already exists."
else
    echo "  Creating virtual environment..."
    python3 -m venv .venv
    echo "  ✓ .venv created."
fi
echo ""

# 3. Activate
source .venv/bin/activate
echo "  ✓ Virtual environment activated."
echo ""

# 4. Upgrade pip
pip install --upgrade pip --quiet

# 5. Extractor deps
echo "  Installing GitHub Extractor dependencies..."
pip install PyGithub requests scrapling
echo ""

# 6. PIA deps
if [ -f "pia/requirements.txt" ]; then
    echo "  Installing PIA dependencies (may take a few minutes)..."
    pip install -r pia/requirements.txt
    echo ""
else
    echo "  [WARN] pia/requirements.txt not found."
    echo "         PIA is already in the pia/ folder"
    echo ""
fi

# 7. Scrapling backend
echo "  Optional: installing Scrapling browser backend..."
python3 -m scrapling install 2>/dev/null || true
echo ""

echo "  ══════════════════════════════════════════════"
echo "   Setup complete!"
echo "  ══════════════════════════════════════════════"
echo ""
echo "   Next steps:"
echo "   1. Edit pia/config.yaml with your API keys"
echo "   2. ./launcher.sh          (terminal menu)"
echo "      python3 gui_app.py     (graphical interface)"
echo ""
