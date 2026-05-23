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
        parsed = urllib.parse.urlparse(url.lower())
        domain = parsed.netloc or parsed.path
        
        shortened_domains = [
            "fktr.cc",
            "amzn.to",
            "amzn.in",
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
        logger.info(f"Shortened URL detected: {url}. Expanding redirect...")
        try:
            # We use allow_redirects=True to follow location headers
            response = requests.head(url, headers=headers, allow_redirects=True, timeout=8)
            logger.info(f"Successfully expanded URL: {url} -> {response.url}")
            return response.url
        except Exception as e:
            logger.warning(f"Failed to expand URL via HEAD: {e}. Trying GET...")
            try:
                response = requests.get(url, headers=headers, allow_redirects=True, timeout=8)
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
            "failures": 0,
            "start_time": None
        }
        self.client = None
        self.is_running = False
        self._handler_ref = None
        self.deal_queue = asyncio.Queue()
        self.queue_worker_task = None
        
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
                "DELAY_INTERVAL": os.getenv("DELAY_INTERVAL", "900")
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
            "delay_interval_raw": config_dict.get("DELAY_INTERVAL", "900")
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
                                if converted_url:
                                    logger.info("Successfully converted link using EarnKaro (Affiliaters IN) API!")
                                    cleaned_url = clean_affiliate_url(converted_url.strip(), api_key)
                                    return cleaned_url
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
            "content": "@everyone",
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
            "content": "@everyone",
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

    # =====================================================================
    # MESSAGE LISTENER HANDLER
    # =====================================================================
    async def process_message(self, event: events.NewMessage.Event):
        """Processes a live incoming message, extracts links, and forwards."""
        text = event.message.message
        if not text and not event.message.photo:
            return

        # Find all raw URLs in the text
        raw_urls = URL_REGEX.findall(text or "")
        
        self.stats["processed"] += 1
        
        # Apply the smart product link filter
        product_urls = [url for url in raw_urls if is_product_url(url)]
        
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

    # =====================================================================
    # LIFECYCLE MANAGEMENT
    # =====================================================================
    async def start(self):
        """Starts the Telethon user client and registers listeners."""
        if self.is_running:
            logger.warning("Service is already running.")
            return True

        api_id = self.config.get("api_id")
        api_hash = self.config.get("api_hash")
        target_chats = list(set(self.config.get("target_channels", []) + self.config.get("whitelist_channels", [])))

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
            logger.warning("No target channels configured. Listening is disabled.")
 
        self.stats["start_time"] = datetime.datetime.now()
        self.is_running = True

        # Start background queue worker
        if not self.queue_worker_task:
            self.queue_worker_task = asyncio.create_task(self.deal_queue_worker())

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

        if self.client:
            if self._handler_ref:
                try:
                    self.client.remove_event_handler(self._handler_ref)
                except Exception:
                    pass
                self._handler_ref = None
            try:
                await self.client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting client: {e}")
            self.client = None
            
        self.is_running = False
        logger.info("Forwarding Service stopped successfully.")
 
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
