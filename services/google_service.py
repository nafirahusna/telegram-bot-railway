# services/google_service.py - Fixed Version with Proper Ownership
import os
import json
import base64
import logging
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload
from datetime import datetime

logger = logging.getLogger(__name__)

# Scopes untuk Google API
SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']

class GoogleService:
    def __init__(self, parent_folder_id="12EU8I2sbhzxyHaiBhoC2xjJ4jTXpYJfY"):
        self.service_drive = None
        self.service_sheets = None
        self.parent_folder_id = parent_folder_id
        self.owner_email = None  # Email pemilik folder parent
        
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
            
            # Get owner email dari parent folder
            self._get_owner_email()
            
            logger.info("✅ Google APIs authenticated successfully with service account!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error authenticating with service account: {e}")
            return False

    def _get_owner_email(self):
        """Get owner email dari parent folder"""
        try:
            # Get permissions dari parent folder
            permissions = self.service_drive.permissions().list(
                fileId=self.parent_folder_id,
                supportsAllDrives=True
            ).execute()
            
            # Cari owner
            for permission in permissions.get('permissions', []):
                if permission.get('role') == 'owner':
                    self.owner_email = permission.get('emailAddress')
                    logger.info(f"✅ Found owner email: {self.owner_email}")
                    break
                    
        except Exception as e:
            logger.warning(f"⚠️ Could not get owner email: {e}")
            # Fallback - set manual jika diperlukan
            self.owner_email = os.environ.get('OWNER_EMAIL')  # Bisa di-set di environment

    def create_folder(self, folder_name, parent_folder_id=None):
        """Create folder dengan ownership yang benar"""
        try:
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            parent_id = parent_folder_id or self.parent_folder_id
            if parent_id:
                folder_metadata['parents'] = [parent_id]
            
            # Create folder
            folder = self.service_drive.files().create(
                body=folder_metadata,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            folder_id = folder.get('id')
            logger.info(f"✅ Folder created: {folder_name} (ID: {folder_id})")
            
            # CRITICAL: Transfer ownership ke pemilik asli
            if folder_id and self.owner_email:
                success = self._transfer_ownership(folder_id, self.owner_email)
                if success:
                    logger.info(f"✅ Ownership transferred to {self.owner_email}")
                else:
                    logger.warning(f"⚠️ Could not transfer ownership, keeping service account ownership")
            
            return folder_id
            
        except Exception as e:
            logger.error(f"❌ Error creating folder: {e}")
            return None

    def _transfer_ownership(self, file_id, owner_email):
        """Transfer ownership file/folder ke owner yang benar"""
        try:
            # Transfer ownership
            permission_body = {
                'role': 'owner',
                'type': 'user',
                'emailAddress': owner_email
            }
            
            self.service_drive.permissions().create(
                fileId=file_id,
                body=permission_body,
                transferOwnership=True,  # CRITICAL: Transfer ownership
                supportsAllDrives=True
            ).execute()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error transferring ownership: {e}")
            # Jika transfer ownership gagal, tetap lanjut tapi dengan warning
            return False

    def upload_to_drive(self, file_path, file_name, folder_id):
        """Upload file dengan ownership yang benar"""
        try:
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            media = MediaFileUpload(file_path, resumable=True)
            
            # Upload file
            uploaded_file = self.service_drive.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            file_id = uploaded_file.get('id')
            logger.info(f"✅ File uploaded: {file_name} (ID: {file_id})")
            
            # CRITICAL: Transfer ownership ke pemilik asli
            if file_id and self.owner_email:
                success = self._transfer_ownership(file_id, self.owner_email)
                if success:
                    logger.info(f"✅ File ownership transferred to {self.owner_email}")
                else:
                    logger.warning(f"⚠️ File ownership transfer failed, but upload succeeded")
            
            return file_id
            
        except Exception as e:
            logger.error(f"❌ Error uploading file: {e}")
            
            # Detailed error analysis
            error_str = str(e).lower()
            if "storagequotaexceeded" in error_str:
                logger.error("💡 SOLUTION: Storage quota issue detected!")
                logger.error("   - Service account quota full (15GB limit)")
                logger.error("   - Need to transfer ownership to personal account")
                logger.error("   - Or use shared drive instead of personal drive")
            elif "insufficient permissions" in error_str:
                logger.error("💡 SOLUTION: Permission issue detected!")
                logger.error("   - Service account needs 'Editor' access to parent folder")
                logger.error("   - Or parent folder owner needs to grant transfer permissions")
            
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
            logger.info(f"Row data: {row_data}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating spreadsheet: {e}")
            return False

    def check_quota_status(self):
        """Check storage quota status"""
        try:
            about = self.service_drive.about().get(fields="storageQuota").execute()
            quota = about.get('storageQuota', {})
            
            usage = int(quota.get('usage', 0))
            limit = int(quota.get('limit', 0))
            
            logger.info(f"📊 Storage Quota Status:")
            logger.info(f"   Used: {usage / (1024**3):.2f} GB")
            logger.info(f"   Limit: {limit / (1024**3):.2f} GB")
            logger.info(f"   Available: {(limit - usage) / (1024**3):.2f} GB")
            
            return {
                'used': usage,
                'limit': limit,
                'available': limit - usage,
                'percentage': (usage / limit) * 100 if limit > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"❌ Error checking quota: {e}")
            return None
