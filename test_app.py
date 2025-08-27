# test_app.py - Simple test version
import os
import logging
import asyncio
import threading
from flask import Flask, request, jsonify
from telegram import Update
from bot import TelegramBot

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
SHEET_NAME = os.environ.get("SHEET_NAME", "Sheet1")  # Default sheet name

logger.info(f"📊 Test Configuration:")
logger.info(f"  - Spreadsheet ID: {SPREADSHEET_ID}")
logger.info(f"  - Sheet Name: {SHEET_NAME}")
logger.info(f"  - Bot Token: {'SET' if BOT_TOKEN else 'NOT_SET'}")")

# Create Flask app
app = Flask(__name__)

# Global variables for bot and event loop
bot = None
loop = None
loop_thread = None

def create_event_loop():
    """Create and run event loop in separate thread"""
    global loop
    
    def run_loop():
        global loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_forever()
    
    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    
    # Wait for loop to be ready
    import time
    time.sleep(0.2)
    
    return thread

def initialize_bot():
    """Initialize bot with error handling"""
    global bot
    
    if not BOT_TOKEN or not SPREADSHEET_ID:
        logger.error("❌ BOT_TOKEN dan SPREADSHEET_ID harus di-set!")
        return False
    
    try:
        bot = TelegramBot(BOT_TOKEN, SPREADSHEET_ID)
        logger.info("✅ Bot initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to initialize bot: {e}")
        return False

@app.route('/')
def index():
    return {
        'status': 'running',
        'bot_initialized': bot is not None,
        'loop_running': loop is not None and not loop.is_closed()
    }

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'bot': 'initialized' if bot else 'not_initialized',
        'loop': 'running' if loop and not loop.is_closed() else 'not_running'
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Check if bot is initialized
        if not bot:
            logger.error("❌ Bot not initialized")
            return jsonify({'error': 'Bot not initialized'}), 500
        
        # Check if loop is running
        if not loop or loop.is_closed():
            logger.error("❌ Event loop not running")
            return jsonify({'error': 'Event loop not running'}), 500
        
        # Get update data
        json_data = request.get_json(force=True)
        logger.info(f"📨 Received webhook data")
        
        # Create Update object
        update = Update.de_json(json_data, bot.application.bot)
        
        # Schedule processing in event loop
        future = asyncio.run_coroutine_threadsafe(
            bot.process_update(update), 
            loop
        )
        
        logger.info("✅ Update scheduled for processing")
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        logger.error(f"❌ Error in webhook: {e}")
        return jsonify({'error': str(e)}), 500

# Initialize when app starts
logger.info("🚀 Starting application...")

# Create event loop first
logger.info("📡 Creating event loop...")
loop_thread = create_event_loop()

# Initialize bot
logger.info("🤖 Initializing bot...")
if not initialize_bot():
    logger.error("❌ Failed to initialize bot, exiting...")
    exit(1)

logger.info("✅ Application started successfully")

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🌐 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
