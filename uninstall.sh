#!/bin/bash
# =========================================================================
# PB HERO BOT - TOTAL UNINSTALLER & CLEANUP SCRIPT
# =========================================================================

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${RED}=========================================================================${NC}"
echo -e "${YELLOW}        ⚠️ PB HERO BOT - TOTAL UNINSTALL & CLEANUP SCRIPT ⚠️         ${NC}"
echo -e "${RED}=========================================================================${NC}"
echo -e "This script will completely remove the bot, its services, and downloaded browsers."
echo -e "WARNING: This will delete all bot data, configurations, and session files permanently."
echo -e "Press Ctrl+C within 5 seconds to cancel..."
sleep 5

echo -e "\n${CYAN}[1/5] Stopping and disabling systemd service...${NC}"
sudo systemctl stop pbherobot.service 2>/dev/null
sudo systemctl disable pbherobot.service 2>/dev/null
sudo rm -f /etc/systemd/system/pbherobot.service
sudo systemctl daemon-reload



echo -e "\n${CYAN}[3/5] Deleting bot installation directory...${NC}"
sudo rm -rf /opt/telegram-affiliate-forwarder

echo -e "\n${CYAN}[4/5] Purging installed Python packages & graphical dependencies...${NC}"
# Purge the specific python tools and dependencies we installed
sudo apt-get purge -y python3-pip python3-venv python3-dev


echo -e "\n${CYAN}[5/5] Cleaning up system packages...${NC}"
# Run an aggressive autoremove to clean up orphaned dependencies 
sudo apt-get autoremove --purge -y
sudo apt-get clean

echo -e "\n${GREEN}=========================================================================${NC}"
echo -e "${GREEN}✅ AGGRESSIVE UNINSTALLATION COMPLETE!${NC}"
echo -e "The PB Hero Bot, systemd service, and virtual environments"
echo -e "have been completely removed. Python PIP and VENV"
echo -e "have been aggressively purged from this VPS."
echo -e "Your VPS is now reverted as close to a fresh install as safely possible."
echo -e "${GREEN}=========================================================================${NC}"
