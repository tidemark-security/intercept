"""
Generic validation library for data types.

This module provides centralized validation rules for various data types
including observables (IOCs) and network fields. Rules are exposed via API
for dynamic frontend consumption.

The validation patterns were consolidated from search_service.py and 
observable_service.py to provide a single source of truth.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any

from app.models.enums import ObservableType, Protocol


@dataclass
class ValidationResult:
    """Result of a validation check."""
    valid: bool
    error: Optional[str] = None


@dataclass
class ValidationRule:
    """Definition of a validation rule."""
    key: str
    label: str
    pattern: Optional[str] = None  # Regex pattern (None if using allowed_values or custom validator)
    pattern_flags: int = 0  # re.IGNORECASE, etc.
    allowed_values: Optional[List[str]] = None  # For enum-based validation
    min_value: Optional[int] = None  # For integer range validation (inclusive)
    max_value: Optional[int] = None  # For integer range validation (inclusive)
    examples: List[str] = field(default_factory=list)
    error_message: str = "Invalid value"
    # Post-regex validation function (e.g., IP address check)
    # Takes the value and returns ValidationResult
    _custom_validator: Optional[Callable[[str], ValidationResult]] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API response (excludes internal fields)."""
        result = {
            "key": self.key,
            "label": self.label,
            "examples": self.examples,
            "error_message": self.error_message,
        }
        if self.pattern is not None:
            result["pattern"] = self.pattern
            if self.pattern_flags:
                result["pattern_flags"] = self.pattern_flags
        if self.allowed_values is not None:
            result["allowed_values"] = self.allowed_values
        if self.min_value is not None:
            result["min_value"] = self.min_value
        if self.max_value is not None:
            result["max_value"] = self.max_value
        return result


# =============================================================================
# Custom Validators (post-regex checks)
# =============================================================================

def _validate_ip_address(value: str) -> ValidationResult:
    """Validate IPv4 or IPv6 address using Python's ipaddress library."""
    try:
        ipaddress.ip_address(value)
        return ValidationResult(True)
    except ValueError:
        return ValidationResult(False, "Invalid IP address format")


# =============================================================================
# Regex Patterns (consolidated from search_service.py)
# =============================================================================

# Observable patterns
IPV4_PATTERN = r'^(\d{1,3}\.){3}\d{1,3}$'
IPV6_PATTERN = (
    r'^(?:'
    r'(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|'  # Full form
    r'(?:[0-9a-fA-F]{1,4}:){1,7}:|'  # Trailing ::
    r'(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|'  # Single omitted group
    r'(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}|'
    r'[0-9a-fA-F]{1,4}:(?:(?::[0-9a-fA-F]{1,4}){1,6})|'
    r':(?:(?::[0-9a-fA-F]{1,4}){1,7}|:)|'  # Leading :: and ::
    r'fe80:(?::[0-9a-fA-F]{0,4}){0,4}%[0-9A-Za-z]+|'
    r'::(?:ffff(?::0{1,4}){0,1}:){0,1}'
    r'(?:25[0-5]|(?:2[0-4]|1{0,1}[0-9])?[0-9])'
    r'(?:\.(?:25[0-5]|(?:2[0-4]|1{0,1}[0-9])?[0-9])){3}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,4}:'
    r'(?:25[0-5]|(?:2[0-4]|1{0,1}[0-9])?[0-9])'
    r'(?:\.(?:25[0-5]|(?:2[0-4]|1{0,1}[0-9])?[0-9])){3}'
    r')$'
)
# Combined IP pattern: IPv4 OR IPv6
IP_PATTERN = f'({IPV4_PATTERN})|({IPV6_PATTERN})'

EMAIL_PATTERN = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
URL_PATTERN = r'^https?://[^\s]+$'
DOMAIN_PATTERN = r'^([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'

# Hash patterns - accept any of MD5 (32), SHA1 (40), or SHA256 (64)
MD5_PATTERN = r'^[a-fA-F0-9]{32}$'
SHA1_PATTERN = r'^[a-fA-F0-9]{40}$'
SHA256_PATTERN = r'^[a-fA-F0-9]{64}$'
HASH_PATTERN = f'({MD5_PATTERN})|({SHA1_PATTERN})|({SHA256_PATTERN})'

# Filename pattern - has extension, no invalid characters
# Group 1 captures the extension for validation against allowed extensions
FILENAME_PATTERN = r'^[^<>:"/\\|?*\x00-\x1f]+\.([a-zA-Z0-9]{1,10})$'

