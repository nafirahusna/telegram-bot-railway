# app.py - Updated with OAuth Support
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

# Configuration from environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")

# Validate required environment variables
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN environment variable is required!")
    exit(1)

if not SPREADSHEET_ID:
    logger.error("❌ SPREADSHEET_ID environment variable is required!")
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

def test_oauth_drive():
    """Test OAuth Drive access"""
    if not bot or not bot.google_service:
        logger.warning("⚠️ Bot or Google service not available for OAuth test")
        return False
    
    try:
        logger.info("🧪 Testing OAuth Drive access...")
        test_result = bot.google_service.test_oauth_drive_access()
        
        if test_result:
            logger.info("✅ OAuth Drive access test PASSED - photos will use personal Gmail quota!")
        else:
            logger.warning("⚠️ OAuth Drive access test FAILED - photo uploads may not work")
        
        return test_result
        
    except Exception as e:
        logger.error(f"❌ Error testing OAuth Drive: {e}")
        return False

@app.route('/')
def index():
    # Get system info
    system_info = {
        'status': 'running',
        'bot_ready': bot_ready,
        'loop_running': loop is not None and not loop.is_closed(),
        'message': 'Telegram Bot with OAuth Drive & Service Account Sheets',
        'services': {
            'drive': 'oauth_personal_account',
            'sheets': 'service_account'
        }
    }
    
    # Get quota info if available
    if bot and bot.google_service:
        try:
            quota_info = bot.google_service.get_drive_quota_info()
            if quota_info:
                system_info['drive_quota'] = quota_info
        except Exception as e:
            logger.error(f"Error getting quota info: {e}")
    
    return jsonify(system_info)

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy' if bot_ready else 'initializing',
        'bot': 'ready' if bot_ready else 'not_ready',
        'loop': 'running' if loop and not loop.is_closed() else 'not_running',
        'services': {
            'drive_oauth': 'ready' if (bot and bot.google_service and bot.google_service.service_drive) else 'not_ready',
            'sheets_service_account': 'ready' if (bot and bot.google_service and bot.google_service.service_sheets) else 'not_ready'
        }
    })

@app.route('/test-oauth')
def test_oauth_endpoint():
    """Test endpoint for OAuth Drive access"""
    try:
        if not bot or not bot.google_service:
            return jsonify({
                'status': 'error',
                'message': 'Bot or Google service not available'
            }), 503
        
        # Test OAuth Drive access
        oauth_test = test_oauth_drive()
        
        # Get quota info
        quota_info = bot.google_service.get_drive_quota_info()
        
        # Get service account info
        service_account_info = bot.google_service.get_service_account_usage()
        
        return jsonify({
            'status': 'success' if oauth_test else 'failed',
            'oauth_drive_working': oauth_test,
            'quota_info': quota_info,
            'service_account_info': service_account_info,
            'message': 'OAuth Drive test completed'
        })
        
    except Exception as e:
        logger.error(f"❌ Error in OAuth test endpoint: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/cleanup')
def cleanup_endpoint():
    """Cleanup endpoint - now only for informational purposes"""
    try:
        if not bot or not bot.google_service:
            return jsonify({
                'status': 'error',
                'message': 'Bot or Google service not available'
            }), 503
        
        # Since we're using OAuth for Drive, no cleanup needed
        cleanup_result = bot.google_service.cleanup_service_account_files()
        
        return jsonify({
            'status': 'success',
            'message': 'No cleanup needed - using OAuth for Drive uploads',
            'note': 'Service account only used for spreadsheet operations'
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
    
    logger.info("🚀 Starting Telegram Bot with OAuth Drive + Service Account Sheets...")
    
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
    
    # Test OAuth Drive capability
    logger.info("🧪 Testing OAuth Drive access...")
    oauth_test_passed = test_oauth_drive()
    
    if oauth_test_passed:
        logger.info("✅ OAUTH DRIVE WORKING - Photos will use your personal Gmail quota (15GB)!")
    else:
        logger.warning("⚠️ OAUTH DRIVE NOT WORKING - Photo uploads may fail!")
        logger.warning("⚠️ Check OAuth credentials: OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, OAUTH_REFRESH_TOKEN")
    
    logger.info("✅ Application startup complete!")

# Run startup
startup()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🌐 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
