#!/bin/bash
# =========================================================================
# PB HERO BOT - BASH TERMINAL MANUAL UPDATER & DIAGNOSTIC LAUNCHER
# =========================================================================

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

clear
echo -e "${CYAN}=========================================================================${NC}"
echo -e "${GREEN}        🚀 PB HERO BOT - TERMINAL UPDATE & DIAGNOSTIC LAUNCHER 🚀         ${NC}"
echo -e "${CYAN}=========================================================================${NC}"
echo -e "Starting manual updates and server status audit..."
echo -e "${GREEN}🔒 [SAFE] Your configurations (.env) and active sessions are 100% safe!${NC}"
echo

# 1. Locate python executable
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PY_CMD="$SCRIPT_DIR/.venv/bin/python"
elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PY_CMD="$SCRIPT_DIR/venv/bin/python"
else
    PY_CMD="python3"
fi

# 2. Run the update script
$PY_CMD "$SCRIPT_DIR/update_and_check.py"

echo
echo -e "${GREEN}[INFO] Maintenance execution cycle ended.${NC}"
