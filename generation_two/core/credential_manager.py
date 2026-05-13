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
    
    def validate_credentials(self) -> bool:
        """
        Validate credentials by attempting authentication
        
        Returns:
            True if credentials are valid, False otherwise
        """
        if not self.credentials or not self.credentials.validate():
            logger.error("No valid credentials to validate")
            return False
        
        try:
            # Create a temporary session for validation
            test_session = requests.Session()
            
            from requests.auth import HTTPBasicAuth
            auth = HTTPBasicAuth(self.credentials.username, self.credentials.password)
            
            # Attempt authentication
            logger.info(f"Validating credentials for: {self.credentials.username}")
            response = test_session.post(
                'https://api.worldquantbrain.com/authentication',
                auth=auth,
                timeout=10
            )
            
            if response.status_code == 201:
                logger.info("✅ Credentials validated successfully")
                self.authenticated = True
                
                # Store session for reuse
                self.session = test_session
                self.session.auth = auth
                
                return True
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
        Complete authentication flow
        
        Args:
            auto_load: Automatically try to load from file
            auto_prompt: Automatically prompt if file not found
        
        Returns:
            True if authenticated, False otherwise
        """
        # Step 1: Try to load from file
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
