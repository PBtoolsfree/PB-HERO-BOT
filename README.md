# 🚀 PB Hero Bot - Automated Telegram Affiliate Deal Forwarder

**PB Hero Bot** is an enterprise-grade, automated deal forwarding and link converter system designed to bridge targeted Telegram channels directly with your own Telegram channels and Discord servers. It features an elegant glassmorphic **FastAPI Control Dashboard** that allows headless SMS/2FA verification, real-time configuration updates, live server log stream, and daemon lifecycle management.

---

## 🌟 Key Features

- 🔗 **Smart Affiliate Link Converter**: Detects and extracts merchant/product URLs (Amazon, Flipkart, Ajio, etc.), follows shortened redirects (e.g. `amzn.to`, `fktr.cc`), and dynamically transforms them into active affiliate formats.
- 💼 **Multi-Platform Integration**:
  - **EarnKaro API** (via `ekaro-api.affiliaters.in` wrapper) with JWT token cleanup.
  - **Cuelinks API v2** integration.
  - **Direct Amazon Associates Tag** replacement.
- 🖥️ **Interactive Web Console**: Built with high-end glassmorphic UI templates and security cookies to securely configure, start, stop, and monitor the bot state.
- 📲 **Programmatic SMS Auth Wizard**: A headless Telethon integration allowing you to trigger and enter verification SMS codes and 2-Factor Authentication (2FA) directly from the web browser.
- ⚡ **Background Daemon Resilience**: Automatically runs as a persistent system background daemon (`systemd`), with automatic restart triggers.
- 🛡️ **Automated Port & Firewall Mapping**: One-click configuration opens standard network communication channels persistently.

---

## 🚀 One-Click Cloud VPS Installer (Ubuntu 20.04/22.04 LTS)

Deploying PB Hero Bot to your cloud virtual machine (e.g., Oracle Cloud Infrastructure (OCI) Always Free VPS, AWS, DigitalOcean) is completely automated. 

Simply connect to your server terminal via SSH and run **either** of the following single-line commands:

### Method A (Using Curl)
```bash
curl -sSO https://raw.githubusercontent.com/PBtoolsfree/PB-HERO-BOT/main/install.sh && sudo bash install.sh
```

### Method B (Using Wget)
```bash
wget -O install.sh https://raw.githubusercontent.com/PBtoolsfree/PB-HERO-BOT/main/install.sh && sudo bash install.sh
```

### What does the Installer do?
1. Checks for `sudo/root` authority and system updates.
2. Installs core dependencies (`Python3`, `pip`, `venv`, `git`, `iptables`, `netfilter-persistent`).
3. Clones the codebase files from GitHub into `/opt/telegram-affiliate-forwarder`.
4. Creates a Python virtual environment (`.venv`) and installs the dependencies.
5. Setup environmental variables (`.env`) and generates a **secure access password** for the Web Dashboard.
6. Automatically creates and launches a system daemon service (`pbherobot.service`) to keep it running 24/7.
7. Installs persistent firewall rules opening TCP **Port 8000** for dashboard access.
8. Displays your Web Dashboard login URL and your generated administrator password.

---

## 🌐 Web Dashboard Access & OCI Setup

Once the installer finishes, it will provide your dashboard URL:
```
http://<YOUR_VPS_PUBLIC_IP>:8000/
```
Enter your generated secure password to manage and run the bot.

> [!IMPORTANT]  
> **Oracle Cloud (OCI) Ingress Rule:**  
> If you are using Oracle Cloud (OCI) Always Free VPS, you **MUST** add an **Ingress Rule** inside your Virtual Cloud Network (VCN) Security Lists:
> - **Source CIDR:** `0.0.0.0/0`
> - **IP Protocol:** `TCP`
> - **Destination Port Range:** `8000`
> *(If this is not done, your browser will not be able to connect to the dashboard).*

---

## 🛠️ Manual Installation & Development

If you prefer to configure the bot manually or run it locally in development mode:

### Linux / macOS
```bash
# 1. Clone the repository
git clone https://github.com/PBtoolsfree/PB-HERO-BOT.git
cd PB-HERO-BOT

# 2. Setup Virtual Environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install packages
pip install -r requirements.txt

# 4. Copy and fill environment config
cp .env.example .env

# 5. Run the web dashboard
python web_dashboard.py
```

