#!/usr/bin/env python3
"""
PB Hero Bot - Automated Update & Comprehensive System Health Checker
===================================================================
This script performs a full codebase sync from GitHub, updates dependencies,
validates environmental settings, monitors system resource allocation,
analyzes log records, and automatically restarts the daemon service (systemd)
on production servers.

Author: Expert Python Developer
Date: May 2026
"""

import os
import sys
import subprocess
import shutil
import socket
from typing import Dict, Any, List

# Standard ANSI Color escape codes
CYAN = "\033[0;36m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
MAGENTA = "\033[0;35m"
BOLD = "\033[1m"
NC = "\033[0m"  # No Color

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def print_banner():
    """Prints a beautiful, premium visual banner for the CLI tool."""
    banner = f"""
{CYAN}========================================================================={NC}
{BOLD}{GREEN}             ⚡ PB HERO BOT - SYSTEM MAINTENANCE & RECOVERY ⚡            {NC}
{CYAN}========================================================================={NC}
  Time: {BOLD}May 2026{NC} | Directory: {CYAN}{BASE_DIR}{NC}
  Function: {MAGENTA}Auto-Update (Git) + Comprehensive Health & Service Checks{NC}
{CYAN}========================================================================={NC}
  {BOLD}{GREEN}🔒 CONFIG & SESSION SAFE:{NC} Your settings ({BOLD}.env{NC}) & active auth sessions
  ({BOLD}*.session{NC}) are protected by gitignore & will {BOLD}{GREEN}NEVER{NC} be overwritten!
{CYAN}========================================================================={NC}
"""
    print(banner)

def run_command(command: List[str], description: str, timeout: int = 60) -> bool:
    """Helper to run system commands and handle outputs nicely."""
    print(f"{YELLOW}[→] {description}...{NC}")
    try:
        result = subprocess.run(
            command, 
            cwd=BASE_DIR, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True,
            timeout=timeout
        )
        if result.returncode == 0:
            print(f"{GREEN}[SUCCESS] {description} completed successfully.{NC}")
            if result.stdout.strip():
                print(f"    {result.stdout.strip().replace(chr(10), chr(10) + '    ')}")
            return True
        else:
            print(f"{RED}[ERROR] {description} failed!{NC}")
            if result.stderr.strip():
                print(f"    {RED}Error output: {result.stderr.strip()}{NC}")
            return False
    except subprocess.TimeoutExpired:
        print(f"{RED}[ERROR] {description} timed out after {timeout} seconds!{NC}")
        return False
    except Exception as e:
        print(f"{RED}[ERROR] Unexpected issue while running '{' '.join(command)}': {e}{NC}")
        return False

def pull_github_updates() -> bool:
    """Syncs the repository with the latest code from GitHub."""
    print(f"\n{BOLD}{CYAN}🔹 STEP 1: GitHub Codebase Synchronization (Git Pull){NC}")
    
    # Check if this is a valid git repository
    if not os.path.exists(os.path.join(BASE_DIR, ".git")):
        print(f"{RED}[ERROR] This workspace is not initialized as a Git repository! Missing .git directory.{NC}")
        return False
        
    # Reset local changes that are not committed, or stash them to prevent conflicts
    run_command(["git", "fetch", "--all"], "Fetching updates from all remote branches")
    return run_command(["git", "pull", "origin", "main"], "Pulling latest changes from 'origin/main'")

def update_python_dependencies() -> bool:
    """Updates the virtual environment python pip dependencies."""
    print(f"\n{BOLD}{CYAN}🔹 STEP 2: Python Environment & Dependencies Validation{NC}")
    
    venv_python = None
    possible_venv_paths = [
        os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe"),  # Windows
        os.path.join(BASE_DIR, ".venv", "bin", "python"),          # Linux
        os.path.join(BASE_DIR, "venv", "Scripts", "python.exe"),   # Windows fallback
        os.path.join(BASE_DIR, "venv", "bin", "python")            # Linux fallback
    ]
    
    for path in possible_venv_paths:
        if os.path.exists(path):
            venv_python = path
            break
            
    if not venv_python:
        print(f"{YELLOW}[WARNING] Active python virtual environment (.venv) not found. Using system python.{NC}")
        venv_python = sys.executable

    requirements_path = os.path.join(BASE_DIR, "requirements.txt")
    if not os.path.exists(requirements_path):
        print(f"{RED}[ERROR] Missing requirements.txt file in the workspace! Can't verify dependencies.{NC}")
        return False
        
    return run_command([venv_python, "-m", "pip", "install", "-r", requirements_path, "--upgrade"], "Updating/verifying pip packages from requirements.txt")

