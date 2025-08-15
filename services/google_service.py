# services/google_service.py
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
    def __init__(self, parent_folder_id="1mLsCBEqEb0R4_pX75-xmpRE1023H6A90"):
        self.service_drive = None
        self.service_sheets = None
        self.parent_folder_id = parent_folder_id
        
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
            logger.info("✅ Google APIs authenticated successfully with service account!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error authenticating with service account: {e}")
            return False

    def create_folder(self, folder_name, parent_folder_id=None):
        """Create folder with proper inheritance"""
        try:
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_folder_id or self.parent_folder_id:
                folder_metadata['parents'] = [parent_folder_id or self.parent_folder_id]
            
            # Create folder dengan shared drive support
            folder = self.service_drive.files().create(
                body=folder_metadata,
                supportsAllDrives=True,  # Support shared drives
                supportsTeamDrives=True  # Legacy support
            ).execute()
            
            folder_id = folder.get('id')
            
            # PENTING: Set permissions explicitly ke folder baru
            try:
                # Get parent folder info untuk inherit permissions
                parent_id = parent_folder_id or self.parent_folder_id
                parent_info = self.service_drive.files().get(
                    fileId=parent_id,
                    supportsAllDrives=True
                ).execute()
                
                # Check if parent is in shared drive
                if 'driveId' in parent_info:
                    logger.info(f"✅ Folder created in shared drive: {folder_name}")
                else:
                    logger.info(f"✅ Folder created in regular drive: {folder_name}")
                    
            except Exception as perm_error:
                logger.warning(f"⚠️ Could not check parent permissions: {perm_error}")
            
            return folder_id
            
        except Exception as e:
            logger.error(f"❌ Error creating folder: {e}")
            return None

    def upload_to_drive(self, file_path, file_name, folder_id):
        """Upload file with proper shared drive support"""
        try:
            # Check if target folder is in shared drive
            try:
                folder_info = self.service_drive.files().get(
                    fileId=folder_id,
                    supportsAllDrives=True
                ).execute()
                is_shared_drive = 'driveId' in folder_info
            except:
                is_shared_drive = False
            
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            media = MediaFileUpload(file_path, resumable=True)
            
            # Upload dengan parameter yang sesuai
            upload_params = {
                'body': file_metadata,
                'media_body': media,
                'supportsAllDrives': True,
                'supportsTeamDrives': True
            }
            
            uploaded_file = self.service_drive.files().create(**upload_params).execute()
            
            if is_shared_drive:
                logger.info(f"✅ File uploaded to shared drive folder: {file_name}")
            else:
                logger.info(f"✅ File uploaded to regular drive folder: {file_name}")
                
            return uploaded_file.get('id')
            
        except Exception as e:
            logger.error(f"❌ Error uploading file: {e}")
            # Log detail error untuk debugging
            if "storageQuotaExceeded" in str(e):
                logger.error("💡 Storage quota issue - check folder ownership and permissions")
            elif "insufficient permissions" in str(e).lower():
                logger.error("💡 Permission issue - check service account access to folder")
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
