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
        self.page = None
        self.is_running = False
        self.qr_code_b64 = None
        self.logged_in = False
        self.deal_queue = asyncio.Queue()
        self._listener_task = None

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
                    await asyncio.sleep(2)
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
