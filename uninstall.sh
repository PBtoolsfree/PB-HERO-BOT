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

echo -e "\n${CYAN}[4/5] Cleaning up system packages...${NC}"
# We run autoremove to clean up any orphaned dependencies safely
sudo apt-get autoremove -y
sudo apt-get clean

echo -e "\n${GREEN}=========================================================================${NC}"
echo -e "${GREEN}✅ UNINSTALLATION COMPLETE!${NC}"
echo -e "The PB Hero Bot, systemd service, virtual environments, and Playwright browsers"
echo -e "have been completely removed from this VPS to free up CPU, RAM, and Disk space."
echo -e "System Python has been kept intact to prevent breaking your Ubuntu OS."
echo -e "${GREEN}=========================================================================${NC}"
