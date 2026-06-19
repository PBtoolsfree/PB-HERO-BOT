#!/usr/bin/env python3
"""
Telegram Affiliate Deal Forwarding System (Service Class & Standalone)
=====================================================================
Flow: Target Telegram Channels -> Python Script (Link Replacer) -> My Telegram Channel + My Discord Server

This script contains the core DealForwarderService which can be imported and controlled
dynamically (e.g., from the web dashboard) or run standalone from the command line.

Author: Expert Python Developer
Date: May 2026
"""

import os
import re
import json
import logging
import asyncio
import datetime

# Compatibility fallback for Python < 3.9 (e.g., Python 3.8 or 3.7) where asyncio.to_thread does not exist
if not hasattr(asyncio, "to_thread"):
    import functools
    import contextvars

    async def _to_thread(func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        ctx = contextvars.copy_context()
        func_call = functools.partial(ctx.run, func, *args, **kwargs)
        return await loop.run_in_executor(None, func_call)

    asyncio.to_thread = _to_thread
import urllib.parse
from typing import List, Union, Dict, Any
import requests
from dotenv import load_dotenv
from telethon import TelegramClient, events
import socket

# Force IPv4 to prevent "Network Unreachable" errors on Oracle Cloud / IPv6 instances
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return old_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = new_getaddrinfo
import sqlite3
import shutil
import base64
from whatsapp_service import whatsapp_service_instance

# Absolute base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database path
DB_PATH = os.path.join(BASE_DIR, "pinterest_deals.db")
PINTEREST_MEDIA_DIR = os.path.join(BASE_DIR, "pinterest_media")

def init_db():
    """Initializes SQLite database and tables for Pinterest integration."""
    os.makedirs(PINTEREST_MEDIA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Create the pinterest_deals table without the pinterest_pin_id field (Pinterest API Data Storage Policy Safety compliance).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pinterest_deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            product_title TEXT,
            cleaned_description TEXT,
            original_text TEXT,
            image_path TEXT,
            original_url TEXT,
            affiliate_url TEXT,
            mrp REAL,
            offer_price REAL,
            discount_percentage INTEGER,
            saving_amount REAL,
            source_platform TEXT DEFAULT 'telegram',
            status TEXT DEFAULT 'pending',
            failure_reason TEXT,
            posted_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# Initialize DB on module load
init_db()

def extract_prices(text: str) -> tuple:
    """
    Extracts original price/MRP and offer price from Indian deal text formats.
    Returns (mrp, offer_price). Values are float or None.
    Supported patterns:
    - MRP: ₹29,999 or MRP: Rs 29,999
    - Deal Price: ₹24,999 or Deal Price: Rs 24,999
    - Now ₹1,499
    - Price: Rs. 999
    """
    if not text:
        return None, None
        
    mrp = None
    offer_price = None

    # Normalize text by removing commas inside numbers (e.g. 29,999 -> 29999) to simplify regex matching
    normalized_text = text
    num_comma_pattern = re.compile(r'(\d),(\d{3})')
    while num_comma_pattern.search(normalized_text):
        normalized_text = num_comma_pattern.sub(r'\1\2', normalized_text)

    # Search for MRP / Was / Original Price / regular / list / regular / List Price / Original Price / MRP
    mrp_match = re.search(r'(?:mrp|original|list|regular|was|m\.r\.p\.)\s*(?:price)?\s*:?\s*(?:₹|Rs\.?)?\s*(\d+(?:\.\d+)?)', normalized_text, re.IGNORECASE)
    if mrp_match:
        try:
            mrp = float(mrp_match.group(1))
        except ValueError:
            pass

    # Search for Deal Price / Offer Price / Now / Price / Buy / Offer / Special Price / Deal / Buy Now
    offer_match = re.search(r'(?:deal|offer|now|price|buy|special|today)\s*(?:price)?\s*:?\s*(?:₹|Rs\.?)?\s*(\d+(?:\.\d+)?)', normalized_text, re.IGNORECASE)
    if offer_match:
        try:
            offer_price = float(offer_match.group(1))
        except ValueError:
            pass
            
    # Fallback: if we didn't find MRP or offer price explicitly by labels, but we have multiple price mentions (e.g., ₹29999 ₹24999)
    if mrp is None or offer_price is None:
        price_mentions = re.findall(r'(?:₹|Rs\.?)\s*(\d+(?:\.\d+)?)', normalized_text, re.IGNORECASE)
        found_prices = []
        for p in price_mentions:
            try:
                found_prices.append(float(p))
            except ValueError:
                pass
        
        if len(found_prices) >= 2:
            mrp_val = max(found_prices)
            offer_val = min(found_prices)
            if mrp_val > offer_val:
                if mrp is None:
                    mrp = mrp_val
                if offer_price is None:
                    offer_price = offer_val
        elif len(found_prices) == 1:
            if offer_price is None:
                offer_price = found_prices[0]

    return mrp, offer_price

def extract_discount_percentage(text: str, mrp: float = None, offer_price: float = None) -> int:
    """
    Extracts the maximum discount percentage from text, or calculates it from MRP and offer price.
    Returns an integer percentage.
    """
    if not text:
        return 0
        
    percentages = []

    # 1. Match direct percentage format: "50% OFF", "Flat 40% Off", "Save 35%", "30 percent discount"
    pct_matches = re.findall(r'(\d+)\s*(?:%|percent)\s*(?:off|discount|save|छूट)?', text, re.IGNORECASE)
    for m in pct_matches:
        try:
            val = int(m)
            if 0 < val <= 100:
                percentages.append(val)
        except ValueError:
            pass

    # Matches "Save 35%"
    save_pct_matches = re.findall(r'save\s*(\d+)\s*(?:%|percent)?', text, re.IGNORECASE)
    for m in save_pct_matches:
        try:
            val = int(m)
            if 0 < val <= 100:
                percentages.append(val)
        except ValueError:
            pass

    # 2. Calculate if not found directly
    if not percentages and mrp and offer_price and mrp > offer_price > 0:
        try:
            pct = int(((mrp - offer_price) / mrp) * 100)
            if 0 < pct <= 100:
                percentages.append(pct)
        except Exception:
            pass

    if percentages:
        return max(percentages)
    return 0

def calculate_saving(mrp: float, offer_price: float) -> float:
    """Calculates the absolute saving amount (mrp - offer_price)."""
    if mrp and offer_price and mrp > offer_price:
        return mrp - offer_price
    return 0.0

def check_duplicate_deal(affiliate_url: str, title: str, offer_price: float, duplicate_days: int) -> bool:
    """
    Checks if a duplicate deal was added to Pinterest queue within the last duplicate_days.
    Returns True if a duplicate is found, False otherwise.
    """
    if not duplicate_days:
        duplicate_days = 7
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Calculate cutoff time
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=duplicate_days)).strftime('%Y-%m-%d %H:%M:%S')
    
    # 1. Check duplicate affiliate URL
    if affiliate_url:
        cursor.execute("""
            SELECT id FROM pinterest_deals 
            WHERE affiliate_url = ? 
              AND status IN ('pending', 'posted') 
              AND created_at >= ?
        """, (affiliate_url, cutoff))
        if cursor.fetchone():
            conn.close()
            return True
            
    # 2. Check duplicate title + price
    if title:
        norm_title = re.sub(r'[^a-zA-Z0-9]', '', title).lower().strip()
        
        cursor.execute("""
            SELECT id, product_title, offer_price FROM pinterest_deals 
            WHERE status IN ('pending', 'posted') 
              AND created_at >= ?
        """, (cutoff,))
        rows = cursor.fetchall()
        for r_id, r_title, r_price in rows:
            if r_title:
                r_norm = re.sub(r'[^a-zA-Z0-9]', '', r_title).lower().strip()
                if r_norm == norm_title:
                    price_match = False
                    if offer_price is None and r_price is None:
                        price_match = True
                    elif offer_price is not None and r_price is not None:
                        if abs(offer_price - r_price) < 1.0:
                            price_match = True
                    
                    if price_match:
                        conn.close()
                        return True
                        
    conn.close()
    return False


# Compute absolute base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configure dual logging: console and log file
log_formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(name)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Console Logger
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# File Logger (writes to deal_forwarder.log)
file_handler = logging.FileHandler(os.path.join(BASE_DIR, 'deal_forwarder.log'), mode='a', encoding='utf-8')
file_handler.setFormatter(log_formatter)

