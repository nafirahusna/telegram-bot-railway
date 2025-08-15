import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from datetime import datetime

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
            from google.oauth2 import service_account
            
            # Load service account credentials
            creds = service_account.Credentials.from_service_account_file(
                'service-account.json',
                scopes=SCOPES
            )
            
            self.service_drive = build('drive', 'v3', credentials=creds)
            self.service_sheets = build('sheets', 'v4', credentials=creds)
            print("✅ Google APIs authenticated successfully with service account!")
            return True
            
        except Exception as e:
            print(f"❌ Error authenticating with service account: {e}")
            return False

    def create_folder(self, folder_name, parent_folder_id=None):
        """Create folder in Google Drive"""
        try:
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_folder_id or self.parent_folder_id:
                folder_metadata['parents'] = [parent_folder_id or self.parent_folder_id]
            
            folder = self.service_drive.files().create(body=folder_metadata).execute()
            print(f"ÃƒÂ¢Ã…â€œÃ¢â‚¬Â¦ Folder created: {folder_name}")
            return folder.get('id')
        except Exception as e:
            print(f"ÃƒÂ¢Ã‚ÂÃ…â€™ Error creating folder: {e}")
            return None

    def upload_to_drive(self, file_path, file_name, folder_id):
        """Upload file to Google Drive"""
        try:
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            media = MediaFileUpload(file_path, resumable=True)
            uploaded_file = self.service_drive.files().create(
                body=file_metadata, 
                media_body=media
            ).execute()
            print(f"ÃƒÂ¢Ã…â€œÃ¢â‚¬Â¦ File uploaded: {file_name}")
            return uploaded_file.get('id')
        except Exception as e:
            print(f"ÃƒÂ¢Ã‚ÂÃ…â€™ Error uploading file: {e}")
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
            
            print(f"ÃƒÂ¢Ã…â€œÃ¢â‚¬Â¦ Successfully added row to spreadsheet")
            print(f"Row data: {row_data}")  # Debug print
            return True
            
        except Exception as e:
            print(f"ÃƒÂ¢Ã‚ÂÃ…â€™ Error updating spreadsheet: {e}")
            return False
