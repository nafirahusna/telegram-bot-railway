# services/google_service.py - FIXED VERSION WITH UPLOAD-TRANSFER-DELETE STRATEGY
import os
import json
import base64
import logging
import time
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload
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
        self.owner_email = "muhamadsidiq2@gmail.com"  # Your personal email
        
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
        NEW STRATEGY: Upload -> Move to target folder -> Delete original
        This avoids service account storage quota issues
        """
        temp_file_id = None
        
        try:
            logger.info(f"📤 Starting upload: {file_name}")
            
            # STEP 1: Upload file to service account's My Drive (temporary)
            file_metadata = {
                'name': f"temp_{int(time.time())}_{file_name}"  # Temporary name
            }
            
            media = MediaFileUpload(file_path, resumable=True)
            
            # Upload to service account's root (no parents = My Drive)
            temp_file = self.service_drive.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            temp_file_id = temp_file.get('id')
            logger.info(f"📤 Temporary file uploaded: {temp_file_id}")
            
            if not temp_file_id:
                raise Exception("Failed to get temp file ID")
            
            # STEP 2: Copy file to target folder with final name
            copy_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            final_file = self.service_drive.files().copy(
                fileId=temp_file_id,
                body=copy_metadata,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            final_file_id = final_file.get('id')
            logger.info(f"📋 File copied to target folder: {final_file_id}")
            
            # STEP 3: Delete temporary file from service account
            try:
                self.service_drive.files().delete(
                    fileId=temp_file_id,
                    supportsAllDrives=True,
                    supportsTeamDrives=True
                ).execute()
                logger.info(f"🗑️ Temporary file deleted from service account")
            except Exception as delete_error:
                logger.warning(f"⚠️ Could not delete temp file: {delete_error}")
                # Don't fail the whole process for this
            
            logger.info(f"✅ Upload complete: {file_name} -> {final_file_id}")
            return final_file_id
            
        except Exception as e:
            logger.error(f"❌ Error in upload process: {e}")
            
            # Cleanup: Delete temp file if it exists
            if temp_file_id:
                try:
                    self.service_drive.files().delete(
                        fileId=temp_file_id,
                        supportsAllDrives=True
                    ).execute()
                    logger.info(f"🧹 Cleaned up temp file: {temp_file_id}")
                except:
                    logger.warning(f"⚠️ Could not clean up temp file: {temp_file_id}")
            
            # Try alternative method if main method fails
            return self._upload_alternative_method(file_path, file_name, folder_id)

    def _upload_alternative_method(self, file_path, file_name, folder_id):
        """Alternative upload method using direct folder upload"""
        try:
            logger.info("🔄 Trying alternative upload method...")
            
            # Try direct upload to target folder
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            # Use smaller chunk size for better reliability
            media = MediaFileUpload(
                file_path, 
                resumable=True,
                chunksize=1024*1024  # 1MB chunks
            )
            
            uploaded_file = self.service_drive.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            file_id = uploaded_file.get('id')
            logger.info(f"✅ Alternative upload successful: {file_id}")
            return file_id
            
        except Exception as alt_error:
            logger.error(f"❌ Alternative upload failed: {alt_error}")
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

    def check_upload_permissions(self):
        """Check if we can upload to the target folder"""
        try:
            logger.info("🔍 Checking upload permissions...")
            
            # Test creating a small text file
            test_content = "test file"
            test_file_path = "test_upload.txt"
            
            # Create test file
            with open(test_file_path, 'w') as f:
                f.write(test_content)
            
            # Try to upload to parent folder
            file_metadata = {
                'name': f"test_{int(time.time())}.txt",
                'parents': [self.parent_folder_id] if self.parent_folder_id else []
            }
            
            media = MediaFileUpload(test_file_path)
            
            test_file = self.service_drive.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True
            ).execute()
            
            test_file_id = test_file.get('id')
            
            # Clean up test file
            if test_file_id:
                self.service_drive.files().delete(
                    fileId=test_file_id,
                    supportsAllDrives=True
                ).execute()
            
            os.remove(test_file_path)
            
            logger.info("✅ Upload permissions confirmed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Upload permission test failed: {e}")
            
            # Clean up test file if it exists
            try:
                if os.path.exists(test_file_path):
                    os.remove(test_file_path)
            except:
                pass
                
            return False

    def get_service_account_usage(self):
        """Check current usage of service account"""
        try:
            # Get files owned by service account
            results = self.service_drive.files().list(
                q="'me' in owners",
                pageSize=100,
                fields="files(id, name, size)"
            ).execute()
            
            files = results.get('files', [])
            total_size = sum(int(file.get('size', 0)) for file in files)
            
            logger.info(f"📊 Service account usage: {len(files)} files, {total_size / (1024*1024):.2f} MB")
            
            return {
                'file_count': len(files),
                'total_size_mb': total_size / (1024*1024),
                'files': files
            }
            
        except Exception as e:
            logger.error(f"❌ Error checking service account usage: {e}")
            return None

    def cleanup_service_account_files(self):
        """Clean up any remaining files in service account"""
        try:
            logger.info("🧹 Cleaning up service account files...")
            
            results = self.service_drive.files().list(
                q="'me' in owners",
                pageSize=100,
                fields="files(id, name, size)"
            ).execute()
            
            files = results.get('files', [])
            
            deleted_count = 0
            for file in files:
                try:
                    self.service_drive.files().delete(
                        fileId=file['id'],
                        supportsAllDrives=True
                    ).execute()
                    deleted_count += 1
                    logger.info(f"🗑️ Deleted: {file['name']}")
                except Exception as delete_error:
                    logger.warning(f"⚠️ Could not delete {file['name']}: {delete_error}")
            
            logger.info(f"✅ Cleanup complete: {deleted_count}/{len(files)} files deleted")
            return True
            
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
            return False
