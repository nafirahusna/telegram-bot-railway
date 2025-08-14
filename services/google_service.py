import os
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
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
            creds = Credentials.from_service_account_file(
                'service-account.json',
                scopes=SCOPES
            )
            
            self.service_drive = build('drive', 'v3', credentials=creds)
            self.service_sheets = build('sheets', 'v4', credentials=creds)
            print("✓ Google APIs authenticated successfully!")
            return True
        except Exception as e:
            print(f"✖ Error authenticating with service account: {e}")
            return False
