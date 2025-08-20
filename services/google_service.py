# services/google_service.py - FIXED VERSION WITH PROPER OWNERSHIP TRANSFER
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
        self.owner_email = "ilhambintang9773@gmail.com"  # FIXED: Set your email directly
        
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
        """Create folder directly in owner's drive with immediate ownership transfer"""
        try:
            parent_id = parent_folder_id or self.parent_folder_id
            
            # STEP 1: Create folder metadata with immediate owner setting
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id] if parent_id else []
            }
            
            # STEP 2: Create folder
            folder = self.service_drive.files().create(
                body=folder_metadata,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            folder_id = folder.get('id')
            logger.info(f"📁 Folder created: {folder_name} (ID: {folder_id})")
            
            # STEP 3: IMMEDIATELY transfer ownership to avoid quota issues
            if folder_id and self.owner_email:
                try:
                    # Add owner permission with transferOwnership=True
                    permission_body = {
                        'role': 'owner',
                        'type': 'user', 
                        'emailAddress': self.owner_email
                    }
                    
                    self.service_drive.permissions().create(
                        fileId=folder_id,
                        body=permission_body,
                        transferOwnership=True,
                        supportsAllDrives=True,
                        sendNotificationEmail=False  # Don't spam email notifications
                    ).execute()
                    
                    logger.info(f"✅ Folder ownership transferred to {self.owner_email}")
                    
                except Exception as transfer_error:
                    logger.error(f"❌ Ownership transfer failed: {transfer_error}")
                    # Don't return None, folder still works without transfer
                    logger.warning("⚠️ Folder created but ownership not transferred")
            
            return folder_id
            
        except Exception as e:
            logger.error(f"❌ Error creating folder: {e}")
            return None

    def upload_to_drive(self, file_path, file_name, folder_id):
        """Upload file with immediate ownership transfer to avoid quota issues"""
        try:
            # STEP 1: Upload file metadata
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            media = MediaFileUpload(file_path, resumable=True)
            
            # STEP 2: Upload file
            uploaded_file = self.service_drive.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            file_id = uploaded_file.get('id')
            logger.info(f"📄 File uploaded: {file_name} (ID: {file_id})")
            
            # STEP 3: IMMEDIATELY transfer ownership to avoid quota counting against service account
            if file_id and self.owner_email:
                try:
                    permission_body = {
                        'role': 'owner',
                        'type': 'user',
                        'emailAddress': self.owner_email
                    }
                    
                    self.service_drive.permissions().create(
                        fileId=file_id,
                        body=permission_body,
                        transferOwnership=True,
                        supportsAllDrives=True,
                        sendNotificationEmail=False  # Don't spam notifications
                    ).execute()
                    
                    logger.info(f"✅ File ownership transferred to {self.owner_email}")
                    
                except Exception as transfer_error:
                    logger.error(f"❌ File ownership transfer failed: {transfer_error}")
                    # File uploaded successfully, just ownership transfer failed
                    logger.warning("⚠️ File uploaded but ownership not transferred")
            
            return file_id
            
        except Exception as e:
            logger.error(f"❌ Error uploading file: {e}")
            
            # Enhanced error handling
            error_str = str(e).lower()
            if "storagequotaexceeded" in error_str:
                logger.error("🚨 QUOTA EXCEEDED - ATTEMPTING WORKAROUND...")
                
                # Try alternative approach: Create file first, then upload content
                return self._upload_with_quota_workaround(file_path, file_name, folder_id)
            elif "insufficient" in error_str and "permission" in error_str:
                logger.error("🚨 PERMISSION ISSUE:")
                logger.error(f"   Make sure {self.owner_email} has granted 'Manager' access to service account")
                logger.error(f"   Or add service account as 'Editor' to parent folder: {self.parent_folder_id}")
            
            return None

    def _upload_with_quota_workaround(self, file_path, file_name, folder_id):
        """Alternative upload method to bypass quota issues"""
        try:
            logger.info("🔄 Trying quota workaround method...")
            
            # Method 1: Create empty file first, transfer ownership, then update content
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            # Create empty file
            empty_file = self.service_drive.files().create(
                body=file_metadata,
                supportsAllDrives=True
            ).execute()
            
            file_id = empty_file.get('id')
            
            if file_id and self.owner_email:
                # Transfer ownership of empty file first
                permission_body = {
                    'role': 'owner',
                    'type': 'user',
                    'emailAddress': self.owner_email
                }
                
                self.service_drive.permissions().create(
                    fileId=file_id,
                    body=permission_body,
                    transferOwnership=True,
                    supportsAllDrives=True,
                    sendNotificationEmail=False
                ).execute()
                
                logger.info("✅ Empty file created and ownership transferred")
                
                # Now try to update with actual content
                media = MediaFileUpload(file_path, resumable=True)
                
                updated_file = self.service_drive.files().update(
                    fileId=file_id,
                    media_body=media,
                    supportsAllDrives=True
                ).execute()
                
                logger.info(f"✅ File content updated successfully: {file_name}")
                return file_id
            
        except Exception as workaround_error:
            logger.error(f"❌ Quota workaround failed: {workaround_error}")
            
            # Last resort: Provide manual instructions
            logger.error("🚨 MANUAL ACTION REQUIRED:")
            logger.error("1. Go to Google Drive")
            logger.error("2. Find the service account files (probably in 'Shared with me')")
            logger.error("3. Move them to your personal drive")
            logger.error("4. Or create a Shared Drive and use that instead")
            
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

    def check_service_account_permissions(self):
        """Check if service account has proper permissions"""
        try:
            # Test drive access
            drive_test = self.service_drive.files().list(pageSize=1).execute()
            logger.info("✅ Drive API access confirmed")
            
            # Test parent folder access
            if self.parent_folder_id:
                folder_info = self.service_drive.files().get(
                    fileId=self.parent_folder_id,
                    supportsAllDrives=True
                ).execute()
                logger.info(f"✅ Parent folder access confirmed: {folder_info.get('name')}")
                
                # Check permissions on parent folder
                permissions = self.service_drive.permissions().list(
                    fileId=self.parent_folder_id,
                    supportsAllDrives=True
                ).execute()
                
                service_account_email = None
                for perm in permissions.get('permissions', []):
                    if perm.get('type') == 'serviceAccount':
                        service_account_email = perm.get('emailAddress')
                        break
                
                if service_account_email:
                    logger.info(f"✅ Service account found in permissions: {service_account_email}")
                else:
                    logger.warning("⚠️ Service account not found in folder permissions")
                    logger.warning("💡 Add service account as 'Editor' to parent folder")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Permission check failed: {e}")
            return False

    def cleanup_service_account_files(self):
        """Clean up files owned by service account (emergency cleanup)"""
        try:
            logger.info("🧹 Cleaning up service account files...")
            
            # List files owned by service account
            results = self.service_drive.files().list(
                q="'me' in owners",
                pageSize=100,
                fields="files(id, name, size, owners)"
            ).execute()
            
            files = results.get('files', [])
            
            total_size = 0
            for file in files:
                size = int(file.get('size', 0))
                total_size += size
                logger.info(f"📁 {file['name']}: {size / (1024*1024):.1f} MB")
            
            logger.info(f"📊 Total size: {total_size / (1024*1024*1024):.2f} GB")
            
            # Transfer ownership of all files
            transferred = 0
            for file in files:
                try:
                    permission_body = {
                        'role': 'owner',
                        'type': 'user',
                        'emailAddress': self.owner_email
                    }
                    
                    self.service_drive.permissions().create(
                        fileId=file['id'],
                        body=permission_body,
                        transferOwnership=True,
                        supportsAllDrives=True,
                        sendNotificationEmail=False
                    ).execute()
                    
                    transferred += 1
                    logger.info(f"✅ Transferred: {file['name']}")
                    
                except Exception as transfer_error:
                    logger.error(f"❌ Failed to transfer {file['name']}: {transfer_error}")
            
            logger.info(f"✅ Cleanup complete: {transferred}/{len(files)} files transferred")
            return True
            
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
            return False
