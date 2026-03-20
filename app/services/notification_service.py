import aiohttp
from app.config import settings
from app.logger import export_logger as logger

class NotificationService:
    def __init__(self):
        self.tg_bot_token = settings.TELEGRAM_BOT_TOKEN
        self.tg_chat_id = settings.TELEGRAM_CHAT_ID
        self.pb_api_key = settings.PUSHBULLET_API_KEY
        
        self.tg_enabled = bool(self.tg_bot_token and self.tg_chat_id)
        self.pb_enabled = bool(self.pb_api_key)

    async def send_telegram(self, message: str):
        if not self.tg_enabled:
            return

        url = f"https://api.telegram.org/bot{self.tg_bot_token}/sendMessage"
        payload = {
            "chat_id": self.tg_chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        text = await response.text()
                        logger.error(f"Telegram failed (disabling): {text}")
                        self.tg_enabled = False
        except Exception as e:
            logger.error(f"Telegram error (disabling): {e}")
            self.tg_enabled = False

    async def send_pushbullet(self, title: str, body: str):
        if not self.pb_enabled:
            return

        url = "https://api.pushbullet.com/v2/pushes"
        headers = {"Access-Token": self.pb_api_key}
        payload = {"type": "note", "title": title, "body": body}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        text = await response.text()
                        logger.error(f"Pushbullet failed (disabling): {text}")
                        self.pb_enabled = False
        except Exception as e:
            logger.error(f"Pushbullet error (disabling): {e}")
            self.pb_enabled = False

    async def notify_trade(self, action: str, symbol: str, side: str, price: float, quantity: float, reason: str = ""):
        emoji = "🚀" if action == "OPEN" else "🏁"
        title = f"{emoji} {action}: {symbol} {side}"
        body = (
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"Price: {price}\n"
            f"Qty: {quantity}\n"
        )
        if reason:
            body += f"Reason: {reason}"
            
        # Send both
        await self.send_telegram(f"*{title}*\n{body}")
        await self.send_pushbullet(title, body)
