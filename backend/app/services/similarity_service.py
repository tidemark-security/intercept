"""Similarity service for finding related alerts/cases/tasks.

Implements similarity scoring based on:
1. Source + normalized title (primary key)
2. Entity overlap (IPs, domains, hashes)
3. Timeline content similarity
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Set, List, Dict, Any
from sqlmodel import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Alert


def compute_similarity_key(alert: Alert) -> str:
    """Compute similarity key for an alert.
    
    Key format: "source::normalized_title"
    
    Args:
        alert: Alert object
        
    Returns:
        Similarity key string (e.g., "crowdstrike::powershell execution detected")
    """
    source = (alert.source or "unknown").strip().lower()
    
    # Normalize title: lowercase, remove special chars, collapse whitespace
    title = alert.title.lower()
    title = re.sub(r'[^a-z0-9\s]', ' ', title)  # Remove special chars
    title = re.sub(r'\s+', ' ', title).strip()  # Collapse whitespace
    
    return f"{source}::{title}"


async def count_similar_alerts(
    db: AsyncSession,
    alert: Alert,
    days: int = 30
) -> int:
    """Count alerts with same similarity key in time window.
    
    Args:
        db: Database session
        alert: Alert to find similar alerts for
        days: Time window in days (default: 30)
        
    Returns:
        Count of similar alerts (excluding the alert itself)
    """
    similarity_key = compute_similarity_key(alert)
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Count alerts with same similarity key
    # Exclude the alert itself if it's already in DB
    query = select(func.count(Alert.id)).where(
        Alert.created_at >= cutoff_time
    )
    
    # Filter by similarity key components
    source = (alert.source or "unknown").strip().lower()
    
    # Compute normalized title for comparison
    title = alert.title.lower()
    title = re.sub(r'[^a-z0-9\s]', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()
    
    # Find alerts with same source
    if alert.source:
        query = query.where(func.lower(Alert.source) == source)
    else:
        query = query.where(Alert.source.is_(None))
    
    # Find alerts with similar normalized title (using LIKE for now)
    # Note: For production, consider using pg_trgm extension for better fuzzy matching
    query = query.where(
        func.lower(
            func.regexp_replace(
                func.regexp_replace(Alert.title, r'[^a-zA-Z0-9\s]', ' ', 'g'),
                r'\s+', ' ', 'g'
            )
        ).like(f"%{title}%")
    )
    
    # Exclude the alert itself if it has an ID
    if alert.id is not None:
        query = query.where(Alert.id != alert.id)
    
    result = await db.execute(query)
    count = result.scalar_one()
    
    return count


def compute_entity_overlap(entities_a: Set[str], entities_b: Set[str]) -> float:
    """Compute Jaccard similarity between two entity sets.
    
    Args:
        entities_a: Set of entities from first item
        entities_b: Set of entities from second item
        
    Returns:
        Jaccard similarity (0.0 to 1.0)
    """
    if not entities_a and not entities_b:
        return 0.0
    
    intersection = len(entities_a & entities_b)
    union = len(entities_a | entities_b)
    
    if union == 0:
        return 0.0
    
    return intersection / union


async def find_related_alerts(
    db: AsyncSession,
    alert: Alert,
    max_matches: int = 10
) -> List[Dict[str, Any]]:
    """Find related alerts with explainable reasons.
    
    Args:
        db: Database session
        alert: Seed alert
        max_matches: Maximum matches to return (1-20)
        
    Returns:
        List of matches with scores and reasons
    """
    from sqlmodel import select, func
    from app.core.id_parser import format_entity_id
    
    matches = []
    
    # Limit max_matches
    max_matches = min(max(1, max_matches), 20)
    
    # Strategy 1: Same source + title similarity
    similarity_key = compute_similarity_key(alert)
    source = (alert.source or "unknown").strip().lower()
    
    # Normalize title for comparison
    title = alert.title.lower()
    title = re.sub(r'[^a-z0-9\s]', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()
    
    # Find alerts with same source and similar normalized title
    query = select(Alert).where(
        Alert.id != alert.id  # Exclude self
    )
    
    # Filter by same source
    if alert.source:
        query = query.where(func.lower(Alert.source) == source)
    
    # Fuzzy title match using LIKE
    query = query.where(
        func.lower(
            func.regexp_replace(
                func.regexp_replace(Alert.title, r'[^a-zA-Z0-9\s]', ' ', 'g'),
                r'\s+', ' ', 'g'
            )
        ).like(f"%{title}%")
    )
    
    # Limit results
    query = query.limit(max_matches)
    
    result = await db.execute(query)
    similar_alerts = result.scalars().all()
    
    for similar_alert in similar_alerts:
        reasons = []
        score = 0.0
        
        # Reason: Same source + title
        if compute_similarity_key(similar_alert) == similarity_key:
            reasons.append("same_source_title")
            score = 0.9  # High confidence for exact match
        else:
            reasons.append("similar_title")
            score = 0.7  # Lower confidence for fuzzy match
        
        # Check for shared entities (IPs, domains, hashes)
        # Extract entities from both alerts
        seed_entities = extract_high_signal_entities(alert.timeline_items or [])
        match_entities = extract_high_signal_entities(similar_alert.timeline_items or [])
        
        # Find shared entities
        shared = seed_entities & match_entities
        if shared:
            for entity in list(shared)[:3]:  # Limit to top 3
                # Determine entity type
                if re.match(r'^(?:\d{1,3}\.){3}\d{1,3}$', entity):
                    reasons.append(f"shared_ip:{entity}")
                elif re.match(r'^[a-fA-F0-9]{32,64}$', entity):
                    reasons.append(f"shared_hash:{entity[:8]}...")
                else:
                    reasons.append(f"shared_domain:{entity}")
            
            # Boost score based on entity overlap
            overlap_score = compute_entity_overlap(seed_entities, match_entities)
            score = min(1.0, score + (overlap_score * 0.3))
        
        matches.append({
            "alert": similar_alert,
            "score": round(score, 2),
            "reasons": reasons,
        })
    
    # Sort by score descending
    matches.sort(key=lambda x: x["score"], reverse=True)
    
    return matches[:max_matches]


def extract_high_signal_entities(timeline_items: List[dict]) -> Set[str]:
    """Extract high-signal entities for similarity matching.
    
    Returns IPs, domains, and hashes from timeline items.
    
    Args:
        timeline_items: List of timeline item dictionaries
        
    Returns:
        Set of entity strings
    """
    from app.services.observable_service import extract_observables
    
    entities: Set[str] = set()
    observables = extract_observables(timeline_items, max_observables=100)
    
    for obs in observables:
        # Only include high-signal types
        if obs.type in ("IP", "DOMAIN", "HASH"):
            entities.add(obs.value)
    
    return entities
