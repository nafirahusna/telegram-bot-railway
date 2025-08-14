import os
import re
import asyncio
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from datetime import datetime
from flask import Flask, request

# Import services
from services.google_service import GoogleService
from services.session_service import SessionService
from config.spreadsheet_config import SpreadsheetConfig

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# States untuk ConversationHandler
SELECT_REPORT_TYPE, INPUT_ID, INPUT_DATA, CONFIRM_DATA, UPLOAD_PHOTO, INPUT_PHOTO_DESC = range(6)

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

    def delete_folder_if_exists(self, user_id):
        """Delete folder if session exists"""
        session = self.session_service.get_session(user_id)
        if session and session.get('folder_id'):
            try:
                self.google_service.service_drive.files().delete(fileId=session['folder_id']).execute()
                print(f"Folder deleted for user {user_id}")
            except Exception as e:
                print(f"Error deleting folder: {e}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user_id = update.effective_user.id
        
        # DIPERBAIKI: Gunakan context.user_data untuk persistence
        context.user_data.clear()
        context.user_data['report_type'] = None
        context.user_data['id_ticket'] = None
        context.user_data['folder_id'] = None
        context.user_data['photos'] = []
        context.user_data['data'] = None
        context.user_data['created_at'] = datetime.now().isoformat()
        
        keyboard = [
            [KeyboardButton("Non B2B"), KeyboardButton("BGES")],
            [KeyboardButton("Squad")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text(
            "Pilih Jenis Laporan:",
            reply_markup=reply_markup
        )
        return SELECT_REPORT_TYPE

    async def select_report_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle report type selection"""
        user_id = update.effective_user.id
        message_text = update.message.text.strip()
        
        logger.info(f"User {user_id} input: '{message_text}'")
        
        # Handle normal report type selection
        valid_types = ['Non B2B', 'BGES', 'Squad']
        if message_text not in valid_types:
            logger.warning(f"Invalid input from user {user_id}: '{message_text}'")
            keyboard = [
                [KeyboardButton("Non B2B"), KeyboardButton("BGES")],
                [KeyboardButton("Squad")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(
                "❌ Pilihan tidak valid!\n\nSilakan pilih salah satu jenis laporan:",
                reply_markup=reply_markup
            )
            return SELECT_REPORT_TYPE
        
        # Simpan report type
        context.user_data['report_type'] = message_text
        logger.info(f"Report type saved: {message_text}")
        
        # Pindah ke INPUT_ID dengan keyboard baru
        cancel_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("❌ Batalkan")]], 
            resize_keyboard=True, 
            one_time_keyboard=True
        )
        
        await update.message.reply_text(
            f"✅ Jenis Laporan: {message_text}\n\n"
            "🎯 Silakan masukkan ID Ticket:",
            reply_markup=cancel_keyboard
        )
        return INPUT_ID  # PENTING: Return INPUT_ID bukan SELECT_REPORT_TYPE

    async def input_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle ID input"""
        user_id = update.effective_user.id
        ticket_id = update.message.text.strip()
        
        if ticket_id == "❌ Batalkan":
            # DIPERBAIKI: Cleanup dari context.user_data
            if context.user_data.get('folder_id'):
                try:
                    self.google_service.service_drive.files().delete(fileId=context.user_data['folder_id']).execute()
                    print(f"Folder deleted for user {user_id}")
                except Exception as e:
                    print(f"Error deleting folder: {e}")
            
            context.user_data.clear()
            await update.message.reply_text(
                "Laporan dibatalkan.",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
            )
            return ConversationHandler.END
        
        if not ticket_id:
            await update.message.reply_text("ID Ticket tidak boleh kosong. Silakan masukkan ID Ticket:")
            return INPUT_ID
        
        # DIPERBAIKI: Update context.user_data
        context.user_data['id_ticket'] = ticket_id
        
        # Buat folder di Google Drive
        folder_name = f"{context.user_data['report_type']}_{ticket_id}"
        folder_id = self.google_service.create_folder(folder_name)
        
        if not folder_id:
            await update.message.reply_text("Gagal membuat folder. Silakan coba lagi.")
            return INPUT_ID
        
        context.user_data['folder_id'] = folder_id
        
        # Kirim format pengisian
        folder_link = self.google_service.get_folder_link(folder_id)
        report_format = (
            f"📋 Format Berhasil Dibuat\n\n"
            f"Report Type : {context.user_data['report_type']}\n"
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

    async def input_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle data input"""
        user_id = update.effective_user.id
        message_text = update.message.text
        
        if message_text == "❌ Batalkan":
            # DIPERBAIKI: Cleanup dari context.user_data
            if context.user_data.get('folder_id'):
                try:
                    self.google_service.service_drive.files().delete(fileId=context.user_data['folder_id']).execute()
                    print(f"Folder deleted for user {user_id}")
                except Exception as e:
                    print(f"Error deleting folder: {e}")
            
            context.user_data.clear()
            await update.message.reply_text(
                "Laporan dibatalkan.",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
            )
            return ConversationHandler.END
        
        # Parse data dari format
        data = {}
        lines = message_text.split('\n')
        
        # Cari bagian setelah "Salin Format Laporan dan isi dibawah ini :"
        start_idx = next((i for i, line in enumerate(lines) if "Salin Format Laporan" in line), len(lines))
        
        for line in lines[start_idx+1:]:
            if ':' in line:
                key, value = line.split(':', 1)
                data[key.strip()] = value.strip()
        
        # Validasi data yang diperlukan
        required_fields = ['Customer Name', 'Service No', 'Segment', 'Teknisi 1', 'Teknisi 2', 'STO', 'Valins ID']
        missing_fields = [field for field in required_fields if field not in data or not data[field]]
        
        if missing_fields:
            await update.message.reply_text(
                f"Data tidak lengkap. Field berikut harus diisi: {', '.join(missing_fields)}\n\n"
                f"Silakan kirim ulang format yang sudah diisi dengan lengkap."
            )
            return INPUT_DATA
        
        # DIPERBAIKI: Simpan data ke context.user_data
        report_data = {
            'report_type': context.user_data['report_type'],
            'id_ticket': context.user_data['id_ticket'],
            'folder_link': self.google_service.get_folder_link(context.user_data['folder_id']),
            'reported': datetime.now().strftime("%d/%m/%Y %H:%M"),
            'customer_name': data['Customer Name'],
            'service_no': data['Service No'],
            'segment': data['Segment'],
            'teknisi_1': data['Teknisi 1'],
            'teknisi_2': data['Teknisi 2'],
            'sto': data['STO'],
            'valins_id': data['Valins ID']
        }
        
        context.user_data['data'] = report_data
        
        # Tampilkan konfirmasi dengan info foto
        photos = context.user_data.get('photos', [])
        photo_info = ""
        if photos:
            photo_info = f"\n📷 Foto Terupload: {len(photos)} foto\n"
            for i, photo in enumerate(photos, 1):
                photo_info += f"   {i}. {photo['name']}\n"
        else:
            photo_info = "\n📷 Foto Eviden: Belum ada foto terupload\n"
        
        confirmation_text = (
            f"📋 Konfirmasi Data Laporan\n\n"
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

    async def confirm_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle data confirmation"""
        user_id = update.effective_user.id
        choice = update.message.text
        
        if choice == "✅ Kirim Laporan":
            # Kirim ke spreadsheet
            success = self.google_service.update_spreadsheet(
                self.spreadsheet_id,
                self.spreadsheet_config,
                context.user_data['data']
            )
            
            if success:
                photos = context.user_data.get('photos', [])
                photo_count = len(photos)
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
            
            context.user_data.clear()
            return ConversationHandler.END
            
        elif choice == "📝 Edit Data":
            # Kirim ulang format untuk diedit
            report_format = (
                f"📝 Edit Data Laporan\n\n"
                f"Report Type : {context.user_data['data']['report_type']}\n"
                f"ID Ticket : {context.user_data['data']['id_ticket']}\n"
                f"Folder Drive : {context.user_data['data']['folder_link']}\n"
                f"-------------------------------------------------------------\n"
                f"Salin Format Laporan dan edit dibawah ini :\n\n"
                f"Customer Name : {context.user_data['data']['customer_name']}\n"
                f"Service No : {context.user_data['data']['service_no']}\n"
                f"Segment : {context.user_data['data']['segment']}\n"
                f"Teknisi 1 : {context.user_data['data']['teknisi_1']}\n"
                f"Teknisi 2 : {context.user_data['data']['teknisi_2']}\n"
                f"STO : {context.user_data['data']['sto']}\n"
                f"Valins ID : {context.user_data['data']['valins_id']}"
            )
            
            await update.message.reply_text(
                report_format,
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Batalkan")]], resize_keyboard=True)
            )
            return INPUT_DATA
            
        elif choice == "📷 Upload Foto Eviden":
            await update.message.reply_text(
                "📷 Upload Foto Eviden\n\n"
                "⚠️ PENTING - Cara Upload Foto:\n"
                "• Satu foto: Kirim 1 foto → input deskripsi custom\n"
                "• Beberapa foto sekaligus: Deskripsi akan otomatis random (foto_1, foto_2, dst)\n\n"
                "📋 Pilih metode upload:",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("📸 Upload Satu-Satu (Custom Nama)")],
                    [KeyboardButton("📷 Upload Banyak (Auto Nama)")],
                    [KeyboardButton("❌ Batalkan")]
                ], resize_keyboard=True)
            )
            return UPLOAD_PHOTO
            
        elif choice == "❌ Batalkan":
            # DIPERBAIKI: Cleanup dari context.user_data
            if context.user_data.get('folder_id'):
                try:
                    self.google_service.service_drive.files().delete(fileId=context.user_data['folder_id']).execute()
                    print(f"Folder deleted for user {user_id}")
                except Exception as e:
                    print(f"Error deleting folder: {e}")
                    
            context.user_data.clear()
            await update.message.reply_text(
                "Laporan dibatalkan.",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
            )
            return ConversationHandler.END

    async def upload_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo upload state"""
        user_id = update.effective_user.id
        message_text = update.message.text
        
        # Handle pilihan metode upload
        if message_text == "📸 Upload Satu-Satu (Custom Nama)":
            context.user_data['upload_mode'] = 'single'
            await update.message.reply_text(
                "📸 Mode Upload Satu-Satu\n\n"
                "Kirimkan foto satu per satu. Setiap foto akan diminta deskripsi custom.\n\n"
                "Kirimkan foto pertama:",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("Selesai Upload"), KeyboardButton("❌ Batalkan")]
                ], resize_keyboard=True)
            )
            return UPLOAD_PHOTO
            
        elif message_text == "📷 Upload Banyak (Auto Nama)":
            context.user_data['upload_mode'] = 'multiple'
            await update.message.reply_text(
                "📷 Mode Upload Banyak\n\n"
                "Kirimkan beberapa foto sekaligus. Nama file akan otomatis: foto_1, foto_2, dst.\n\n"
                "Kirimkan foto-foto Anda:",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("Selesai Upload"), KeyboardButton("❌ Batalkan")]
                ], resize_keyboard=True)
            )
            return UPLOAD_PHOTO
        
        if message_text == "Selesai Upload":
            if 'upload_mode' in context.user_data:
                del context.user_data['upload_mode']
            
            # Kembali ke konfirmasi data dengan info foto terbaru
            photos = context.user_data.get('photos', [])
            photo_info = ""
            if photos:
                photo_info = f"\n📷 Foto Terupload: {len(photos)} foto\n"
                for i, photo in enumerate(photos, 1):
                    photo_info += f"   {i}. {photo['name']}\n"
            else:
                photo_info = "\n📷 Foto Eviden: Belum ada foto terupload\n"
            
            confirmation_text = (
                f"📋 Konfirmasi Data Laporan\n\n"
                f"Report Type: {context.user_data['data']['report_type']}\n"
                f"ID Ticket: {context.user_data['data']['id_ticket']}\n"
                f"Customer Name: {context.user_data['data']['customer_name']}\n"
                f"Service No: {context.user_data['data']['service_no']}\n"
                f"Segment: {context.user_data['data']['segment']}\n"
                f"Teknisi 1: {context.user_data['data']['teknisi_1']}\n"
                f"Teknisi 2: {context.user_data['data']['teknisi_2']}\n"
                f"STO: {context.user_data['data']['sto']}\n"
                f"Valins ID: {context.user_data['data']['valins_id']}"
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
                
            if context.user_data.get('folder_id'):
                try:
                    self.google_service.service_drive.files().delete(fileId=context.user_data['folder_id']).execute()
                    print(f"Folder deleted for user {user_id}")
                except Exception as e:
                    print(f"Error deleting folder: {e}")
                    
            context.user_data.clear()
            await update.message.reply_text(
                "Laporan dibatalkan.",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
            )
            return ConversationHandler.END
        
        # Handle photo message
        if update.message.photo:
            upload_mode = context.user_data.get('upload_mode', 'single')
            
            if upload_mode == 'single':
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
                if not context.user_data.get('folder_id'):
                    await update.message.reply_text(
                        "❌ Session tidak valid. Silakan mulai ulang.",
                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True)
                    )
                    return ConversationHandler.END
                
                photo = update.message.photo[-1]
                try:
                    file = await context.bot.get_file(photo.file_id)
                    
                    photos = context.user_data.get('photos', [])
                    photo_count = len(photos) + 1
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"foto_{photo_count}_{timestamp}.jpg"
                    filepath = f"temp_{filename}"
                    
                    await file.download_to_drive(filepath)
                    
                    file_id = self.google_service.upload_to_drive(filepath, filename, context.user_data['folder_id'])
                    
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    
                    if file_id:
                        photos.append({
                            'id': file_id,
                            'name': filename
                        })
                        context.user_data['photos'] = photos
                        
                        await update.message.reply_text(
                            f"✅ Foto '{filename}' berhasil diupload!\n\n"
                            f"📷 Total foto terupload: {len(photos)}\n\n"
                            f"Kirim foto lain atau ketik 'Selesai Upload'."
                        )
                    else:
                        await update.message.reply_text(
                            "❌ Gagal mengupload foto. Silakan coba lagi."
                        )
                        
                except Exception as e:
                    print(f"Error uploading photo: {e}")
                    await update.message.reply_text(
                        "❌ Terjadi kesalahan saat mengupload foto. Silakan coba lagi."
                    )
                
                return UPLOAD_PHOTO
        else:
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

    async def input_photo_desc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo description input"""
        user_id = update.effective_user.id
        description = update.message.text.strip()
        
        if description == "❌ Batalkan":
            await update.message.reply_text(
                "📸 Mode Upload Satu-Satu\n\n"
                "Kirimkan foto satu per satu. Setiap foto akan diminta deskripsi custom.\n\n"
                "Kirimkan foto:",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("Selesai Upload"), KeyboardButton("❌ Batalkan")]
                ], resize_keyboard=True)
            )
            return UPLOAD_PHOTO
        
        if not description:
            await update.message.reply_text("Deskripsi tidak boleh kosong. Silakan masukkan deskripsi foto:")
            return INPUT_PHOTO_DESC
        
        # Clean description untuk nama file
        clean_desc = re.sub(r'[^\w\s-]', '', description).strip()
        clean_desc = re.sub(r'[\s]+', '_', clean_desc)
        
        # Process foto yang disimpan sementara
        temp_photo = context.user_data.get('temp_photo')
        
        if temp_photo and context.user_data.get('folder_id'):
            try:
                file = await context.bot.get_file(temp_photo.file_id)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{clean_desc}_{timestamp}.jpg"
                filepath = f"temp_{filename}"
                
                await file.download_to_drive(filepath)
                
                file_id = self.google_service.upload_to_drive(filepath, filename, context.user_data['folder_id'])
                
                if os.path.exists(filepath):
                    os.remove(filepath)
                
                if file_id:
                    photos = context.user_data.get('photos', [])
                    photos.append({
                        'id': file_id,
                        'name': filename
                    })
                    context.user_data['photos'] = photos
                    
                    await update.message.reply_text(
                        f"✅ Foto '{filename}' berhasil diupload!\n\n"
                        f"📷 Total foto terupload: {len(photos)}\n\n"
                        f"Kirim foto lain atau ketik 'Selesai Upload'.",
                        reply_markup=ReplyKeyboardMarkup([
                            [KeyboardButton("Selesai Upload"), KeyboardButton("❌ Batalkan")]
                        ], resize_keyboard=True)
                    )
                else:
                    await update.message.reply_text(
                        "❌ Gagal mengupload foto. Silakan coba lagi.",
                        reply_markup=ReplyKeyboardMarkup([
                            [KeyboardButton("Selesai Upload"), KeyboardButton("❌ Batalkan")]
                        ], resize_keyboard=True)
                    )
            except Exception as e:
                print(f"Error uploading photo: {e}")
                await update.message.reply_text(
                    "❌ Terjadi kesalahan saat mengupload foto. Silakan coba lagi.",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("Selesai Upload"), KeyboardButton("❌ Batalkan")]
                    ], resize_keyboard=True)
                )
        
        # Clear temp photo
        if 'temp_photo' in context.user_data:
            del context.user_data['temp_photo']
        
        return UPLOAD_PHOTO

    def create_application(self):
        """Create telegram application"""
        application = Application.builder().token(self.token).build()
        
        # Conversation handler
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('start', self.start)
            ],
            states={
                SELECT_REPORT_TYPE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.select_report_type
                    )
                ],
                INPUT_ID: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.input_id
                    )
                ],
                INPUT_DATA: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.input_data
                    )
                ],
                CONFIRM_DATA: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.confirm_data
                    )
                ],
                UPLOAD_PHOTO: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.upload_photo
                    ),
                    MessageHandler(
                        filters.PHOTO,
                        self.upload_photo
                    )
                ],
                INPUT_PHOTO_DESC: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.input_photo_desc
                    )
                ]
            },
            fallbacks=[CommandHandler('start', self.start)],
            allow_reentry=True
        )
        
        # Add handlers
        application.add_handler(conv_handler)
        return application

