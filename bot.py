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
            
            # Tampilkan konfirmasi dengan info foto
            session = self.session_service.get_session(user_id)
            photo_info = ""
            if session.get('photos'):
                photo_info = f"\n📷 Foto Terupload: {len(session['photos'])} foto\n"
                for i, photo in enumerate(session['photos'], 1):
                    photo_info += f"   {i}. {photo['name']}\n"
            else:
                photo_info = "\n📷 Foto Eviden: Belum ada foto terupload\n"
            
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
                f"Valins ID: {report_data['valins_id']}"
                f"{photo_info}\n"
                f"Pilih tindakan:"
            )
            
            keyboard = [
                [KeyboardButton("✅ Kirim Laporan"), KeyboardButton("📝 Edit Data")],
                [KeyboardButton("📷 Upload Foto Eviden"), KeyboardButton("❌ Batalkan")]
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

            elif choice == "📝 Edit Data":
                # Kirim ulang format untuk diedit
                report_format = (
                    f"📝 Edit Data Laporan\n\n"
                    f"Report Type : {session['data']['report_type']}\n"
                    f"ID Ticket : {session['data']['id_ticket']}\n"
                    f"Folder Drive : {session['data']['folder_link']}\n"
                    f"-------------------------------------------------------------\n"
                    f"Salin Format Laporan dan edit dibawah ini :\n\n"
                    f"Customer Name : {session['data']['customer_name']}\n"
                    f"Service No : {session['data']['service_no']}\n"
                    f"Segment : {session['data']['segment']}\n"
                    f"Teknisi 1 : {session['data']['teknisi_1']}\n"
                    f"Teknisi 2 : {session['data']['teknisi_2']}\n"
                    f"STO : {session['data']['sto']}\n"
                    f"Valins ID : {session['data']['valins_id']}"
                )
                
                await update.message.reply_text(
                    report_format,
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Batalkan")]], resize_keyboard=True)
                )
                return INPUT_DATA
            
            elif choice == "📷 Upload Foto Eviden":
                # Cek apakah sudah ada foto terupload
                session = self.session_service.get_session(user_id)
                has_photos = session.get('photos') and len(session['photos']) > 0
                
                if has_photos:
                    # Jika sudah ada foto, langsung ke opsi upload
                    keyboard = [
                        [KeyboardButton("🔸 Upload Satu-Satu (Custom Nama)")],
                        [KeyboardButton("📷 Upload Banyak (Auto Nama)")],
                        [KeyboardButton("🗑️ Hapus Semua & Upload Ulang")],
                        [KeyboardButton("🔙 Kembali ke Konfirmasi")]
                    ]
                else:
                    # Jika belum ada foto, tampilkan opsi kembali
                    keyboard = [
                        [KeyboardButton("🔸 Upload Satu-Satu (Custom Nama)")],
                        [KeyboardButton("📷 Upload Banyak (Auto Nama)")],
                        [KeyboardButton("🔙 Kembali ke Konfirmasi")]
                    ]
                
                await update.message.reply_text(
                    "📷 **Upload Foto Eviden**\n\n"
                    "⚡ **PENTING - Cara Upload Foto:**\n"
                    "• **Satu foto**: Kirim 1 foto → input deskripsi custom\n"
                    "• **Beberapa foto sekaligus**: Deskripsi akan otomatis random (foto_1, foto_2, dst)\n\n"
                    "🔧 **Pilih metode upload:**",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                )
                return UPLOAD_PHOTO
                
        except Exception as e:
            logger.error(f"❌ Error in confirm_data: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan. Silakan /start ulang.")
            return ConversationHandler.END

    async def upload_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo upload state - FIXED VERSION with better controls"""
        user_id = update.effective_user.id
        message_text = update.message.text

        if context.user_data.get('confirming_single_photo'):
            if message_text == "✅ Benar, Lanjut Upload":
                # Clear confirmation state dan lanjut upload
                context.user_data['confirming_single_photo'] = False
                if 'last_uploaded_photo' in context.user_data:
                    del context.user_data['last_uploaded_photo']
                
                # Kembali ke mode upload satu-satu
                session = self.session_service.get_session(user_id)
                has_photos = session.get('photos') and len(session['photos']) > 0
                
                keyboard = [
                    [KeyboardButton("✅ Selesai Upload")],
                    [KeyboardButton("🗑️ Hapus Semua & Upload Ulang")],
                    [KeyboardButton("🔙 Kembali ke Konfirmasi")]
                ]
                
                await update.message.reply_text(
                    f"📷 **Total foto terupload: {len(session.get('photos', []))}**\n\n"
                    f"Kirimkan foto berikutnya atau pilih opsi:",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                )
                return UPLOAD_PHOTO
            
            elif message_text == "❌ Salah, Hapus Foto Ini":
                # Hapus foto yang baru saja diupload
                last_photo = context.user_data.get('last_uploaded_photo')
                session = self.session_service.get_session(user_id)
                
                if last_photo and session:
                    try:
                        # Hapus dari Drive
                        self.google_service.service_drive.files().delete(fileId=last_photo['id']).execute()
                        logger.info(f"🗑️ Deleted incorrect photo: {last_photo['name']}")
                        
                        # Hapus dari session
                        if 'photos' in session:
                            session['photos'] = [p for p in session['photos'] if p['id'] != last_photo['id']]
                            self.session_service.update_session(user_id, {'photos': session['photos']})
                        
                        await update.message.reply_text("🗑️ Foto berhasil dihapus!")
                        
                    except Exception as e:
                        logger.error(f"❌ Error deleting photo: {e}")
                        await update.message.reply_text("❌ Terjadi kesalahan saat menghapus foto.")
                
                # Clear confirmation state
                context.user_data['confirming_single_photo'] = False
                if 'last_uploaded_photo' in context.user_data:
                    del context.user_data['last_uploaded_photo']
                
                # Kembali ke mode upload satu-satu
                session = self.session_service.get_session(user_id)
                has_photos = session.get('photos') and len(session['photos']) > 0
                
                if has_photos:
                    keyboard = [
                        [KeyboardButton("✅ Selesai Upload")],
                        [KeyboardButton("🗑️ Hapus Semua & Upload Ulang")],
                        [KeyboardButton("🔙 Kembali ke Konfirmasi")]
                    ]
                else:
                    keyboard = [
                        [KeyboardButton("🔙 Kembali ke Konfirmasi")]
                    ]
                
                await update.message.reply_text(
                    "Kirimkan foto lagi atau pilih opsi:",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                )
                return UPLOAD_PHOTO
            
            elif message_text == "🏁 Selesai Upload":
                # Same as "✅ Selesai Upload" - go to confirmation
                context.user_data['confirming_single_photo'] = False
                if 'last_uploaded_photo' in context.user_data:
                    del context.user_data['last_uploaded_photo']
                
                # Reset upload mode
                if 'upload_mode' in context.user_data:
                    del context.user_data['upload_mode']
                
                # Kembali ke konfirmasi data
                session = self.session_service.get_session(user_id)
                if not session:
                    await update.message.reply_text("❌ Session error. Silakan /start ulang.")
                    return ConversationHandler.END
                    
                photo_info = ""
                if session.get('photos'):
                    photo_info = f"\n📷 Foto Terupload: {len(session['photos'])} foto\n"
                    for i, photo in enumerate(session['photos'], 1):
                        photo_info += f"   {i}. {photo['name']}\n"
                else:
                    photo_info = "\n📷 Foto Eviden: Belum ada foto terupload\n"
                
                confirmation_text = (
                    f"✅ Konfirmasi Data Laporan\n\n"
                    f"Report Type: {session['data']['report_type']}\n"
                    f"ID Ticket: {session['data']['id_ticket']}\n"
                    f"Customer Name: {session['data']['customer_name']}\n"
                    f"Service No: {session['data']['service_no']}\n"
                    f"Segment: {session['data']['segment']}\n"
                    f"Teknisi 1: {session['data']['teknisi_1']}\n"
                    f"Teknisi 2: {session['data']['teknisi_2']}\n"
                    f"STO: {session['data']['sto']}\n"
                    f"Valins ID: {session['data']['valins_id']}"
                    f"{photo_info}\n"
                    f"Pilih tindakan:"
                )
                
                keyboard = [
                    [KeyboardButton("✅ Kirim Laporan"), KeyboardButton("📝 Edit Data")],
                    [KeyboardButton("📷 Upload Foto Eviden"), KeyboardButton("❌ Batalkan")]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                await update.message.reply_text(confirmation_text, reply_markup=reply_markup)
                return CONFIRM_DATA
        
        # Handle pilihan awal dan navigasi
        if message_text == "🔙 Kembali ke Konfirmasi":
            # Kembali ke konfirmasi data
            session = self.session_service.get_session(user_id)
            if not session:
                await update.message.reply_text("❌ Session error. Silakan /start ulang.")
                return ConversationHandler.END
                
            photo_info = ""
            if session.get('photos'):
                photo_info = f"\n📷 Foto Terupload: {len(session['photos'])} foto\n"
                for i, photo in enumerate(session['photos'], 1):
                    photo_info += f"   {i}. {photo['name']}\n"
            else:
                photo_info = "\n📷 Foto Eviden: Belum ada foto terupload\n"
            
            confirmation_text = (
                f"✅ Konfirmasi Data Laporan\n\n"
                f"Report Type: {session['data']['report_type']}\n"
                f"ID Ticket: {session['data']['id_ticket']}\n"
                f"Customer Name: {session['data']['customer_name']}\n"
                f"Service No: {session['data']['service_no']}\n"
                f"Segment: {session['data']['segment']}\n"
                f"Teknisi 1: {session['data']['teknisi_1']}\n"
                f"Teknisi 2: {session['data']['teknisi_2']}\n"
                f"STO: {session['data']['sto']}\n"
                f"Valins ID: {session['data']['valins_id']}"
                f"{photo_info}\n"
                f"Pilih tindakan:"
            )
            
            keyboard = [
                [KeyboardButton("✅ Kirim Laporan"), KeyboardButton("📝 Edit Data")],
                [KeyboardButton("📷 Upload Foto Eviden"), KeyboardButton("❌ Batalkan")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(confirmation_text, reply_markup=reply_markup)
            return CONFIRM_DATA
    
        elif message_text == "🗑️ Hapus Semua & Upload Ulang":
            # Hapus semua foto yang sudah diupload
            session = self.session_service.get_session(user_id)
            if session and session.get('photos'):
                try:
                    # Hapus foto dari Drive
                    for photo in session['photos']:
                        try:
                            self.google_service.service_drive.files().delete(fileId=photo['id']).execute()
                            logger.info(f"🗑️ Deleted photo: {photo['name']}")
                        except Exception as e:
                            logger.error(f"❌ Error deleting photo {photo['name']}: {e}")
                    
                    # Hapus dari session
                    self.session_service.update_session(user_id, {'photos': []})
                    
                    await update.message.reply_text("🗑️ Semua foto berhasil dihapus!")
                    
                except Exception as e:
                    logger.error(f"❌ Error deleting photos: {e}")
                    await update.message.reply_text("❌ Terjadi kesalahan saat menghapus foto.")
            
            # Kembali ke pilihan upload awal (tanpa opsi hapus karena sudah tidak ada foto)
            keyboard = [
                [KeyboardButton("🔸 Upload Satu-Satu (Custom Nama)")],
                [KeyboardButton("📷 Upload Banyak (Auto Nama)")],
                [KeyboardButton("🔙 Kembali ke Konfirmasi")]
            ]
            
            await update.message.reply_text(
                "📷 **Upload Foto Eviden**\n\n"
                "⚡ **PENTING - Cara Upload Foto:**\n"
                "• **Satu foto**: Kirim 1 foto → input deskripsi custom\n"
                "• **Beberapa foto sekaligus**: Deskripsi akan otomatis random (foto_1, foto_2, dst)\n\n"
                "🔧 **Pilih metode upload:**",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return UPLOAD_PHOTO
    
        elif message_text == "🔸 Upload Satu-Satu (Custom Nama)":
            # Set mode upload satu-satu
            context.user_data['upload_mode'] = 'single'
            
            # Cek apakah sudah ada foto
            session = self.session_service.get_session(user_id)
            has_photos = session.get('photos') and len(session['photos']) > 0
            
            if has_photos:
                keyboard = [
                    [KeyboardButton("✅ Selesai Upload")],
                    [KeyboardButton("🗑️ Hapus Semua & Upload Ulang")],
                    [KeyboardButton("🔙 Kembali ke Konfirmasi")]
                ]
            else:
                keyboard = [
                    [KeyboardButton("🔙 Kembali ke Konfirmasi")]
                ]
            
            await update.message.reply_text(
                "🔸 **Mode Upload Satu-Satu**\n\n"
                "Kirimkan foto satu per satu. Setiap foto akan diminta deskripsi custom.\n\n"
                "Kirimkan foto pertama:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return UPLOAD_PHOTO
            
        elif message_text == "📷 Upload Banyak (Auto Nama)":
            # Set mode upload banyak
            context.user_data['upload_mode'] = 'multiple'
            
            # Cek apakah sudah ada foto
            session = self.session_service.get_session(user_id)
            has_photos = session.get('photos') and len(session['photos']) > 0
            
            if has_photos:
                keyboard = [
                    [KeyboardButton("✅ Selesai Upload")],
                    [KeyboardButton("🗑️ Hapus Semua & Upload Ulang")],
                    [KeyboardButton("🔙 Kembali ke Konfirmasi")]
                ]
            else:
                keyboard = [
                    [KeyboardButton("🔙 Kembali ke Konfirmasi")]
                ]
            
            await update.message.reply_text(
                "📷 **Mode Upload Banyak**\n\n"
                "Kirimkan beberapa foto sekaligus. Nama file akan otomatis: foto_1, foto_2, dst.\n\n"
                "Kirimkan foto-foto Anda:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return UPLOAD_PHOTO
        
        elif message_text == "✅ Selesai Upload":
            # Reset upload mode
            if 'upload_mode' in context.user_data:
                del context.user_data['upload_mode']
            
            # Kembali ke konfirmasi data dengan info foto terbaru
            session = self.session_service.get_session(user_id)
            if not session:
                await update.message.reply_text("❌ Session error. Silakan /start ulang.")
                return ConversationHandler.END
                
            photo_info = ""
            if session.get('photos'):
                photo_info = f"\n📷 Foto Terupload: {len(session['photos'])} foto\n"
                for i, photo in enumerate(session['photos'], 1):
                    photo_info += f"   {i}. {photo['name']}\n"
            else:
                photo_info = "\n📷 Foto Eviden: Belum ada foto terupload\n"
            
            confirmation_text = (
                f"✅ Konfirmasi Data Laporan\n\n"
                f"Report Type: {session['data']['report_type']}\n"
                f"ID Ticket: {session['data']['id_ticket']}\n"
                f"Customer Name: {session['data']['customer_name']}\n"
                f"Service No: {session['data']['service_no']}\n"
                f"Segment: {session['data']['segment']}\n"
                f"Teknisi 1: {session['data']['teknisi_1']}\n"
                f"Teknisi 2: {session['data']['teknisi_2']}\n"
                f"STO: {session['data']['sto']}\n"
                f"Valins ID: {session['data']['valins_id']}"
                f"{photo_info}\n"
                f"Pilih tindakan:"
            )
            
            keyboard = [
                [KeyboardButton("✅ Kirim Laporan"), KeyboardButton("📝 Edit Data")],
                [KeyboardButton("📷 Upload Foto Eviden"), KeyboardButton("❌ Batalkan")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(confirmation_text, reply_markup=reply_markup)
            return CONFIRM_DATA
    
        elif message_text == "❌ Batalkan":
            # Reset upload mode
            if 'upload_mode' in context.user_data:
                del context.user_data['upload_mode']
            self.delete_folder_if_exists(user_id)
            self.session_service.end_session(user_id)
            await update.message.reply_text(
                "❌ Laporan dibatalkan.",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
            )
            return ConversationHandler.END
        
        # Handle photo message
        if update.message.photo:
            upload_mode = context.user_data.get('upload_mode', 'single')
            
            if upload_mode == 'single':
                # Mode upload satu-satu - minta deskripsi
                photo = update.message.photo[-1]
                context.user_data['temp_photo'] = photo
                
                await update.message.reply_text(
                    "📝 Masukkan deskripsi untuk foto ini (akan digunakan sebagai nama file):\n\n"
                    "Contoh: 'foto sebelum perbaikan', 'hasil instalasi', dll",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("🔙 Kembali ke Upload")]
                    ], resize_keyboard=True)
                )
                return INPUT_PHOTO_DESC
            
            elif upload_mode == 'multiple':
                # Mode upload banyak - langsung proses dengan nama auto
                session = self.session_service.get_session(user_id)
                if not session or not session.get('folder_id'):
                    await update.message.reply_text(
                        "❌ Session tidak valid. Silakan mulai ulang.",
                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
                    )
                    return ConversationHandler.END
                
                photo = update.message.photo[-1]
                
                # Send processing message
                processing_msg = await update.message.reply_text("⏳ Mengupload foto...")
                
                try:
                    # Get file info
                    file = await context.bot.get_file(photo.file_id)
                    
                    # Generate nama otomatis
                    photo_count = len(session.get('photos', [])) + 1
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"foto_{photo_count}_{timestamp}.jpg"
                    filepath = f"temp_{filename}"
                    
                    # Download file
                    await file.download_to_drive(filepath)
                    
                    # Check if file was downloaded properly
                    if not os.path.exists(filepath):
                        raise Exception("File download failed")
                    
                    file_size = os.path.getsize(filepath)
                    if file_size == 0:
                        raise Exception("Downloaded file is empty")
                    
                    logger.info(f"📥 File downloaded: {filename} ({file_size} bytes)")
                    
                    # Upload to Drive using new strategy
                    file_id = self.google_service.upload_to_drive(filepath, filename, session['folder_id'])
                    
                    # Clean up local file
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    
                    if file_id:
                        # Initialize photos list if not exists
                        if 'photos' not in session:
                            session['photos'] = []
                        
                        # Tambahkan ke daftar foto
                        session['photos'].append({
                            'id': file_id,
                            'name': filename
                        })
                        
                        # Update session
                        self.session_service.update_session(user_id, {'photos': session['photos']})
                        
                        # Update keyboard dengan tombol selesai upload
                        keyboard = [
                            [KeyboardButton("✅ Selesai Upload")],
                            [KeyboardButton("🗑️ Hapus Semua & Upload Ulang")],
                            [KeyboardButton("🔙 Kembali ke Konfirmasi")]
                        ]
                        
                        # Update processing message with success
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=processing_msg.message_id,
                            text=f"✅ Foto '{filename}' berhasil diupload!\n\n"
                                 f"📷 Total foto terupload: {len(session['photos'])}\n\n"
                                 f"Kirim foto lain atau pilih opsi:"
                        )
                        
                        # Send new keyboard
                        await update.message.reply_text(
                            "Pilih tindakan:",
                            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                        )
                    else:
                        # Update processing message with error
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=processing_msg.message_id,
                            text="❌ Gagal mengupload foto ke Drive. Silakan coba lagi."
                        )
                        
                except Exception as e:
                    logger.error(f"❌ Error uploading photo: {e}")
                    
                    # Clean up local file if exists
                    try:
                        if os.path.exists(filepath):
                            os.remove(filepath)
                    except:
                        pass
                    
                    # Update processing message with error
                    try:
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=processing_msg.message_id,
                            text=f"❌ Terjadi kesalahan saat mengupload foto: {str(e)[:100]}...\n\nSilakan coba lagi."
                        )
                    except:
                        await update.message.reply_text(
                            "❌ Terjadi kesalahan saat mengupload foto. Silakan coba lagi."
                        )
                
                return UPLOAD_PHOTO
        else:
            # Belum pilih mode upload atau input tidak valid
            if 'upload_mode' not in context.user_data:
                await update.message.reply_text(
                    "Silakan pilih metode upload terlebih dahulu."
                )
                return UPLOAD_PHOTO
            else:
                await update.message.reply_text(
                    "Silakan kirim foto atau pilih salah satu opsi yang tersedia."
                )
                return UPLOAD_PHOTO

    async def input_photo_desc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo description input - FIXED VERSION with confirmation"""
        user_id = update.effective_user.id
        description = update.message.text.strip()
        
        if description == "🔙 Kembali ke Upload":
            # Clear temp photo dan kembali ke upload mode single
            if 'temp_photo' in context.user_data:
                del context.user_data['temp_photo']
            
            # Kembali ke upload mode single
            session = self.session_service.get_session(user_id)
            has_photos = session.get('photos') and len(session['photos']) > 0
            
            if has_photos:
                keyboard = [
                    [KeyboardButton("✅ Selesai Upload")],
                    [KeyboardButton("🗑️ Hapus Semua & Upload Ulang")],
                    [KeyboardButton("🔙 Kembali ke Konfirmasi")]
                ]
            else:
                keyboard = [
                    [KeyboardButton("🔙 Kembali ke Konfirmasi")]
                ]
            
            await update.message.reply_text(
                "🔸 **Mode Upload Satu-Satu**\n\n"
                "Kirimkan foto satu per satu. Setiap foto akan diminta deskripsi custom.\n\n"
                "Kirimkan foto:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return UPLOAD_PHOTO
        
        if not description:
            await update.message.reply_text("Deskripsi tidak boleh kosong. Silakan masukkan deskripsi foto:")
            return INPUT_PHOTO_DESC
        
        # Clean description untuk nama file
        import re
        clean_desc = re.sub(r'[^\w\s-]', '', description).strip()
        clean_desc = re.sub(r'[\s]+', '_', clean_desc)
        
        # Process foto yang disimpan sementara
        session = self.session_service.get_session(user_id)
        temp_photo = context.user_data.get('temp_photo')
        
        if temp_photo and session and session.get('folder_id'):
            # Send processing message
            processing_msg = await update.message.reply_text("⏳ Mengupload foto...")
            
            try:
                file = await context.bot.get_file(temp_photo.file_id)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{clean_desc}_{timestamp}.jpg"
                filepath = f"temp_{filename}"
                
                # Download file
                await file.download_to_drive(filepath)
                
                # Check if file was downloaded properly
                if not os.path.exists(filepath):
                    raise Exception("File download failed")
                
                file_size = os.path.getsize(filepath)
                if file_size == 0:
                    raise Exception("Downloaded file is empty")
                
                logger.info(f"📥 File downloaded: {filename} ({file_size} bytes)")
                
                # Upload to Drive using new strategy
                file_id = self.google_service.upload_to_drive(filepath, filename, session['folder_id'])
                
                # Clean up local file
                if os.path.exists(filepath):
                    os.remove(filepath)
                
                if file_id:
                    # Initialize photos list if not exists
                    if 'photos' not in session:
                        session['photos'] = []
                    
                    # Tambahkan ke daftar foto
                    session['photos'].append({
                        'id': file_id,
                        'name': filename
                    })
                    
                    # Update session
                    self.session_service.update_session(user_id, {'photos': session['photos']})
                    
                    # Clear temp photo
                    if 'temp_photo' in context.user_data:
                        del context.user_data['temp_photo']
                    
                    # Update processing message with success and confirmation
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=processing_msg.message_id,
                        text=f"✅ Foto berhasil diupload!\n\n"
                             f"📷 **Nama file:** {filename}\n"
                             f"📝 **Deskripsi:** {description}\n\n"
                             f"Apakah foto dan deskripsi sudah benar?"
                    )
                    
                    # Tampilkan opsi konfirmasi
                    keyboard = [
                        [KeyboardButton("✅ Benar, Lanjut Upload"), KeyboardButton("❌ Salah, Hapus Foto Ini")],
                        [KeyboardButton("🏁 Selesai Upload"), KeyboardButton("🔙 Kembali ke Konfirmasi")]
                    ]
                    
                    await update.message.reply_text(
                        "Pilih tindakan:",
                        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                    )
                    
                    # Set flag untuk confirmation state
                    context.user_data['confirming_single_photo'] = True
                    context.user_data['last_uploaded_photo'] = {
                        'id': file_id,
                        'name': filename
                    }
                    
                    return UPLOAD_PHOTO
                    
                else:
                    # Update processing message with error
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=processing_msg.message_id,
                        text="❌ Gagal mengupload foto ke Drive. Silakan coba lagi."
                    )
                    
            except Exception as e:
                logger.error(f"❌ Error uploading photo: {e}")
                
                # Clean up local file if exists
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except:
                    pass
                
                # Update processing message with error
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=processing_msg.message_id,
                        text=f"❌ Terjadi kesalahan: {str(e)[:100]}...\n\nSilakan coba lagi."
                    )
                except:
                    await update.message.reply_text(
                        "❌ Terjadi kesalahan saat mengupload foto. Silakan coba lagi."
                    )
        
        return INPUT_PHOTO_DESC

    def delete_folder_if_exists(self, user_id):
        """Delete folder if session exists"""
        try:
            session = self.session_service.get_session(user_id)
            if session and session.get('folder_id'):
                self.google_service.service_drive.files().delete(fileId=session['folder_id']).execute()
                logger.info(f"🗑️ Folder deleted for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error deleting folder: {e}")
