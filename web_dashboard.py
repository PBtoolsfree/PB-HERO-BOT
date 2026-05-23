#!/usr/bin/env python3
"""
PB Hero Bot - Control Dashboard Server
======================================
FastAPI Web Backend to manage, configure, run, and authenticate the 
Telegram Affiliate Deal Forwarding System without any code editing.

Author: Expert Python Developer
Date: May 2026
"""

import os
import re
import secrets
import hashlib
import logging
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

# Import the service class from deal_forwarder.py
from deal_forwarder import DealForwarderService, logger as service_logger
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# Initialize FastAPI App
app = FastAPI(title="PB Hero Bot Control System")

# Configure Dashboard Loggers
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DashboardServer")

# Compute absolute base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Templates Configuration
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Load env file initially
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"), override=True)

# Global Application States
bot_service = None
bot_status = "stopped"  # 'stopped', 'running', 'authenticating', 'error'
phone_code_hashes = {}  # Map phone_number -> phone_code_hash

# =====================================================================
# AUTOMATED BOT AUTO-START ON BOOT / RESTART
# =====================================================================
@app.on_event("startup")
async def startup_event():
    """Tries to auto-start the forwarding service on boot if already authenticated."""
    global bot_service, bot_status
    load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"), override=True)
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    
    if not api_id or not api_hash:
        logger.info("Auto-start: Missing API credentials in .env. Waiting for manual configuration.")
        return
        
    try:
        logger.info("Auto-start: Attempting to automatically start forwarding service...")
        bot_service = DealForwarderService()
        session_path = os.path.join(BASE_DIR, 'deal_forwarder_session')
        bot_service.client = TelegramClient(session_path, int(api_id), api_hash)
        
        await bot_service.client.connect()
        
        if await bot_service.client.is_user_authorized():
            success = await bot_service.start()
            if success:
                bot_status = "running"
                logger.info("Auto-start: Forwarding service successfully auto-started on boot!")
            else:
                bot_status = "error"
                logger.error("Auto-start: Client authorized but listener streams failed to launch.")
        else:
            bot_status = "stopped"
            logger.info("Auto-start: Client not authorized yet. SMS authentication is required via dashboard.")
            # Gracefully disconnect
            await bot_service.client.disconnect()
    except Exception as e:
        bot_status = "error"
        logger.error(f"Auto-start failure: {e}", exc_info=True)

# =====================================================================
# DYNAMIC PASSWORD SETUP & COOKIE AUTH
# =====================================================================
def ensure_dashboard_password() -> str:
    """Ensures a dashboard password exists in the .env file. If not, generates one."""
    env_path = os.path.join(BASE_DIR, ".env")
    password = os.getenv("DASHBOARD_PASSWORD")
    if not password:
        password = secrets.token_urlsafe(12)  # Generates a secure random password
        try:
            content = ""
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    content = f.read()
            
            if "DASHBOARD_PASSWORD=" in content:
                content = re.sub(r"DASHBOARD_PASSWORD=.*", f"DASHBOARD_PASSWORD={password}", content)
            else:
                if content and not content.endswith("\n"):
                    content += "\n"
                content += f"\n# [DASHBOARD SECURITY]\nDASHBOARD_PASSWORD={password}\n"
                
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Generated secure new dashboard password and saved to .env: {password}")
        except Exception as e:
            logger.error(f"Failed to save generated dashboard password to .env: {e}")
    return password

# Initialize or load password
DASHBOARD_PASSWORD = ensure_dashboard_password()

def is_authenticated(request: Request) -> bool:
    """Verifies if the client is authenticated via the cookie session token."""
    if not DASHBOARD_PASSWORD:
        return True
    session_cookie = request.cookies.get("pb_hero_session")
    expected_token = hashlib.sha256(DASHBOARD_PASSWORD.encode("utf-8")).hexdigest()
    return session_cookie == expected_token