# Flask app untuk webhook Railway
app = Flask(__name__)

# DIPERBAIKI: Sederhana tanpa global persistence yang kompleks
bot_instance = None
application_instance = None

def get_bot_application():
    """Get or create bot and application instances"""
    global bot_instance, application_instance
    
    if bot_instance is None:
        BOT_TOKEN = os.getenv("BOT_TOKEN")
        SPREADSHEET_ID = os.getenv("SPREADSHEET_ID") 
        
        if not BOT_TOKEN or not SPREADSHEET_ID:
            raise ValueError("BOT_TOKEN dan SPREADSHEET_ID harus diset!")
            
        bot_instance = TelegramBot(BOT_TOKEN, SPREADSHEET_ID)
        application_instance = bot_instance.create_application()
        
    return application_instance

@app.route('/')
def index():
    return "Telegram Bot is running!"

@app.route('/debug')
def debug():
    """Debug endpoint to check environment variables"""
    try:
        bot_token = os.getenv("BOT_TOKEN")
        spreadsheet_id = os.getenv("SPREADSHEET_ID")
        google_creds = os.getenv("GOOGLE_CREDENTIALS_BASE64")
        
        return {
            "bot_token": "SET" if bot_token else "NOT SET",
            "spreadsheet_id": "SET" if spreadsheet_id else "NOT SET", 
            "google_credentials": "SET" if google_creds else "NOT SET",
            "google_creds_length": len(google_creds) if google_creds else 0
        }
    except Exception as e:
        return {"error": str(e)}

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook endpoint for Telegram"""
    try:
        application = get_bot_application()
        
        # Process update
        update_data = request.get_json()
        logger.info(f"Received update: {update_data}")
        
        if update_data:
            logger.info(f"Processing update: {update_data}")
            update = Update.de_json(update_data, application.bot)
            
            # DIPERBAIKI: Proses update dengan event loop yang benar
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                async def process():
                    # Initialize application jika belum
                    if not application.running:
                        await application.initialize()
                        await application.start()
                    
                    # Process update
                    await application.process_update(update)
                
                loop.run_until_complete(process())
            finally:
                loop.close()
        
        return "OK", 200
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return "Error", 500

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Set webhook URL"""
    try:
        BOT_TOKEN = os.getenv("BOT_TOKEN")
        
        if not BOT_TOKEN:
            return {"error": "BOT_TOKEN not found"}, 500
        
        # Get Railway URL from environment or use default
        railway_url = os.getenv('RAILWAY_STATIC_URL') or os.getenv('RAILWAY_PUBLIC_DOMAIN')
        
        if not railway_url:
            # Try to construct from request
            railway_url = request.url_root.rstrip('/')
        
        webhook_url = f"{railway_url}/webhook"
        logger.info(f"Setting webhook to: {webhook_url}")
        
        import requests
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            json={"url": webhook_url}
        )
        
        result = response.json()
        logger.info(f"Webhook response: {result}")
        return result
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
        return {"error": str(e)}, 500

if __name__ == "__main__":
    # Untuk development lokal
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
