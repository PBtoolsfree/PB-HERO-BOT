#!/bin/bash
# =========================================================================
# PB HERO BOT - AUTOMATED OCI VPS ONE-CLICK INSTALLER
# =========================================================================
# Target OS: Ubuntu 20.04 LTS / 22.04 LTS (Optimized for OCI Always Free)
# =========================================================================

# Formatting constants
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

clear
echo -e "${CYAN}=========================================================================${NC}"
echo -e "${GREEN}             🚀 PB HERO BOT - AUTOMATED ONE-CLICK INSTALLER 🚀            ${NC}"
echo -e "${CYAN}=========================================================================${NC}"
echo -e "Starting cloud deployment configuration..."
echo

# 1. Check root permissions
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERROR] Please run this installer as root (use sudo)!${NC}"
  exit 1
fi

# 2. Update package list & install core system dependencies
echo -e "${YELLOW}[1/6] Installing core system packages (Python, Git, iptables)...${NC}"
apt-get update -y
# Auto-approve iptables-persistent prompts during install
echo "iptables-persistent iptables-persistent/whitesole select true" | debconf-set-selections
echo "iptables-persistent iptables-persistent/autosave_v4 select true" | debconf-set-selections
echo "iptables-persistent iptables-persistent/autosave_v6 select true" | debconf-set-selections

apt-get install -y python3 python3-pip python3-venv git iptables iptables-persistent netfilter-persistent
if [ $? -ne 0 ]; then
  echo -e "${RED}[ERROR] Failed to install core system dependencies! Check your internet or apt sources.${NC}"
  exit 1
fi
echo -e "${GREEN}[SUCCESS] Core system dependencies successfully installed.${NC}"
echo

# 3. Setup workspace directory
echo -e "${YELLOW}[2/6] Setting up project workspace...${NC}"
WORKSPACE_DIR="/opt/telegram-affiliate-forwarder"
if [ -d "$WORKSPACE_DIR" ]; then
  echo -e "Project folder already exists at $WORKSPACE_DIR. Syncing codebase..."
else
  mkdir -p "$WORKSPACE_DIR"
  echo -e "Created deployment workspace folder at: $WORKSPACE_DIR"
fi

# Copy current files if we are executing within the repository, otherwise clone
if [ -f "web_dashboard.py" ]; then
  cp -r ./* "$WORKSPACE_DIR/"
  cd "$WORKSPACE_DIR"
else
  echo -e "Cloning repository from GitHub remote..."
  git clone https://github.com/PBtoolsfree/PB-HERO-BOT.git "$WORKSPACE_DIR"
  cd "$WORKSPACE_DIR"
fi

# 4. Setup Python Virtual Environment and packages
echo -e "${YELLOW}[3/6] Configuring virtual environment and installing pip packages...${NC}"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
if [ $? -ne 0 ]; then
  echo -e "${RED}[ERROR] Python package installation failed!${NC}"
  exit 1
fi
echo -e "${GREEN}[SUCCESS] Virtual environment configured and verified.${NC}"
echo

# 5. Handle environment configuration and secure password generation
echo -e "${YELLOW}[4/6] Initializing secure environment config (.env)...${NC}"
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp .env.example .env
  else
    touch .env
  fi
fi

# Check or generate security password
DASH_PASS=$(grep -E "^DASHBOARD_PASSWORD=" .env | cut -d'=' -f2)
if [ -z "$DASH_PASS" ]; then
  DASH_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(12))")
  if grep -q "^DASHBOARD_PASSWORD=" .env; then
    sed -i "s/^DASHBOARD_PASSWORD=.*/DASHBOARD_PASSWORD=$DASH_PASS/" .env
  else
    echo -e "\n# [DASHBOARD SECURITY]\nDASHBOARD_PASSWORD=$DASH_PASS" >> .env
  fi
  echo -e "Security key: Generated secure dashboard access password."
else
  echo -e "Security key: Found existing dashboard access password in config."
fi

# 6. Configure Systemd Daemon Service
echo -e "${YELLOW}[5/6] Spawning background systemd service daemon...${NC}"
SERVICE_FILE="/etc/systemd/system/pbherobot.service"

cat <<EOT > $SERVICE_FILE
[Unit]
Description=PB Hero Bot - FastAPI Dashboard & Telegram Affiliate Forwarder
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$WORKSPACE_DIR
ExecStart=$WORKSPACE_DIR/.venv/bin/python $WORKSPACE_DIR/web_dashboard.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOT

systemctl daemon-reload
systemctl enable pbherobot.service
systemctl restart pbherobot.service

if [ $? -ne 0 ]; then
  echo -e "${RED}[ERROR] Failed to start systemd service!${NC}"
  exit 1
fi
echo -e "${GREEN}[SUCCESS] Daemon service successfully enabled and started!${NC}"
echo

# 7. Automate Linux VPS Firewalls
echo -e "${YELLOW}[6/6] Opening network ports in system firewall (Port 8000)...${NC}"
# Allow TCP traffic on 8000 inside iptables
iptables -I INPUT 6 -p tcp --dport 8000 -j ACCEPT
# Save rules permanently across reboots
netfilter-persistent save
echo -e "${GREEN}[SUCCESS] Network ports mapped and saved to persistent iptables rules.${NC}"
echo

# Get public IP address
PUBLIC_IP=$(curl -s https://api.ipify.org || echo "YOUR_VPS_IP")

echo -e "${CYAN}=========================================================================${NC}"
echo -e "${GREEN}             🎉 PB HERO BOT - DEPLOYMENT COMPLETED SUCCESS! 🎉            ${NC}"
echo -e "${CYAN}=========================================================================${NC}"
echo -e "Your daemon services are now actively running in the cloud background."
echo
echo -e "🌐 ${YELLOW}Dashboard Access URL:${NC} http://$PUBLIC_IP:8000/"
echo -e "🔐 ${YELLOW}Dashboard Password:${NC}   $DASH_PASS"
echo
echo -e "💡 ${CYAN}OCI Reminder:${NC} Please ensure you have added an INGRESS rule for TCP port"
echo -e "   ${CYAN}8000${NC} in your Oracle Cloud Subnet Security List / NSG configuration!"
echo -e "${CYAN}=========================================================================${NC}"
