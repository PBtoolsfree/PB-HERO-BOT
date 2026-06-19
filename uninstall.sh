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

echo -e "\n${CYAN}[2/5] Removing Playwright Chromium browsers and caches...${NC}"
# Remove from root cache where sudo installs it
sudo rm -rf /root/.cache/ms-playwright
# Remove from ubuntu user
sudo rm -rf /home/ubuntu/.cache/ms-playwright
# Remove from current user just in case
rm -rf ~/.cache/ms-playwright

echo -e "\n${CYAN}[3/5] Deleting bot installation directory...${NC}"
sudo rm -rf /opt/telegram-affiliate-forwarder

echo -e "\n${CYAN}[4/5] Purging installed Python packages & graphical dependencies...${NC}"
# Purge the specific python tools and dependencies we installed
sudo apt-get purge -y python3-pip python3-venv python3-dev
# Purge common Playwright / Chromium graphical dependencies that were installed
sudo apt-get purge -y libnss3 libxss1 libasound2 libatk-bridge2.0-0 libgtk-3-0 libgbm1 libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 libxi6 libxtst6 libxrandr2 xdg-utils xvfb xserver-common gconf-service libasound2t64 libatk1.0-0 libcairo2 libcups2 libdbus-1-3 libexpat1 libfontconfig1 libgcc1 libgconf-2-4 libgdk-pixbuf2.0-0 libglib2.0-0 libnspr4 libpango-1.0-0 libpangocairo-1.0-0 libstdc++6 libx11-6 libxcb1 libxext6 libxfixes3 libxrender1

echo -e "\n${CYAN}[5/5] Cleaning up system packages...${NC}"
# Run an aggressive autoremove to clean up orphaned dependencies 
sudo apt-get autoremove --purge -y
sudo apt-get clean

echo -e "\n${GREEN}=========================================================================${NC}"
echo -e "${GREEN}✅ AGGRESSIVE UNINSTALLATION COMPLETE!${NC}"
echo -e "The PB Hero Bot, systemd service, virtual environments, and Playwright browsers"
echo -e "have been completely removed. Python PIP, VENV, and all the graphical Chromium"
echo -e "dependencies have been aggressively purged from this VPS."
echo -e "Your VPS is now reverted as close to a fresh install as safely possible."
echo -e "${GREEN}=========================================================================${NC}"
