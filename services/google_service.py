import os
import json
import base64
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload
from datetime import datetime

SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']

class GoogleService:
    def __init__(self, parent_folder_id="1mLsCBEqEb0R4_pX75-xmpRE1023H6A90"):
        self.service_drive = None
        self.service_sheets = None
        self.parent_folder_id = parent_folder_id
        
    def authenticate(self):
        """Authenticate with Google APIs using service account"""
        try:
            service_account_info = None
            
            if os.getenv('GOOGLE_CREDENTIALS_BASE64'):
                try:
                    encoded_creds = os.getenv('GOOGLE_CREDENTIALS_BASE64')
                    decoded_creds = base64.b64decode(encoded_creds).decode('utf-8')
                    service_account_info = json.loads(decoded_creds)
                except Exception as e:
                    print(f"Error decoding base64 credentials: {e}")
            
            elif os.path.exists('service-account.json'):
                with open('service-account.json', 'r') as f:
                    service_account_info = json.load(f)
            
            else:
                raise FileNotFoundError("No service account credentials found")
            
            if not service_account_info:
                raise ValueError("Service account information is empty")
            
            creds = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=SCOPES
            )
            
            self.service_drive = build('drive', 'v3', credentials=creds)
            self.service_sheets = build('sheets', 'v4', credentials=creds)
            return True
            
        except Exception as e:
            print(f"Error authenticating Google APIs: {e}")
            return False

    def create_folder(self, folder_name, parent_folder_id=None):
        """Create folder in Google Drive"""
        try:
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_folder_id or self.parent_folder_id]
            }
            
            folder = self.service_drive.files().create(body=folder_metadata).execute()
            return folder.get('id')
        except Exception as e:
            print(f"Error creating folder: {e}")
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
            return uploaded_file.get('id')
        except Exception as e:
            print(f"Error uploading file: {e}")
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
            
            return True
            
        except Exception as e:
            print(f"Error updating spreadsheet: {e}")
            return False
