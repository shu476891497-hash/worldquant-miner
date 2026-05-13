"""
Secure Credential Manager
Handles WorldQuant Brain authentication securely

IMPORTANT: Credentials are NEVER embedded in code or executable.
All credentials are loaded from external files or user input only.
"""

import json
import os
import logging
import requests
from pathlib import Path
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
from getpass import getpass

logger = logging.getLogger(__name__)


@dataclass
class Credentials:
    """Secure credential container (never logged or stored in code)"""
    username: str
    password: str
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary (for API calls only)"""
        return {
            'username': self.username,
            'password': self.password
        }
    
    def validate(self) -> bool:
        """Basic validation"""
        return bool(self.username and self.password and len(self.username) > 0 and len(self.password) > 0)


class CredentialManager:
    """
    Secure credential manager
    
    Features:
    - Loads from credential.txt or credentials.txt
    - Prompts for login if file not found
    - Validates credentials before use
    - NEVER embeds credentials in code
    - Stores credentials only in memory
    """
    
    # Possible credential file names (checked in order)
    CREDENTIAL_FILE_NAMES = ['credential.txt', 'credentials.txt']
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize credential manager
        
        Args:
            base_path: Base directory to search for credential files
                      If None, searches current directory and parent directories
        """
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self.credentials: Optional[Credentials] = None
        self.authenticated = False
        self.session: Optional[requests.Session] = None
    
    def find_credential_file(self) -> Optional[Path]:
        """
        Find credential file in common locations
        
        Returns:
            Path to credential file if found, None otherwise
        """
        # Search locations (in order of priority):
        search_paths = [
            self.base_path,  # Current/base directory
            self.base_path.parent,  # Parent directory
            Path.home(),  # User home directory
            Path.cwd(),  # Current working directory
        ]
        
        for search_path in search_paths:
            for filename in self.CREDENTIAL_FILE_NAMES:
                credential_file = search_path / filename
                if credential_file.exists() and credential_file.is_file():
                    logger.info(f"Found credential file: {credential_file}")
                    return credential_file
        
        logger.warning("No credential file found in standard locations")
        return None
    
    def load_from_file(self, file_path: Optional[Path] = None) -> bool:
        """
        Load credentials from file
        
        Args:
            file_path: Path to credential file. If None, searches automatically.
        
        Returns:
            True if credentials loaded successfully, False otherwise
        """
        if file_path is None:
            file_path = self.find_credential_file()
        
        if file_path is None:
            logger.error("No credential file specified or found")
            return False
        
        if not file_path.exists():
            logger.error(f"Credential file not found: {file_path}")
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            # Try JSON format first: ["username", "password"]
            try:
                creds_list = json.loads(content)
                if isinstance(creds_list, list) and len(creds_list) >= 2:
                    username = creds_list[0]
                    password = creds_list[1]
                else:
                    raise ValueError("Invalid credential format")
            except (json.JSONDecodeError, ValueError):
                # Try line-separated format: username\npassword
                lines = content.split('\n')
                if len(lines) >= 2:
                    username = lines[0].strip()
                    password = lines[1].strip()
                else:
                    raise ValueError("Invalid credential format")
            
            self.credentials = Credentials(username=username, password=password)
            
            if not self.credentials.validate():
                logger.error("Invalid credentials: empty username or password")
                self.credentials = None
                return False
            
            logger.info(f"✅ Credentials loaded from: {file_path}")
            logger.info(f"   Username: {self.credentials.username}")
            # NEVER log password
            return True
            
        except Exception as e:
            logger.error(f"Failed to load credentials from {file_path}: {e}")
            self.credentials = None
            return False
    
    def prompt_for_credentials(self) -> bool:
        """
        Prompt user for credentials (interactive)
        
        Returns:
            True if credentials entered, False if cancelled
        """
        try:
            print("\n" + "="*60)
            print("🔐 WORLDQUANT BRAIN AUTHENTICATION REQUIRED")
            print("="*60)
            print("Please enter your WorldQuant Brain credentials:")
            print()
            
            username = input("Username (email): ").strip()
            if not username:
                logger.warning("Username not provided")
                return False
            
            # Use getpass to hide password input
            password = getpass("Password: ").strip()
            if not password:
                logger.warning("Password not provided")
                return False
            
            self.credentials = Credentials(username=username, password=password)
            
            if not self.credentials.validate():
                logger.error("Invalid credentials: empty username or password")
                self.credentials = None
                return False
            
            logger.info(f"✅ Credentials entered (username: {self.credentials.username})")
            return True
            
        except (KeyboardInterrupt, EOFError):
            logger.warning("Credential entry cancelled by user")
            self.credentials = None
            return False
        except Exception as e:
            logger.error(f"Error prompting for credentials: {e}")
            self.credentials = None
            return False
    
    def try_auth_json(self) -> bool:
        """
        Try to authenticate using saved cookies from auth.json (bypasses Biometrics).
        Supports both cookie-based and Bearer token (JWT 't' cookie) auth.
        Returns True if the saved session is still valid.
        """
        auth_json_path = Path(__file__).parent.parent / 'auth.json'
        if not auth_json_path.exists():
            return False
        try:
            with open(auth_json_path, 'r') as f:
                storage = json.load(f)
            cookies = storage.get('cookies', [])
            if not cookies:
                return False

            # 找 't' JWT token，优先用 Authorization Bearer
            jwt_token = None
            for c in cookies:
                if c.get('name') == 't' and c.get('value', '').startswith('eyJ'):
                    jwt_token = c['value']
                    break

            test_session = requests.Session()

            if jwt_token:
                # 方式1：Bearer header（WQ Brain API 标准）
                test_session.headers['Authorization'] = f'Bearer {jwt_token}'
                resp = test_session.get('https://api.worldquantbrain.com/users/self', timeout=10)
                if resp.status_code == 200:
                    user = resp.json()
                    import base64, json as _json
                    try:
                        payload = _json.loads(base64.b64decode(jwt_token.split('.')[1] + '=='))
                        from datetime import datetime
                        exp_dt = datetime.fromtimestamp(payload.get('exp', 0))
                        hours_left = (exp_dt - datetime.now()).total_seconds() / 3600
                        logger.info(f"✅ auth.json JWT 登录成功: {user.get('email')} | Level={user.get('geniusLevel')} | token还有 {hours_left:.1f}h")
                        if hours_left < 1:
                            logger.warning("⚠️ JWT token 不足1小时到期！尝试自动从浏览器刷新...")
                            try:
                                from .auto_token_refresh import fetch_token_from_browser, save_token_to_auth_json
                                new_tok = fetch_token_from_browser()
                                if new_tok:
                                    save_token_to_auth_json(new_tok, auth_json_path)
                                    test_session.headers['Authorization'] = f'Bearer {new_tok}'
                                    logger.info("[AutoToken] token 已自动刷新")
                            except Exception as _re:
                                logger.warning(f"[AutoToken] 自动刷新失败: {_re}，请手动运行: python update_token.py <token>")
                    except Exception:
                        logger.info(f"✅ auth.json JWT 登录成功: {user.get('email')} / Level={user.get('geniusLevel')}")
                    self.authenticated = True
                    self.session = test_session
                    return True
                else:
                    logger.warning(f"auth.json JWT 已过期 (status={resp.status_code})，尝试从浏览器自动刷新...")
                    try:
                        from .auto_token_refresh import auto_refresh_if_needed
                        new_tok = auto_refresh_if_needed(auth_json_path, threshold_hours=0)
                        if new_tok:
                            test_session.headers['Authorization'] = f'Bearer {new_tok}'
                            resp_retry = test_session.get('https://api.worldquantbrain.com/users/self', timeout=10)
                            if resp_retry.status_code == 200:
                                user2 = resp_retry.json()
                                logger.info(f"[AutoToken] 自动刷新后登录成功: {user2.get('email')}")
                                self.authenticated = True
                                self.session = test_session
                                return True
                    except Exception as _re:
                        logger.warning(f"[AutoToken] 自动刷新失败: {_re}")

            # 方式2：Cookie jar 方式（兼容旧格式）
            test_session2 = requests.Session()
            for c in cookies:
                test_session2.cookies.set(c['name'], c['value'], domain=c.get('domain', '.worldquantbrain.com'))
            resp2 = test_session2.get('https://api.worldquantbrain.com/users/self', timeout=10)
            if resp2.status_code == 200:
                user = resp2.json()
                logger.info(f"✅ auth.json cookie 登录成功: {user.get('email')} / Level={user.get('geniusLevel')}")
                self.authenticated = True
                self.session = test_session2
                return True
            else:
                logger.warning(f"auth.json cookies 已过期 (status={resp2.status_code})，最后尝试浏览器自动刷新...")
                try:
                    from .auto_token_refresh import auto_refresh_if_needed
                    new_tok = auto_refresh_if_needed(auth_json_path, threshold_hours=0)
                    if new_tok:
                        sess_final = requests.Session()
                        sess_final.headers['Authorization'] = f'Bearer {new_tok}'
                        r_final = sess_final.get('https://api.worldquantbrain.com/users/self', timeout=10)
                        if r_final.status_code == 200:
                            uf = r_final.json()
                            logger.info(f"[AutoToken] 最终自动刷新成功: {uf.get('email')}")
                            self.authenticated = True
                            self.session = sess_final
                            return True
                except Exception as _re:
                    logger.warning(f"[AutoToken] 最终刷新失败: {_re}")
                return False
        except Exception as e:
            logger.warning(f"auth.json 读取失败: {e}")
            return False

    def validate_credentials(self) -> bool:
        """
        Validate credentials by attempting authentication.
        Handles Biometrics/inquiry 401 gracefully.
        
        Returns:
            True if credentials are valid, False otherwise
        """
        if not self.credentials or not self.credentials.validate():
            logger.error("No valid credentials to validate")
            return False
        
        try:
            test_session = requests.Session()
            from requests.auth import HTTPBasicAuth
            auth = HTTPBasicAuth(self.credentials.username, self.credentials.password)
            
            logger.info(f"Validating credentials for: {self.credentials.username}")
            response = test_session.post(
                'https://api.worldquantbrain.com/authentication',
                auth=auth,
                timeout=10
            )
            
            if response.status_code == 201:
                logger.info("✅ Credentials validated successfully")
                self.authenticated = True
                self.session = test_session
                self.session.auth = auth
                return True
            elif response.status_code == 401:
                body = response.json() if response.content else {}
                inquiry_id = body.get('inquiry', '')
                if inquiry_id:
                    logger.error(f"❌ WQ Brain 要求 Biometrics 验证 (inquiry={inquiry_id})")
                    logger.error("   请运行: python inject_cookies.py \"<从DevTools复制的Cookie>\"")
                    logger.error("   或参考 README 了解如何获取 Cookie")
                else:
                    logger.error(f"❌ Authentication failed: 401 {response.text[:200]}")
                self.authenticated = False
                return False
            else:
                logger.error(f"❌ Authentication failed: {response.status_code}")
                logger.error(f"   Response: {response.text[:200]}")
                self.authenticated = False
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Network error during credential validation: {e}")
            self.authenticated = False
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error during credential validation: {e}")
            self.authenticated = False
            return False
    
    def get_credentials(self) -> Optional[Credentials]:
        """
        Get current credentials (if authenticated)
        
        Returns:
            Credentials object if available, None otherwise
        """
        if self.authenticated and self.credentials:
            return self.credentials
        return None
    
    def get_session(self) -> Optional[requests.Session]:
        """
        Get authenticated session
        
        Returns:
            Authenticated requests.Session if available, None otherwise
        """
        if self.authenticated and self.session:
            return self.session
        return None
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        return self.authenticated
    
    def authenticate(self, auto_load: bool = True, auto_prompt: bool = True) -> bool:
        """
        Complete authentication flow.
        Priority: auth.json cookies > credential.txt password > prompt
        
        Returns:
            True if authenticated, False otherwise
        """
        # Step 0: Try saved cookies first (bypasses Biometrics completely)
        logger.info("尝试 auth.json Cookie 登录...")
        if self.try_auth_json():
            return True
        logger.info("auth.json 不可用，尝试密码登录...")

        # Step 1: Try to load from credential file
        if auto_load:
            if self.load_from_file():
                if self.validate_credentials():
                    return True
                else:
                    logger.warning("Credentials from file failed validation")
        
        # Step 2: Prompt user if file not found or validation failed
        if auto_prompt:
            if self.prompt_for_credentials():
                if self.validate_credentials():
                    return True
                else:
                    logger.error("Entered credentials failed validation")
        
        logger.error("❌ Authentication failed - cannot proceed without valid credentials")
        return False
    
    def clear_credentials(self):
        """Clear credentials from memory (security)"""
        if self.credentials:
            # Overwrite password in memory (best effort)
            self.credentials.password = "***CLEARED***"
        self.credentials = None
        self.authenticated = False
        self.session = None
        logger.info("Credentials cleared from memory")


def get_credential_manager(base_path: Optional[str] = None) -> CredentialManager:
    """
    Factory function to get credential manager instance
    
    Args:
        base_path: Base directory to search for credentials
    
    Returns:
        CredentialManager instance
    """
    return CredentialManager(base_path=base_path)