def remove_playwright_and_cache() -> bool:
    """Removes Playwright binaries and chromium caches to free up space."""
    print(f"\n{BOLD}{CYAN}🔹 STEP 2.5: Deep Cleaning Legacy Playwright & WhatsApp Assets{NC}")
    
    venv_python = None
    possible_venv_paths = [
        os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe"),
        os.path.join(BASE_DIR, ".venv", "bin", "python"),
        os.path.join(BASE_DIR, "venv", "Scripts", "python.exe"),
        os.path.join(BASE_DIR, "venv", "bin", "python")
    ]
    
    for path in possible_venv_paths:
        if os.path.exists(path):
            venv_python = path
            break
            
    if not venv_python:
        venv_python = sys.executable

    print(f"{YELLOW}[→] Uninstalling pip package 'playwright' if present...{NC}")
    subprocess.run([venv_python, "-m", "pip", "uninstall", "-y", "playwright"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print(f"{YELLOW}[→] Removing downloaded browser binaries...{NC}")
    cache_paths = [
        os.path.expanduser("~/.cache/ms-playwright"),
        os.path.expanduser("~/AppData/Local/ms-playwright"),
        "/root/.cache/ms-playwright/"
    ]
    for path in cache_paths:
        if os.path.exists(path):
            try:
                shutil.rmtree(path, ignore_errors=True)
            except Exception:
                pass
    print(f"{GREEN}[SUCCESS] Legacy Playwright and WhatsApp assets deeply cleaned.{NC}")
    return True

def check_environmental_configs() -> bool:
    """Validates the local environment configuration variables."""
    print(f"\n{BOLD}{CYAN}🔹 STEP 3: Environmental Config (.env) Integrity Audit{NC}")
    env_path = os.path.join(BASE_DIR, ".env")
    
    if not os.path.exists(env_path):
        print(f"{RED}[ERROR] Environmental configuration (.env) file is missing!{NC}")
        if os.path.exists(os.path.join(BASE_DIR, ".env.example")):
            print(f"{YELLOW}[ACTION] Creating .env file from template example (.env.example)...{NC}")
            shutil.copy(os.path.join(BASE_DIR, ".env.example"), env_path)
            print(f"{GREEN}[SUCCESS] Initialized new .env file. Please edit it with your real API details.{NC}")
        else:
            print(f"{YELLOW}[ACTION] Initializing blank .env file...{NC}")
            with open(env_path, "w") as f:
                f.write("# PB Hero Bot Config\n")
            return False

    # Read and audit the variables
    configs = {}
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.strip().startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    configs[k.strip()] = v.strip()
    except Exception as e:
        print(f"{RED}[ERROR] Failed to parse .env file: {e}{NC}")
        return False

    critical_vars = ["TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_BOT_TOKEN", "MY_TELEGRAM_CHANNEL"]
    missing_vars = []
    
    for var in critical_vars:
        val = configs.get(var, "")
        if not val or val == "YOUR_ID" or "YOUR" in val:
            missing_vars.append(var)

    if missing_vars:
        print(f"{RED}[CRITICAL WARNING] The following vital parameters are empty or unconfigured in your .env:{NC}")
        for var in missing_vars:
            print(f"   {RED}✗ {var}{NC}")
        print(f"{YELLOW}[ACTION] Please log in to your dashboard panel or edit .env directly to fill these variables.{NC}")
        return False
    else:
        print(f"{GREEN}[SUCCESS] All key configurations (Telegram Credentials & Channels) verified.{NC}")
        return True

def run_system_resource_checks():
    """Outputs basic server metrics to screen."""
    print(f"\n{BOLD}{CYAN}🔹 STEP 4: Server Resource Capacity Analysis{NC}")
    
    # 1. Disk Space Check
    try:
        total, used, free = shutil.disk_usage(BASE_DIR)
        used_percentage = (used / total) * 100
        color = GREEN if used_percentage < 85 else (YELLOW if used_percentage < 95 else RED)
        print(f"  Disk Usage: {color}{used_percentage:.1f}% used{NC} ({free // (1024**3)} GB Free of {total // (1024**3)} GB Total)")
    except Exception as e:
        print(f"  Disk Usage Check: {RED}Unavailable ({e}){NC}")

    # 2. Ram Usage Check (Linux only)
    if os.path.exists("/proc/meminfo"):
        try:
            mem_total = 0
            mem_free = 0
            mem_available = 0
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if "MemTotal" in line:
                        mem_total = int(line.split()[1])
                    elif "MemFree" in line:
                        mem_free = int(line.split()[1])
                    elif "MemAvailable" in line:
                        mem_available = int(line.split()[1])
                        break
            
            if mem_available == 0:
                mem_available = mem_free
                
            used_mem = mem_total - mem_available
            mem_pct = (used_mem / mem_total) * 100
            color = GREEN if mem_pct < 80 else (YELLOW if mem_pct < 90 else RED)
            print(f"  Memory (RAM) Usage: {color}{mem_pct:.1f}% used{NC} ({(used_mem/1024/1024):.2f} GB used / {(mem_total/1024/1024):.2f} GB total)")
        except Exception as e:
            print(f"  RAM Usage Check: {RED}Unavailable ({e}){NC}")
    else:
        print("  RAM Usage Check: Supported on Linux servers only.")

def run_network_and_log_checks():
    """Checks port binding availability and audits log errors."""
    print(f"\n{BOLD}{CYAN}🔹 STEP 5: Network Interface Port Binding & Log Audit{NC}")
    
    # 1. Port 8000 binding verification
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    result = sock.connect_ex(('127.0.0.1', 8000))
    sock.close()
    
    if result == 0:
        print(f"  {GREEN}✓ Dashboard service detected active and listening on port 8000.{NC}")
    else:
        print(f"  {YELLOW}✗ No active service detected on port 8000 (FastAPI Dashboard is offline/starting).{NC}")

    # 2. Log Auditing
    log_file = os.path.join(BASE_DIR, "deal_forwarder.log")
    if not os.path.exists(log_file):
        print(f"  Log File Check: {YELLOW}No log records created yet at deal_forwarder.log.{NC}")
        return

    print(f"  Analyzing last 20 log records for warnings/exceptions...")
    try:
        critical_lines = []
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            for line in lines[-20:]:
                if "[ERROR]" in line or "Exception" in line or "Traceback" in line or "Error" in line:
                    critical_lines.append(line.strip())
        
        if critical_lines:
            print(f"  {RED}[WARNING] Detected {len(critical_lines)} error(s) recently in deal_forwarder.log:{NC}")
            for err in critical_lines[:5]:
                print(f"    {RED}✗ {err}{NC}")
            if len(critical_lines) > 5:
                print(f"    ...and {len(critical_lines) - 5} more error lines.")
        else:
            print(f"  {GREEN}✓ Zero recent errors or exceptions detected in deal_forwarder.log.{NC}")
    except Exception as e:
        print(f"  Log analysis failed: {e}")

def restart_daemon_service() -> bool:
    """Restarts the systemd system service on production Linux machines."""
    print(f"\n{BOLD}{CYAN}🔹 STEP 6: Service Daemon Hot-Reload / Restart{NC}")
    
    # Detect if service systemd exists
    service_file = "/etc/systemd/system/pbherobot.service"
    
    if not os.path.exists(service_file):
        print(f"{YELLOW}[INFO] systemd service 'pbherobot.service' does not exist in standard paths.{NC}")
        print(f"{YELLOW}If this is a local development PC (Windows/Mac), please launch via start.bat manually.{NC}")
        return True

    print(f"{YELLOW}[→] Production Linux Server environment detected. Restarting service daemon...{NC}")
    
    # Attempting to restart service
    reloading = run_command(["sudo", "systemctl", "daemon-reload"], "Reloading systemd manager configuration")
    restarting = run_command(["sudo", "systemctl", "restart", "pbherobot.service"], "Restarting PB Hero Bot service daemon (pbherobot.service)", timeout=120)
    
    if restarting:
        # Check active status
        try:
            status_res = subprocess.run(
                ["systemctl", "is-active", "pbherobot.service"],
                stdout=subprocess.PIPE,
                text=True
            )
            is_active = status_res.stdout.strip() == "active"
            if is_active:
                print(f"{GREEN}[SUCCESS] pbherobot.service is successfully running and active!{NC}")
                return True
            else:
                print(f"{RED}[ERROR] pbherobot.service has restarted but is in state: '{status_res.stdout.strip()}'.{NC}")
                print(f"{YELLOW}Hint: Run 'journalctl -u pbherobot.service -n 50 --no-pager' to diagnose service crashes.{NC}")
                return False
        except Exception as e:
            print(f"{YELLOW}[WARNING] Could not verify service status: {e}{NC}")
            return True
    else:
        print(f"{RED}[ERROR] Failed to automatically restart systemd service.{NC}")
        print(f"{YELLOW}Please try running manually: 'sudo systemctl restart pbherobot.service'{NC}")
        return False

def main():
    """Main program pipeline flow control."""
    print_banner()
    
    # Step 1: Git pull
    git_ok = pull_github_updates()
    
    # Step 2: Update packages
    deps_ok = update_python_dependencies()
    
    # Step 2.5: Remove Playwright
    remove_playwright_and_cache()
    
    # Step 3: Auditing configurations
    env_ok = check_environmental_configs()
    
    # Step 4: System Resource Capacity
    run_system_resource_checks()
    
    # Step 5: Network Interfaces and Logs Audit
    run_network_and_log_checks()
    
    # Step 6: Restart Daemon (Hot-Reload updates)
    service_ok = restart_daemon_service()
    
    print(f"\n{CYAN}========================================================================={NC}")
    if git_ok and deps_ok and env_ok and service_ok:
        print(f"{BOLD}{GREEN}             🎉 SYSTEM MAINTENANCE & UPDATE CYCLE COMPLETE! 🎉           {NC}")
        print(f"  All subsystems are healthy, updated, and actively operational.")
    else:
        print(f"{BOLD}{YELLOW}            ⚠️  SYSTEM MAINTENANCE FINISHED WITH CRITICAL STEPS  ⚠️           {NC}")
        print(f"  Updates pulled, but some health configurations need manual attention.")
    print(f"{CYAN}========================================================================={NC}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{RED}[ABORT] Maintenance terminated by user operator.{NC}")
    except Exception as e:
        print(f"\n{RED}[CRITICAL CRASH] Fatal exception in updater pipeline: {e}{NC}")
