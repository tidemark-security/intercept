"""
Security utilities for encryption, hashing, and secret management.
"""
from cryptography.fernet import Fernet
from typing import Optional
import base64


class EncryptionService:
    """
    Service for encrypting and decrypting sensitive data using Fernet symmetric encryption.
    
    Uses a master key from the SECRET_KEY environment variable to encrypt/decrypt settings.
    This implements envelope encryption where the master key encrypts individual values.
    """
    
    def __init__(self, master_key: bytes):
        """
        Initialize the encryption service with a master key.
        
        Args:
            master_key: The master encryption key (must be 32 URL-safe base64-encoded bytes)
        """
        # If the key is not in the right format, derive a proper Fernet key
        if len(master_key) != 44:  # Fernet keys are 44 bytes when base64-encoded
            # Use the first 32 bytes of the key and base64 encode
            key_bytes = master_key[:32].ljust(32, b'0')
            master_key = base64.urlsafe_b64encode(key_bytes)
        
        self.fernet = Fernet(master_key)
    
    def encrypt(self, value: str) -> str:
        """
        Encrypt a plain text value.
        
        Args:
            value: Plain text string to encrypt
            
        Returns:
            Base64-encoded encrypted string
        """
        if not value:
            return ""
        encrypted_bytes = self.fernet.encrypt(value.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')
    
    def decrypt(self, encrypted_value: str) -> str:
        """
        Decrypt an encrypted value.
        
        Args:
            encrypted_value: Base64-encoded encrypted string
            
        Returns:
            Decrypted plain text string
            
        Raises:
            InvalidToken: If the encrypted value is invalid or tampered with
        """
        if not encrypted_value:
            return ""
        decrypted_bytes = self.fernet.decrypt(encrypted_value.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    
    def mask_secret(self, value: Optional[str]) -> str:
        """
        Mask a secret value for display in logs or API responses.
        
        Args:
            value: The secret value to mask
            
        Returns:
            Masked string (typically "***")
        """
        return "***" if value else ""
    
    @staticmethod
    def generate_key() -> bytes:
        """
        Generate a new Fernet encryption key.
        
        Returns:
            A new base64-encoded 32-byte key suitable for Fernet encryption
        """
        return Fernet.generate_key()


# Global encryption service instance (initialized in main.py or config.py)
encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """
    Get the global encryption service instance.
    
    Returns:
        The initialized EncryptionService instance
        
    Raises:
        RuntimeError: If the encryption service has not been initialized
    """
    if encryption_service is None:
        raise RuntimeError(
            "Encryption service not initialized. "
            "Call initialize_encryption_service() with the master key first."
        )
    return encryption_service


def initialize_encryption_service(master_key: bytes) -> None:
    """
    Initialize the global encryption service with the master key.
    
    Args:
        master_key: The master encryption key from SECRET_KEY environment variable
    """
    global encryption_service
    encryption_service = EncryptionService(master_key)