# MITRE ATT&CK ID pattern - technique (T1234) or sub-technique (T1234.001)
# Covers techniques T0000-T9999 and sub-techniques with .000-.999 suffix
MITRE_ATTACK_PATTERN = r'^[Tt][0-9]{4}(\.[0-9]{3})?$'

# Registry key pattern - must start with HKEY_
REGISTRY_KEY_PATTERN = r'^HKEY_[A-Z_]+\\.*$'

# Process name pattern - any non-empty string (permissive)
PROCESS_NAME_PATTERN = r'^.+$'

# Network patterns
PORT_PATTERN = r'^\d{1,5}$'


# =============================================================================
# Validation Rules Registry
# =============================================================================

def _build_validation_rules() -> Dict[str, ValidationRule]:
    """Build the validation rules registry."""
    rules = {}
    
    # Observable rules
    rules["observable.IP"] = ValidationRule(
        key="observable.IP",
        label="IP Address",
        pattern=IP_PATTERN,
        examples=["192.168.1.1", "10.0.0.1", "2001:db8::1", "::1"],
        error_message="Invalid IP address format. Expected IPv4 (e.g., 192.168.1.1) or IPv6 (e.g., 2001:db8::1)",
        _custom_validator=_validate_ip_address,
    )
    
    rules["observable.DOMAIN"] = ValidationRule(
        key="observable.DOMAIN",
        label="Domain",
        pattern=DOMAIN_PATTERN,
        examples=["example.com", "sub.domain.org", "mail.google.com"],
        error_message="Invalid domain format. Expected format: subdomain.domain.tld",
    )
    
    rules["observable.HASH"] = ValidationRule(
        key="observable.HASH",
        label="Hash",
        pattern=HASH_PATTERN,
        examples=[
            "d41d8cd98f00b204e9800998ecf8427e",  # MD5
            "da39a3ee5e6b4b0d3255bfef95601890afd80709",  # SHA1
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # SHA256
        ],
        error_message="Invalid hash format. Expected MD5 (32 chars), SHA1 (40 chars), or SHA256 (64 chars) hexadecimal",
    )
    
    rules["observable.FILENAME"] = ValidationRule(
        key="observable.FILENAME",
        label="Filename",
        pattern=FILENAME_PATTERN,
        examples=["malware.exe", "document.pdf", "script.ps1"],
        error_message="Invalid filename. Must have an extension and cannot contain special characters (<>:\"/\\|?*)",
    )
    
    rules["observable.URL"] = ValidationRule(
        key="observable.URL",
        label="URL",
        pattern=URL_PATTERN,
        pattern_flags=re.IGNORECASE,
        examples=["https://example.com/path", "http://malicious.site/payload"],
        error_message="Invalid URL format. Must start with http:// or https://",
    )
    
    rules["observable.EMAIL"] = ValidationRule(
        key="observable.EMAIL",
        label="Email",
        pattern=EMAIL_PATTERN,
        examples=["user@example.com", "phishing@malicious.org"],
        error_message="Invalid email format. Expected format: user@domain.tld",
    )
    
    rules["observable.REGISTRY_KEY"] = ValidationRule(
        key="observable.REGISTRY_KEY",
        label="Registry Key",
        pattern=REGISTRY_KEY_PATTERN,
        examples=[
            "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run",
            "HKEY_CURRENT_USER\\Software\\Classes",
        ],
        error_message="Invalid registry key. Must start with HKEY_ followed by a valid hive name and path",
    )
    
    rules["observable.PROCESS_NAME"] = ValidationRule(
        key="observable.PROCESS_NAME",
        label="Process Name",
        pattern=PROCESS_NAME_PATTERN,
        examples=["cmd.exe", "powershell.exe", "svchost.exe"],
        error_message="Process name cannot be empty",
    )
    
    # Network rules
    rules["network.src_ip"] = ValidationRule(
        key="network.src_ip",
        label="Source IP Address",
        pattern=IP_PATTERN,
        examples=["192.168.1.100", "10.0.0.50", "fe80::1"],
        error_message="Invalid source IP format. Expected IPv4 or IPv6 address",
        _custom_validator=_validate_ip_address,
    )
    
    rules["network.dst_ip"] = ValidationRule(
        key="network.dst_ip",
        label="Destination IP Address",
        pattern=IP_PATTERN,
        examples=["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888"],
        error_message="Invalid destination IP format. Expected IPv4 or IPv6 address",
        _custom_validator=_validate_ip_address,
    )
    
    rules["network.src_port"] = ValidationRule(
        key="network.src_port",
        label="Source Port",
        min_value=0,
        max_value=65535,
        examples=["443", "8080", "22"],
        error_message="Invalid port. Must be a number between 0 and 65535",
    )
    
    rules["network.dst_port"] = ValidationRule(
        key="network.dst_port",
        label="Destination Port",
        min_value=0,
        max_value=65535,
        examples=["443", "80", "22"],
        error_message="Invalid port. Must be a number between 0 and 65535",
    )
    
    # Protocol uses allowed_values from the Protocol enum
    rules["network.protocol"] = ValidationRule(
        key="network.protocol",
        label="Protocol",
        allowed_values=[p.value for p in Protocol],
        examples=["TCP", "UDP", "ICMP"],
        error_message="Invalid protocol. Must be a valid IANA protocol name",
    )
    
    return rules


