# bot.py - OAuth2 Version with Environment Variables
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
        
        # Validate environment variables
        required_env_vars = [
            'GOOGLE_CLIENT_ID',
            'GOOGLE_CLIENT_SECRET', 
            'GOOGLE_REFRESH_TOKEN',
            'GOOGLE_PARENT_FOLDER_ID',
            'GOOGLE_OWNER_EMAIL'
        ]
        
        missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
        if missing_vars:
            raise Exception(f"Missing required environment variables: {missing_vars}")
        
        # Initialize services
        logger.info("🔧 Initializing Google services with OAuth2...")
        self.google_service = GoogleService()
        self.session_service = SessionService(self.google_service)
        self.spreadsheet_config = SpreadsheetConfig()
        
        # Authenticate Google
        logger.info("🔐 Authenticating Google APIs with OAuth2...")
        if not self.google_service.authenticate():
            raise Exception("Failed to authenticate Google APIs with OAuth2")
        
        logger.info("✅ TelegramBot services initialized with OAuth2")

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
            user_name = update.effective_user.first_name or "User"
            logger.info(f"👤 User {user_id} ({user_name}) started bot")
            
            # Create new session
            self.session_service.create_session(user_id)
            
            keyboard = [
                [KeyboardButton("Non B2B"), KeyboardButton("BGES")],
                [KeyboardButton("Squad")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            welcome_message = (
                f"👋 Halo {user_name}!\n\n"
                f"🔷 **Telegram Report Bot - OAuth2 Version**\n\n"
                f"📋 Pilih Jenis Laporan yang ingin dibuat:"
            )
            
            await update.message.reply_text(
                welcome_message,
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
                f"✅ Report Type: **{message_text}**\n\n🎫 Masukkan ID Ticket:",
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
            folder_name = f"{session['report_type']}_{ticket_id}_{datetime.now().strftime('%Y%m%d')}"
            
            # Send creating folder message
            creating_msg = await update.message.reply_text("📁 Membuat folder di Google Drive...")
            
            folder_id = self.google_service.create_folder(folder_name)
            
            if not folder_id:
                await update.message.reply_text("❌ Gagal membuat folder. Silakan coba lagi.")
                return INPUT_ID
            
            self.session_service.update_session(user_id, {'folder_id': folder_id})
            
            # Update creating message
            folder_link = self.google_service.get_folder_link(folder_id)
            
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=creating_msg.message_id,
                text="✅ Folder berhasil dibuat di Google Drive!"
            )
            
            # Send format
            report_format = (
                f"✅ **Format Laporan Berhasil Dibuat**\n\n"
                f"📋 **Info Laporan:**\n"
                f"• Report Type: {session['report_type']}\n"
                f"• ID Ticket: {ticket_id}\n"
                f"• Folder Drive: [Klik di sini]({folder_link})\n"
                f"• Dibuat: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                f"📝 **Salin dan Isi Format Berikut:**\n\n"
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
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Batalkan")]], resize_keyboard=True),
                parse_mode='Markdown'
            )
            return INPUT_DATA
            
        except Exception as e:
            logger.error(f"❌ Error in input_id: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan. Silakan /start ulang.")
            return ConversationHandler.END

    async def input_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle data input - improved version"""
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
            
            # Parse data from message
            data = {}
            lines = message_text.split('\n')
            
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    if value:  # Only add non-empty values
                        data[key] = value
            
            # Check required fields
            required_fields = ['Customer Name', 'Service No', 'Segment', 'Teknisi 1', 'Teknisi 2', 'STO', 'Valins ID']
            missing_fields = [field for field in required_fields if field not in data or not data[field]]
            
            if missing_fields:
                missing_list = '\n'.join([f"• {field}" for field in missing_fields])
                await update.message.reply_text(
                    f"❌ **Data Tidak Lengkap**\n\n"
                    f"Field berikut harus diisi:\n{missing_list}\n\n"
                    f"📝 Silakan kirim ulang format yang sudah diisi dengan lengkap.",
                    parse_mode='Markdown'
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
            
            # Show confirmation with photo info
            photo_info = ""
            if session.get('photos'):
                photo_info = f"\n📷 **Foto Terupload:** {len(session['photos'])} foto\n"
                for i, photo in enumerate(session['photos'], 1):
                    photo_info += f"   {i}. {photo['name']}\n"
            else:
                photo_info = "\n📷 **Foto Eviden:** Belum ada foto terupload\n"
            
            confirmation_text = (
                f"✅ **Konfirmasi Data Laporan**\n\n"
                f"📋 **Detail Laporan:**\n"
                f"• Report Type: {report_data['report_type']}\n"
                f"• ID Ticket: {report_data['id_ticket']}\n"
                f"• Customer Name: {report_data['customer_name']}\n"
                f"• Service No: {report_data['service_no']}\n"
                f"• Segment: {report_data['segment']}\n"
                f"• Teknisi 1: {report_data['teknisi_1']}\n"
                f"• Teknisi 2: {report_data['teknisi_2']}\n"
                f"• STO: {report_data['sto']}\n"
                f"• Valins ID: {report_data['valins_id']}"
                f"{photo_info}\n"
                f"🔧 **Pilih tindakan:**"
            )
            
            keyboard = [
                [KeyboardButton("✅ Kirim Laporan"), KeyboardButton("📝 Edit Data")],
                [KeyboardButton("📷 Upload Foto Eviden"), KeyboardButton("❌ Batalkan")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(
                confirmation_text, 
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return CONFIRM_DATA
            
        except Exception as e:
            logger.error(f"❌ Error in input_data: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan. Silakan /start ulang.")
            return ConversationHandler.END

    async def confirm_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle data confirmation"""
        try:
            user_id = update.effective_user.id
            choice = update.message.text
            
            session = self.session_service.get_session(user_id)
            if not session:
                await update.message.reply_text("❌ Session error. Silakan /start ulang.")
                return ConversationHandler.END
            
            if choice == "✅ Kirim Laporan":
                # Send processing message
                processing_msg = await update.message.reply_text("⏳ Mengirim laporan ke spreadsheet...")
                
                # Send to spreadsheet
                success = self.google_service.update_spreadsheet(
                    self.spreadsheet_id,
                    self.spreadsheet_config,
                    session['data']
                )
                
                if success:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=processing_msg.message_id,
                        text="✅ **Laporan berhasil dikirim!**\n\n"
                             "📊 Data sudah tersimpan di spreadsheet\n"
                             f"📁 Foto tersimpan di: [Google Drive]({session['data']['folder_link']})",
                        parse_mode='Markdown'
                    )
                    
                    await update.message.reply_text(
                        "🎉 Terima kasih! Laporan Anda telah berhasil disubmit.\n\n"
                        "Ketik /start untuk membuat laporan baru.",
                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
                    )
                else:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=processing_msg.message_id,
                        text="❌ Gagal mengirim laporan ke spreadsheet. Silakan coba lagi."
                    )
                
                self.session_service.end_session(user_id)
                return ConversationHandler.END
                
            elif choice == "❌ Batalkan":
                self.delete_folder_if_exists(user_id)
                self.session_service.end_session(user_id)
                await update.message.reply_text(
                    "❌ Laporan dibatalkan. Folder Google Drive telah dihapus.",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
                )
                return ConversationHandler.END

            elif choice == "📝 Edit Data":
                # Send format untuk edit
                report_format = (
                    f"📝 **Edit Data Laporan**\n\n"
                    f"📋 **Info Laporan:**\n"
                    f"• Report Type: {session['data']['report_type']}\n"
                    f"• ID Ticket: {session['data']['id_ticket']}\n"
                    f"• Folder Drive: [Klik di sini]({session['data']['folder_link']})\n\n"
                    f"📝 **Edit Format Berikut:**\n\n"
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
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Batalkan")]], resize_keyboard=True),
                    parse_mode='Markdown'
                )
                return INPUT_DATA
            
            elif choice == "📷 Upload Foto Eviden":
                await update.message.reply_text(
                    "📷 **Upload Foto Eviden**\n\n"
                    "⚡ **PENTING - Cara Upload Foto:**\n"
                    "• **Satu foto**: Kirim 1 foto → input deskripsi custom\n"
                    "• **Beberapa foto sekaligus**: Deskripsi akan otomatis random (foto_1, foto_2, dst)\n\n"
                    "🔧 **Pilih metode upload:**",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("🔸 Upload Satu-Satu (Custom Nama)")],
                        [KeyboardButton("📷 Upload Banyak (Auto Nama)")],
                        [KeyboardButton("❌ Batalkan")]
                    ], resize_keyboard=True),
                    parse_mode='Markdown'
                )
                return UPLOAD_PHOTO
                
        except Exception as e:
            logger.error(f"❌ Error in confirm_data: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan. Silakan /start ulang.")
            return ConversationHandler.END

    async def upload_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo upload state"""
        user_id = update.effective_user.id
        message_text = update.message.text
        
        # Handle pilihan metode upload
        if message_text == "🔸 Upload Satu-Satu (Custom Nama)":
            context.user_data['upload_mode'] = 'single'
            await update.message.reply_text(
                "🔸 **Mode Upload Satu-Satu**\n\n"
                "Kirimkan foto satu per satu. Setiap foto akan diminta deskripsi custom.\n\n"
                "📷 Kirimkan foto pertama:",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("Selesai Upload"), KeyboardButton("❌ Batalkan")]
                ], resize_keyboard=True),
                parse_mode='Markdown'
            )
            return UPLOAD_PHOTO
            
        elif message_text == "📷 Upload Banyak (Auto Nama)":
            context.user_data['upload_mode'] = 'multiple'
            await update.message.reply_text(
                "📷 **Mode Upload Banyak**\n\n"
                "Kirimkan beberapa foto sekaligus. Nama file akan otomatis: foto_1, foto_2, dst.\n\n"
                "📷 Kirimkan foto-foto Anda:",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("Selesai Upload"), KeyboardButton("❌ Batalkan")]
                ], resize_keyboard=True),
                parse_mode='Markdown'
            )
            return UPLOAD_PHOTO
        
        if message_text == "Selesai Upload":
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
                photo_info = f"\n📷 **Foto Terupload:** {len(session['photos'])} foto\n"
                for i, photo in enumerate(session['photos'], 1):
                    photo_info += f"   {i}. {photo['name']}\n"
            else:
                photo_info = "\n📷 **Foto Eviden:** Belum ada foto terupload\n"
            
            confirmation_text = (
                f"✅ **Konfirmasi Data Laporan**\n\n"
                f"📋 **Detail Laporan:**\n"
                f"• Report Type: {session['data']['report_type']}\n"
                f"• ID Ticket: {session['data']['id_ticket']}\n"
                f"• Customer Name: {session['data']['customer_name']}\n"
                f"• Service No: {session['data']['service_no']}\n"
                f"• Segment: {session['data']['segment']}\n"
                f"• Teknisi 1: {session['data']['teknisi_1']}\n"
                f"• Teknisi 2: {session['data']['teknisi_2']}\n"
                f"• STO: {session['data']['sto']}\n"
                f"• Valins ID: {session['data']['valins_id']}"
                f"{photo_info}\n"
                f"🔧 **Pilih tindakan:**"
            )
            
            keyboard = [
                [KeyboardButton("✅ Kirim Laporan"), KeyboardButton("📝 Edit Data")],
                [KeyboardButton("📷 Upload Foto Eviden"), KeyboardButton("❌ Batalkan")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(
                confirmation_text, 
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
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
                    "📝 **Masukkan Deskripsi Foto**\n\n"
                    "Deskripsi akan digunakan sebagai nama file.\n\n"
                    "💡 **Contoh:** 'foto_sebelum_perbaikan', 'hasil_instalasi', 'kondisi_kabel'",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("❌ Batalkan")]
                    ], resize_keyboard=True),
                    parse_mode='Markdown'
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
                    
                    # Validate downloaded file
                    if not os.path.exists(filepath):
                        raise Exception("File download failed")
                    
                    file_size = os.path.getsize(filepath)
                    if file_size == 0:
                        raise Exception("Downloaded file is empty")
                    
                    logger.info(f"📥 File downloaded: {filename} ({file_size} bytes)")
                    
                    # Upload to Drive
                    file_id = self.google_service.upload_to_drive(filepath, filename, session['folder_id'])
                    
                    # Clean up local file
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    
                    if file_id:
                        # Initialize photos list if not exists
                        if 'photos' not in session:
                            session['photos'] = []
                        
                        # Add to photo list
                        session['photos'].append({
                            'id': file_id,
                            'name': filename
                        })
                        
                        # Update session
                        self.session_service.update_session(user_id, {'photos': session['photos']})
                        
                        # Update processing message with success
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=processing_msg.message_id,
                            text=f"✅ **Foto berhasil diupload!**\n\n"
                                 f"📄 Nama file: `{filename}`\n"
                                 f"📷 Total foto: {len(session['photos'])}\n\n"
                                 f"Kirim foto lain atau ketik 'Selesai Upload'.",
                            parse_mode='Markdown'
                        )
                    else:
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=processing_msg.message_id,
                            text="❌ Gagal mengupload foto ke Google Drive. Silakan coba lagi."
                        )
                        
                except Exception as e:
                    logger.error(f"❌ Error uploading photo: {e}")
                    
                    # Clean up local file if exists
                    try:
                        if 'filepath' in locals() and os.path.exists(filepath):
                            os.remove(filepath)
                    except:
                        pass
                    
                    # Update processing message with error
                    try:
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=processing_msg.message_id,
                            text=f"❌ **Upload Gagal**\n\n"
                                 f"Error: {str(e)[:100]}...\n\n"
                                 f"Silakan coba lagi.",
                            parse_mode='Markdown'
                        )
                    except:
                        await update.message.reply_text(
                            "❌ Terjadi kesalahan saat mengupload foto. Silakan coba lagi."
                        )
                
                return UPLOAD_PHOTO
        else:
            # Handle non-photo messages in upload mode
            if 'upload_mode' not in context.user_data:
                await update.message.reply_text(
                    "❓ Silakan pilih metode upload terlebih dahulu."
                )
                return UPLOAD_PHOTO
            else:
                await update.message.reply_text(
                    "📷 Silakan kirim foto atau pilih 'Selesai Upload' jika sudah selesai."
                )
                return UPLOAD_PHOTO

    async def input_photo_desc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo description input"""
        user_id = update.effective_user.id
        description = update.message.text.strip()
        
        if description == "❌ Batalkan":
            # Kembali ke upload photo mode single
            await update.message.reply_text(
                "🔸 **Mode Upload Satu-Satu**\n\n"
                "Kirimkan foto satu per satu. Setiap foto akan diminta deskripsi custom.\n\n"
                "📷 Kirimkan foto:",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("Selesai Upload"), KeyboardButton("❌ Batalkan")]
                ], resize_keyboard=True),
                parse_mode='Markdown'
            )
            return UPLOAD_PHOTO
        
        if not description:
            await update.message.reply_text(
                "❌ Deskripsi tidak boleh kosong.\n\n📝 Silakan masukkan deskripsi foto:"
            )
            return INPUT_PHOTO_DESC
        
        # Clean description untuk nama file
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
                
                # Validate downloaded file
                if not os.path.exists(filepath):
                    raise Exception("File download failed")
                
                file_size = os.path.getsize(filepath)
                if file_size == 0:
                    raise Exception("Downloaded file is empty")
                
                logger.info(f"📥 File downloaded: {filename} ({file_size} bytes)")
                
                # Upload to Drive
                file_id = self.google_service.upload_to_drive(filepath, filename, session['folder_id'])
                
                # Clean up local file
                if os.path.exists(filepath):
                    os.remove(filepath)
                
                if file_id:
                    # Initialize photos list if not exists
                    if 'photos' not in session:
                        session['photos'] = []
                    
                    # Add to photo list
                    session['photos'].append({
                        'id': file_id,
                        'name': filename
                    })
                    
                    # Update session
                    self.session_service.update_session(user_id, {'photos': session['photos']})
                    
                    # Update processing message with success
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=processing_msg.message_id,
                        text=f"✅ **Foto berhasil diupload!**\n\n"
                             f"📄 Nama file: `{filename}`\n" 
                             f"📷 Total foto: {len(session['photos'])}\n\n"
                             f"Kirim foto lain atau ketik 'Selesai Upload'.",
                        parse_mode='Markdown'
                    )
                    
                    # Clear temp photo
                    if 'temp_photo' in context.user_data:
                        del context.user_data['temp_photo']
                    
                    return UPLOAD_PHOTO
                    
                else:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=processing_msg.message_id,
                        text="❌ Gagal mengupload foto ke Google Drive. Silakan coba lagi."
                    )
                    
            except Exception as e:
                logger.error(f"❌ Error uploading photo: {e}")
                
                # Clean up local file if exists
                try:
                    if 'filepath' in locals() and os.path.exists(filepath):
                        os.remove(filepath)
                except:
                    pass
                
                # Update processing message with error
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=processing_msg.message_id,
                        text=f"❌ **Upload Gagal**\n\n"
                             f"Error: {str(e)[:100]}...\n\n"
                             f"Silakan coba lagi.",
                        parse_mode='Markdown'
                    )
                except:
                    await update.message.reply_text(
                        "❌ Terjadi kesalahan saat mengupload foto. Silakan coba lagi."
                    )
        
        # Keep the reply markup for continuing uploads
        await update.message.reply_text(
            "📷 Kirimkan foto lain atau ketik 'Selesai Upload'.",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("Selesai Upload"), KeyboardButton("❌ Batalkan")]
            ], resize_keyboard=True)
        )
        
        return UPLOAD_PHOTO

    def delete_folder_if_exists(self, user_id):
        """Delete folder if session exists"""
        try:
            session = self.session_service.get_session(user_id)
            if session and session.get('folder_id'):
                # Ensure token is valid before deletion
                if self.google_service._ensure_token_valid():
                    self.google_service.service_drive.files().delete(
                        fileId=session['folder_id'],
                        supportsAllDrives=True,
                        supportsTeamDrives=True
                    ).execute()
                    logger.info(f"🗑️ Folder deleted for user {user_id}")
                else:
                    logger.warning(f"⚠️ Could not refresh token to delete folder for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error deleting folder: {e}")
