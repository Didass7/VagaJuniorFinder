import os
import requests
import logging
from typing import List

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TelegramNotifier")

TELEGRAM_MAX_LENGTH = 4000  # Telegram message char limit is 4096

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.bot_token or not self.chat_id:
            logger.warning("⚠️ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set. Skipping Telegram notification.")
            return False

        url = f"{self.api_url}/sendMessage"
        
        # Split text into chunks if it exceeds Telegram's limit
        chunks = self._split_text(text, TELEGRAM_MAX_LENGTH)
        
        success = True
        for i, chunk in enumerate(chunks):
            payload = {
                "chat_id": self.chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            if not self._post_with_retry(url, json=payload):
                success = False

            # Small delay between chunks to avoid rate limits
            if i < len(chunks) - 1:
                import time
                time.sleep(1)

        if success:
            logger.info("✅ Telegram notification successfully sent!")
        return success

    def send_document(self, filepath: str, caption: str = "") -> bool:
        if not self.bot_token or not self.chat_id or not os.path.exists(filepath):
            return False

        url = f"{self.api_url}/sendDocument"
        try:
            with open(filepath, "rb") as f:
                files = {"document": f}
                data = {"chat_id": self.chat_id, "caption": caption[:1024]}
                if self._post_with_retry(url, data=data, files=files):
                    logger.info("✅ Telegram report file attachment sent!")
                    return True
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram document: {e}")
        return False

    def _post_with_retry(self, url: str, max_retries: int = 3, **kwargs) -> bool:
        """POST with exponential backoff: 30s → 60s → 90s timeout, 5s → 15s → 30s wait."""
        import time

        for attempt in range(1, max_retries + 1):
            timeout = 30 * attempt  # 30s, 60s, 90s
            try:
                resp = requests.post(url, timeout=timeout, **kwargs)
                if resp.status_code == 200:
                    return True
                elif resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 10))
                    logger.warning(f"⏳ Telegram rate-limited. Waiting {retry_after}s (attempt {attempt}/{max_retries})")
                    time.sleep(retry_after)
                else:
                    logger.error(f"❌ Telegram API Error ({resp.status_code}): {resp.text}")
                    return False
            except requests.exceptions.Timeout:
                wait = 5 * (2 ** (attempt - 1))  # 5s, 10s, 20s
                logger.warning(f"⏳ Telegram timeout ({timeout}s). Retrying in {wait}s (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    time.sleep(wait)
            except requests.exceptions.ConnectionError as e:
                wait = 10 * attempt  # 10s, 20s, 30s
                logger.warning(f"⏳ Connection error: {e}. Retrying in {wait}s (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    time.sleep(wait)
            except Exception as e:
                logger.error(f"❌ Unexpected Telegram error: {e}")
                return False

        logger.error(f"❌ Telegram request failed after {max_retries} attempts.")
        return False

    def _split_text(self, text: str, max_len: int) -> List[str]:
        if len(text) <= max_len:
            return [text]

        chunks = []
        lines = text.split("\n")
        current_chunk = []
        current_len = 0

        for line in lines:
            if current_len + len(line) + 1 > max_len:
                chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_len = len(line) + 1
            else:
                current_chunk.append(line)
                current_len += len(line) + 1

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks
