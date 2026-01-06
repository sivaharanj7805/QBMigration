import requests
import time
import json
import os
from datetime import datetime, timedelta
from typing import Optional, List
from config import *

class OAuthManager:
    """
    Enhanced OAuth 2.0 manager with:
    - Automatic token refresh
    - Scope verification
    - Token introspection
    - Secure token storage
    """
    
    def __init__(self, client_id, client_secret, refresh_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = None
        self.token_expiry = None
        self.token_file = os.path.join(DATA_DIR, "oauth_tokens.json")
        self.scopes = []
        
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
                self.scopes = data.get('scopes', [])
                
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
            'token_expiry': self.token_expiry.isoformat() if self.token_expiry else None,
            'scopes': self.scopes,
            'updated_at': datetime.now().isoformat()
        }
        
        os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
        
        with open(self.token_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Make file readable only by owner
        os.chmod(self.token_file, 0o600)
        
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
        
        response = requests.post(OAUTH_TOKEN_URL, headers=headers, data=data)
        
        if response.status_code == 200:
            result = response.json()
            
            self.access_token = result["access_token"]
            self.refresh_token = result["refresh_token"]  # New refresh token
            
            # Parse scopes
            scope_string = result.get("x_refresh_token_expires_in", "")
            self.scopes = scope_string.split() if scope_string else []
            
            # Token expires in 3600 seconds (1 hour)
            expires_in = result.get("expires_in", 3600)
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in)
            
            self.save_tokens()
            
            print(f"✓ Access token refreshed (expires in {expires_in}s)")
            
            # Verify scopes
            self.verify_scopes()
            
            return self.access_token
        else:
            error_detail = response.text
            raise Exception(f"Token refresh failed: {response.status_code} - {error_detail}")
    
    def get_access_token(self):
        """Get valid access token (refresh if needed)"""
        if self.is_token_expired():
            self.refresh_access_token()
        
        return self.access_token
    
    def verify_scopes(self) -> bool:
        """
        Verify token has required scopes for migration
        
        Required scope: com.intuit.quickbooks.accounting
        """
        print("\nVerifying OAuth permissions...")
        
        try:
            # Introspect token
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = {
                "token": self.access_token
            }
            
            # Use client credentials for introspection
            import base64
            credentials = f"{self.client_id}:{self.client_secret}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
            
            introspect_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/introspect"
            response = requests.post(introspect_url, headers=headers, data=data)
            
            if response.status_code == 200:
                result = response.json()
                
                if not result.get('active', False):
                    print("  ❌ Token is not active")
                    return False
                
                scope_string = result.get('scope', '')
                actual_scopes = scope_string.split() if scope_string else []
                
                # Check for required scope
                required = "com.intuit.quickbooks.accounting"
                
                if required in actual_scopes:
                    print(f"  ✓ Token has required scope: {required}")
                    return True
                else:
                    print(f"  ❌ Token missing required scope: {required}")
                    print(f"     Actual scopes: {', '.join(actual_scopes)}")
                    
                    raise Exception(
                        f"OAuth token does not have required scope: {required}\n"
                        f"Please re-authorize the application with full accounting access."
                    )
            else:
                # If introspection fails, assume OK (some QBO apps don't support it)
                print("  ⚠️  Could not verify scopes (assuming OK)")
                return True
                
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  Scope verification failed: {e}")
            return True  # Don't block migration if verification fails
    
    def revoke_tokens(self):
        """Revoke refresh and access tokens"""
        print("Revoking OAuth tokens...")
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        # Basic auth
        import base64
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
        
        # Revoke refresh token
        data = {"token": self.refresh_token}
        
        response = requests.post(OAUTH_REVOKE_URL, headers=headers, data=data)
        
        if response.status_code == 200:
            print("✓ Tokens revoked")
            
            # Delete local token file
            if os.path.exists(self.token_file):
                os.remove(self.token_file)
        else:
            print(f"Warning: Token revocation failed: {response.status_code}")
    
    def get_company_info(self) -> Optional[dict]:
        """Get company info to verify connection"""
        try:
            headers = {
                "Authorization": f"Bearer {self.get_access_token()}",
                "Accept": "application/json"
            }
            
            url = f"{BASE_URL}/companyinfo/{REALM_ID}"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                company_info = result.get("CompanyInfo", {})
                
                print(f"\n✓ Connected to: {company_info.get('CompanyName')}")
                print(f"  Legal Name: {company_info.get('LegalName', 'N/A')}")
                print(f"  Country: {company_info.get('Country', 'N/A')}")
                
                return company_info
            else:
                print(f"Warning: Could not fetch company info: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Warning: Could not fetch company info: {e}")
            return None