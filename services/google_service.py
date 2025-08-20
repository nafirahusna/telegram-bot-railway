# services/google_service.py - FIXED VERSION WITH OWNERSHIP TRANSFER
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
        self.owner_email = "ilhambintang9773@gmail.com"  # Your personal Gmail
        
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

    def transfer_ownership(self, file_id, owner_email):
        """Transfer file ownership to personal Gmail account"""
        try:
            logger.info(f"🔄 Transferring ownership of {file_id} to {owner_email}")
            
            # Create permission for ownership transfer
            permission = {
                'role': 'owner',
                'type': 'user',
                'emailAddress': owner_email
            }
            
            # Transfer ownership
            self.service_drive.permissions().create(
                fileId=file_id,
                body=permission,
                transferOwnership=True,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            logger.info(f"✅ Ownership transferred successfully to {owner_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error transferring ownership: {e}")
            return False

    def upload_to_drive(self, file_path, file_name, folder_id):
        """
        NEW STRATEGY: Upload -> Transfer Ownership -> Move to folder
        This ensures files are owned by your personal Gmail (with 15GB quota)
        """
        temp_file_id = None
        
        try:
            logger.info(f"📤 Starting upload with ownership transfer: {file_name}")
            
            # STEP 1: Upload file to service account's My Drive (temporary)
            temp_name = f"temp_{int(time.time())}_{file_name}"
            file_metadata = {
                'name': temp_name
                # No parents = uploads to service account's My Drive
            }
            
            media = MediaFileUpload(file_path, resumable=True)
            
            # Upload to service account's root
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
            
            # STEP 2: Transfer ownership to your personal Gmail
            logger.info(f"🔄 Transferring ownership to {self.owner_email}...")
            
            ownership_transferred = self.transfer_ownership(temp_file_id, self.owner_email)
            
            if not ownership_transferred:
                logger.warning("⚠️ Ownership transfer failed, proceeding with copy method")
                # Fallback: copy to target folder and delete temp
                return self._copy_and_cleanup(temp_file_id, file_name, folder_id)
            
            # STEP 3: Move file to target folder and rename
            logger.info(f"📋 Moving file to target folder...")
            
            # Update file: move to folder and rename
            update_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            # Remove from current parents (service account's My Drive)
            file_info = self.service_drive.files().get(
                fileId=temp_file_id,
                fields='parents',
                supportsAllDrives=True
            ).execute()
            
            previous_parents = ",".join(file_info.get('parents', []))
            
            # Move file
            moved_file = self.service_drive.files().update(
                fileId=temp_file_id,
                body=update_metadata,
                addParents=folder_id,
                removeParents=previous_parents,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            final_file_id = moved_file.get('id')
            logger.info(f"✅ File moved and renamed successfully: {final_file_id}")
            
            # STEP 4: Verify ownership transfer worked
            try:
                file_details = self.service_drive.files().get(
                    fileId=final_file_id,
                    fields='owners',
                    supportsAllDrives=True
                ).execute()
                
                owners = file_details.get('owners', [])
                is_owned_by_personal = any(owner.get('emailAddress') == self.owner_email for owner in owners)
                
                if is_owned_by_personal:
                    logger.info(f"✅ Ownership confirmed: File owned by {self.owner_email}")
                else:
                    logger.warning(f"⚠️ Ownership verification failed")
                    
            except Exception as verify_error:
                logger.warning(f"⚠️ Could not verify ownership: {verify_error}")
            
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
                except Exception as cleanup_error:
                    logger.warning(f"⚠️ Could not clean up temp file: {cleanup_error}")
            
            # Try fallback method
            return self._upload_fallback_method(file_path, file_name, folder_id)

    def _copy_and_cleanup(self, temp_file_id, file_name, folder_id):
        """Fallback: Copy to target folder and cleanup temp file"""
        try:
            logger.info("🔄 Using copy and cleanup fallback method...")
            
            # Copy to target folder
            copy_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            copied_file = self.service_drive.files().copy(
                fileId=temp_file_id,
                body=copy_metadata,
                supportsAllDrives=True,
                supportsTeamDrives=True
            ).execute()
            
            final_file_id = copied_file.get('id')
            
            # Delete temp file
            try:
                self.service_drive.files().delete(
                    fileId=temp_file_id,
                    supportsAllDrives=True
                ).execute()
                logger.info(f"🗑️ Temp file deleted")
            except Exception as delete_error:
                logger.warning(f"⚠️ Could not delete temp file: {delete_error}")
            
            logger.info(f"✅ Copy and cleanup successful: {final_file_id}")
            return final_file_id
            
        except Exception as e:
            logger.error(f"❌ Copy and cleanup failed: {e}")
            return None

    def _upload_fallback_method(self, file_path, file_name, folder_id):
        """Final fallback: Direct upload to target folder"""
        try:
            logger.info("🔄 Using direct upload fallback method...")
            
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
            
            # Try to transfer ownership even in fallback
            if file_id:
                try:
                    self.transfer_ownership(file_id, self.owner_email)
                    logger.info(f"✅ Fallback upload with ownership transfer: {file_id}")
                except Exception as transfer_error:
                    logger.warning(f"⚠️ Ownership transfer failed in fallback: {transfer_error}")
                    logger.info(f"✅ Fallback upload successful (no ownership transfer): {file_id}")
            
            return file_id
            
        except Exception as alt_error:
            logger.error(f"❌ All upload methods failed: {alt_error}")
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

    def test_ownership_transfer(self):
        """Test ownership transfer functionality"""
        try:
            logger.info("🧪 Testing ownership transfer...")
            
            # Create test file
            test_content = f"Test file created at {datetime.now()}"
            test_file_path = "test_ownership.txt"
            
            with open(test_file_path, 'w') as f:
                f.write(test_content)
            
            # Upload test file
            file_metadata = {
                'name': f"ownership_test_{int(time.time())}.txt"
            }
            
            media = MediaFileUpload(test_file_path)
            
            test_file = self.service_drive.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True
            ).execute()
            
            test_file_id = test_file.get('id')
            logger.info(f"📤 Test file uploaded: {test_file_id}")
            
            # Try ownership transfer
            if test_file_id:
                transfer_success = self.transfer_ownership(test_file_id, self.owner_email)
                
                if transfer_success:
                    logger.info("✅ Ownership transfer test PASSED")
                    
                    # Clean up - delete test file
                    try:
                        self.service_drive.files().delete(
                            fileId=test_file_id,
                            supportsAllDrives=True
                        ).execute()
                        logger.info("🧹 Test file cleaned up")
                    except Exception as cleanup_error:
                        logger.warning(f"⚠️ Could not cleanup test file: {cleanup_error}")
                        
                else:
                    logger.error("❌ Ownership transfer test FAILED")
                    
                    # Still try to clean up
                    try:
                        self.service_drive.files().delete(
                            fileId=test_file_id,
                            supportsAllDrives=True
                        ).execute()
                    except:
                        pass
            
            # Clean up local test file
            if os.path.exists(test_file_path):
                os.remove(test_file_path)
            
            return transfer_success if test_file_id else False
            
        except Exception as e:
            logger.error(f"❌ Ownership transfer test failed: {e}")
            
            # Clean up test file if it exists
            try:
                if os.path.exists(test_file_path):
                    os.remove(test_file_path)
            except:
                pass
                
            return False

    def check_upload_permissions(self):
        """Check if we can upload and transfer ownership"""
        try:
            logger.info("🔍 Checking upload permissions and ownership transfer...")
            
            # Test both upload and ownership transfer
            upload_test = self.test_ownership_transfer()
            
            if upload_test:
                logger.info("✅ Upload permissions and ownership transfer confirmed")
                return True
            else:
                logger.warning("⚠️ Upload or ownership transfer test failed")
                return False
                
        except Exception as e:
            logger.error(f"❌ Permission check failed: {e}")
            return False

    def get_service_account_usage(self):
        """Check current usage of service account"""
        try:
            # Get files owned by service account
            results = self.service_drive.files().list(
                q="'me' in owners",
                pageSize=100,
                fields="files(id, name, size, owners)"
            ).execute()
            
            files = results.get('files', [])
            total_size = sum(int(file.get('size', 0)) for file in files)
            
            logger.info(f"📊 Service account usage: {len(files)} files, {total_size / (1024*1024):.2f} MB")
            
            # Count files owned by service account vs personal account
            service_owned = []
            personal_owned = []
            
            for file in files:
                owners = file.get('owners', [])
                if any(owner.get('emailAddress') == self.owner_email for owner in owners):
                    personal_owned.append(file)
                else:
                    service_owned.append(file)
            
            logger.info(f"📊 Service account owned: {len(service_owned)} files")
            logger.info(f"📊 Personal account owned: {len(personal_owned)} files")
            
            return {
                'file_count': len(files),
                'total_size_mb': total_size / (1024*1024),
                'service_owned_count': len(service_owned),
                'personal_owned_count': len(personal_owned),
                'files': files
            }
            
        except Exception as e:
            logger.error(f"❌ Error checking service account usage: {e}")
            return None

    def cleanup_service_account_files(self):
        """Clean up any remaining files in service account (owned by service account only)"""
        try:
            logger.info("🧹 Cleaning up service account owned files...")
            
            # Get files owned by service account only
            results = self.service_drive.files().list(
                q="'me' in owners",
                pageSize=100,
                fields="files(id, name, size, owners)"
            ).execute()
            
            files = results.get('files', [])
            deleted_count = 0
            
            for file in files:
                try:
                    # Check if file is owned by service account (not transferred)
                    owners = file.get('owners', [])
                    is_service_owned = not any(owner.get('emailAddress') == self.owner_email for owner in owners)
                    
                    if is_service_owned:
                        self.service_drive.files().delete(
                            fileId=file['id'],
                            supportsAllDrives=True
                        ).execute()
                        deleted_count += 1
                        logger.info(f"🗑️ Deleted service-owned file: {file['name']}")
                    else:
                        logger.info(f"⏭️ Skipping personal-owned file: {file['name']}")
                        
                except Exception as delete_error:
                    logger.warning(f"⚠️ Could not delete {file['name']}: {delete_error}")
            
            logger.info(f"✅ Cleanup complete: {deleted_count}/{len(files)} service-owned files deleted")
            return True
            
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
            return False

    def get_quota_info(self):
        """Get quota information for debugging"""
        try:
            # Get about info
            about = self.service_drive.about().get(fields='storageQuota').execute()
            quota = about.get('storageQuota', {})
            
            usage = int(quota.get('usage', 0))
            limit = int(quota.get('limit', 0))
            
            usage_mb = usage / (1024*1024)
            limit_gb = limit / (1024*1024*1024) if limit > 0 else 0
            
            logger.info(f"📊 Quota info: {usage_mb:.2f} MB used / {limit_gb:.2f} GB limit")
            
            return {
                'usage_mb': usage_mb,
                'limit_gb': limit_gb,
                'usage_bytes': usage,
                'limit_bytes': limit
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting quota info: {e}")
            return None
