# app.py - Entry point untuk webhook (FIXED VERSION)
import os
import logging
import asyncio
import threading
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

# Global event loop for async operations
loop = None
loop_thread = None

def run_event_loop():
    """Run event loop in separate thread"""
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_forever()

def ensure_event_loop():
    """Ensure event loop is running"""
    global loop, loop_thread
    if loop is None or loop_thread is None or not loop_thread.is_alive():
        loop_thread = threading.Thread(target=run_event_loop, daemon=True)
        loop_thread.start()
        # Wait a bit for loop to be ready
        import time
        time.sleep(0.1)

def run_async_task(coro):
    """Run async task in the event loop"""
    ensure_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        # Don't wait for result to avoid blocking Flask
        return future
    except Exception as e:
        logger.error(f"❌ Error running async task: {e}")
        return None

@app.route('/')
def index():
    return 'Telegram Bot is running with webhook! 🤖'

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        json_data = request.get_json(force=True)
        logger.info(f"📨 Received update: {json_data}")
        
        update = Update.de_json(json_data, bot.application.bot)
        
        # Process update asynchronously without blocking
        future = run_async_task(bot.process_update(update))
        
        if future is not None:
            logger.info("✅ Update queued for processing")
            return 'ok'
        else:
            logger.error("❌ Failed to queue update")
            return 'error', 500
            
    except Exception as e:
        logger.error(f"❌ Error in webhook handler: {e}")
        return 'error', 500

# Initialize event loop when app starts
ensure_event_loop()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
