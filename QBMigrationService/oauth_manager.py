import requests
import time
import json
import os
from datetime import datetime, timedelta
from config import *

class OAuthManager:
    """Manage OAuth 2.0 tokens with automatic refresh"""
    
    def __init__(self, client_id, client_secret, refresh_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = None
        self.token_expiry = None
        self.token_file = os.path.join(DATA_DIR, "oauth_tokens.json")
        
        # Load existing tokens if available
        self.load_tokens()
    
    def load_tokens(self):
        """Load tokens from file"""
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, 'r') as f:
                    data = json.load(f)
                
                self.access_token = data.get('access_token')
                self.refresh_token = data.get('refresh_token')
                
                expiry_str = data.get('token_expiry')
                if expiry_str:
                    self.token_expiry = datetime.fromisoformat(expiry_str)
                
                print("✓ OAuth tokens loaded from cache")
                
            except Exception as e:
                print(f"Warning: Could not load cached tokens: {e}")
    
    def save_tokens(self):
        """Save tokens to file"""
        data = {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'token_expiry': self.token_expiry.isoformat() if self.token_expiry else None
        }
        
        os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
        
        with open(self.token_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print("✓ OAuth tokens saved to cache")
    
    def is_token_expired(self):
        """Check if access token is expired"""
        if not self.access_token or not self.token_expiry:
            return True
        
        # Add 5-minute buffer
        return datetime.now() >= (self.token_expiry - timedelta(minutes=5))
    
    def refresh_access_token(self):
        """Refresh the access token using refresh token"""
        print("Refreshing OAuth access token...")
        
        url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }
        
        # Basic auth with client credentials
        import base64
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
        
        response = requests.post(url, headers=headers, data=data)
        
        if response.status_code == 200:
            result = response.json()
            
            self.access_token = result["access_token"]
            self.refresh_token = result["refresh_token"]  # New refresh token
            
            # Token expires in 3600 seconds (1 hour)
            expires_in = result.get("expires_in", 3600)
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in)
            
            self.save_tokens()
            
            print(f"✓ Access token refreshed (expires in {expires_in}s)")
            return self.access_token
        else:
            raise Exception(f"Token refresh failed: {response.status_code} - {response.text}")
    
    def get_access_token(self):
        """Get valid access token (refresh if needed)"""
        if self.is_token_expired():
            self.refresh_access_token()
        
        return self.access_token