# Global registry - built once at module load
VALIDATION_RULES: Dict[str, ValidationRule] = _build_validation_rules()


# =============================================================================
# Validation Functions
# =============================================================================

def validate_value(key: str, value: str) -> ValidationResult:
    """
    Validate a value against the rule identified by key.
    
    Args:
        key: The validation rule key (e.g., "observable.IP", "network.src_port")
        value: The value to validate
        
    Returns:
        ValidationResult with valid=True if valid, or valid=False with error message
    """
    if key not in VALIDATION_RULES:
        # Unknown rule - pass validation (permissive for extensibility)
        return ValidationResult(True)
    
    rule = VALIDATION_RULES[key]
    
    # Check allowed_values first (for enum-based validation)
    if rule.allowed_values is not None:
        if value not in rule.allowed_values:
            return ValidationResult(False, rule.error_message)
        return ValidationResult(True)
    
    # Check integer range (for numeric validation like ports)
    if rule.min_value is not None or rule.max_value is not None:
        try:
            num_value = int(value)
            if rule.min_value is not None and num_value < rule.min_value:
                return ValidationResult(False, rule.error_message)
            if rule.max_value is not None and num_value > rule.max_value:
                return ValidationResult(False, rule.error_message)
            return ValidationResult(True)
        except ValueError:
            return ValidationResult(False, rule.error_message)
    
    # Check regex pattern
    if rule.pattern is not None:
        pattern = re.compile(rule.pattern, rule.pattern_flags)
        if not pattern.match(value):
            return ValidationResult(False, rule.error_message)
    
    # Run custom validator if defined (e.g., IP octet range, port range)
    if rule._custom_validator is not None:
        result = rule._custom_validator(value)
        if not result.valid:
            return result
    
    return ValidationResult(True)


def get_all_rules() -> Dict[str, Dict[str, Any]]:
    """
    Get all validation rules as a dict for API response.
    
    Returns:
        Dict mapping rule keys to their definitions (patterns, examples, error messages)
    """
    return {key: rule.to_dict() for key, rule in VALIDATION_RULES.items()}


def get_rule(key: str) -> Optional[ValidationRule]:
    """
    Get a specific validation rule by key.
    
    Args:
        key: The validation rule key
        
    Returns:
        ValidationRule if found, None otherwise
    """
    return VALIDATION_RULES.get(key)


# =============================================================================
# Exported Patterns (for use in search_service.py and other modules)
# =============================================================================

# Compiled patterns for extraction (with word boundaries for text search)
EXTRACTION_PATTERNS = {
    "ip": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
    "domain": re.compile(r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b'),
    "md5": re.compile(r'\b[a-fA-F0-9]{32}\b'),
    "sha1": re.compile(r'\b[a-fA-F0-9]{40}\b'),
    "sha256": re.compile(r'\b[a-fA-F0-9]{64}\b'),
    "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
}

# Strict validation patterns (anchored, for form validation)
STRICT_PATTERNS = {
    "ipv4": re.compile(IPV4_PATTERN),
    "ipv6": re.compile(IPV6_PATTERN),
    "email": re.compile(EMAIL_PATTERN),
    "url": re.compile(URL_PATTERN, re.IGNORECASE),
    "domain": re.compile(DOMAIN_PATTERN),
    "md5": re.compile(MD5_PATTERN),
    "sha1": re.compile(SHA1_PATTERN),
    "sha256": re.compile(SHA256_PATTERN),
    "hash": re.compile(HASH_PATTERN),
    "filename": re.compile(FILENAME_PATTERN),
    "registry_key": re.compile(REGISTRY_KEY_PATTERN),
    "port": re.compile(PORT_PATTERN),
    "mitre_attack": re.compile(MITRE_ATTACK_PATTERN),
}
