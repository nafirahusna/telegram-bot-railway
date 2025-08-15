import os
from bot import TelegramBot

# Konfigurasi
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8284891962:AAHbRY1FB23MIh4TZ8qeSh6CXQ35XKH_XjQ")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1bs_6iDuxgTX4QF_FTra3YDYVsRFatwRXLQ0tiQfNZyI")

if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or SPREADSHEET_ID == "YOUR_SPREADSHEET_ID_HERE":
    print("❌ Error: Please set your BOT_TOKEN and SPREADSHEET_ID!")
    exit(1)

# Create bot instance
bot = TelegramBot(BOT_TOKEN, SPREADSHEET_ID)

# Create Flask app
app = bot.run()

if __name__ == "__main__":
    # For local development
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
