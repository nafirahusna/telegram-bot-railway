# bot.py - Main bot logic (FIXED VERSION)
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
        
        # Initialize services
        self.google_service = GoogleService()
        self.session_service = SessionService(self.google_service)
        self.spreadsheet_config = SpreadsheetConfig()
        
        # Authenticate Google
        if not self.google_service.authenticate():
            raise Exception("Failed to authenticate Google APIs")
        
        # Initialize Telegram Application
        self.application = Application.builder().token(self.token).build()
        self._setup_handlers()
        
        logger.info("✅ TelegramBot initialized successfully")

    def _setup_handlers(self):
        """Setup conversation handlers"""
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

    async def process_update(self, update):
        """Process incoming update asynchronously"""
        try:
            logger.info(f"🔄 Processing update for user: {update.effective_user.id if update.effective_user else 'Unknown'}")
            await self.application.process_update(update)
            logger.info("✅ Update processed successfully")
        except Exception as e:
            logger.error(f"❌ Error processing update: {e}")
            # Try to send error message to user if possible
            try:
                if update.effective_chat:
                    await self.application.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ Terjadi kesalahan sistem. Silakan coba lagi dengan /start"
                    )
            except:
                pass  # If we can't send error message, just log it

    def delete_folder_if_exists(self, user_id):
        """Delete folder if session exists"""
        session = self.session_service.get_session(user_id)
        if session and session.get('folder_id'):
            try:
                self.google_service.service_drive.files().delete(fileId=session['folder_id']).execute()
                logger.info(f"🗑️ Folder deleted for user {user_id}")
            except Exception as e:
                logger.error(f"❌ Error deleting folder: {e}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user_id = update.effective_user.id
        logger.info(f"👤 User {user_id} started bot")
        
        try:
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
        user_id = update.effective_user.id
        message_text = update.message.text
        
        logger.info(f"📝 User {user_id} selected: {message_text}")
        
        try:
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
        user_id = update.effective_user.id
        ticket_id = update.message.text.strip()
        
        logger.info(f"🎫 User {user_id} entered ticket ID: {ticket_id}")
        
        try:
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
        """Handle data input"""
        user_id = update.effective_user.id
        message_text = update.message.text
        
        try:
            if message_text == "❌ Batalkan":
                self.delete_folder_if_exists(user_id)
                self.session_service.end_session(user_id)
                await update.message.reply_text(
                    "❌ Laporan dibatalkan.",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
                )
                return ConversationHandler.END
            
            # Parse data from format
            data = {}
            lines = message_text.split('\n')
            
            # Find section after "Salin Format Laporan dan isi dibawah ini :"
            start_idx = next((i for i, line in enumerate(lines) if "Salin Format Laporan" in line), len(lines))
            
            for line in lines[start_idx+1:]:
                if ':' in line:
                    key, value = line.split(':', 1)
                    data[key.strip()] = value.strip()
            
            # Validate required fields
            required_fields = ['Customer Name', 'Service No', 'Segment', 'Teknisi 1', 'Teknisi 2', 'STO', 'Valins ID']
            missing_fields = [field for field in required_fields if field not in data or not data[field]]
            
            if missing_fields:
                await update.message.reply_text(
                    f"❌ Data tidak lengkap. Field berikut harus diisi: {', '.join(missing_fields)}\n\n"
                    f"Silakan kirim ulang format yang sudah diisi dengan lengkap."
                )
                return INPUT_DATA
            
            # Save data to session
            session = self.session_service.get_session(user_id)
            if not session:
                await update.message.reply_text("❌ Session error. Silakan /start ulang.")
                return ConversationHandler.END
                
            report_data = {
                'report_type': session['report_type'],
                'id_ticket': session['id_ticket'],
                'folder_link': self.google_service.get_folder_link(session['folder_id']),
                'reported': datetime.now().strftime("%d/%m/%Y %H:%M"),
                'customer_name': data['Customer Name'],
                'service_no': data['Service No'],
                'segment': data['Segment'],
                'teknisi_1': data['Teknisi 1'],
                'teknisi_2': data['Teknisi 2'],
                'sto': data['STO'],
                'valins_id': data['Valins ID']
            }
            
            self.session_service.update_session(user_id, {'data': report_data})
            
            # Show confirmation
            session = self.session_service.get_session(user_id)
            photo_info = ""
            if session['photos']:
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
        """Handle data confirmation"""
        user_id = update.effective_user.id
        choice = update.message.text
        
        try:
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
                    photo_count = len(session['photos'])
                    success_message = "✅ Laporan berhasil dikirim ke spreadsheet!"
                    if photo_count > 0:
                        success_message += f"\n📷 {photo_count} foto eviden tersimpan di folder Drive."
                    
                    await update.message.reply_text(
                        success_message,
                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
                    )
                else:
                    await update.message.reply_text(
                        "❌ Gagal mengirim laporan. Silakan coba lagi.",
                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
                    )
                
                self.session_service.end_session(user_id)
                return ConversationHandler.END
                
            elif choice == "📝 Edit Data":
                # Send format again for editing
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
                await update.message.reply_text(
                    "📷 **Upload Foto Eviden**\n\n"
                    "⚠️ **PENTING - Cara Upload Foto:**\n"
                    "• **Satu foto**: Kirim 1 foto → input deskripsi custom\n"
                    "• **Beberapa foto sekaligus**: Deskripsi akan otomatis random (foto_1, foto_2, dst)\n\n"
                    "📋 **Pilih metode upload:**",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("🔸 Upload Satu-Satu (Custom Nama)")],
                        [KeyboardButton("📷 Upload Banyak (Auto Nama)")],
                        [KeyboardButton("❌ Batalkan")]
                    ], resize_keyboard=True)
                )
                return UPLOAD_PHOTO
                
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

    async def upload_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo upload state"""
        user_id = update.effective_user.id
        message_text = update.message.text
        
        try:
            # Handle upload mode selection
            if message_text == "🔸 Upload Satu-Satu (Custom Nama)":
                context.user_data['upload_mode'] = 'single'
                await update.message.reply_text(
                    "🔸 **Mode Upload Satu-Satu**\n\n"
                    "Kirimkan foto satu per satu. Setiap foto akan diminta deskripsi custom.\n\n"
                    "Kirimkan foto pertama:",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("✅ Selesai Upload"), KeyboardButton("❌ Batalkan")]
                    ], resize_keyboard=True)
                )
                return UPLOAD_PHOTO
                
            elif message_text == "📷 Upload Banyak (Auto Nama)":
                context.user_data['upload_mode'] = 'multiple'
                await update.message.reply_text(
                    "📷 **Mode Upload Banyak**\n\n"
                    "Kirimkan beberapa foto sekaligus. Nama file akan otomatis: foto_1, foto_2, dst.\n\n"
                    "Kirimkan foto-foto Anda:",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("✅ Selesai Upload"), KeyboardButton("❌ Batalkan")]
                    ], resize_keyboard=True)
                )
                return UPLOAD_PHOTO
            
            if message_text == "✅ Selesai Upload":
                # Reset upload mode
                if 'upload_mode' in context.user_data:
                    del context.user_data['upload_mode']
                
                # Back to confirmation with updated photo info
                session = self.session_service.get_session(user_id)
                if not session:
                    await update.message.reply_text("❌ Session error. Silakan /start ulang.")
                    return ConversationHandler.END
                    
                photo_info = ""
                if session['photos']:
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
                    # Single upload mode - ask for description
                    photo = update.message.photo[-1]
                    context.user_data['temp_photo'] = photo
                    
                    await update.message.reply_text(
                        "📝 Masukkan deskripsi untuk foto ini (akan digunakan sebagai nama file):\n\n"
                        "Contoh: 'foto_sebelum_perbaikan', 'hasil_instalasi', dll",
                        reply_markup=ReplyKeyboardMarkup([
                            [KeyboardButton("❌ Batalkan")]
                        ], resize_keyboard=True)
                    )
                    return INPUT_PHOTO_DESC
                
                elif upload_mode == 'multiple':
                    # Multiple upload mode - process directly with auto name
                    session = self.session_service.get_session(user_id)
                    if not session or not session.get('folder_id'):
                        await update.message.reply_text(
                            "❌ Session tidak valid. Silakan mulai ulang.",
                            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
                        )
                        return ConversationHandler.END
                    
                    photo = update.message.photo[-1]
                    try:
                        file = await context.bot.get_file(photo.file_id)
                        
                        # Generate auto name
                        photo_count = len(session['photos']) + 1
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"foto_{photo_count}_{timestamp}.jpg"
                        filepath = f"temp_{filename}"
                        
                        await file.download_to_drive(filepath)
                        
                        file_id = self.google_service.upload_to_drive(filepath, filename, session['folder_id'])
                        
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        
                        if file_id:
                            # Add to photo list
                            session['photos'].append({
                                'id': file_id,
                                'name': filename
                            })
                            self.session_service.update_session(user_id, {'photos': session['photos']})
                            
                            await update.message.reply_text(
                                f"✅ Foto '{filename}' berhasil diupload!\n\n"
                                f"📷 Total foto terupload: {len(session['photos'])}\n\n"
                                f"Kirim foto lain atau ketik 'Selesai Upload'."
                            )
                        else:
                            await update.message.reply_text(
                                "❌ Gagal mengupload foto. Silakan coba lagi."
                            )
                            
                    except Exception as e:
                        logger.error(f"Error uploading photo: {e}")
                        await update.message.reply_text(
                            "❌ Terjadi kesalahan saat mengupload foto. Silakan coba lagi."
                        )
                    
                    return UPLOAD_PHOTO
            else:
                # No upload mode selected yet
                if 'upload_mode' not in context.user_data:
                    await update.message.reply_text(
                        "Silakan pilih metode upload terlebih dahulu."
                    )
                    return UPLOAD_PHOTO
                else:
                    await update.message.reply_text(
                        "Silakan kirim foto atau pilih 'Selesai Upload' jika sudah selesai."
                    )
                    return UPLOAD_PHOTO
        except Exception as e:
            logger.error(f"❌ Error in upload_photo: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan. Silakan /start ulang.")
            return ConversationHandler.END

    async def input_photo_desc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo description input"""
        user_id = update.effective_user.id
        description = update.message.text.strip()
        
        try:
            if description == "❌ Batalkan":
                # Back to single upload mode
                await update.message.reply_text(
                    "🔸 **Mode Upload Satu-Satu**\n\n"
                    "Kirimkan foto satu per satu. Setiap foto akan diminta deskripsi custom.\n\n"
                    "Kirimkan foto:",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("✅ Selesai Upload"), KeyboardButton("❌ Batalkan")]
                    ], resize_keyboard=True)
                )
                return UPLOAD_PHOTO
            
            if not description:
                await update.message.reply_text("❌ Deskripsi tidak boleh kosong. Silakan masukkan deskripsi foto:")
                return INPUT_PHOTO_DESC
            
            # Clean description for filename
            clean_desc = re.sub(r'[^\w\s-]', '', description).strip()
            clean_desc = re.sub(r'[\s]+', '_', clean_desc)
            
            # Process temporarily saved photo
            session = self.session_service.get_session(user_id)
            temp_photo = context.user_data.get('temp_photo')
            
            if temp_photo and session and session.get('folder_id'):
                try:
                    file = await context.bot.get_file(temp_photo.file_id)
                    
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"{clean_desc}_{timestamp}.jpg"
                    filepath = f"temp_{filename}"
                    
                    await file.download_to_drive(filepath)
                    
                    file_id = self.google_service.upload_to_drive(filepath, filename, session['folder_id'])
                    
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    
                    if file_id:
                        # Add to photo list
                        session['photos'].append({
                            'id': file_id,
                            'name': filename
                        })
                        self.session_service.update_session(user_id, {'photos': session['photos']})
                        
                        await update.message.reply_text(
                            f"✅ Foto '{filename}' berhasil diupload!\n\n"
                            f"📷 Total foto terupload: {len(session['photos'])}\n\n"
                            f"Kirim foto lain atau ketik 'Selesai Upload'.",
                            reply_markup=ReplyKeyboardMarkup([
                                [KeyboardButton("✅ Selesai Upload"), KeyboardButton("❌ Batalkan")]
                            ], resize_keyboard=True)
                        )
                    else:
                        await update.message.reply_text(
                            "❌ Gagal mengupload foto. Silakan coba lagi.",
                            reply_markup=ReplyKeyboardMarkup([
                                [KeyboardButton("✅ Selesai Upload"), KeyboardButton("❌ Batalkan")]
                            ], resize_keyboard=True)
                        )
                except Exception as e:
                    logger.error(f"Error uploading photo: {e}")
                    await update.message.reply_text(
                        "❌ Terjadi kesalahan saat mengupload foto. Silakan coba lagi.",
                        reply_markup=ReplyKeyboardMarkup([
                            [KeyboardButton("✅ Selesai Upload"), KeyboardButton("❌ Batalkan")]
                        ], resize_keyboard=True)
                    )
            
            # Clear temp photo
            if 'temp_photo' in context.user_data:
                del context.user_data['temp_photo']
            
            return UPLOAD_PHOTO
        except Exception as e:
            logger.error(f"❌ Error in input_photo_desc: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan. Silakan /start ulang.")
            return ConversationHandler.END
