# app.py - Entry point untuk webhook (FIXED VERSION)
import os
import logging
import asyncio
from flask import Flask, request
from telegram import Update
from bot import TelegramBot

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8284891962:AAHbRY1FB23MIh4TZ8qeSh6CXQ35XKH_XjQ")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1bs_6iDuxgTX4QF_FTra3YDYVsRFatwRXLQ0tiQfNZyI")

if not BOT_TOKEN or not SPREADSHEET_ID:
    logger.error("❌ BOT_TOKEN dan SPREADSHEET_ID harus di-set!")
    exit(1)

# Create Flask app
app = Flask(__name__)

# Initialize bot
try:
    bot = TelegramBot(BOT_TOKEN, SPREADSHEET_ID)
    logger.info("✅ Bot initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize bot: {e}")
    exit(1)

@app.route('/')
def index():
    return 'Telegram Bot is running with webhook! 🤖'

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        json_data = request.get_json(force=True)
        logger.info(f"📨 Received update: {json_data}")
        
        update = Update.de_json(json_data, bot.application.bot)
        
        # Process update asynchronously using asyncio
        asyncio.create_task(bot.process_update(update))
        
        return 'ok'
    except Exception as e:
        logger.error(f"❌ Error processing update: {e}")
        return 'error', 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