# =====================================================================
# CORE UTILITY METHODS
# =====================================================================
def save_env_configs(configs: Dict[str, str]):
    """Saves updated parameters directly to the local .env file."""
    try:
        env_path = os.path.join(BASE_DIR, ".env")
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("# ===================================================\n")
            f.write("# PB HERO BOT - AUTOMATED AFFILIATE FORWARDER CONFIG\n")
            f.write("# ===================================================\n\n")
            
            f.write("# [TELEGRAM API SETTINGS]\n")
            f.write(f"TELEGRAM_API_ID={configs.get('TELEGRAM_API_ID', '').strip()}\n")
            f.write(f"TELEGRAM_API_HASH={configs.get('TELEGRAM_API_HASH', '').strip()}\n\n")
            
            f.write("# [TELEGRAM BOT & DESTINATION SETTINGS]\n")
            f.write(f"TELEGRAM_BOT_TOKEN={configs.get('TELEGRAM_BOT_TOKEN', '').strip()}\n")
            f.write(f"MY_TELEGRAM_CHANNEL={configs.get('MY_TELEGRAM_CHANNEL', '').strip()}\n\n")
            
            f.write("# [DEAL SOURCES - TARGET CHANNELS (Comma separated)]\n")
            f.write(f"TARGET_CHANNELS={configs.get('TARGET_CHANNELS', '').strip()}\n")
            f.write(f"WHITELIST_CHANNELS={configs.get('WHITELIST_CHANNELS', '').strip()}\n\n")
            
            f.write("# [DISCORD INTEGRATION]\n")
            f.write(f"DISCORD_MODE={configs.get('DISCORD_MODE', 'webhook').strip()}\n")
            f.write(f"DISCORD_WEBHOOK_URL={configs.get('DISCORD_WEBHOOK_URL', '').strip()}\n")
            f.write(f"DISCORD_BOT_TOKEN={configs.get('DISCORD_BOT_TOKEN', '').strip()}\n")
            f.write(f"DISCORD_CHANNEL_IDS={configs.get('DISCORD_CHANNEL_IDS', '').strip()}\n\n")
            
            f.write("# [MERCHANT AFFILIATE EARNKARO PARTNER ID]\n")
            f.write(f"EARNKARO_PARTNER_ID={configs.get('EARNKARO_PARTNER_ID', '').strip()}\n\n")
            
            f.write("# [CUELINKS API SETTINGS]\n")
            f.write(f"AFFILIATE_PLATFORM={configs.get('AFFILIATE_PLATFORM', 'earnkaro').strip()}\n")
            f.write(f"CUELINKS_API_KEY={configs.get('CUELINKS_API_KEY', '').strip()}\n\n")
            
            f.write("# [DIRECT AMAZON ASSOCIATES SETTINGS]\n")
            f.write(f"AMAZON_ASSOCIATE_TAG={configs.get('AMAZON_ASSOCIATE_TAG', '').strip()}\n\n")

            f.write("# [SMART QUEUE POSTING DELAY (SECONDS)]\n")
            f.write(f"DELAY_INTERVAL={configs.get('DELAY_INTERVAL', '900').strip()}\n\n")

            f.write("# [DASHBOARD SECURITY]\n")
            f.write(f"DASHBOARD_PASSWORD={configs.get('DASHBOARD_PASSWORD', DASHBOARD_PASSWORD).strip()}\n")
            
        logger.info("Successfully updated .env configuration file.")
    except Exception as e:
        logger.error(f"Failed to write to .env file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save settings to env file.")

def read_last_log_lines(filepath: str = None, line_count: int = 80):
    """Safely reads the last N lines of logs to feed to the browser terminal."""
    if filepath is None:
        filepath = os.path.join(BASE_DIR, "deal_forwarder.log")
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            return [l.strip() for l in lines[-line_count:]]
    except Exception as e:
        return [f"[ERROR] Failed to fetch server log lines: {e}"]

# =====================================================================
# WEB ENDPOINTS & PAGES
# =====================================================================
@app.get("/", response_class=HTMLResponse)
async def get_dashboard_homepage(request: Request):
    """Renders the HTML glassmorphic dashboard homepage or login screen."""
    if not is_authenticated(request):
        return templates.TemplateResponse(request=request, name="login.html")
    return templates.TemplateResponse(request=request, name="dashboard.html")

# =====================================================================
# LOGIN / LOGOUT SECURITY APIs
# =====================================================================
class LoginRequest(BaseModel):
    password: str

@app.post("/api/login")
async def api_login(payload: LoginRequest, response: Response):
    """Authenticates admin password and returns secure session cookie."""
    if payload.password == DASHBOARD_PASSWORD:
        session_token = hashlib.sha256(DASHBOARD_PASSWORD.encode("utf-8")).hexdigest()
        response.set_cookie(
            key="pb_hero_session",
            value=session_token,
            max_age=30 * 24 * 60 * 60,  # 30 Days active session
            httponly=True,
            samesite="lax"
        )
        return {"status": "success", "message": "Successfully authenticated!"}
    raise HTTPException(status_code=401, detail="Incorrect password. Access denied.")