### Windows (Command Prompt)
```cmd
:: 1. Clone repository
git clone https://github.com/PBtoolsfree/PB-HERO-BOT.git
cd PB-HERO-BOT

:: 2. Launch using Windows Startup Wizard
start.bat
```

---

## ⚡ Automated Maintenance & System Diagnostics

PB Hero Bot features a premium, comprehensive CLI maintenance utility (`update_and_check.py`) to automatically synchronize the bot's codebase, update system dependencies, analyze logs, audit environment settings, monitor resources, and gracefully reload the daemon service.

### 🛡️ System Diagnostic Pipeline
1. **GitHub Synchronization:** Auto-fetches and pulls the latest updates from the remote repository's `main` branch.
2. **Dependency Audit:** Dynamically identifies the active virtual environment (`.venv`) and installs/upgrades packages listed in `requirements.txt`.
3. **Environmental Auditing:** Scans `.env` to verify the presence and syntax integrity of vital credentials (e.g. API keys, channel IDs, tokens).
4. **Hardware Capacity Metrics:** Displays active server performance data including **Disk Usage** and **RAM (Memory) Capacity** (with custom threshold alerts).
5. **Logs & Port Diagnostic:** Scans `deal_forwarder.log` for any runtime errors or connection failures, and verifies if the FastAPI Server is listening on Port 8000.
6. **System Daemon Hot-Reload:** In Linux production environments, it automatically reloads systemd manager configurations and runs `sudo systemctl restart pbherobot.service` to apply changes instantly while verifying the service becomes fully `active`.

### 🚀 Running the Diagnostic Update Tool

Connect to your server terminal via SSH and run:
```bash
python3 update_and_check.py
```

---

## ⚙️ Environment Configuration (`.env`)

The system configuration is read from `.env`. The key parameters can be set directly via the Web Dashboard settings tab or manually:

| Key | Description | Example |
| :--- | :--- | :--- |
| `TELEGRAM_API_ID` | Telegram API ID from my.telegram.org | `1234567` |
| `TELEGRAM_API_HASH` | Telegram API Hash from my.telegram.org | `abcdef0123456789...` |
| `TELEGRAM_BOT_TOKEN` | Bot token to broadcast messages | `123456:ABC-Def...` |
| `MY_TELEGRAM_CHANNEL` | Channel ID or Username where deals are sent | `-1001234567890` or `@MyDeals` |
| `TARGET_CHANNELS` | Target sources (comma separated) | `@targetchannel1, @targetchannel2` |
| `DISCORD_MODE` | Discord integration mode (`webhook` or `bot`) | `webhook` |
| `DISCORD_WEBHOOK_URL` | Discord webhook address | `https://discord.com/api/webhooks/...` |
| `DISCORD_BOT_TOKEN` | Discord Bot Token (if mode is `bot`) | `MT...` |
| `DISCORD_CHANNEL_IDS` | Target Discord channel IDs (comma separated) | `112233445566` |
| `EARNKARO_PARTNER_ID` | Your EarnKaro Partner ID or API Key | `partner_id_or_jwt_token` |
| `AFFILIATE_PLATFORM` | Affiliate network (`earnkaro` or `cuelinks`) | `earnkaro` |
| `CUELINKS_API_KEY` | Cuelinks API Key token | `cuelinks_token` |
| `AMAZON_ASSOCIATE_TAG` | Your Amazon Associates Tag for direct rewrite | `myassociatetag-21` |
| `DASHBOARD_PASSWORD` | Access security password for the web console | `SecurePass123` |

---

## 📊 File Structure
```
PB-HERO-BOT/
├── deal_forwarder.py       # Core affiliate forwarding & link converter service
├── web_dashboard.py        # FastAPI control server and headless programmatic auth backend
├── update_and_check.py     # Premium auto-updater and system diagnostics health check tool
├── install.sh              # One-click Ubuntu cloud deployment script
├── start.bat               # Windows environment setup and startup wizard script
├── requirements.txt        # System requirements
├── .env.example            # Sample configuration template
├── templates/
│   ├── dashboard.html      # High-end glassmorphic control center template
│   └── login.html          # Dynamic dashboard portal login interface template
└── deal_forwarder.log      # Runtime execution logger database file
```

---

## ⚖️ License
This project is open-source and free to use. Built with ❤️ by expert Python developers.
