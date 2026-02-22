"""Observable extraction service for MCP tools.

Extracts and deduplicates observables (IPs, domains, hashes, etc.)
from timeline items.
"""

import re
from typing import List, Dict, Set
from collections import defaultdict

from app.mcp.schemas import ObservableSummary


# Regex patterns for observable extraction
IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
DOMAIN_PATTERN = re.compile(r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b')
MD5_PATTERN = re.compile(r'\b[a-fA-F0-9]{32}\b')
SHA1_PATTERN = re.compile(r'\b[a-fA-F0-9]{40}\b')
SHA256_PATTERN = re.compile(r'\b[a-fA-F0-9]{64}\b')
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')


def extract_observables(timeline_items: List[Dict], max_observables: int = 20) -> List[ObservableSummary]:
    """Extract and deduplicate observables from timeline items.
    
    Args:
        timeline_items: List of timeline item dictionaries
        max_observables: Maximum number of observables to return
        
    Returns:
        List of ObservableSummary objects, deduplicated and sorted by count
        
    Extracts from:
        - ObservableItem types (type="observable")
        - NetworkTrafficItem (type="network_traffic")
        - SystemItem (type="system")
        - Note items (searches body text)
    """
    # Track observables with counts
    observable_counts: Dict[tuple, int] = defaultdict(int)
    
    for item in timeline_items:
        item_type = item.get("type", "")
        
        # Extract from ObservableItem
        if item_type == "observable":
            obs_type = item.get("observable_type", "").upper()
            obs_value = item.get("value", "").strip()
            if obs_type and obs_value:
                observable_counts[(obs_type, obs_value)] += 1
        
        # Extract from NetworkTrafficItem
        elif item_type == "network_traffic":
            src_ip = item.get("source_ip")
            dst_ip = item.get("destination_ip")
            domain = item.get("domain")
            
            if src_ip:
                observable_counts[("IP", src_ip.strip())] += 1
            if dst_ip:
                observable_counts[("IP", dst_ip.strip())] += 1
            if domain:
                observable_counts[("DOMAIN", domain.strip())] += 1
        
        # Extract from SystemItem
        elif item_type == "system":
            hostname = item.get("hostname")
            ip_address = item.get("ip_address")
            
            if hostname:
                # Determine if it's an IP or hostname
                if IP_PATTERN.fullmatch(hostname.strip()):
                    observable_counts[("IP", hostname.strip())] += 1
                else:
                    observable_counts[("DOMAIN", hostname.strip())] += 1
            
            if ip_address:
                observable_counts[("IP", ip_address.strip())] += 1
        
        # Extract from note/other text fields
        body = item.get("body") or item.get("content") or item.get("description") or ""
        if body:
            _extract_from_text(body, observable_counts)
    
    # Convert to list and sort by count (descending)
    observables = [
        ObservableSummary(type=obs_type, value=value, count=count)
        for (obs_type, value), count in observable_counts.items()
    ]
    observables.sort(key=lambda x: x.count, reverse=True)
    
    # Limit to max_observables
    return observables[:max_observables]


def _extract_from_text(text: str, observable_counts: Dict[tuple, int]) -> None:
    """Extract observables from free-form text.
    
    Args:
        text: Text to extract from
        observable_counts: Dictionary to update with found observables
    """
    # Extract IPs
    for match in IP_PATTERN.finditer(text):
        ip = match.group(0)
        # Basic validation: no part > 255
        parts = [int(p) for p in ip.split('.')]
        if all(0 <= p <= 255 for p in parts):
            observable_counts[("IP", ip)] += 1
    
    # Extract hashes
    for match in SHA256_PATTERN.finditer(text):
        observable_counts[("HASH", match.group(0).lower())] += 1
    for match in SHA1_PATTERN.finditer(text):
        # Avoid double-counting if already captured as SHA256
        hash_val = match.group(0).lower()
        if ("HASH", hash_val) not in observable_counts:
            observable_counts[("HASH", hash_val)] += 1
    for match in MD5_PATTERN.finditer(text):
        # Avoid double-counting
        hash_val = match.group(0).lower()
        if ("HASH", hash_val) not in observable_counts:
            observable_counts[("HASH", hash_val)] += 1
    
    # Extract emails
    for match in EMAIL_PATTERN.finditer(text):
        observable_counts[("EMAIL", match.group(0).lower())] += 1
    
    # Extract domains (but exclude emails and IPs)
    for match in DOMAIN_PATTERN.finditer(text):
        domain = match.group(0).lower()
        # Skip if it's part of an email
        if "@" not in text[max(0, match.start()-1):match.end()+1]:
            # Skip if it looks like an IP
            if not IP_PATTERN.fullmatch(domain):
                observable_counts[("DOMAIN", domain)] += 1


def extract_high_signal_entities(timeline_items: List[Dict]) -> Set[str]:
    """Extract high-signal entities for similarity matching.
    
    Returns a set of entity strings (IPs, domains, hashes) that appear
    in the timeline items, for use in similarity scoring.
    
    Args:
        timeline_items: List of timeline item dictionaries
        
    Returns:
        Set of entity strings (e.g., {"10.0.0.1", "malware.com", "abc123..."})
    """
    entities: Set[str] = set()
    observables = extract_observables(timeline_items, max_observables=100)
    
    for obs in observables:
        # Only include high-signal types
        if obs.type in ("IP", "DOMAIN", "HASH"):
            entities.add(obs.value)
    
    return entities