@app.post("/api/logout")
async def api_logout(response: Response):
    """Clears authentication session cookie."""
    response.delete_cookie("pb_hero_session")
    return {"status": "success", "message": "Logged out successfully."}

# =====================================================================
# SETTINGS CONFIGURATION APIs
# =====================================================================
@app.get("/api/config")
async def get_current_configuration(request: Request):
    """Reads and returns the active environment variables."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized access.")
    load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"), override=True)
    return {
        "TELEGRAM_API_ID": os.getenv("TELEGRAM_API_ID", ""),
        "TELEGRAM_API_HASH": os.getenv("TELEGRAM_API_HASH", ""),
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "MY_TELEGRAM_CHANNEL": os.getenv("MY_TELEGRAM_CHANNEL", ""),
        "TARGET_CHANNELS": os.getenv("TARGET_CHANNELS", ""),
        "WHITELIST_CHANNELS": os.getenv("WHITELIST_CHANNELS", ""),
        "DISCORD_MODE": os.getenv("DISCORD_MODE", "webhook"),
        "DISCORD_WEBHOOK_URL": os.getenv("DISCORD_WEBHOOK_URL", ""),
        "DISCORD_BOT_TOKEN": os.getenv("DISCORD_BOT_TOKEN", ""),
        "DISCORD_CHANNEL_IDS": os.getenv("DISCORD_CHANNEL_IDS", ""),
        "EARNKARO_PARTNER_ID": os.getenv("EARNKARO_PARTNER_ID", "YOUR_ID"),
        "AFFILIATE_PLATFORM": os.getenv("AFFILIATE_PLATFORM", "earnkaro"),
        "CUELINKS_API_KEY": os.getenv("CUELINKS_API_KEY", ""),
        "AMAZON_ASSOCIATE_TAG": os.getenv("AMAZON_ASSOCIATE_TAG", ""),
        "DELAY_INTERVAL": os.getenv("DELAY_INTERVAL", "900"),
        "DASHBOARD_PASSWORD": os.getenv("DASHBOARD_PASSWORD", DASHBOARD_PASSWORD)
    }

@app.post("/api/config")
async def post_new_configuration(payload: Dict[str, str], request: Request):
    """Receives edited inputs from UI and saves them to local env."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized access.")
    
    global DASHBOARD_PASSWORD
    if "DASHBOARD_PASSWORD" in payload and payload["DASHBOARD_PASSWORD"].strip():
        DASHBOARD_PASSWORD = payload["DASHBOARD_PASSWORD"].strip()

    save_env_configs(payload)
    # If the bot is active, reload config dynamically
    global bot_service
    if bot_service and bot_service.is_running:
        bot_service.load_config()
        logger.info("Bot configuration hot-reloaded successfully.")
    return {"status": "success", "message": "Configurations saved successfully!"}

# =====================================================================
# BOT SYSTEM LOGS API
# =====================================================================
@app.get("/api/logs")
async def get_system_logs(request: Request):
    """Serves the latest log records from the local file storage."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized access.")
    return read_last_log_lines()

# =====================================================================
# BOT STATE & STATISTICS APIs
# =====================================================================
@app.get("/api/bot/status")
async def get_bot_status(request: Request):
    """Returns bot state (stopped/running/authenticating/error) and metrics."""
    # Note: Status check is allowed unauthenticated to keep client status check alive
    global bot_service, bot_status
    
    stats = {
        "processed": 0,
        "telegram_success": 0,
        "discord_success": 0,
        "failures": 0
    }
    
    if bot_service:
        stats = {
            "processed": bot_service.stats["processed"],
            "telegram_success": bot_service.stats["telegram_success"],
            "discord_success": bot_service.stats["discord_success"],
            "failures": bot_service.stats["failures"]
        }
        if not bot_service.is_running and bot_status == "running":
            bot_status = "stopped"
            
    return {"status": bot_status, "stats": stats}

@app.post("/api/bot/start")
async def start_bot_service(request: Request):
    """Starts the deal forwarding listener service."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized access.")
    global bot_service, bot_status
    
    if bot_service and bot_service.is_running:
        return {"status": "running", "message": "Bot is already running."}
        
    load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"), override=True)
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    
    if not api_id or not api_hash:
        raise HTTPException(
            status_code=400, 
            detail="Missing TELEGRAM_API_ID or TELEGRAM_API_HASH. Complete API settings first."
        )

    try:
        bot_service = DealForwarderService()
        session_path = os.path.join(BASE_DIR, 'deal_forwarder_session')
        bot_service.client = TelegramClient(session_path, int(api_id), api_hash)
        
        await bot_service.client.connect()
        
        if not await bot_service.client.is_user_authorized():
            bot_status = "authenticating"
            service_logger.info("Headless auth needed. Opening Web SMS Code wizard...")
            return {"status": "authenticating", "message": "Telegram SMS authorization required."}
            
        success = await bot_service.start()
        if success:
            bot_status = "running"
            service_logger.info("Deal forwarding daemon successfully started from Web Console.")
            return {"status": "running", "message": "Bot is fully operational!"}
        else:
            bot_status = "error"
            return {"status": "error", "message": "Failed to launch listener chat streams."}
            
    except Exception as e:
        bot_status = "error"
        logger.error(f"Startup crash: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Startup crashed: {str(e)}")

