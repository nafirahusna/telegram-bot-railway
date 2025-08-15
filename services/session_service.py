# services/session_service.py
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class SessionService:
    def __init__(self, google_service):
        self.google_service = google_service
        self.session_file = 'user_sessions.json'
    
    def _load_sessions(self):
        """Load sessions from file"""
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"❌ Error loading sessions: {e}")
                return {}
        return {}
    
    def _save_sessions(self, sessions):
        """Save sessions to file"""
        try:
            with open(self.session_file, 'w') as f:
                json.dump(sessions, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Error saving sessions: {e}")
    
    def create_session(self, user_id):
        """Create new session"""
        try:
            sessions = self._load_sessions()
            sessions[str(user_id)] = {
                'report_type': None,
                'id_ticket': None,
                'folder_id': None,
                'photos': [],
                'data': None,
                'created_at': datetime.now().isoformat()
            }
            self._save_sessions(sessions)
            logger.info(f"✅ Session created for user {user_id}")
            return sessions[str(user_id)]
        except Exception as e:
            logger.error(f"❌ Error creating session: {e}")
            return None
    
    def get_session(self, user_id):
        """Get current session"""
        try:
            sessions = self._load_sessions()
            return sessions.get(str(user_id))
        except Exception as e:
            logger.error(f"❌ Error getting session: {e}")
            return None
    
    def update_session(self, user_id, data):
        """Update session data"""
        try:
            sessions = self._load_sessions()
            if str(user_id) in sessions:
                sessions[str(user_id)].update(data)
                self._save_sessions(sessions)
                logger.info(f"✅ Session updated for user {user_id}")
                return True
            else:
                logger.error(f"❌ Session not found for user {user_id}")
                return False
        except Exception as e:
            logger.error(f"❌ Error updating session: {e}")
            return False
    
    def end_session(self, user_id):
        """End current session"""
        try:
            sessions = self._load_sessions()
            if str(user_id) in sessions:
                del sessions[str(user_id)]
                self._save_sessions(sessions)
                logger.info(f"✅ Session ended for user {user_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Error ending session: {e}")
            return False
