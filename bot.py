# bot.py - Simple Fixed Version
import os
import re
import asyncio
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

from services.google_service import GoogleService
from services.session_service import SessionService
from config.spreadsheet_config import SpreadsheetConfig

# States untuk ConversationHandler
SELECT_REPORT_TYPE, INPUT_ID, INPUT_DATA, CONFIRM_DATA, UPLOAD_PHOTO, INPUT_PHOTO_DESC = range(6)

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token, spreadsheet_id):
        self.token = token
        self.spreadsheet_id = spreadsheet_id
        self.application = None
        
        # Initialize services
        logger.info("🔧 Initializing Google services...")
        self.google_service = GoogleService()
        self.session_service = SessionService(self.google_service)
        self.spreadsheet_config = SpreadsheetConfig()
        
        # Authenticate Google
        logger.info("🔐 Authenticating Google APIs...")
        if not self.google_service.authenticate():
            raise Exception("Failed to authenticate Google APIs")
        
        logger.info("✅ TelegramBot services initialized")

    async def initialize_application(self):
        """Initialize Telegram Application"""
        try:
            logger.info("🤖 Building Telegram Application...")
            
            # Build application
            self.application = Application.builder().token(self.token).build()
            
            # Setup handlers
            self._setup_handlers()
            
            # Initialize application
            logger.info("🔄 Initializing Telegram Application...")
            await self.application.initialize()
            
            logger.info("✅ Telegram Application initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Telegram Application: {e}")
            return False

    def _setup_handlers(self):
        """Setup conversation handlers"""
        logger.info("📋 Setting up conversation handlers...")
        
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('start', self.start)
            ],
            states={
                SELECT_REPORT_TYPE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.select_report_type)
                ],
                INPUT_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.input_id)
                ],
                INPUT_DATA: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.input_data)
                ],
                CONFIRM_DATA: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.confirm_data)
                ],
                UPLOAD_PHOTO: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.upload_photo),
                    MessageHandler(filters.PHOTO, self.upload_photo)
                ],
                INPUT_PHOTO_DESC: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.input_photo_desc)
                ]
            },
            fallbacks=[CommandHandler('start', self.start)],
            allow_reentry=True
        )
        
        self.application.add_handler(conv_handler)
        logger.info("✅ Handlers setup complete")

    async def process_update(self, update):
        """Process incoming update"""
        try:
            if not self.application:
                logger.error("❌ Application not initialized")
                return
                
            user_id = update.effective_user.id if update.effective_user else 'Unknown'
            logger.info(f"🔄 Processing update for user: {user_id}")
            
            # Process the update
            await self.application.process_update(update)
            logger.info("✅ Update processed successfully")
            
        except Exception as e:
            logger.error(f"❌ Error processing update: {e}")
            
            # Try to send error message
            try:
                if update.effective_chat and self.application:
                    await self.application.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ Terjadi kesalahan sistem. Silakan coba lagi dengan /start"
                    )
            except Exception as send_error:
                logger.error(f"❌ Failed to send error message: {send_error}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        try:
            user_id = update.effective_user.id
            logger.info(f"👤 User {user_id} started bot")
            
            # Create new session
            self.session_service.create_session(user_id)
            
            keyboard = [
                [KeyboardButton("Non B2B"), KeyboardButton("BGES")],
                [KeyboardButton("Squad")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(
                "🔷 Pilih Jenis Laporan:",
                reply_markup=reply_markup
            )
            return SELECT_REPORT_TYPE
            
        except Exception as e:
            logger.error(f"❌ Error in start handler: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan. Silakan coba lagi.")
            return ConversationHandler.END

    async def select_report_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle report type selection"""
        try:
            user_id = update.effective_user.id
            message_text = update.message.text
            
            logger.info(f"📝 User {user_id} selected: {message_text}")
            
            valid_types = ['Non B2B', 'BGES', 'Squad']
            if message_text not in valid_types:
                await update.message.reply_text("❌ Pilihan tidak valid. Silakan pilih jenis laporan yang tersedia.")
                return SELECT_REPORT_TYPE
            
            # Update session
            success = self.session_service.update_session(user_id, {'report_type': message_text})
            if not success:
                await update.message.reply_text("❌ Session error. Silakan /start ulang.")
                return ConversationHandler.END
            
            await update.message.reply_text(
                "🎫 Masukkan ID Ticket:",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Batalkan")]], resize_keyboard=True)
            )
            return INPUT_ID
            
        except Exception as e:
            logger.error(f"❌ Error in select_report_type: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan. Silakan /start ulang.")
            return ConversationHandler.END

    async def input_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle ID input"""
        try:
            user_id = update.effective_user.id
            ticket_id = update.message.text.strip()
            
            logger.info(f"🎫 User {user_id} entered ticket ID: {ticket_id}")
            
            if ticket_id == "❌ Batalkan":
                self.delete_folder_if_exists(user_id)
                self.session_service.end_session(user_id)
                await update.message.reply_text(
                    "❌ Laporan dibatalkan.",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
                )
                return ConversationHandler.END
            
            if not ticket_id:
                await update.message.reply_text("❌ ID Ticket tidak boleh kosong. Silakan masukkan ID Ticket:")
                return INPUT_ID
            
            # Get session
            session = self.session_service.get_session(user_id)
            if not session:
                await update.message.reply_text("❌ Session tidak ditemukan. Silakan /start ulang.")
                return ConversationHandler.END
            
            # Update session with ticket ID
            self.session_service.update_session(user_id, {'id_ticket': ticket_id})
            
            # Create folder in Google Drive
            folder_name = f"{session['report_type']}_{ticket_id}"
            folder_id = self.google_service.create_folder(folder_name)
            
            if not folder_id:
                await update.message.reply_text("❌ Gagal membuat folder. Silakan coba lagi.")
                return INPUT_ID
            
            self.session_service.update_session(user_id, {'folder_id': folder_id})
            
            # Send format
            folder_link = self.google_service.get_folder_link(folder_id)
            report_format = (
                f"✅ Format Berhasil Dibuat\n\n"
                f"Report Type : {session['report_type']}\n"
                f"ID Ticket : {ticket_id}\n"
                f"Folder Drive : {folder_link}\n"
                f"-------------------------------------------------------------\n"
                f"Salin Format Laporan dan isi dibawah ini :\n\n"
                f"Customer Name : \n"
                f"Service No : \n"
                f"Segment : \n"
                f"Teknisi 1 : \n"
                f"Teknisi 2 : \n"
                f"STO : \n"
                f"Valins ID : "
            )
            
            await update.message.reply_text(
                report_format,
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Batalkan")]], resize_keyboard=True)
            )
            return INPUT_DATA
            
        except Exception as e:
            logger.error(f"❌ Error in input_id: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan. Silakan /start ulang.")
            return ConversationHandler.END

    async def input_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle data input - simplified version"""
        try:
            user_id = update.effective_user.id
            message_text = update.message.text
            
            if message_text == "❌ Batalkan":
                self.delete_folder_if_exists(user_id)
                self.session_service.end_session(user_id)
                await update.message.reply_text(
                    "❌ Laporan dibatalkan.",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
                )
                return ConversationHandler.END
            
            # Simple data parsing
            data = {}
            lines = message_text.split('\n')
            
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    data[key.strip()] = value.strip()
            
            # Check if we have the required fields
            required_fields = ['Customer Name', 'Service No', 'Segment', 'Teknisi 1', 'Teknisi 2', 'STO', 'Valins ID']
            missing_fields = [field for field in required_fields if field not in data or not data[field]]
            
            if missing_fields:
                await update.message.reply_text(
                    f"❌ Data tidak lengkap. Field berikut harus diisi: {', '.join(missing_fields)}\n\n"
                    f"Silakan kirim ulang format yang sudah diisi dengan lengkap."
                )
                return INPUT_DATA
            
            # Get session
            session = self.session_service.get_session(user_id)
            if not session:
                await update.message.reply_text("❌ Session error. Silakan /start ulang.")
                return ConversationHandler.END
            
            # Create report data
            report_data = {
                'report_type': session['report_type'],
                'id_ticket': session['id_ticket'],
                'folder_link': self.google_service.get_folder_link(session['folder_id']),
                'reported': datetime.now().strftime("%d/%m/%Y %H:%M"),
                'customer_name': data.get('Customer Name', ''),
                'service_no': data.get('Service No', ''),
                'segment': data.get('Segment', ''),
                'teknisi_1': data.get('Teknisi 1', ''),
                'teknisi_2': data.get('Teknisi 2', ''),
                'sto': data.get('STO', ''),
                'valins_id': data.get('Valins ID', '')
            }
            
            # Save to session
            self.session_service.update_session(user_id, {'data': report_data})
            
            # Show confirmation
            confirmation_text = (
                f"✅ Konfirmasi Data Laporan\n\n"
                f"Report Type: {report_data['report_type']}\n"
                f"ID Ticket: {report_data['id_ticket']}\n"
                f"Customer Name: {report_data['customer_name']}\n"
                f"Service No: {report_data['service_no']}\n"
                f"Segment: {report_data['segment']}\n"
                f"Teknisi 1: {report_data['teknisi_1']}\n"
                f"Teknisi 2: {report_data['teknisi_2']}\n"
                f"STO: {report_data['sto']}\n"
                f"Valins ID: {report_data['valins_id']}\n\n"
                f"Pilih tindakan:"
            )
            
            keyboard = [
                [KeyboardButton("✅ Kirim Laporan"), KeyboardButton("❌ Batalkan")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(confirmation_text, reply_markup=reply_markup)
            return CONFIRM_DATA
            
        except Exception as e:
            logger.error(f"❌ Error in input_data: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan. Silakan /start ulang.")
            return ConversationHandler.END

    async def confirm_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle data confirmation - simplified"""
        try:
            user_id = update.effective_user.id
            choice = update.message.text
            
            session = self.session_service.get_session(user_id)
            if not session:
                await update.message.reply_text("❌ Session error. Silakan /start ulang.")
                return ConversationHandler.END
            
            if choice == "✅ Kirim Laporan":
                # Send to spreadsheet
                success = self.google_service.update_spreadsheet(
                    self.spreadsheet_id,
                    self.spreadsheet_config,
                    session['data']
                )
                
                if success:
                    await update.message.reply_text(
                        "✅ Laporan berhasil dikirim ke spreadsheet!",
                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
                    )
                else:
                    await update.message.reply_text(
                        "❌ Gagal mengirim laporan. Silakan coba lagi.",
                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
                    )
                
                self.session_service.end_session(user_id)
                return ConversationHandler.END
                
            elif choice == "❌ Batalkan":
                self.delete_folder_if_exists(user_id)
                self.session_service.end_session(user_id)
                await update.message.reply_text(
                    "❌ Laporan dibatalkan.",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
                )
                return ConversationHandler.END
                
        except Exception as e:
            logger.error(f"❌ Error in confirm_data: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan. Silakan /start ulang.")
            return ConversationHandler.END

    # Placeholder methods for photo upload (simplified for now)
    async def upload_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📷 Fitur upload foto sedang dalam pengembangan.")
        return CONFIRM_DATA

    async def input_photo_desc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📝 Fitur deskripsi foto sedang dalam pengembangan.")
        return UPLOAD_PHOTO

    def delete_folder_if_exists(self, user_id):
        """Delete folder if session exists"""
        try:
            session = self.session_service.get_session(user_id)
            if session and session.get('folder_id'):
                self.google_service.service_drive.files().delete(fileId=session['folder_id']).execute()
                logger.info(f"🗑️ Folder deleted for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error deleting folder: {e}")
