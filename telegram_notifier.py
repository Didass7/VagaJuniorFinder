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
        for chunk in chunks:
            payload = {
                "chat_id": self.chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            try:
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code != 200:
                    logger.error(f"❌ Telegram API Error ({resp.status_code}): {resp.text}")
                    success = False
            except Exception as e:
                logger.error(f"❌ Failed to send Telegram message: {e}")
                success = False

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
                resp = requests.post(url, data=data, files=files, timeout=15)
                if resp.status_code == 200:
                    logger.info("✅ Telegram report file attachment sent!")
                    return True
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram document: {e}")
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
