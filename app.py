# app.py - Simple Stable Version with Ownership Transfer
import os
import logging
import asyncio
import threading
import time
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
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8284891962:AAHbRY1FB23MIh4TZ8qeSh6CXQ35XKH_XjQ")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1bs_6iDuxgTX4QF_FTra3YDYVsRFatwRXLQ0tiQfNZyI")

if not BOT_TOKEN or not SPREADSHEET_ID:
    logger.error("❌ BOT_TOKEN dan SPREADSHEET_ID harus di-set!")
    exit(1)

# Create Flask app
app = Flask(__name__)

# Global variables
bot = None
loop = None
loop_thread = None
bot_ready = False

def create_and_run_loop():
    """Create and run event loop in dedicated thread"""
    global loop
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info("🔄 Event loop created and running")
        loop.run_forever()
    except Exception as e:
        logger.error(f"❌ Error in event loop: {e}")

def start_event_loop():
    """Start event loop in background thread"""
    global loop_thread
    loop_thread = threading.Thread(target=create_and_run_loop, daemon=True)
    loop_thread.start()
    
    # Wait for loop to be ready
    time.sleep(0.5)
    return loop is not None

async def initialize_bot_async():
    """Initialize bot asynchronously"""
    global bot, bot_ready
    try:
        logger.info("🤖 Creating TelegramBot instance...")
        bot = TelegramBot(BOT_TOKEN, SPREADSHEET_ID)
        
        logger.info("🔧 Initializing Telegram Application...")
        success = await bot.initialize_application()
        
        if success:
            bot_ready = True
            logger.info("✅ Bot fully initialized and ready")
            return True
        else:
            logger.error("❌ Failed to initialize bot application")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error initializing bot: {e}")
        return False

def initialize_bot():
    """Initialize bot synchronously"""
    if not loop:
        logger.error("❌ Event loop not available")
        return False
    
    try:
        future = asyncio.run_coroutine_threadsafe(initialize_bot_async(), loop)
        return future.result(timeout=60)  # Wait up to 60 seconds
    except Exception as e:
        logger.error(f"❌ Error initializing bot: {e}")
        return False

def test_ownership_transfer():
    """Test ownership transfer capability synchronously"""
    if not bot or not bot.google_service:
        logger.warning("⚠️ Bot or Google service not available for ownership test")
        return False
    
    try:
        logger.info("🧪 Testing ownership transfer capability...")
        test_result = bot.google_service.test_ownership_transfer()
        
        if test_result:
            logger.info("✅ Ownership transfer test PASSED - files will use personal Gmail quota!")
        else:
            logger.warning("⚠️ Ownership transfer test FAILED - files will use service account quota")
            logger.warning("⚠️ This may cause upload failures due to quota limits")
        
        return test_result
        
    except Exception as e:
        logger.error(f"❌ Error testing ownership transfer: {e}")
        return False

@app.route('/')
def index():
    # Get quota info if available
    quota_info = {}
    if bot and bot.google_service:
        try:
            quota_info = bot.google_service.get_quota_info() or {}
        except:
            pass
    
    return jsonify({
        'status': 'running',
        'bot_ready': bot_ready,
        'loop_running': loop is not None and not loop.is_closed(),
        'message': 'Telegram Bot Webhook Server',
        'quota_info': quota_info
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy' if bot_ready else 'initializing',
        'bot': 'ready' if bot_ready else 'not_ready',
        'loop': 'running' if loop and not loop.is_closed() else 'not_running'
    })

@app.route('/test-ownership')
def test_ownership_endpoint():
    """Test endpoint for ownership transfer"""
    try:
        if not bot or not bot.google_service:
            return jsonify({
                'status': 'error',
                'message': 'Bot or Google service not available'
            }), 503
        
        test_result = test_ownership_transfer()
        
        # Get usage info
        usage_info = bot.google_service.get_service_account_usage()
        
        return jsonify({
            'status': 'success' if test_result else 'failed',
            'ownership_transfer_working': test_result,
            'service_account_usage': usage_info,
            'message': 'Ownership transfer test completed'
        })
        
    except Exception as e:
        logger.error(f"❌ Error in test ownership endpoint: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/cleanup')
def cleanup_endpoint():
    """Cleanup endpoint for service account files"""
    try:
        if not bot or not bot.google_service:
            return jsonify({
                'status': 'error',
                'message': 'Bot or Google service not available'
            }), 503
        
        cleanup_result = bot.google_service.cleanup_service_account_files()
        
        return jsonify({
            'status': 'success' if cleanup_result else 'failed',
            'message': 'Cleanup completed'
        })
        
    except Exception as e:
        logger.error(f"❌ Error in cleanup endpoint: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Check if bot is ready
        if not bot_ready or not bot:
            logger.warning("⚠️ Bot not ready, ignoring webhook")
            return jsonify({'status': 'bot_not_ready'}), 503
        
        # Check loop
        if not loop or loop.is_closed():
            logger.error("❌ Event loop not available")
            return jsonify({'status': 'loop_error'}), 503
        
        # Get and validate JSON data
        json_data = request.get_json(force=True)
        if not json_data:
            logger.error("❌ Empty JSON data received")
            return jsonify({'status': 'invalid_data'}), 400
        
        logger.info(f"📨 Processing webhook update")
        
        try:
            # Create Update object
            update = Update.de_json(json_data, bot.application.bot)
            
            # Schedule processing (don't wait for result)
            future = asyncio.run_coroutine_threadsafe(
                bot.process_update(update), 
                loop
            )
            
            logger.info("✅ Update queued successfully")
            return jsonify({'status': 'ok'})
            
        except Exception as parse_error:
            logger.error(f"❌ Error parsing update: {parse_error}")
            return jsonify({'status': 'parse_error'}), 400
        
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Application startup
def startup():
    global bot_ready
    
    logger.info("🚀 Starting Telegram Bot Webhook Server...")
    
    # Start event loop
    logger.info("⚡ Starting event loop...")
    if not start_event_loop():
        logger.error("❌ Failed to start event loop")
        exit(1)
    
    # Initialize bot
    logger.info("🤖 Initializing bot...")
    if not initialize_bot():
        logger.error("❌ Failed to initialize bot")
        exit(1)
    
    # Test ownership transfer capability
    logger.info("🧪 Testing ownership transfer capability...")
    ownership_test_passed = test_ownership_transfer()
    
    if ownership_test_passed:
        logger.info("✅ OWNERSHIP TRANSFER WORKING - Files will use your personal Gmail quota (15GB)!")
    else:
        logger.warning("⚠️ OWNERSHIP TRANSFER NOT WORKING - Files will use service account quota (limited)!")
        logger.warning("⚠️ Uploads may fail due to quota limitations!")
    
    logger.info("✅ Application startup complete!")

# Run startup
startup()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🌐 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
