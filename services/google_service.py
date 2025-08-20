# services/google_service.py - OAuth Version with Service Account for Sheets
import os
import json
import base64
import logging
import time
from googleapiclient.discovery import build
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from datetime import datetime

logger = logging.getLogger(__name__)

# Scopes untuk Google API
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive']
SHEETS_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

class GoogleService:
    def __init__(self):
        # Get environment variables with fallbacks
        self.parent_folder_id = os.environ.get('PARENT_FOLDER_ID', '12EU8I2sbhzxyHaiBhoC2xjJ4jTXpYJfY')
        self.owner_email = os.environ.get('OWNER_EMAIL', 'ilhambintang9773@gmail.com')
        
        # OAuth credentials for Drive (photo uploads)
        self.oauth_client_id = os.environ.get('OAUTH_CLIENT_ID')
        self.oauth_client_secret = os.environ.get('OAUTH_CLIENT_SECRET')
        self.oauth_refresh_token = os.environ.get('OAUTH_REFRESH_TOKEN')
        
        # Service account for Sheets (spreadsheet operations)
        self.service_account_key = os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY')
        
        # Services
        self.service_drive = None  # Will use OAuth
        self.service_sheets = None  # Will use Service Account
        
    def authenticate(self):
        """Authenticate with Google APIs using OAuth for Drive and Service Account for Sheets"""
        try:
            # 1. Authenticate Drive with OAuth (for photo uploads)
            if not self._authenticate_drive_oauth():
                logger.error("❌ Failed to authenticate Drive with OAuth")
                return False
                
            # 2. Authenticate Sheets with Service Account (for spreadsheet operations)
            if not self._authenticate_sheets_service_account():
                logger.error("❌ Failed to authenticate Sheets with Service Account")
                return False
                
            logger.info("✅ Both Drive (OAuth) and Sheets (Service Account) authenticated successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error during authentication: {e}")
            return False

    def _authenticate_drive_oauth(self):
        """Authenticate Drive service with OAuth credentials"""
        try:
            if not all([self.oauth_client_id, self.oauth_client_secret, self.oauth_refresh_token]):
                logger.error("❌ Missing OAuth credentials for Drive")
                logger.error("Required: OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, OAUTH_REFRESH_TOKEN")
                return False
            
            # Create OAuth credentials
            creds = Credentials(
                token=None,
                refresh_token=self.oauth_refresh_token,
                client_id=self.oauth_client_id,
                client_secret=self.oauth_client_secret,
                token_uri='https://oauth2.googleapis.com/token',
                scopes=DRIVE_SCOPES
            )
            
            # Refresh the token
            creds.refresh(Request())
            
            # Build Drive service
            self.service_drive = build('drive', 'v3', credentials=creds)
            
            logger.info("✅ Drive service authenticated with OAuth")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error authenticating Drive with OAuth: {e}")
            return False

    def _authenticate_sheets_service_account(self):
        """Authenticate Sheets service with Service Account"""
        try:
            if not self.service_account_key:
                logger.error("❌ Missing GOOGLE_SERVICE_ACCOUNT_KEY for Sheets")
                return False
            
            # Decode and load service account
            try:
                service_account_info = json.loads(base64.b64decode(self.service_account_key))
                creds = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=SHEETS_SCOPES
                )
                logger.info("✅ Using service account from environment variable for Sheets")
            except Exception as e:
                logger.error(f"❌ Error decoding service account: {e}")
                return False
            
            # Build Sheets service
            self.service_sheets = build('sheets', 'v4', credentials=creds)
            
            logger.info("✅ Sheets service authenticated with Service Account")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error authenticating Sheets with Service Account: {e}")
            return False

    def create_folder(self, folder_name, parent_folder_id=None):
        """Create folder using OAuth Drive service"""
        try:
            if not self.service_drive:
                logger.error("❌ Drive service not authenticated")
                return None
                
            parent_id = parent_folder_id or self.parent_folder_id
            
            # Create folder metadata
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id] if parent_id else []
            }
            
            # Create folder
            folder = self.service_drive.files().create(
                body=folder_metadata,
                supportsAllDrives=True
            ).execute()
            
            folder_id = folder.get('id')
            logger.info(f"📁 Folder created: {folder_name} (ID: {folder_id})")
            
            return folder_id
            
        except Exception as e:
            logger.error(f"❌ Error creating folder: {e}")
            return None

    def upload_to_drive(self, file_path, file_name, folder_id):
        """Upload file to Drive using OAuth credentials"""
        try:
            if not self.service_drive:
                logger.error("❌ Drive service not authenticated")
                return None
                
            logger.info(f"📤 Starting OAuth upload: {file_name}")
            
            # File metadata
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            # Upload with chunked upload for better reliability
            media = MediaFileUpload(
                file_path, 
                resumable=True,
                chunksize=1024*1024  # 1MB chunks
            )
            
            # Create the file
            uploaded_file = self.service_drive.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True
            ).execute()
            
            file_id = uploaded_file.get('id')
            logger.info(f"✅ OAuth upload successful: {file_name} -> {file_id}")
            
            return file_id
            
        except Exception as e:
            logger.error(f"❌ OAuth upload failed: {e}")
            return None

    def get_folder_link(self, folder_id):
        """Get shareable link for Google Drive folder"""
        return f"https://drive.google.com/drive/folders/{folder_id}"

    def update_spreadsheet(self, spreadsheet_id, spreadsheet_config, laporan_data):
        """Update Google Spreadsheet using Service Account"""
        try:
            if not self.service_sheets:
                logger.error("❌ Sheets service not authenticated")
                return False
                
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

    def test_oauth_drive_access(self):
        """Test if OAuth Drive access is working"""
        try:
            if not self.service_drive:
                logger.error("❌ Drive service not available")
                return False
            
            # Try to get information about the parent folder
            folder_info = self.service_drive.files().get(
                fileId=self.parent_folder_id,
                supportsAllDrives=True
            ).execute()
            
            logger.info(f"✅ OAuth Drive access confirmed - Parent folder: {folder_info.get('name')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ OAuth Drive access test failed: {e}")
            return False

    def get_drive_quota_info(self):
        """Get Drive quota information using OAuth"""
        try:
            if not self.service_drive:
                return None
                
            about = self.service_drive.about().get(
                fields='storageQuota,user'
            ).execute()
            
            storage_quota = about.get('storageQuota', {})
            user_info = about.get('user', {})
            
            quota_info = {
                'user_email': user_info.get('emailAddress', 'Unknown'),
                'total_gb': int(storage_quota.get('limit', 0)) / (1024**3),
                'used_gb': int(storage_quota.get('usage', 0)) / (1024**3),
                'used_drive_gb': int(storage_quota.get('usageInDrive', 0)) / (1024**3)
            }
            
            quota_info['available_gb'] = quota_info['total_gb'] - quota_info['used_gb']
            
            logger.info(f"📊 Drive quota: {quota_info['used_gb']:.2f}GB / {quota_info['total_gb']:.2f}GB used")
            
            return quota_info
            
        except Exception as e:
            logger.error(f"❌ Error getting quota info: {e}")
            return None

    def cleanup_service_account_files(self):
        """This method is no longer needed since we're using OAuth for Drive"""
        logger.info("ℹ️ Cleanup not needed - using OAuth for Drive uploads")
        return True

    def get_service_account_usage(self):
        """Get minimal service account info (only for sheets)"""
        return {
            'note': 'Service account only used for spreadsheet operations',
            'drive_uploads': 'Using OAuth personal account'
        }
