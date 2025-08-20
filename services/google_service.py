# services/google_service.py - FIXED VERSION WITHOUT SERVICE ACCOUNT STORAGE
import os
import json
import base64
import logging
import time
import io
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
from datetime import datetime

logger = logging.getLogger(__name__)

# Scopes untuk Google API
SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']

class GoogleService:
    def __init__(self, parent_folder_id="12EU8I2sbhzxyHaiBhoC2xjJ4jTXpYJfY"):
        self.service_drive = None
        self.service_sheets = None
        self.parent_folder_id = parent_folder_id
        self.owner_email = "ilhambintang9773@gmail.com"  # Your personal email
        
    def authenticate(self):
        """Authenticate with Google APIs using service account"""
        try:
            # Try to load from environment variable first
            service_account_key = os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY')
            
            if service_account_key:
                try:
                    # Decode base64 and load JSON
                    service_account_info = json.loads(base64.b64decode(service_account_key))
                    creds = service_account.Credentials.from_service_account_info(
                        service_account_info,
                        scopes=SCOPES
                    )
                    logger.info("✅ Using service account from environment variable")
                except Exception as e:
                    logger.error(f"❌ Error decoding service account from env var: {e}")
                    return False
            else:
                # Load from file (fallback)
                if os.path.exists('service-account.json'):
                    creds = service_account.Credentials.from_service_account_file(
                        'service-account.json',
                        scopes=SCOPES
                    )
                    logger.info("✅ Using service account from file")
                else:
                    logger.error("❌ No service account found (neither env var nor file)")
                    return False
            
            self.service_drive = build('drive', 'v3', credentials=creds)
            self.service_sheets = build('sheets', 'v4', credentials=creds)
            
            logger.info(f"✅ Google APIs authenticated successfully! Owner: {self.owner_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error authenticating with service account: {e}")
            return False

    def create_folder(self, folder_name, parent_folder_id=None):
        """Create folder in target drive (personal drive) directly"""
        try:
            parent_id = parent_folder_id or self.parent_folder_id
            
            # Create folder metadata
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id] if parent_id else []
            }
            
            # Create folder in target parent (which should be in personal drive)
            folder = self.service_drive.files().create(
                body=folder_metadata,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            folder_id = folder.get('id')
            logger.info(f"📁 Folder created: {folder_name} (ID: {folder_id})")
            
            return folder_id
            
        except Exception as e:
            logger.error(f"❌ Error creating folder: {e}")
            return None

    def upload_to_drive(self, file_path, file_name, folder_id):
        """
        STRATEGY: Upload directly to personal drive using in-memory approach
        This completely avoids service account storage
        """
        try:
            logger.info(f"📤 Starting memory-based upload: {file_name}")
            
            # Read file into memory
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            logger.info(f"📋 File loaded into memory: {len(file_content)} bytes")
            
            # Create file metadata for direct upload to target folder
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            # Create media upload from memory
            media_body = MediaIoBaseUpload(
                io.BytesIO(file_content),
                mimetype='image/jpeg',
                resumable=True,
                chunksize=1024*1024  # 1MB chunks
            )
            
            # Upload directly to target folder
            uploaded_file = self.service_drive.files().create(
                body=file_metadata,
                media_body=media_body,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            file_id = uploaded_file.get('id')
            
            if file_id:
                logger.info(f"✅ Direct upload successful: {file_name} -> {file_id}")
                return file_id
            else:
                raise Exception("No file ID returned from upload")
                
        except HttpError as e:
            error_details = e.error_details if hasattr(e, 'error_details') else str(e)
            logger.error(f"❌ Google API Error during upload: {error_details}")
            
            # Check for specific quota error
            if "storageQuotaExceeded" in str(e):
                logger.error("🚨 STORAGE QUOTA EXCEEDED!")
                logger.error("This means the target folder's owner (your personal account) is out of storage.")
                logger.error("Solutions:")
                logger.error("1. Free up space in your personal Google Drive")
                logger.error("2. Upgrade your Google Drive storage plan")
                logger.error("3. Use a different target folder with available storage")
                return None
                
            # Try alternative smaller upload method
            return self._upload_alternative_method(file_path, file_name, folder_id)
            
        except Exception as e:
            logger.error(f"❌ Error in memory-based upload: {e}")
            return self._upload_alternative_method(file_path, file_name, folder_id)

    def _upload_alternative_method(self, file_path, file_name, folder_id):
        """Alternative method: Create empty file then update content"""
        try:
            logger.info("🔄 Trying alternative upload method (create then update)...")
            
            # Step 1: Create empty file
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            empty_file = self.service_drive.files().create(
                body=file_metadata,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            file_id = empty_file.get('id')
            logger.info(f"📄 Empty file created: {file_id}")
            
            # Step 2: Update with actual content
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            media_body = MediaIoBaseUpload(
                io.BytesIO(file_content),
                mimetype='image/jpeg',
                resumable=True,
                chunksize=512*1024  # 512KB chunks (smaller)
            )
            
            updated_file = self.service_drive.files().update(
                fileId=file_id,
                media_body=media_body,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            logger.info(f"✅ Alternative upload successful: {file_id}")
            return file_id
            
        except Exception as alt_error:
            logger.error(f"❌ Alternative upload also failed: {alt_error}")
            
            # Try the most basic method
            return self._upload_basic_method(file_path, file_name, folder_id)

    def _upload_basic_method(self, file_path, file_name, folder_id):
        """Most basic upload method: tiny chunks, no resumable"""
        try:
            logger.info("🔄 Trying basic upload method (non-resumable)...")
            
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            # Check file size
            file_size = len(file_content)
            logger.info(f"📊 File size: {file_size} bytes")
            
            if file_size > 5 * 1024 * 1024:  # If > 5MB
                logger.error("❌ File too large for basic method")
                return None
            
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            # Non-resumable upload for small files
            media_body = MediaIoBaseUpload(
                io.BytesIO(file_content),
                mimetype='image/jpeg',
                resumable=False  # Non-resumable
            )
            
            uploaded_file = self.service_drive.files().create(
                body=file_metadata,
                media_body=media_body,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            file_id = uploaded_file.get('id')
            logger.info(f"✅ Basic upload successful: {file_id}")
            return file_id
            
        except Exception as basic_error:
            logger.error(f"❌ All upload methods failed: {basic_error}")
            return None

    def get_folder_link(self, folder_id):
        """Get shareable link for Google Drive folder"""
        return f"https://drive.google.com/drive/folders/{folder_id}"

    def update_spreadsheet(self, spreadsheet_id, spreadsheet_config, laporan_data):
        """Update Google Spreadsheet with report data"""
        try:
            row_data = spreadsheet_config.prepare_row_data(laporan_data, 0)
            
            body = {'values': [row_data]}
            
            result = self.service_sheets.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=spreadsheet_config.get_append_range(),
                valueInputOption='RAW',
                body=body
            ).execute()
            
            logger.info(f"✅ Successfully added row to spreadsheet")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating spreadsheet: {e}")
            return False

    def check_target_folder_permissions(self):
        """Check if we can write to the target folder"""
        try:
            logger.info("🔍 Checking target folder permissions...")
            
            # Check if we can access the target folder
            folder_info = self.service_drive.files().get(
                fileId=self.parent_folder_id,
                supportsAllDrives=True,
                fields="id,name,permissions,owners"
            ).execute()
            
            logger.info(f"📁 Target folder: {folder_info.get('name')} ({folder_info.get('id')})")
            
            # Try to create a test file directly in target folder
            test_metadata = {
                'name': f'test_permissions_{int(time.time())}.txt',
                'parents': [self.parent_folder_id]
            }
            
            test_content = "test"
            media_body = MediaIoBaseUpload(
                io.BytesIO(test_content.encode()),
                mimetype='text/plain',
                resumable=False
            )
            
            test_file = self.service_drive.files().create(
                body=test_metadata,
                media_body=media_body,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            test_file_id = test_file.get('id')
            
            # Clean up test file
            if test_file_id:
                self.service_drive.files().delete(
                    fileId=test_file_id,
                    supportsAllDrives=True,
                    supportsTeamDrives=True
                ).execute()
                
            logger.info("✅ Target folder permissions confirmed - we can upload directly!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Target folder permission test failed: {e}")
            return False

    def get_drive_usage_info(self):
        """Get drive usage information"""
        try:
            # Get about info
            about = self.service_drive.about().get(fields="storageQuota,user").execute()
            
            storage_quota = about.get('storageQuota', {})
            user_info = about.get('user', {})
            
            usage_info = {
                'user_email': user_info.get('emailAddress', 'Unknown'),
                'total_gb': int(storage_quota.get('limit', 0)) / (1024**3),
                'used_gb': int(storage_quota.get('usage', 0)) / (1024**3),
                'available_gb': (int(storage_quota.get('limit', 0)) - int(storage_quota.get('usage', 0))) / (1024**3)
            }
            
            logger.info(f"💾 Drive usage: {usage_info['used_gb']:.2f}GB / {usage_info['total_gb']:.2f}GB")
            logger.info(f"💿 Available: {usage_info['available_gb']:.2f}GB")
            
            return usage_info
            
        except Exception as e:
            logger.error(f"❌ Error getting drive usage: {e}")
            return None