logger = logging.getLogger("AffiliateForwarder")
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Prevent log propagation to avoid double logging
logger.propagate = False

# Regex compiler to detect and extract standard HTTP/HTTPS URLs.
URL_REGEX = re.compile(
    r'https?://(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?::\d+)?(?:/[^\s<>"]*?)?(?=[.,;:!?")\]]?(?:\s|$))',
    re.IGNORECASE
)

# =====================================================================
# UTILITY FUNCTIONS
# =====================================================================
def escape_html(text: str) -> str:
    """Escapes raw HTML characters to prevent Telegram API parsing errors."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

async def async_post(url: str, **kwargs) -> requests.Response:
    """Wraps synchronous requests.post in an executor to avoid blocking the event loop."""
    return await asyncio.to_thread(requests.post, url, **kwargs)

import base64

def get_earnkaro_partner_id_from_token(token: str) -> str:
    """Decodes base64 payload of a JWT token to extract the numeric EarnKaro partner ID."""
    try:
        parts = token.split('.')
        if len(parts) >= 2:
            payload_b64 = parts[1]
            # Add base64 padding if required
            payload_b64 += '=' * (4 - len(payload_b64) % 4)
            payload_json = base64.b64decode(payload_b64).decode('utf-8')
            payload = json.loads(payload_json)
            return str(payload.get("earnkaro", ""))
    except Exception as e:
        logger.error(f"Failed to decode JWT token: {e}")
    return ""

def clean_affiliate_url(url: str, token: str) -> str:
    """Replaces full JWT token partner_id in the URL with the numeric partner ID if needed."""
    if "partner_id=eyJ" in url:
        partner_id = get_earnkaro_partner_id_from_token(token)
        if partner_id:
            url = re.sub(r'partner_id=eyJ[^&]+', f'partner_id={partner_id}', url)
            logger.info(f"Successfully cleaned up JWT token from partner_id in converted link. Using actual partner ID: {partner_id}")
    return url

def is_product_url(url: str) -> bool:
    """Checks if a URL is a product/deal URL suitable for affiliate conversion."""
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url.lower())
        domain = parsed.netloc or parsed.path
        
        # Exclude Telegram channels/chats and standard social channels
        ignored_domains = [
            "t.me",
            "telegram.me",
            "telegram.dog",
            "tg.me",
            "youtube.com",
            "youtu.be",
            "facebook.com",
            "instagram.com",
            "twitter.com",
            "x.com",
            "wa.me",
            "whatsapp.com"
        ]
        
        for d in ignored_domains:
            if d in domain:
                return False
                
        return True
    except Exception as e:
        logger.error(f"Error checking product URL: {e}")
        return False

def expand_url(url: str) -> str:
    """Follows HTTP redirects to expand shortened URLs (e.g. fktr.cc, amzn.to, ajiio.in) to their full destination."""
    if not url:
        return url
    try:
        req_url = url
        if not req_url.startswith('http'):
            req_url = 'https://' + req_url
            
        parsed = urllib.parse.urlparse(req_url.lower())
        domain = parsed.netloc
        
        shortened_domains = [
            "fktr.cc",
            "amzn.to",
            "amzn.in",
            "amzaff.to",
            "ajiio.in",
            "grbn.in",
            "fkrt.it",
            "bit.ly",
            "tinyurl.com",
            "t.co"
        ]
        
        is_shortened = any(d in domain for d in shortened_domains)
        if not is_shortened:
            return url
            
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        logger.info(f"Shortened URL detected: {req_url}. Expanding redirect...")
        try:
            # We use allow_redirects=True to follow location headers
            response = requests.head(req_url, headers=headers, allow_redirects=True, timeout=8)
            logger.info(f"Successfully expanded URL: {url} -> {response.url}")
            return response.url
        except Exception as e:
            logger.warning(f"Failed to expand URL via HEAD: {e}. Trying GET...")
            try:
                response = requests.get(req_url, headers=headers, allow_redirects=True, timeout=8)
                logger.info(f"Successfully expanded URL via GET: {url} -> {response.url}")
                return response.url
            except Exception as e2:
                logger.error(f"Failed to expand URL completely: {e2}")
                return url
    except Exception as e:
        logger.error(f"Exception inside expand_url: {e}")
        return url

# =====================================================================
# SERVICE CLASS IMPLEMENTATION
# =====================================================================
class DealForwarderService:
    def __init__(self, config_dict: Dict[str, Any] = None):
        """
        Initializes the forwarding service.
        If config_dict is provided, it loads settings from it, otherwise loads from env.
        """
        self.config = {}
        self.stats = {
            "processed": 0,
            "telegram_success": 0,
            "discord_success": 0,
            "pinterest_success": 0,
            "failures": 0,
            "start_time": None
        }
        self.client = None
        self.is_running = False
        self._handler_ref = None
        self._me_handler_ref = None
        self.deal_queue = asyncio.Queue()
        self.queue_worker_task = None
        self.rss_worker_task = None
        
        # Load configs
        self.load_config(config_dict)

    def load_config(self, config_dict: Dict[str, Any] = None):
        """Loads configuration from environment or provided dictionary."""
        if not config_dict:
            load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"), override=True)
            config_dict = {
                "TELEGRAM_API_ID": os.getenv("TELEGRAM_API_ID"),
                "TELEGRAM_API_HASH": os.getenv("TELEGRAM_API_HASH"),
                "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
                "MY_TELEGRAM_CHANNEL": os.getenv("MY_TELEGRAM_CHANNEL"),
                "TARGET_CHANNELS": os.getenv("TARGET_CHANNELS"),
                "WHITELIST_CHANNELS": os.getenv("WHITELIST_CHANNELS"),
                "DISCORD_MODE": os.getenv("DISCORD_MODE", "webhook"),
                "DISCORD_WEBHOOK_URL": os.getenv("DISCORD_WEBHOOK_URL"),
                "DISCORD_BOT_TOKEN": os.getenv("DISCORD_BOT_TOKEN"),
                "DISCORD_CHANNEL_IDS": os.getenv("DISCORD_CHANNEL_IDS"),
                "EARNKARO_PARTNER_ID": os.getenv("EARNKARO_PARTNER_ID", "YOUR_ID"),
                "AFFILIATE_PLATFORM": os.getenv("AFFILIATE_PLATFORM", "earnkaro"),
                "CUELINKS_API_KEY": os.getenv("CUELINKS_API_KEY", ""),
                "AMAZON_ASSOCIATE_TAG": os.getenv("AMAZON_ASSOCIATE_TAG", ""),
                "DELAY_INTERVAL": os.getenv("DELAY_INTERVAL", "900"),
                "PINTEREST_ENABLED": os.getenv("PINTEREST_ENABLED", "false"),
                "PINTEREST_ACCESS_TOKEN": os.getenv("PINTEREST_ACCESS_TOKEN", ""),
                "PINTEREST_BOARD_ID": os.getenv("PINTEREST_BOARD_ID", ""),
                "PINTEREST_MIN_DISCOUNT": os.getenv("PINTEREST_MIN_DISCOUNT", "30"),
                "PINTEREST_MIN_SAVING": os.getenv("PINTEREST_MIN_SAVING", "300"),
                "PINTEREST_DAILY_LIMIT": os.getenv("PINTEREST_DAILY_LIMIT", "5"),
                "PINTEREST_DUPLICATE_DAYS": os.getenv("PINTEREST_DUPLICATE_DAYS", "7"),
                "ENABLE_TELEGRAM_API": os.getenv("ENABLE_TELEGRAM_API", "true"),
                "ENABLE_TELEGRAM_BOT": os.getenv("ENABLE_TELEGRAM_BOT", "true"),
                "ENABLE_SOURCE_CHANNELS": os.getenv("ENABLE_SOURCE_CHANNELS", "true"),
                "ENABLE_WHITELIST_CHANNELS": os.getenv("ENABLE_WHITELIST_CHANNELS", "true"),
                "ENABLE_DESIDIME_RSS": os.getenv("ENABLE_DESIDIME_RSS", "false"),
                "FACEBOOK_PAGE_TOKEN": os.getenv("FACEBOOK_PAGE_TOKEN", ""),
                "FACEBOOK_PAGE_ID": os.getenv("FACEBOOK_PAGE_ID", ""),
                "FACEBOOK_KEYWORDS": os.getenv("FACEBOOK_KEYWORDS", "smartphone, laptop, computer, desktop, headphone, gaming console, electric gadget"),
                "ENABLE_WHATSAPP_SOURCE": os.getenv("ENABLE_WHATSAPP_SOURCE", "false"),
                "WHATSAPP_SOURCE_CHANNELS": os.getenv("WHATSAPP_SOURCE_CHANNELS", ""),
                "WHATSAPP_TARGET_CHANNEL": os.getenv("WHATSAPP_TARGET_CHANNEL", "")
            }

        self.config = {
            "api_id": config_dict.get("TELEGRAM_API_ID"),
            "api_hash": config_dict.get("TELEGRAM_API_HASH"),
            "bot_token": config_dict.get("TELEGRAM_BOT_TOKEN"),
            "discord_mode": config_dict.get("DISCORD_MODE", "webhook"),
            "discord_webhook": config_dict.get("DISCORD_WEBHOOK_URL"),
            "discord_bot_token": config_dict.get("DISCORD_BOT_TOKEN"),
            "discord_channel_ids": config_dict.get("DISCORD_CHANNEL_IDS"),
            "partner_id": config_dict.get("EARNKARO_PARTNER_ID", "YOUR_ID"),
            "affiliate_platform": config_dict.get("AFFILIATE_PLATFORM", "earnkaro"),
            "cuelinks_api_key": config_dict.get("CUELINKS_API_KEY", ""),
            "amazon_tag": config_dict.get("AMAZON_ASSOCIATE_TAG", ""),
            "whitelist_channels_raw": config_dict.get("WHITELIST_CHANNELS", ""),
            "delay_interval_raw": config_dict.get("DELAY_INTERVAL", "900"),
            "enable_tg_api": str(config_dict.get("ENABLE_TELEGRAM_API", "true")).lower() == "true",
            "enable_tg_bot": str(config_dict.get("ENABLE_TELEGRAM_BOT", "true")).lower() == "true",
            "enable_source_channels": str(config_dict.get("ENABLE_SOURCE_CHANNELS", "true")).lower() == "true",
            "enable_whitelist_channels": str(config_dict.get("ENABLE_WHITELIST_CHANNELS", "true")).lower() == "true",
            "enable_desidime_rss": str(config_dict.get("ENABLE_DESIDIME_RSS", "false")).lower() == "true",
            "pinterest_enabled": str(config_dict.get("PINTEREST_ENABLED", "false")).lower() == "true",
            "pinterest_access_token": config_dict.get("PINTEREST_ACCESS_TOKEN", ""),
            "pinterest_board_id": config_dict.get("PINTEREST_BOARD_ID", ""),
            "pinterest_min_discount": int(config_dict.get("PINTEREST_MIN_DISCOUNT") if str(config_dict.get("PINTEREST_MIN_DISCOUNT")).isdigit() else 30),
            "pinterest_min_saving": float(config_dict.get("PINTEREST_MIN_SAVING") if str(config_dict.get("PINTEREST_MIN_SAVING")).replace('.', '', 1).isdigit() else 300.0),
            "pinterest_daily_limit": int(config_dict.get("PINTEREST_DAILY_LIMIT") if str(config_dict.get("PINTEREST_DAILY_LIMIT")).isdigit() else 5),
            "pinterest_duplicate_days": int(config_dict.get("PINTEREST_DUPLICATE_DAYS") if str(config_dict.get("PINTEREST_DUPLICATE_DAYS")).isdigit() else 7),
            "facebook_page_token": config_dict.get("FACEBOOK_PAGE_TOKEN", ""),
            "facebook_page_id": config_dict.get("FACEBOOK_PAGE_ID", ""),
            "facebook_keywords": [k.strip().lower() for k in str(config_dict.get("FACEBOOK_KEYWORDS", "")).split(',') if k.strip()],
            "enable_whatsapp_source": str(config_dict.get("ENABLE_WHATSAPP_SOURCE", "false")).lower() == "true",
            "whatsapp_source_channels": [c.strip() for c in str(config_dict.get("WHATSAPP_SOURCE_CHANNELS", "")).split(',') if c.strip()],
            "whatsapp_target_channel": config_dict.get("WHATSAPP_TARGET_CHANNEL", "")
        }

        # Parse Channels
        self.config["my_channel"] = self._parse_channel_id(config_dict.get("MY_TELEGRAM_CHANNEL", ""))
        self.config["target_channels"] = self._parse_target_channels(config_dict.get("TARGET_CHANNELS", ""))
        self.config["whitelist_channels"] = self._parse_target_channels(config_dict.get("WHITELIST_CHANNELS", ""))
        self.config["delay_interval"] = int(self.config["delay_interval_raw"] if str(self.config["delay_interval_raw"]).isdigit() else 900)
        
        # Parse Discord Target Channels
        self.config["discord_channels"] = [
            int(c.strip()) for c in str(self.config["discord_channel_ids"] or "").split(",") if c.strip().isdigit()
        ]

    def _parse_channel_id(self, channel_raw: str) -> Union[int, str]:
        """Parses individual channel identifier to integer or string."""
        if not channel_raw:
            return ""
        channel_str = str(channel_raw).strip()
        if channel_str.lstrip('-').isdigit():
            return int(channel_str)
        return channel_str

    def _parse_target_channels(self, channels_str: str) -> List[Union[int, str]]:
        """Parses comma-separated channel strings into structured list."""
        if not channels_str:
            return []
        parsed = []
        for item in str(channels_str).split(','):
            val = self._parse_channel_id(item)
            if val:
                parsed.append(val)
        return parsed

    def convert_to_affiliate(self, original_url: str) -> str:
        """Transforms extracted URL into the active affiliate platform's format."""
        
        # 1. Expand shortened URLs first (e.g. fktr.cc, amzn.to, ajiio.in) to get full merchant URLs
        original_url = expand_url(original_url)
        
        # 2. Check if direct Amazon Associates tag conversion is enabled and this is an Amazon link
        amazon_tag = self.config.get("amazon_tag", "").strip()
        if amazon_tag:
            parsed_url = urllib.parse.urlparse(original_url.lower())
            domain = parsed_url.netloc or parsed_url.path
            if "amazon." in domain:
                try:
                    logger.info(f"Direct Amazon Affiliate conversion detected. URL: {original_url} using tag: {amazon_tag}")
                    u = urllib.parse.urlparse(original_url)
                    query = urllib.parse.parse_qs(u.query)
                    
                    # Force overwrite the 'tag' query parameter
                    query["tag"] = [amazon_tag]
                    
                    # Reconstruct the URL query and the full URL
                    new_query = urllib.parse.urlencode(query, doseq=True)
                    final_url = urllib.parse.urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))
                    logger.info(f"Direct Amazon converted URL: {final_url}")
                    return final_url
                except Exception as e:
                    logger.error(f"Failed to convert Amazon URL directly: {e}")

        # 3. Extract nested target URL if it's a known redirect link (e.g. earnkaro.com/connect)
        if "earnkaro.com" in original_url or "cuelinks.com" in original_url:
            try:
                parsed_orig = urllib.parse.urlparse(original_url)
                query_params = urllib.parse.parse_qs(parsed_orig.query)
                nested_url = query_params.get("url")
                if nested_url:
                    target_url = nested_url[0]
                    logger.info(f"Detected redirect link. Extracted nested target URL for conversion: {target_url}")
                    original_url = target_url
            except Exception as e:
                logger.error(f"Failed to parse nested redirect URL: {e}")

        platform = self.config.get("affiliate_platform", "earnkaro").lower()
        
        if platform == "cuelinks":
            api_key = self.config.get("cuelinks_api_key", "")
            if api_key:
                try:
                    headers = {
                        "Authorization": f'Token token="{api_key.strip()}"',
                        "Content-Type": "application/json"
                    }
                    encoded_url = urllib.parse.quote(original_url)
                    api_url = f"https://www.cuelinks.com/api/v2/links.json?url={encoded_url}"
                    response = requests.get(api_url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if isinstance(data, dict):
                            link_data = data.get("link", {})
                            if isinstance(link_data, dict) and "affiliate_url" in link_data:
                                logger.info("Successfully converted link using Cuelinks API!")
                                return link_data["affiliate_url"]
                            elif "affiliate_url" in data:
                                logger.info("Successfully converted link using Cuelinks API!")
                                return data["affiliate_url"]
                            elif "url" in data:
                                return data["url"]
                            elif isinstance(link_data, dict) and "url" in link_data:
                                return link_data["url"]
                    
                    logger.error(f"Cuelinks API returned status {response.status_code}: {response.text}")
                except Exception as e:
                    logger.error(f"Cuelinks API conversion exception: {e}")
            
            logger.warning("Cuelinks conversion failed or is unconfigured. Falling back to original URL.")
            return original_url
        else:
            # EarnKaro API (Affiliaters IN wrapper)
            api_key = self.config.get("partner_id")
            if api_key and api_key.strip() and api_key.strip() not in ["YOUR_ID", "YOUR_PARTNER_ID"]:
                try:
                    headers = {
                        "Authorization": f"Bearer {api_key.strip()}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "deal": original_url,
                        "convert_option": "convert_only"
                    }
                    response = requests.post(
                        "https://ekaro-api.affiliaters.in/api/converter/public",
                        headers=headers,
                        json=payload,
                        timeout=15
                    )
                    if response.status_code == 200:
                        res_json = response.json()
                        if isinstance(res_json, dict):
                            if res_json.get("success") == 1 or "data" in res_json:
                                converted_url = res_json.get("data")
                                if converted_url and isinstance(converted_url, str) and converted_url.strip().startswith("http"):
                                    logger.info("Successfully converted link using EarnKaro (Affiliaters IN) API!")
                                    cleaned_url = clean_affiliate_url(converted_url.strip(), api_key)
                                    return cleaned_url
                                else:
                                    logger.error(f"EarnKaro API returned invalid URL or error string: {converted_url}")
                            elif "message" in res_json:
                                logger.error(f"EarnKaro API returned error: {res_json['message']}")
                    else:
                        logger.error(f"EarnKaro API returned status {response.status_code}: {response.text}")
                except Exception as e:
                    logger.error(f"EarnKaro API conversion exception: {e}")
            
            logger.warning("EarnKaro API conversion failed or is unconfigured. Returning original URL.")
            return original_url


    def clean_message_text(self, text: str, urls: List[str]) -> str:
        """Removes original URLs from message body, cleaning white spaces."""
        cleaned = text
        for url in urls:
            cleaned = cleaned.replace(url, "")
        cleaned = re.sub(r' +', ' ', cleaned)
        cleaned = re.sub(r'\n\s*\n+', '\n\n', cleaned).strip()
        return cleaned

    # =====================================================================
    # BROADCASTING DISPATCHERS
    # =====================================================================
    async def send_to_telegram(self, text: str, affiliate_url: str = None, photo_path: str = None) -> bool:
        """Sends deal to Telegram channel via bot token."""
        if not self.config.get("enable_tg_bot", True):
            logger.info("Telegram Bot Broadcasting is DISABLED. Skipping Telegram forward.")
            return False

        bot_token = self.config.get("bot_token")
        my_channel = self.config.get("my_channel")
        
        if not bot_token or not my_channel:
            logger.error("Telegram Send Failed: BOT_TOKEN or MY_TELEGRAM_CHANNEL is missing.")
            return False

        reply_markup = None
        if affiliate_url:
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "🛒 Shop Now / खरीदें", "url": affiliate_url}]
                ]
            }

        # Append affiliate URL to text/caption to enable automatic webpage link previews and clicks
        formatted_text = text
        if affiliate_url:
            formatted_text = f"{text}\n\n🛒 <b>Buy Link / यहाँ से खरीदें:</b> <a href=\"{affiliate_url}\">{affiliate_url}</a>"

        try:
            if photo_path and os.path.exists(photo_path):
                api_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                def _post_photo():
                    payload = {
                        "chat_id": str(my_channel),
                        "caption": formatted_text,
                        "parse_mode": "HTML"
                    }
                    if reply_markup:
                        payload["reply_markup"] = json.dumps(reply_markup)
                    with open(photo_path, "rb") as f:
                        return requests.post(api_url, data=payload, files={"photo": f}, timeout=20)
                
                response = await asyncio.to_thread(_post_photo)
            else:
                api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {
                    "chat_id": str(my_channel),
                    "text": formatted_text,
                    "parse_mode": "HTML"
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                response = await async_post(api_url, json=payload, timeout=20)
                
            response.raise_for_status()
            self.stats["telegram_success"] += 1
            logger.info("Successfully sent deal to Telegram!")
            return True
        except Exception as e:
            self.stats["failures"] += 1
            logger.error(f"Telegram API Error: {e}")
            if 'response' in locals() and hasattr(response, 'text'):
                logger.error(f"Telegram Response Detail: {response.text}")
            return False

    async def send_to_discord(self, text: str, affiliate_url: str = None, photo_path: str = None) -> bool:
        """Dispatches deal to Discord using the active integration mode (webhook or bot)."""
        # If no affiliate_url was provided, but there are URLs in the text, extract the first one (e.g. for whitelisted channels)
        if not affiliate_url:
            urls = URL_REGEX.findall(text or "")
            if urls:
                affiliate_url = urls[0]
                
        mode = self.config.get("discord_mode", "webhook").lower()
        if mode == "bot":
            return await self.send_to_discord_bot(text, affiliate_url, photo_path)
        return await self.send_to_discord_webhook(text, affiliate_url, photo_path)

    async def send_to_discord_webhook(self, text: str, affiliate_url: str = None, photo_path: str = None) -> bool:
        """Sends a beautiful Rich Embed and native Buy Button to Discord webhook with optional image."""
        webhook_url = self.config.get("discord_webhook")
        if not webhook_url:
            return False
            
        # Clean URL out of description block if we render it as a button
        cleaned_msg_text = text
        if affiliate_url:
            cleaned_msg_text = text.replace(affiliate_url, "").strip()
            cleaned_msg_text = re.sub(r'\n\s*\n+', '\n\n', cleaned_msg_text).strip()
            
        # Format the description block with premium markdown styling
        if affiliate_url:
            description_text = (
                f"✨ **LIMITED TIME DEAL** ✨\n"
                f"━━━━━━━━━━━━━━━━━━━\n\n"
                f"{cleaned_msg_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🚀 **[🛒 SHOP NOW / यहाँ से खरीदें]({affiliate_url})** ➔\n"
                f"━━━━━━━━━━━━━━━━━━━"
            )
        else:
            description_text = text
            
        payload = {
            "embeds": [
                {
                    "title": "🔥🔥 Limited Time Deal! 🔥🔥",
                    "description": description_text,
                    "color": 15094272,  # Orange/Red
                    "footer": {
                        "text": "Automated via PB Hero Bot"
                    },
                    "timestamp": datetime.datetime.utcnow().isoformat()
                }
            ]
        }
        
        # Add a premium native Link Button to the bottom of the embed card!
        if affiliate_url:
            payload["components"] = [
                {
                    "type": 1,  # Action Row
                    "components": [
                        {
                            "type": 2,  # Button Component
                            "style": 5,  # Link Button Style
                            "label": "🛍️ SHOP NOW / यहाँ से खरीदें ➔",
                            "url": affiliate_url
                        }
                    ]
                }
            ]
        
        if photo_path and os.path.exists(photo_path):
            payload["embeds"][0]["image"] = {"url": "attachment://image.jpg"}
            
            def _post_discord_with_file():
                with open(photo_path, "rb") as f:
                    files = {
                        "file": ("image.jpg", f, "image/jpeg")
                    }
                    data = {
                        "payload_json": json.dumps(payload)
                    }
                    return requests.post(webhook_url, data=data, files=files, timeout=20)
            
            try:
                response = await asyncio.to_thread(_post_discord_with_file)
                if response.status_code in [200, 204]:
                    self.stats["discord_success"] += 1
                    logger.info("Successfully sent deal and image to Discord Webhook!")
                    return True
                response.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"Discord Webhook Image Send Error: {e}")
                if 'response' in locals() and hasattr(response, 'text'):
                    logger.error(f"Discord Response Detail: {response.text}")
                return False
        else:
            try:
                response = await async_post(webhook_url, json=payload, timeout=15)
                if response.status_code in [200, 204]:
                    self.stats["discord_success"] += 1
                    logger.info("Successfully sent deal to Discord Webhook!")
                    return True
                response.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"Discord Webhook Error: {e}")
                if 'response' in locals() and hasattr(response, 'text'):
                    logger.error(f"Discord Response Detail: {response.text}")
                return False

    async def send_to_discord_bot(self, text: str, affiliate_url: str = None, photo_path: str = None) -> bool:
        """Broadcasts Rich Embed to multiple Discord Channels using direct HTTP bot APIs."""
        bot_token = self.config.get("discord_bot_token")
        target_channels = self.config.get("discord_channels", [])
        
        if not bot_token or not target_channels:
            logger.error("Discord Bot Send Failed: Bot token or target channel list is empty.")
            return False

        # Clean URL out of description block if we render it as a button
        cleaned_msg_text = text
        if affiliate_url:
            cleaned_msg_text = text.replace(affiliate_url, "").strip()
            cleaned_msg_text = re.sub(r'\n\s*\n+', '\n\n', cleaned_msg_text).strip()
            
        # Format the description block with premium markdown styling
        if affiliate_url:
            description_text = (
                f"✨ **LIMITED TIME DEAL** ✨\n"
                f"━━━━━━━━━━━━━━━━━━━\n\n"
                f"{cleaned_msg_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🚀 **[🛒 SHOP NOW / यहाँ से खरीदें]({affiliate_url})** ➔\n"
                f"━━━━━━━━━━━━━━━━━━━"
            )
        else:
            description_text = text
            
        payload = {
            "embeds": [
                {
                    "title": "🔥🔥 Limited Time Deal! 🔥🔥",
                    "description": description_text,
                    "color": 15094272,  # Orange/Red
                    "footer": {
                        "text": "Automated via PB Hero Bot"
                    },
                    "timestamp": datetime.datetime.utcnow().isoformat()
                }
            ]
        }
        
        # Add a premium native Link Button to the bottom of the embed card!
        if affiliate_url:
            payload["components"] = [
                {
                    "type": 1,  # Action Row
                    "components": [
                        {
                            "type": 2,  # Button Component
                            "style": 5,  # Link Button Style
                            "label": "🛍️ SHOP NOW / यहाँ से खरीदें ➔",
                            "url": affiliate_url
                        }
                    ]
                }
            ]

        headers = {
            "Authorization": f"Bot {bot_token.strip()}"
        }

        success_count = 0
        for channel_id in target_channels:
            api_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
            
            try:
                if photo_path and os.path.exists(photo_path):
                    payload["embeds"][0]["image"] = {"url": "attachment://image.jpg"}
                    
                    def _post_bot_with_file(chan_url):
                        with open(photo_path, "rb") as f:
                            files = {
                                "file": ("image.jpg", f, "image/jpeg")
                            }
                            data = {
                                "payload_json": json.dumps(payload)
                            }
                            return requests.post(chan_url, headers=headers, data=data, files=files, timeout=20)
                    
                    response = await asyncio.to_thread(_post_bot_with_file, api_url)
                else:
                    headers["Content-Type"] = "application/json"
                    response = await asyncio.to_thread(requests.post, api_url, headers=headers, json=payload, timeout=15)
                
                if response.status_code in [200, 201, 204]:
                    success_count += 1
                    logger.info(f"Discord Bot successfully sent deal to channel: {channel_id}")
                    
                    # Try to automatically crosspost/publish the message (extremely useful for News/Announcement channels)
                    res_json = response.json()
                    msg_id = res_json.get("id")
                    if msg_id:
                        try:
                            crosspost_url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{msg_id}/crosspost"
                            def _crosspost():
                                return requests.post(crosspost_url, headers={"Authorization": f"Bot {bot_token.strip()}"}, timeout=8)
                            crosspost_res = await asyncio.to_thread(_crosspost)
                            if crosspost_res.status_code == 200:
                                logger.info(f"Discord Bot successfully auto-published (crossposted) message {msg_id} on channel {channel_id}!")
                            else:
                                logger.debug(f"Auto-publish skipped or returned status {crosspost_res.status_code}")
                        except Exception as cp_err:
                            logger.debug(f"Auto-publish exception: {cp_err}")
                else:
                    logger.error(f"Discord Bot failed for channel {channel_id} with status {response.status_code}: {response.text}")
            except Exception as e:
                logger.error(f"Discord Bot exception for channel {channel_id}: {e}")
                
        if success_count > 0:
            self.stats["discord_success"] += success_count
            return True
        return False

    async def send_to_facebook(self, text: str, affiliate_url: str = None, photo_path: str = None) -> bool:
        """Posts deal to Facebook Page using Graph API if it matches keyword filters."""
        page_token = self.config.get("facebook_page_token")
        page_id = self.config.get("facebook_page_id")
        
        if not page_token or not page_id:
            logger.debug("Facebook Page posting skipped: No token or page ID configured.")
            return False

        # Apply Keyword Filter
        keywords = self.config.get("facebook_keywords", [])
        if keywords:
            text_lower = text.lower()
            if not any(kw in text_lower for kw in keywords):
                logger.info(f"Facebook: Deal skipped due to keyword filter. Required keywords: {keywords}")
                return False

        formatted_text = text
        if affiliate_url:
            formatted_text = f"{text}\n\n🛍️ Buy Now: {affiliate_url}"

        try:
            if photo_path and os.path.exists(photo_path):
                url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
                payload = {
                    "message": formatted_text,
                    "access_token": page_token
                }
                def _post_photo():
                    with open(photo_path, "rb") as f:
                        return requests.post(url, data=payload, files={"source": f}, timeout=20)
                response = await asyncio.to_thread(_post_photo)
            else:
                url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
                payload = {
                    "message": formatted_text,
                    "access_token": page_token
                }
                if affiliate_url:
                    payload["link"] = affiliate_url
                response = await async_post(url, data=payload, timeout=20)
                
            response.raise_for_status()
            logger.info("Successfully posted to Facebook Page!")
            return True
        except Exception as e:
            logger.error(f"Facebook Graph API Error: {e}")
            if 'response' in locals() and hasattr(response, 'text'):
                logger.error(f"Facebook Response Detail: {response.text}")
            return False

    # =====================================================================
    # MESSAGE LISTENER HANDLER
    # =====================================================================
    async def process_test_message(self, event: events.NewMessage.Event):
        """Processes a message sent in Saved Messages (me) to test affiliate conversion AND broadcast it."""
        text = event.message.message
        if not text and not event.message.photo:
            return

        # Extract URLs using Telegram's message entities (most reliable)
        url_entities = []
        if getattr(event.message, 'entities', None):
            for entity, entity_text in event.message.get_entities_text():
                entity_type = type(entity).__name__
                if entity_type == 'MessageEntityTextUrl':
                    url_entities.append(entity.url)
                elif entity_type == 'MessageEntityUrl':
                    url_entities.append(entity_text)
                        
        # Fallback to regex if entities are empty
        if not url_entities:
            url_entities = URL_REGEX.findall(text or "")
            
        product_urls = [url for url in url_entities if is_product_url(url)]
        
        if product_urls:
            logger.info(f"Manual deal detected in Saved Messages. Extracted product URL count: {len(product_urls)}")
            original_url = product_urls[0]
            affiliate_url = self.convert_to_affiliate(original_url)
            
            cleaned_text = self.clean_message_text(text, product_urls)
            escaped_tg_text = escape_html(cleaned_text)
            
            # Build test response
            formatted_text = f"✅ <b>Deal Intercepted & Broadcasted!</b>\n\n{escaped_tg_text}\n\n🛒 <b>Buy Link:</b> <a href=\"{affiliate_url}\">{affiliate_url}</a>"
            
            try:
                await event.reply(formatted_text, parse_mode="HTML", link_preview=False)
            except Exception as e:
                logger.error(f"Failed to reply to test message: {e}")
        else:
            try:
                await event.reply("✅ <b>Broadcasted!</b> (No product links detected, sending as plain text/image).", parse_mode="HTML")
            except Exception:
                pass
                
        # Send it to the main processor to actually post it to Telegram, Discord, Facebook, and Pinterest!
        await self.process_message(event)

    async def handle_whatsapp_message(self, text: str, is_sandbox: bool):
        """Processes a scraped message from WhatsApp Web."""
        if not text:
            return
            
        logger.info(f"Received WhatsApp Scraped Message. Is Sandbox: {is_sandbox}")
        
        url_entities = URL_REGEX.findall(text)
        product_urls = [url for url in url_entities if is_product_url(url)]
        
        if is_sandbox:
            if product_urls:
                original_url = product_urls[0]
                affiliate_url = self.convert_to_affiliate(original_url)
                cleaned_text = self.clean_message_text(text, product_urls)
                
                try:
                    reply_text = f"✅ *Deal Intercepted & Broadcasted!*\n\n{cleaned_text}\n\n🛒 *Buy Link:* {affiliate_url}"
                    # Use a background task to avoid blocking the pipeline
                    asyncio.create_task(whatsapp_service_instance.post_to_channel("Message yourself", reply_text))
                except Exception as e:
                    logger.error(f"Failed to reply to WhatsApp sandbox: {e}")
            else:
                try:
                    asyncio.create_task(whatsapp_service_instance.post_to_channel("Message yourself", "✅ *Broadcasted!* (No product links detected)."))
                except Exception:
                    pass

        # Feed into standard processor using a Mock Event
        class MockMessage:
            def __init__(self, t):
                self.message = t
                self.photo = None
                self.entities = None
            def get_entities_text(self):
                return []
                
        class MockEvent:
            def __init__(self, t):
                self.message = MockMessage(t)
                self.chat_id = "whatsapp_source"
                self.chat = None
                
        await self.process_message(MockEvent(text))


    async def process_message(self, event: events.NewMessage.Event):
        """Processes a live incoming message, extracts links, and forwards."""
        text = event.message.message
        if not text and not event.message.photo:
            return

        # Extract URLs using Telegram's message entities (most reliable)
        url_entities = []
        if getattr(event.message, 'entities', None):
            for entity, entity_text in event.message.get_entities_text():
                entity_type = type(entity).__name__
                if entity_type == 'MessageEntityTextUrl':
                    url_entities.append(entity.url)
                elif entity_type == 'MessageEntityUrl':
                    url_entities.append(entity_text)
                        
        # Fallback to regex if entities are empty
        if not url_entities:
            url_entities = URL_REGEX.findall(text or "")
            
        self.stats["processed"] += 1
        
        # Apply the smart product link filter
        product_urls = [url for url in url_entities if is_product_url(url)]
        
        # Check if the source is whitelisted (Skip link conversion)
        is_whitelisted = False
        whitelist_list = self.config.get("whitelist_channels", [])
        
        # 1. Match numeric ID
        if event.chat_id in whitelist_list:
            is_whitelisted = True
            
        # 2. Match username
        if not is_whitelisted and hasattr(event, 'chat') and getattr(event.chat, 'username', None):
            username_cleaned = event.chat.username.lower().strip()
            for wl in whitelist_list:
                if isinstance(wl, str) and wl.lower().strip().lstrip('@') == username_cleaned:
                    is_whitelisted = True
                    break

        affiliate_url = None
        cleaned_text = text or ""
        
        if is_whitelisted:
            logger.info(f"Incoming post is from WHITELISTED channel: {event.chat_id}. Forwarding directly without link conversion.")
        elif product_urls:
            logger.info(f"Incoming deal detected. Extracted product URL count: {len(product_urls)} (out of {len(raw_urls)} total URLs)")
            original_url = product_urls[0]
            affiliate_url = self.convert_to_affiliate(original_url)
            # Only clean out actual product deal URLs from the message body
            cleaned_text = self.clean_message_text(text, product_urls)
        else:
            logger.info("Incoming deal detected without any product links. Forwarding content directly.")
            
        escaped_tg_text = escape_html(cleaned_text)
        
        # Handle Image download
        photo_path = None
        if event.message.photo:
            try:
                temp_media_dir = os.path.join(BASE_DIR, "temp_media")
                os.makedirs(temp_media_dir, exist_ok=True)
                photo_path = await event.message.download_media(file=temp_media_dir + "/")
                logger.info(f"Downloaded media: {photo_path}")
            except Exception as e:
                logger.error(f"Media download failed: {e}")

        # Put the processed deal into our queue!
        deal_payload = {
            "escaped_text": escaped_tg_text,
            "raw_text": cleaned_text,
            "affiliate_url": affiliate_url,
            "photo_path": photo_path  # The worker will clean this up after sending!
        }
        
        try:
            await self.deal_queue.put(deal_payload)
            logger.info(f"Successfully added deal to queue. Current queue size: {self.deal_queue.qsize()}. Will post shortly.")
            
            # --- START PINTEREST ELIGIBILITY & DB WORKFLOW ---
            # Run Pinterest logic asynchronously so it doesn't block Telegram / Discord send
            async def run_pinterest_validation():
                try:
                    # Clean title & prices
                    product_title = text.split('\n')[0].strip()
                    product_title = re.sub(r'<[^>]*>', '', product_title) # Strip HTML tags
                    product_title = product_title.replace('*', '').replace('_', '').replace('~', '').strip()
                    product_title = product_title[:100] # Pinterest title length limit
                    
                    mrp, offer_price = extract_prices(text)
                    discount_percentage = extract_discount_percentage(text, mrp, offer_price)
                    saving_amount = calculate_saving(mrp, offer_price)
                    
                    # Eligibility Rules
                    pinterest_eligible = True
                    pinterest_reject_reason = None
                    
                    if not self.config.get("pinterest_enabled"):
                        pinterest_eligible = False
                        pinterest_reject_reason = "pinterest_disabled"
                    elif not photo_path or not os.path.exists(photo_path):
                        pinterest_eligible = False
                        pinterest_reject_reason = "no_image"
                    elif not affiliate_url:
                        pinterest_eligible = False
                        pinterest_reject_reason = "missing_affiliate_link"
                    elif discount_percentage < self.config.get("pinterest_min_discount", 30):
                        pinterest_eligible = False
                        pinterest_reject_reason = "low_discount"
                    elif mrp is not None and offer_price is not None and saving_amount < self.config.get("pinterest_min_saving", 300):
                        pinterest_eligible = False
                        pinterest_reject_reason = "low_saving"
                    elif mrp is not None and offer_price is not None and mrp <= offer_price:
                        pinterest_eligible = False
                        pinterest_reject_reason = "invalid_price"
                    elif check_duplicate_deal(affiliate_url, product_title, offer_price, self.config.get("pinterest_duplicate_days", 7)):
                        pinterest_eligible = False
                        pinterest_reject_reason = "duplicate"
                        
                    # Store in SQLite database
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    
                    # If eligible, copy the image to persistent directory
                    persistent_image_path = None
                    if pinterest_eligible:
                        os.makedirs(PINTEREST_MEDIA_DIR, exist_ok=True)
                        _, ext = os.path.splitext(photo_path)
                        dest_filename = f"pin_{int(datetime.datetime.now().timestamp())}_{os.path.basename(photo_path)}"
                        dest_path = os.path.join(PINTEREST_MEDIA_DIR, dest_filename)
                        shutil.copy2(photo_path, dest_path)
                        persistent_image_path = dest_path
                        logger.info(f"Pinterest: Copied image to persistent store: {persistent_image_path}")
                    
                    # Clean description for storage
                    cleaned_desc = re.sub(r'<[^>]*>', '', text)
                    cleaned_desc = cleaned_desc.replace('*', '').replace('_', '').replace('~', '').strip()
                    cleaned_desc = cleaned_desc[:500]
                    
                    status = "pending" if pinterest_eligible else "rejected"
                    failure_reason = pinterest_reject_reason if not pinterest_eligible else None
                    
                    # Save rejected deals as rejected with reason (or pending if eligible)
                    if pinterest_reject_reason != "pinterest_disabled":
                        cursor.execute("""
                            INSERT INTO pinterest_deals (
                                product_title, cleaned_description, original_text, image_path,
                                original_url, affiliate_url, mrp, offer_price,
                                discount_percentage, saving_amount, status, failure_reason
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            product_title, cleaned_desc, text, persistent_image_path,
                            product_urls[0] if product_urls else None, affiliate_url, mrp, offer_price,
                            discount_percentage, saving_amount, status, failure_reason
                        ))
                        conn.commit()
                        
                        if pinterest_eligible:
                            logger.info(f"Pinterest pending deal created: {product_title}")
                        else:
                            logger.info(f"Pinterest rejected candidate saved: reason={pinterest_reject_reason}, title={product_title}")
                    else:
                        logger.info("Pinterest disabled, deal skipped for Pinterest queue.")
                    conn.close()
                except Exception as ex:
                    logger.error(f"Error in Pinterest validation thread: {ex}", exc_info=True)
            
            # Start background validation task
            asyncio.create_task(run_pinterest_validation())
            # --- END PINTEREST ELIGIBILITY & DB WORKFLOW ---
            
        except Exception as e:
            logger.error(f"Failed to queue deal: {e}")
            # Fallback: clean up temp file if queuing failed
            if photo_path and os.path.exists(photo_path):
                try:
                    os.remove(photo_path)
                except:
                    pass

    async def deal_queue_worker(self):
        """Asynchronous worker to process and send deals at configured intervals to prevent spam."""
        logger.info("Deal Queue Worker: Thread started and listening for deals...")
        try:
            while self.is_running:
                # Wait for the next deal
                deal = await self.deal_queue.get()
                
                try:
                    logger.info(f"Queue Worker: Processing deal. Queue size: {self.deal_queue.qsize()}")
                    # Send to Telegram
                    await self.send_to_telegram(deal["escaped_text"], deal["affiliate_url"], deal["photo_path"])
                    # Send to Discord
                    await self.send_to_discord(deal["raw_text"], deal["affiliate_url"], deal["photo_path"])
                    # Send to Facebook
                    await self.send_to_facebook(deal["raw_text"], deal["affiliate_url"], deal["photo_path"])
                    # Send to WhatsApp
                    if self.config.get("enable_whatsapp_source") and self.config.get("whatsapp_target_channel"):
                        target_channel = self.config.get("whatsapp_target_channel")
                        formatted_wa_text = deal["raw_text"]
                        if deal["affiliate_url"]:
                            formatted_wa_text += f"\n\n🛒 *Buy Now:* {deal['affiliate_url']}"
                        await whatsapp_service_instance.post_to_channel(target_channel, formatted_wa_text, deal["photo_path"])
                except Exception as ex:
                    logger.error(f"Queue Worker: Error sending queued deal: {ex}")
                finally:
                    # Clean up the photo file if it exists
                    photo_path = deal.get("photo_path")
                    if photo_path and os.path.exists(photo_path):
                        try:
                            os.remove(photo_path)
                            logger.info(f"Queue Worker: Cleaned up temporary media: {photo_path}")
                        except Exception as e:
                            logger.error(f"Queue Worker: Failed to delete temp media: {e}")
                    
                    self.deal_queue.task_done()
                
                # Sleep for configured interval
                delay = int(self.config.get("delay_interval", 900))
                if delay > 0 and self.is_running:
                    logger.info(f"Queue Worker: Waiting {delay} seconds before next post to prevent spam...")
                    await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.info("Queue Worker: Worker task cancelled cleanly.")
        except Exception as e:
            logger.error(f"Queue Worker: Crash exception: {e}")

    async def desidime_rss_worker_loop(self):
        """Asynchronously fetches deals from DesiDime (via HTML scraping) every 5 minutes."""
        logger.info("DesiDime RSS Worker: Started fetching deals in background...")
        import time
        import re
        import html

        seen_urls = set()
        
        while self.is_running:
            try:
                # Use a proper User-Agent to avoid getting blocked
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                logger.info("RSS Worker: Fetching latest deals from DesiDime HTML...")
                
                # DesiDime Atom feeds (posts.atom) are broken (Status 500) from their end.
                # So we fallback to scraping the homepage HTML directly.
                response = await asyncio.to_thread(requests.get, "https://www.desidime.com/", headers=headers, timeout=15)
                
                if response.status_code == 200:
                    html_content = response.text
                    
                    # Regex to find deals on the homepage HTML
                    # Looks for: href="/deals/some-deal-url" ... <span class="font-medium">Deal Title</span>
                    pattern = re.compile(r'href="(/deals/[^"]+)".*?<span class="font-medium">\s*(.*?)\s*</span>', re.DOTALL)
                    matches = pattern.findall(html_content)
                    
                    # Keywords for filtering
                    whitelist = ["electric", "tech", "gaming", "phone", "computer", "headphone", "microphone", "finger sleeve", "laptop", "smartwatch", "monitor", "earbuds", "tv"]
                    blacklist = ["fashion", "clothes", "shoe", "wear", "shirt", "pant", "grocery", "food"]
                    
                    for match in matches[:40]:
                        link_path = match[0]
                        title = html.unescape(match[1].strip())
                        
                        if '?' in link_path:
                            link_path = link_path.split('?')[0]
                        link = "https://www.desidime.com" + link_path
                        
                        if not link or link in seen_urls:
                            continue
                            
                        seen_urls.add(link)
                        
                        # Apply Filtering
                        combined_text = title.lower()
                        
                        has_whitelist = any(wl in combined_text for wl in whitelist)
                        has_blacklist = any(bl in combined_text for bl in blacklist)
                        
                        if has_whitelist and not has_blacklist:
                            logger.info(f"RSS Worker: Found matching deal! Title: {title}")
                            
                            # Convert to affiliate
                            affiliate_url = self.convert_to_affiliate(link)
                            
                            raw_text = f"{title}"
                            escaped_text = escape_html(raw_text)
                            
                            deal_payload = {
                                "escaped_text": escaped_text,
                                "raw_text": raw_text,
                                "affiliate_url": affiliate_url,
                                "photo_path": None
                            }
                            
                            await self.deal_queue.put(deal_payload)
                            logger.info(f"RSS Worker: Deal added to queue. Queue size: {self.deal_queue.qsize()}")
                            
                else:
                    logger.error(f"RSS Worker: Failed to fetch DesiDime HTML. Status Code: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"RSS Worker Exception: {e}")
                
            # Wait 5 minutes before fetching again
            await asyncio.sleep(300)

    # =====================================================================
    # LIFECYCLE MANAGEMENT
    # =====================================================================
    async def start(self):
        """Starts the Telegram listener and/or RSS worker."""
        if self.is_running:
            logger.warning("Service is already running.")
            return True

        enable_tg_api = self.config.get("enable_tg_api", True)
        enable_source_channels = self.config.get("enable_source_channels", True)
        enable_whitelist_channels = self.config.get("enable_whitelist_channels", True)
        enable_desidime_rss = self.config.get("enable_desidime_rss", False)

        # Mutual Exclusion Check
        if enable_source_channels and enable_desidime_rss:
            logger.warning("MUTUAL EXCLUSION: Both Source Channels and DesiDime RSS are enabled. Disabling RSS feed to prevent duplicate posting loops.")
            enable_desidime_rss = False
            # We don't modify self.config here permanently, just the local execution flag.

        target_chats = []
        if enable_source_channels:
            target_chats.extend(self.config.get("target_channels", []))
        if enable_whitelist_channels:
            target_chats.extend(self.config.get("whitelist_channels", []))
            
        target_chats = list(set(target_chats))

        if enable_tg_api:
            api_id = self.config.get("api_id")
            api_hash = self.config.get("api_hash")
            
            if not api_id or not api_hash:
                raise ValueError("Telegram API_ID and API_HASH are required to start Telethon.")

            if self.client is None:
                logger.info("Starting Telethon Client session...")
                session_path = os.path.join(BASE_DIR, 'deal_forwarder_session')
                self.client = TelegramClient(session_path, int(api_id), api_hash)
            
            if not self.client.is_connected():
                await self.client.connect()
            
            if not await self.client.is_user_authorized():
                logger.warning("Session is not authorized. Web or Console authentication is required.")
                self.is_running = False
                return False
     
            # Register event handler
            if target_chats:
                if not self._handler_ref:
                    @self.client.on(events.NewMessage(chats=target_chats))
                    async def handler(event):
                        await self.process_message(event)
                    self._handler_ref = handler
                    logger.info(f"Registered live listener for chats: {target_chats}")
            else:
                logger.warning("No target channels configured or enabled. Telegram listener is active but idle.")

            # Register Sandbox "me" handler for testing
            if not self._me_handler_ref:
                @self.client.on(events.NewMessage(chats=["me"]))
                async def me_handler(event):
                    await self.process_test_message(event)
                self._me_handler_ref = me_handler
                logger.info("Registered sandbox listener for 'Saved Messages' (me)")
        else:
            logger.info("Telegram API is DISABLED. Skipping user session connection and live channel listener.")
 
        self.stats["start_time"] = datetime.datetime.now()
        self.is_running = True

        # Start WhatsApp Service if enabled
        if self.config.get("enable_whatsapp_source"):
            whatsapp_service_instance.set_message_handler(self.handle_whatsapp_message)
            asyncio.create_task(whatsapp_service_instance.start())

        # Start background queue worker
        if not self.queue_worker_task:
            self.queue_worker_task = asyncio.create_task(self.deal_queue_worker())

        # Start background RSS worker if enabled
        if enable_desidime_rss:
            if not self.rss_worker_task:
                self.rss_worker_task = asyncio.create_task(self.desidime_rss_worker_loop())
                logger.info("Started DesiDime RSS Worker.")

        logger.info("Deal Forwarding Service is fully operational!")
        return True
 
    async def stop(self):
        """Gracefully disconnects and stops the listener service."""
        if not self.is_running and not self.client:
            return
            
        logger.info("Stopping Deal Forwarding Service...")
        
        # Cancel background queue worker
        if self.queue_worker_task:
            self.queue_worker_task.cancel()
            self.queue_worker_task = None
            
        # Cancel RSS worker
        if self.rss_worker_task:
            self.rss_worker_task.cancel()
            self.rss_worker_task = None

        if self.client:
            if self._handler_ref:
                try:
                    self.client.remove_event_handler(self._handler_ref)
                except Exception:
                    pass
                self._handler_ref = None
                
            if self._me_handler_ref:
                try:
                    self.client.remove_event_handler(self._me_handler_ref)
                except Exception:
                    pass
                self._me_handler_ref = None
                
            try:
                await self.client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting client: {e}")
            self.client = None
            
        self.is_running = False
        
        # Stop WhatsApp Service
        await whatsapp_service_instance.stop()
        
        logger.info("Forwarding Service stopped successfully.")

    async def post_approved_deal_to_pinterest(self, deal_id: int, custom_affiliate_url: str = None) -> tuple:
        """
        Publishes an approved deal to Pinterest using Pinterest API v5.
        Verifies the daily posting limit, updates any edited affiliate link,
        prepends the affiliate disclosure, and encodes/uploads the image.
        Returns (success_status, detail_message).
        """
        access_token = self.config.get("pinterest_access_token")
        board_id = self.config.get("pinterest_board_id")
        
        if not access_token or not board_id:
            logger.error("Pinterest Approved Pin Failed: Pinterest Access Token or Board ID is missing.")
            return False, "Pinterest Access Token or Board ID is missing."

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 1. Fetch deal row
        cursor.execute("SELECT * FROM pinterest_deals WHERE id = ?", (deal_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, "Deal not found in database."

        # 2. Check Daily Limit (Only posted pins today in local calendar day)
        today_start = datetime.datetime.now().strftime('%Y-%m-%d 00:00:00')
        cursor.execute("SELECT COUNT(id) FROM pinterest_deals WHERE status = 'posted' AND posted_at >= ?", (today_start,))
        posted_today_count = cursor.fetchone()[0]
        
        daily_limit = self.config.get("pinterest_daily_limit", 5)
        if posted_today_count >= daily_limit:
            conn.close()
            logger.warning(f"Pinterest: Daily posting limit reached ({posted_today_count}/{daily_limit}). Keeping deal in Pending.")
            return False, "limit_reached"

        # 3. Update affiliate link in database if edited by the user
        affiliate_url = row["affiliate_url"]
        if custom_affiliate_url and custom_affiliate_url.strip():
            affiliate_url = custom_affiliate_url.strip()
            cursor.execute("UPDATE pinterest_deals SET affiliate_url = ? WHERE id = ?", (affiliate_url, deal_id))
            conn.commit()

        # 4. Check image file
        image_path = row["image_path"]
        if not image_path or not os.path.exists(image_path):
            conn.close()
            logger.error(f"PinterestApprovedPinError: Persistent image file does not exist at {image_path}")
            return False, "Image file not found on disk."

        # 5. Base64 encode the image
        try:
            def _encode_image():
                with open(image_path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            base64_data = await asyncio.to_thread(_encode_image)
        except Exception as e:
            conn.close()
            return False, f"Failed to encode image: {str(e)}"

        content_type = "image/jpeg"
        if str(image_path).lower().endswith(".png"):
            content_type = "image/png"
        elif str(image_path).lower().endswith(".gif"):
            content_type = "image/gif"

        # 6. Format Pin properties (title & description)
        title = row["product_title"] or "Amazing Affiliate Deal!"
        # Prepend the required affiliate disclosure at the beginning of the Pin description
        disclosure = "Affiliate link: इस लिंक से खरीदने पर मुझे commission मिल सकता है, आपको extra charge नहीं लगेगा.\n\n"
        cleaned_desc = row["cleaned_description"] or ""
        description = (disclosure + cleaned_desc)[:500]

        # 7. Request payload
        payload = {
            "board_id": board_id.strip(),
            "title": title[:100],
            "description": description,
            "media_source": {
                "source_type": "image_base64",
                "content_type": content_type,
                "data": base64_data
            }
        }
        
        if affiliate_url:
            payload["link"] = affiliate_url

        headers = {
            "Authorization": f"Bearer {access_token.strip()}",
            "Content-Type": "application/json"
        }

        api_url = "https://api.pinterest.com/v5/pins"
        
        try:
            logger.info(f"Approved Pin Trigger: Uploading Pin for deal {deal_id} to board {board_id}...")
            response = await async_post(api_url, headers=headers, json=payload, timeout=25)
            
            if response.status_code in [200, 201]:
                # Pin creation successful
                now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                # Comply with Pinterest API Data Storage Policy Safety:
                # Do NOT permanently store API-returned Pinterest data (such as pin ID) in our database.
                cursor.execute("""
                    UPDATE pinterest_deals 
                    SET status = 'posted', posted_at = ?, failure_reason = NULL 
                    WHERE id = ?
                """, (now_str, deal_id))
                conn.commit()
                
                self.stats["pinterest_success"] += 1
                logger.info("Pinterest approved and posted successfully.")
                conn.close()
                return True, "posted_successfully"
            else:
                # Pin creation failed
                err_text = response.text
                try:
                    err_json = response.json()
                    err_message = err_json.get("message", err_text)
                except:
                    err_message = err_text
                    
                logger.error(f"Pinterest API Error: Status {response.status_code} - {err_message}")
                
                cursor.execute("""
                    UPDATE pinterest_deals 
                    SET status = 'failed', failure_reason = ? 
                    WHERE id = ?
                """, (err_message, deal_id))
                conn.commit()
                conn.close()
                return False, err_message
        except Exception as e:
            err_message = str(e)
            logger.error(f"Pinterest post exception: {err_message}")
            cursor.execute("""
                UPDATE pinterest_deals 
                SET status = 'failed', failure_reason = ? 
                WHERE id = ?
            """, (err_message, deal_id))
            conn.commit()
            conn.close()
            return False, err_message

 
# =====================================================================
# STANDALONE EXECUTION ENTRY
# =====================================================================
async def run_standalone():
    load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"), override=True)
    
    # Check variables
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        logger.critical("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH in .env file.")
        return
 
    service = DealForwarderService()
    
    # Command line interactive setup is handled by Telethon's built-in start()
    logger.info("Launching standalone interactive session...")
    session_path = os.path.join(BASE_DIR, 'deal_forwarder_session')
    service.client = TelegramClient(session_path, int(api_id), api_hash)
    
    # Standalone interactive start
    await service.client.start()
    
    # Register events
    target_chats = list(set(service.config.get("target_channels", []) + service.config.get("whitelist_channels", [])))
    if target_chats:
        @service.client.on(events.NewMessage(chats=target_chats))
        async def handler(event):
            await service.process_message(event)
        logger.info(f"Active standalone listener running for channels: {target_chats}")
    else:
        logger.warning("No TARGET_CHANNELS defined. Listening is disabled.")

    service.is_running = True
    # Start background queue worker
    service.queue_worker_task = asyncio.create_task(service.deal_queue_worker())
    
    logger.info("Waiting for deals... Press Ctrl+C to terminate.")
    try:
        await service.client.run_until_disconnected()
    finally:
        if service.queue_worker_task:
            service.queue_worker_task.cancel()

if __name__ == '__main__':
    try:
        asyncio.run(run_standalone())
    except KeyboardInterrupt:
        logger.info("Terminated cleanly by operator.")
    except Exception as e:
        logger.critical(f"Standalone crash: {e}", exc_info=True)
