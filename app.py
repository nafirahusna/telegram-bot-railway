# app.py - OAuth2 Version with Environment Variables
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

# Configuration dari environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")

# Validate required environment variables
required_env_vars = [
    "BOT_TOKEN",
    "SPREADSHEET_ID",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET", 
    "GOOGLE_REFRESH_TOKEN",
    "GOOGLE_PARENT_FOLDER_ID",
    "GOOGLE_OWNER_EMAIL"
]

missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
if missing_vars:
    logger.error(f"❌ Missing required environment variables: {missing_vars}")
    logger.error("❌ Please set all required environment variables before running the app")
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

def test_google_connection():
    """Test Google API connection"""
    if not bot or not bot.google_service:
        logger.warning("⚠️ Bot or Google service not available for connection test")
        return False
    
    try:
        logger.info("🧪 Testing Google API connection...")
        test_result = bot.google_service.test_connection()
        
        if test_result:
            logger.info("✅ Google API connection test PASSED!")
            logger.info(f"👤 Connected as: {test_result.get('user_email', 'Unknown')}")
            
            quota = test_result.get('storage_quota', {})
            if quota:
                usage_gb = round(int(quota.get('usage', 0)) / (1024**3), 2)
                limit_gb = round(int(quota.get('limit', 0)) / (1024**3), 2)
                logger.info(f"💾 Storage: {usage_gb}GB / {limit_gb}GB used")
        else:
            logger.warning("⚠️ Google API connection test FAILED")
        
        return test_result
        
    except Exception as e:
        logger.error(f"❌ Error testing Google connection: {e}")
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
        'message': 'Telegram Bot Webhook Server - OAuth2 Version',
        'quota_info': quota_info,
        'authentication': 'OAuth2'
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy' if bot_ready else 'initializing',
        'bot': 'ready' if bot_ready else 'not_ready',
        'loop': 'running' if loop and not loop.is_closed() else 'not_running',
        'auth_method': 'OAuth2'
    })

@app.route('/test-connection')
def test_connection_endpoint():
    """Test endpoint for Google API connection"""
    try:
        if not bot or not bot.google_service:
            return jsonify({
                'status': 'error',
                'message': 'Bot or Google service not available'
            }), 503
        
        test_result = test_google_connection()
        
        return jsonify({
            'status': 'success' if test_result else 'failed',
            'connection_working': bool(test_result),
            'connection_info': test_result if test_result else None,
            'message': 'Google API connection test completed'
        })
        
    except Exception as e:
        logger.error(f"❌ Error in test connection endpoint: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/cleanup')
def cleanup_endpoint():
    """Cleanup endpoint for old temporary files"""
    try:
        if not bot or not bot.google_service:
            return jsonify({
                'status': 'error',
                'message': 'Bot or Google service not available'
            }), 503
        
        cleanup_result = bot.google_service.cleanup_old_files(days_old=7)
        
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
    
    logger.info("🚀 Starting Telegram Bot Webhook Server - OAuth2 Version...")
    logger.info(f"🔑 Using OAuth2 authentication for: {os.environ.get('GOOGLE_OWNER_EMAIL')}")
    
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
    
    # Test Google API connection
    logger.info("🧪 Testing Google API connection...")
    connection_test_passed = test_google_connection()
    
    if connection_test_passed:
        logger.info("✅ GOOGLE API CONNECTION WORKING!")
        logger.info("✅ Using OAuth2 - no quota limitations!")
    else:
        logger.warning("⚠️ GOOGLE API CONNECTION FAILED!")
        logger.warning("⚠️ Bot may not work properly!")
    
    logger.info("✅ Application startup complete!")

# Run startup
startup()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🌐 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
