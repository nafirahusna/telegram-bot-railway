# services/google_service.py - OAUTH2 VERSION WITH AUTO TOKEN REFRESH
import os
import json
import base64
import logging
import time
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from datetime import datetime

logger = logging.getLogger(__name__)

# Scopes untuk Google API
SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']

class GoogleService:
    def __init__(self):
        self.service_drive = None
        self.service_sheets = None
        self.credentials = None
        
        # Load dari environment variables
        self.parent_folder_id = os.environ.get('GOOGLE_PARENT_FOLDER_ID')
        self.owner_email = os.environ.get('GOOGLE_OWNER_EMAIL')
        
        # OAuth2 configuration dari environment
        self.client_id = os.environ.get('GOOGLE_CLIENT_ID')
        self.client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
        self.refresh_token = os.environ.get('GOOGLE_REFRESH_TOKEN')
        
        # Validate required environment variables
        required_vars = [
            'GOOGLE_PARENT_FOLDER_ID',
            'GOOGLE_OWNER_EMAIL', 
            'GOOGLE_CLIENT_ID',
            'GOOGLE_CLIENT_SECRET',
            'GOOGLE_REFRESH_TOKEN'
        ]
        
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        if missing_vars:
            logger.error(f"❌ Missing required environment variables: {missing_vars}")
            raise Exception(f"Missing environment variables: {missing_vars}")
        
        logger.info(f"✅ OAuth2 configuration loaded for: {self.owner_email}")
        
    def authenticate(self):
        """Authenticate with Google APIs using OAuth2 with automatic token refresh"""
        try:
            logger.info("🔐 Authenticating with OAuth2...")
            
            # Create credentials object from refresh token
            self.credentials = Credentials(
                token=None,  # Will be refreshed
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=SCOPES
            )
            
            # Refresh the access token
            if self.credentials.expired or not self.credentials.token:
                logger.info("🔄 Refreshing access token...")
                request = Request()
                self.credentials.refresh(request)
                logger.info("✅ Access token refreshed successfully")
            
            # Build services
            self.service_drive = build('drive', 'v3', credentials=self.credentials)
            self.service_sheets = build('sheets', 'v4', credentials=self.credentials)
            
            # Test the connection
            about = self.service_drive.about().get(fields="user").execute()
            user_email = about.get('user', {}).get('emailAddress', 'Unknown')
            
            logger.info(f"✅ Google APIs authenticated successfully!")
            logger.info(f"👤 Authenticated as: {user_email}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error authenticating with OAuth2: {e}")
            return False
    
    def _ensure_token_valid(self):
        """Ensure access token is valid, refresh if needed"""
        try:
            if self.credentials and (self.credentials.expired or not self.credentials.token):
                logger.info("🔄 Token expired, refreshing...")
                request = Request()
                self.credentials.refresh(request)
                logger.info("✅ Token refreshed successfully")
                
                # Rebuild services with new token
                self.service_drive = build('drive', 'v3', credentials=self.credentials)
                self.service_sheets = build('sheets', 'v4', credentials=self.credentials)
                
            return True
        except Exception as e:
            logger.error(f"❌ Error refreshing token: {e}")
            return False

    def create_folder(self, folder_name, parent_folder_id=None):
        """Create folder in Google Drive"""
        try:
            # Ensure token is valid
            if not self._ensure_token_valid():
                logger.error("❌ Cannot refresh token")
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
        Upload file to Google Drive directly to target folder
        Using OAuth2, we don't need the upload-transfer-delete strategy
        """
        try:
            # Ensure token is valid
            if not self._ensure_token_valid():
                logger.error("❌ Cannot refresh token")
                return None
                
            logger.info(f"📤 Starting upload: {file_name}")
            
            # Upload directly to target folder
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            media = MediaFileUpload(
                file_path, 
                resumable=True,
                chunksize=1024*1024  # 1MB chunks for better reliability
            )
            
            uploaded_file = self.service_drive.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            file_id = uploaded_file.get('id')
            logger.info(f"✅ Upload successful: {file_name} -> {file_id}")
            
            return file_id
            
        except HttpError as e:
            logger.error(f"❌ HTTP Error during upload: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error uploading file: {e}")
            return None

    def get_folder_link(self, folder_id):
        """Get shareable link for Google Drive folder"""
        return f"https://drive.google.com/drive/folders/{folder_id}"

    def update_spreadsheet(self, spreadsheet_id, spreadsheet_config, laporan_data):
        """Update Google Spreadsheet with report data"""
        try:
            # Ensure token is valid
            if not self._ensure_token_valid():
                logger.error("❌ Cannot refresh token")
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
            
        except HttpError as e:
            logger.error(f"❌ HTTP Error updating spreadsheet: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Error updating spreadsheet: {e}")
            return False

    def test_connection(self):
        """Test Google Drive and Sheets connection"""
        try:
            # Ensure token is valid
            if not self._ensure_token_valid():
                logger.error("❌ Cannot refresh token")
                return False
                
            # Test Drive connection
            about = self.service_drive.about().get(fields="user,storageQuota").execute()
            user_email = about.get('user', {}).get('emailAddress', 'Unknown')
            storage_quota = about.get('storageQuota', {})
            
            # Test Sheets connection (list some spreadsheets)
            sheets_response = self.service_drive.files().list(
                q="mimeType='application/vnd.google-apps.spreadsheet'",
                pageSize=1,
                fields="files(id, name)"
            ).execute()
            
            logger.info(f"✅ Connection test successful!")
            logger.info(f"👤 User: {user_email}")
            logger.info(f"💾 Storage used: {storage_quota.get('usage', 'Unknown')} / {storage_quota.get('limit', 'Unknown')}")
            
            return {
                'success': True,
                'user_email': user_email,
                'storage_quota': storage_quota
            }
            
        except Exception as e:
            logger.error(f"❌ Connection test failed: {e}")
            return False

    def get_quota_info(self):
        """Get current quota information"""
        try:
            # Ensure token is valid
            if not self._ensure_token_valid():
                return None
                
            about = self.service_drive.about().get(fields="user,storageQuota").execute()
            storage_quota = about.get('storageQuota', {})
            user_email = about.get('user', {}).get('emailAddress', 'Unknown')
            
            return {
                'user_email': user_email,
                'usage_bytes': int(storage_quota.get('usage', 0)),
                'limit_bytes': int(storage_quota.get('limit', 0)),
                'usage_gb': round(int(storage_quota.get('usage', 0)) / (1024**3), 2),
                'limit_gb': round(int(storage_quota.get('limit', 0)) / (1024**3), 2)
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting quota info: {e}")
            return None

    def cleanup_old_files(self, days_old=7):
        """Clean up old temporary files"""
        try:
            # Ensure token is valid
            if not self._ensure_token_valid():
                return False
                
            from datetime import datetime, timedelta
            
            # Calculate date threshold
            threshold_date = datetime.now() - timedelta(days=days_old)
            threshold_iso = threshold_date.isoformat() + 'Z'
            
            # Find old files
            results = self.service_drive.files().list(
                q=f"name contains 'temp_' and createdTime < '{threshold_iso}'",
                pageSize=100,
                fields="files(id, name, createdTime)"
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
                    logger.info(f"🗑️ Deleted old temp file: {file['name']}")
                except Exception as delete_error:
                    logger.warning(f"⚠️ Could not delete {file['name']}: {delete_error}")
            
            logger.info(f"✅ Cleanup complete: {deleted_count}/{len(files)} old files deleted")
            return True
            
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
            return False
