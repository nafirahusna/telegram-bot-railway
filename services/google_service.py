# services/google_service.py - OAuth Delegation Version
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
        self.owner_email = "muhamadsidiq2@gmail.com"  # Your personal email for delegation
        
    def authenticate(self):
        """Authenticate with Google APIs using service account with OAuth delegation"""
        try:
            # Try to load from environment variable first
            service_account_key = os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY')
            
            if service_account_key:
                try:
                    # Decode base64 and load JSON
                    service_account_info = json.loads(base64.b64decode(service_account_key))
                    
                    # Create credentials with delegation to your personal account
                    creds = service_account.Credentials.from_service_account_info(
                        service_account_info,
                        scopes=SCOPES
                    )
                    
                    # IMPORTANT: Delegate to your personal Google account
                    # This allows the service account to act on behalf of your personal account
                    # which has storage quota
                    delegated_creds = creds.with_subject(self.owner_email)
                    
                    logger.info(f"✅ Using service account with OAuth delegation to {self.owner_email}")
                    
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
                    
                    # Delegate to personal account
                    delegated_creds = creds.with_subject(self.owner_email)
                    
                    logger.info(f"✅ Using service account from file with delegation to {self.owner_email}")
                else:
                    logger.error("❌ No service account found (neither env var nor file)")
                    return False
            
            # Build services with delegated credentials
            self.service_drive = build('drive', 'v3', credentials=delegated_creds)
            self.service_sheets = build('sheets', 'v4', credentials=delegated_creds)
            
            logger.info(f"✅ Google APIs authenticated with delegation to: {self.owner_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error authenticating with delegated service account: {e}")
            logger.error(f"❌ Make sure domain-wide delegation is enabled for this service account")
            logger.error(f"❌ And that {self.owner_email} has the necessary permissions")
            return False

    def create_folder(self, folder_name, parent_folder_id=None):
        """Create folder in Google Drive"""
        try:
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
        Upload file to Google Drive using OAuth delegation
        This should now work since we're using the personal account's storage quota
        """
        try:
            logger.info(f"📤 Starting upload with delegation: {file_name}")
            
            # Check file exists and has content
            if not os.path.exists(file_path):
                raise Exception(f"File not found: {file_path}")
            
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                raise Exception("File is empty")
            
            logger.info(f"📁 File size: {file_size} bytes")
            
            # Prepare file metadata
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            # Create media upload with smaller chunk size for reliability
            media = MediaFileUpload(
                file_path,
                resumable=True,
                chunksize=1024*512  # 512KB chunks for better reliability
            )
            
            # Upload file using delegated credentials
            uploaded_file = self.service_drive.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            file_id = uploaded_file.get('id')
            
            if file_id:
                logger.info(f"✅ File uploaded successfully: {file_name} -> {file_id}")
                logger.info(f"🔗 File URL: https://drive.google.com/file/d/{file_id}/view")
                return file_id
            else:
                raise Exception("No file ID returned from upload")
                
        except HttpError as http_error:
            logger.error(f"❌ HTTP Error during upload: {http_error}")
            
            if "storageQuotaExceeded" in str(http_error):
                logger.error("❌ Storage quota exceeded. Check if:")
                logger.error("   1. Domain-wide delegation is properly configured")
                logger.error(f"   2. {self.owner_email} has enough Google Drive storage")
                logger.error("   3. Service account has permission to impersonate the user")
            
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

    def test_delegation(self):
        """Test if OAuth delegation is working properly"""
        try:
            logger.info("🧪 Testing OAuth delegation...")
            
            # Try to get user info to confirm delegation
            about = self.service_drive.about().get(fields='user').execute()
            user_email = about.get('user', {}).get('emailAddress', 'Unknown')
            
            logger.info(f"✅ Successfully authenticated as: {user_email}")
            
            if user_email == self.owner_email:
                logger.info("✅ OAuth delegation is working correctly!")
                return True
            else:
                logger.warning(f"⚠️ Expected {self.owner_email}, got {user_email}")
                return False
                
        except Exception as e:
            logger.error(f"❌ OAuth delegation test failed: {e}")
            return False

    def check_storage_quota(self):
        """Check available storage quota"""
        try:
            about = self.service_drive.about().get(fields='storageQuota').execute()
            storage = about.get('storageQuota', {})
            
            limit = int(storage.get('limit', 0))
            usage = int(storage.get('usage', 0))
            
            if limit > 0:
                available = limit - usage
                usage_percent = (usage / limit) * 100
                
                logger.info(f"📊 Storage usage: {usage / (1024**3):.2f}GB / {limit / (1024**3):.2f}GB ({usage_percent:.1f}%)")
                logger.info(f"📊 Available: {available / (1024**3):.2f}GB")
                
                return {
                    'total_gb': limit / (1024**3),
                    'used_gb': usage / (1024**3),
                    'available_gb': available / (1024**3),
                    'usage_percent': usage_percent
                }
            else:
                logger.info("📊 Unlimited storage or unable to determine quota")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error checking storage quota: {e}")
            return None

    def cleanup_old_files(self, days=30):
        """Clean up old files from Google Drive (optional maintenance)"""
        try:
            from datetime import datetime, timedelta
            
            # Calculate cutoff date
            cutoff_date = datetime.now() - timedelta(days=days)
            cutoff_str = cutoff_date.strftime('%Y-%m-%dT%H:%M:%S')
            
            logger.info(f"🧹 Looking for files older than {days} days ({cutoff_str})")
            
            # Search for old files
            query = f"createdTime < '{cutoff_str}' and parents in '{self.parent_folder_id}'"
            
            results = self.service_drive.files().list(
                q=query,
                pageSize=100,
                fields="files(id, name, createdTime)"
            ).execute()
            
            files = results.get('files', [])
            
            if not files:
                logger.info("✅ No old files found to cleanup")
                return True
            
            logger.info(f"🗑️ Found {len(files)} old files to cleanup")
            
            deleted_count = 0
            for file in files:
                try:
                    self.service_drive.files().delete(fileId=file['id']).execute()
                    deleted_count += 1
                    logger.info(f"🗑️ Deleted: {file['name']}")
                except Exception as delete_error:
                    logger.warning(f"⚠️ Could not delete {file['name']}: {delete_error}")
            
            logger.info(f"✅ Cleanup complete: {deleted_count}/{len(files)} files deleted")
            return True
            
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
            return False
