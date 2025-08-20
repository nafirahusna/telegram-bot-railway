#!/usr/bin/env python3
"""
setup_oauth2.py - Script untuk mendapatkan refresh token OAuth2

INSTRUKSI PENGGUNAAN:
1. Download client_secrets.json dari Google Cloud Console
2. Letakkan file tersebut di folder yang sama dengan script ini
3. Run: python setup_oauth2.py
4. Follow instruksi di browser untuk authorize
5. Copy refresh_token yang dihasilkan ke environment variable

REQUIREMENTS:
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""

import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Scopes yang diperlukan
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]

def generate_refresh_token():
    """Generate refresh token untuk OAuth2"""
    
    # Check if client_secrets.json exists
    if not os.path.exists('client_secrets.json'):
        print("❌ File 'client_secrets.json' tidak ditemukan!")
        print("📋 Langkah-langkah untuk mendapatkan file ini:")
        print("1. Buka https://console.cloud.google.com/")
        print("2. Pilih project atau buat project baru")
        print("3. Enable Google Drive API dan Google Sheets API")
        print("4. Buat OAuth2 credentials (Desktop Application)")
        print("5. Download file JSON dan rename menjadi 'client_secrets.json'")
        print("6. Letakkan di folder yang sama dengan script ini")
        return None
    
    try:
        # Load client secrets
        with open('client_secrets.json', 'r') as f:
            client_config = json.load(f)
        
        print("✅ client_secrets.json loaded successfully")
        print(f"📧 Client ID: {client_config['installed']['client_id']}")
        
        # Create flow
        flow = InstalledAppFlow.from_client_secrets_file(
            'client_secrets.json', 
            SCOPES
        )
        
        # Run local server for authorization
        print("\n🔐 Starting OAuth2 authorization flow...")
        print("📱 Your browser will open automatically")
        print("🔗 If browser doesn't open, copy the URL from terminal")
        
        # This will open browser and handle the OAuth flow
        creds = flow.run_local_server(port=0)
        
        print("\n✅ Authorization successful!")
        
        # Extract information
        client_id = client_config['installed']['client_id']
        client_secret = client_config['installed']['client_secret']
        refresh_token = creds.refresh_token
        
        print("\n" + "="*60)
        print("🎉 OAUTH2 SETUP BERHASIL!")
        print("="*60)
        print("\n📋 Copy informasi berikut ke environment variables:")
        print(f"\nGOOGLE_CLIENT_ID={client_id}")
        print(f"GOOGLE_CLIENT_SECRET={client_secret}")
        print(f"GOOGLE_REFRESH_TOKEN={refresh_token}")
        
        print("\n" + "="*60)
        print("📝 LANGKAH SELANJUTNYA:")
        print("="*60)
        print("1. Copy ketiga environment variables di atas")
        print("2. Set ke Railway/Heroku/platform deployment Anda")
        print("3. Atau tambahkan ke file .env untuk development")
        print("4. Restart aplikasi Anda")
        print("\n✅ Aplikasi akan menggunakan OAuth2 dengan auto-refresh token!")
        
        # Save to file for backup
        oauth_info = {
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
            'generated_at': str(datetime.now())
        }
        
        with open('oauth2_credentials.json', 'w') as f:
            json.dump(oauth_info, f, indent=2)
        
        print(f"\n💾 Backup saved to: oauth2_credentials.json")
        print("⚠️  JANGAN commit file ini ke repository!")
        
        return {
            'client_id': client_id,
            'client_secret': client_secret, 
            'refresh_token': refresh_token
        }
        
    except FileNotFoundError:
        print("❌ File client_secrets.json tidak ditemukan!")
        return None
    except Exception as e:
        print(f"❌ Error during OAuth2 setup: {e}")
        return None

def test_refresh_token(client_id, client_secret, refresh_token):
    """Test refresh token untuk memastikan working"""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        
        print("\n🧪 Testing refresh token...")
        
        # Create credentials object
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES
        )
        
        # Refresh token
        request = Request()
        creds.refresh(request)
        
        print("✅ Refresh token test PASSED!")
        print(f"🔑 New access token generated: {creds.token[:20]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Refresh token test FAILED: {e}")
        return False

if __name__ == "__main__":
    print("🚀 OAuth2 Setup Script untuk Google APIs")
    print("="*50)
    
    result = generate_refresh_token()
    
    if result:
        print("\n🧪 Testing the generated refresh token...")
        test_success = test_refresh_token(
            result['client_id'],
            result['client_secret'], 
            result['refresh_token']
        )
        
        if test_success:
            print("\n🎉 SETUP LENGKAP DAN BERHASIL!")
            print("✅ Refresh token working dengan baik")
            print("✅ Siap untuk production deployment!")
        else:
            print("\n⚠️ Setup berhasil tapi ada masalah dengan refresh token")
            print("🔄 Silakan coba run script ini lagi")
    else:
        print("\n❌ Setup gagal. Silakan periksa client_secrets.json dan coba lagi.")
