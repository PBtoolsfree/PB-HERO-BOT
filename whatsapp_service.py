import os
import asyncio
import base64
import logging
from playwright.async_api import async_playwright
import time
import re

logger = logging.getLogger("WhatsAppService")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - [%(levelname)s] - %(name)s - %(message)s'))
    logger.addHandler(ch)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WHATSAPP_SESSION_DIR = os.path.join(BASE_DIR, "whatsapp_session")

class WhatsAppService:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.is_running = False
        self.logged_in = False
        self.qr_code_b64 = None
        self.main_task = None
        self.seen_messages = set() # To prevent duplicate scraping
        self.on_message_callback = None # Function to route deals to DealForwarderService
        self.deal_queue = asyncio.Queue()
        self._listener_task = None
        
    def set_message_handler(self, handler):
        """Sets the callback function to receive incoming WhatsApp messages."""
        self.on_message_callback = handler

    async def start(self):
        if self.is_running:
            return
        logger.info("Starting WhatsApp Web Service...")
        self.playwright = await async_playwright().start()
        # Use a persistent context to keep login session
        os.makedirs(WHATSAPP_SESSION_DIR, exist_ok=True)
        self.browser = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=WHATSAPP_SESSION_DIR,
            headless=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        self.page = await self.browser.new_page()
        self.is_running = True
        
        # Start the background task to manage connection and listen
        self._listener_task = asyncio.create_task(self._main_loop())
        logger.info("WhatsApp Web Service started.")

    async def stop(self):
        self.is_running = False
        if self._listener_task:
            self._listener_task.cancel()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("WhatsApp Web Service stopped.")

    async def get_qr_code(self) -> str:
        """Returns the base64 encoded QR code if available."""
        return self.qr_code_b64

    def is_logged_in(self) -> bool:
        return self.logged_in

    async def _main_loop(self):
        """Main background loop to manage session and scrape/post."""
        try:
            await self.page.goto("https://web.whatsapp.com", timeout=60000)
        except Exception as e:
            logger.error(f"Failed to load WhatsApp Web: {e}")
            return

        while self.is_running:
            try:
                # DEBUG: Capture screenshot to see what playwright sees
                try:
                    debug_path = os.path.join(BASE_DIR, "pinterest_media", "whatsapp_debug.png")
                    os.makedirs(os.path.dirname(debug_path), exist_ok=True)
                    await self.page.screenshot(path=debug_path)
                except Exception as e:
                    logger.error(f"Failed to capture debug screenshot: {e}")

                # First, check if we are successfully logged in by looking for the main chats pane
                chat_pane = await self.page.query_selector("#pane-side")
                
                if chat_pane:
                    if not self.logged_in:
                        logger.info("Successfully logged into WhatsApp Web!")
                        self.logged_in = True
                        self.qr_code_b64 = None
                    
                    # --- WHATSAPP DOM SCRAPER LOGIC ---
                    import os
                    from dotenv import load_dotenv
                    load_dotenv(override=True)
                    
                    # Fetch configured channels
                    wa_source_str = os.getenv("WHATSAPP_SOURCE_CHANNELS", "")
                    sources = [s.strip() for s in wa_source_str.split(",") if s.strip()]
                    
                    # Add Sandbox "Message yourself"
                    if "Message yourself" not in sources:
                        sources.append("Message yourself")
                        
                    for target_chat in sources:
                        try:
                            # 1. Search for chat
                            search_box = await self.page.query_selector("div[contenteditable='true'][data-tab='3']")
                            if not search_box:
                                continue
                                
                            await search_box.fill(target_chat)
                            await self.page.keyboard.press("Enter")
                            await asyncio.sleep(2) # Wait for chat to load
                            
                            # 2. Extract recent messages
                            # `.message-in` for incoming, `.message-out` for outgoing (e.g. from "me")
                            msg_elements = await self.page.query_selector_all(".message-in, .message-out")
                            if not msg_elements:
                                continue
                                
                            # Check the last 3 messages
                            for msg_el in msg_elements[-3:]:
                                # Extract text
                                text_el = await msg_el.query_selector("span.selectable-text")
                                if not text_el:
                                    continue
                                    
                                msg_text = await text_el.inner_text()
                                if not msg_text or len(msg_text) < 5:
                                    continue
                                    
                                # Create a unique fingerprint
                                msg_hash = hash(msg_text + target_chat)
                                if msg_hash in self.seen_messages:
                                    continue
                                    
                                self.seen_messages.add(msg_hash)
                                
                                # Send to DealForwarderService if callback is set
                                if self.on_message_callback:
                                    # Identify if it's the sandbox chat
                                    is_sandbox = (target_chat == "Message yourself")
                                    await self.on_message_callback(msg_text, is_sandbox)
                                    
                        except Exception as e:
                            logger.error(f"Error scraping WhatsApp channel {target_chat}: {e}")
                            
                    await asyncio.sleep(15) # Polling delay to avoid spamming
                    continue

                # If we reach here, we are not fully logged in yet
                self.logged_in = False
                
                # Check if QR code canvas is present
                qr_canvas = await self.page.query_selector("canvas")
                if qr_canvas:
                    # Extract QR code data URL using page evaluation
                    self.qr_code_b64 = await self.page.evaluate('''() => {
                        const canvas = document.querySelector("canvas");
                        if (canvas) {
                            const dataUrl = canvas.toDataURL('image/png');
                            return dataUrl.includes(',') ? dataUrl.split(',')[1] : null;
                        }
                        return null;
                    }''')
                else:
                    self.qr_code_b64 = None
                
            except Exception as e:
                logger.error(f"Error in WhatsApp main loop: {e}")
            
            await asyncio.sleep(5)

    async def post_to_channel(self, channel_name: str, text: str, image_path: str = None) -> bool:
        """Posts a message to a specific WhatsApp channel/chat."""
        if not self.logged_in or not self.page:
            logger.error("Cannot post: WhatsApp is not logged in.")
            return False
        
        try:
            # 1. Search for the channel
            search_box = await self.page.wait_for_selector("div[contenteditable='true'][data-tab='3']", timeout=10000)
            await search_box.fill(channel_name)
            await self.page.keyboard.press("Enter")
            await asyncio.sleep(2) # Wait for chat to load
            
            # 2. Type the message
            message_box = await self.page.wait_for_selector("div[contenteditable='true'][data-tab='10']", timeout=5000)
            
            if image_path and os.path.exists(image_path):
                # Attach image
                attach_btn = await self.page.query_selector("div[title='Attach']")
                if attach_btn:
                    await attach_btn.click()
                    await asyncio.sleep(1)
                    
                    # File input
                    file_input = await self.page.query_selector("input[accept='image/*,video/mp4,video/3gpp,video/quicktime']")
                    if file_input:
                        await file_input.set_input_files(image_path)
                        await asyncio.sleep(2) # Wait for image preview
                        
                        # In preview, there's another text box for caption
                        caption_box = await self.page.query_selector("div[contenteditable='true'][data-tab='10']")
                        if caption_box:
                            # Use clipboard or keyboard to type (keyboard is safer for newlines, or evaluate)
                            await self.page.evaluate(f'''(text) => {{
                                const el = document.querySelector("div[contenteditable='true'][data-tab='10']");
                                el.focus();
                                document.execCommand('insertText', false, text);
                            }}''', text)
                            
                        # Click send
                        send_btn = await self.page.query_selector("span[data-icon='send']")
                        if send_btn:
                            await send_btn.click()
                            logger.info(f"Successfully posted to WhatsApp channel {channel_name} with image.")
                            return True
            
            # If no image or image attach failed, send text only
            # Use javascript to insert text to handle newlines correctly
            await self.page.evaluate(f'''(text) => {{
                const el = document.querySelector("div[contenteditable='true'][data-tab='10']");
                el.focus();
                document.execCommand('insertText', false, text);
            }}''', text)
            
            await self.page.keyboard.press("Enter")
            logger.info(f"Successfully posted text to WhatsApp channel {channel_name}.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to post to WhatsApp channel {channel_name}: {e}")
            return False

# Global instance for dashboard and forwarder to use
whatsapp_service_instance = WhatsAppService()