@app.post("/api/bot/stop")
async def stop_bot_service(request: Request):
    """Stops the active deal forwarder thread daemon."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized access.")
    global bot_service, bot_status
    
    if bot_service:
        await bot_service.stop()
        bot_service = None
        
    bot_status = "stopped"
    service_logger.info("Deal forwarding daemon stopped via Web Console.")
    return {"status": "stopped", "message": "Bot stopped successfully."}

# =====================================================================
# TELETHON PROGRAMMATIC WEB AUTHENTICATION APIs
# =====================================================================
class SendCodeRequest(BaseModel):
    phone_number: str

class VerifyCodeRequest(BaseModel):
    phone_number: str
    code: str
    password: str = ""

@app.post("/api/auth/send_code")
async def api_auth_send_code(payload: SendCodeRequest, request: Request):
    """Triggers Telethon SMS login code request to Telegram."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized access.")
    global bot_service, phone_code_hashes
    
    if not bot_service or not bot_service.client:
        raise HTTPException(status_code=400, detail="Forwarder bot is not initialized. Run start first.")
        
    try:
        if not bot_service.client.is_connected():
            await bot_service.client.connect()
            
        service_logger.info(f"Triggering verification code dispatch to {payload.phone_number}...")
        result = await bot_service.client.send_code_request(payload.phone_number)
        phone_code_hashes[payload.phone_number] = result.phone_code_hash
        return {"status": "success", "message": "SMS Code requested successfully."}
    except Exception as e:
        logger.error(f"SMS code request error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Telegram Dispatched Error: {str(e)}")

@app.post("/api/auth/verify_code")
async def api_auth_verify_code(payload: VerifyCodeRequest, request: Request):
    """Verifies SMS login code and starts the forwarding service daemon."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized access.")
    global bot_service, bot_status, phone_code_hashes
    
    if not bot_service or not bot_service.client:
        raise HTTPException(status_code=400, detail="Bot is not initialized.")
        
    phone_hash = phone_code_hashes.get(payload.phone_number)
    if not phone_hash:
        raise HTTPException(status_code=400, detail="No verification hash found for this phone number.")
        
    try:
        try:
            await bot_service.client.sign_in(
                payload.phone_number,
                payload.code,
                phone_code_hash=phone_hash
            )
        except SessionPasswordNeededError:
            if not payload.password:
                raise HTTPException(
                    status_code=401,
                    detail="2-Factor Auth enabled on this account. Please enter your 2FA password."
                )
            await bot_service.client.sign_in(password=payload.password)
            
        service_logger.info("Telegram authentication successful! Finalizing startup...")
        
        success = await bot_service.start()
        if success:
            bot_status = "running"
            return {"status": "success", "message": "Signed in successfully and bot listening."}
        else:
            bot_status = "error"
            return {"status": "error", "message": "Signed in but listener setup failed."}
            
    except Exception as e:
        logger.error(f"Dynamic auth verification failure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Authentication Failure: {str(e)}")

# =====================================================================
# SERVER RUN HOOK
# =====================================================================
if __name__ == '__main__':
    logger.info("Initializing PB Hero Bot Control Systems...")
    # Runs the dashboard uvicorn server on all interfaces to allow external cloud connection
    uvicorn.run("web_dashboard:app", host="0.0.0.0", port=8000, reload=True)
