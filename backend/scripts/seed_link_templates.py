#!/usr/bin/env python3
"""
Seed Link Templates Script

Populates the database with default link template configurations.
These templates define how to generate contextual action links from timeline items.

Usage:
    cd backend
    conda activate intercept
    python scripts/seed_link_templates.py
"""

import asyncio
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models.models import LinkTemplate
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Default link template configurations
# Based on frontend/src/utils/linkTemplates.tsx
DEFAULT_TEMPLATES = [
    {
        "template_id": "email",
        "name": "Email",
        "icon_name": "Mail",
        "tooltip_template": "Email {{contact_email}}",
        "url_template": "mailto:{{contact_email}}",
        "field_names": ["contact_email", "email"],
        "conditions": None,
        "surface_scopes": ["timeline_item"],
        "entity_types": None,
        "enabled": True,
        "display_order": 10,
    },
    {
        "template_id": "phone",
        "name": "Phone Call",
        "icon_name": "Phone",
        "tooltip_template": "Call {{contact_phone}}",
        "url_template": "tel:{{contact_phone}}",
        "field_names": ["contact_phone", "phone"],
        "conditions": None,
        "surface_scopes": ["timeline_item"],
        "entity_types": None,
        "enabled": True,
        "display_order": 20,
    },
    {
        "template_id": "ms-teams-chat",
        "name": "Microsoft Teams Chat",
        "icon_name": "Send",
        "tooltip_template": "Chat with {{user_id}} on Teams",
        "url_template": "https://teams.microsoft.com/l/chat/0/0?users={{user_id}}",
        "field_names": ["user_id"],
        "conditions": {"type": "internal_actor"},
        "surface_scopes": ["timeline_item"],
        "entity_types": None,
        "enabled": True,
        "display_order": 30,
    },
    {
        "template_id": "ms-teams-call",
        "name": "Microsoft Teams Call",
        "icon_name": "Video",
        "tooltip_template": "Call {{user_id}} on Teams",
        "url_template": "https://teams.microsoft.com/l/call/0/0?users={{user_id}}",
        "field_names": ["user_id"],
        "conditions": {"type": "internal_actor"},
        "surface_scopes": ["timeline_item"],
        "entity_types": None,
        "enabled": True,
        "display_order": 40,
    },
    {
        "template_id": "slack-dm",
        "name": "Slack Direct Message",
        "icon_name": "Slack",
        "tooltip_template": "Message on Slack",
        "url_template": "https://slack.com/app_redirect?team=YOUR_TEAM_ID&channel={{slack_user_id}}",
        "field_names": ["slack_user_id"],
        "conditions": None,
        "surface_scopes": ["timeline_item"],
        "entity_types": None,
        "enabled": False,  # Disabled by default - requires configuration
        "display_order": 50,
    },
    {
        "template_id": "cmdb-lookup",
        "name": "CMDB Lookup",
        "icon_name": "Database",
        "tooltip_template": "View in CMDB: {{cmdb_id}}",
        "url_template": "https://cmdb.example.com/asset/{{cmdb_id}}",
        "field_names": ["cmdb_id"],
        "conditions": None,
        "surface_scopes": ["timeline_item"],
        "entity_types": None,
        "enabled": False,  # Disabled by default - requires configuration
        "display_order": 60,
    },
    {
        "template_id": "user-directory",
        "name": "User Directory",
        "icon_name": "User",
        "tooltip_template": "View user profile",
        "url_template": "https://directory.example.com/user/{{user_id}}",
        "field_names": ["user_id"],
        "conditions": None,
        "surface_scopes": ["timeline_item"],
        "entity_types": None,
        "enabled": False,  # Disabled by default - requires configuration
        "display_order": 70,
    },
    {
        "template_id": "threat-intel",
        "name": "Threat Intelligence Search",
        "icon_name": "Search",
        "tooltip_template": "Search threat intel for {{observable_value}}",
        "url_template": "https://threatintel.example.com/search?q={{observable_value}}",
        "field_names": ["observable_value"],
        "conditions": None,
        "surface_scopes": ["timeline_item"],
        "entity_types": None,
        "enabled": False,  # Disabled by default - requires configuration
        "display_order": 80,
    },
    {
        "template_id": "virustotal-domain",
        "name": "VirusTotal Domain Lookup",
        "icon_name": "VirusTotalIcon",
        "tooltip_template": "Check domain {{observable_value}} on VirusTotal",
        "url_template": "https://www.virustotal.com/gui/domain/{{observable_value}}",
        "field_names": ["observable_value"],
        "conditions": {"observable_type": "DOMAIN"},
        "surface_scopes": ["timeline_item"],
        "entity_types": None,
        "enabled": True,
        "display_order": 95,
    },
    {
        "template_id": "virustotal-ip",
        "name": "VirusTotal IP Lookup",
        "icon_name": "VirusTotalIcon",
        "tooltip_template": "Check IP {{observable_value}} on VirusTotal",
        "url_template": "https://www.virustotal.com/gui/ip-address/{{observable_value}}",
        "field_names": ["observable_value"],
        "conditions": {"observable_type": "IP"},
        "surface_scopes": ["timeline_item"],
        "entity_types": None,
        "enabled": True,
        "display_order": 99,
    },
]

UPDATABLE_TEMPLATE_FIELDS = (
    "name",
    "icon_name",
    "tooltip_template",
    "url_template",
    "field_names",
    "conditions",
    "surface_scopes",
    "entity_types",
    "display_order",
)


async def seed_link_templates():
    """Seed the database with default link templates."""
    
    async with AsyncSession(engine) as session:
        logger.info("Starting link template seeding...")
        
        # Check existing templates
        result = await session.execute(select(LinkTemplate))
        existing_templates = result.scalars().all()
        existing_by_id = {
            template.template_id: template
            for template in existing_templates
        }
        
        logger.info(f"Found {len(existing_templates)} existing link templates")
        
        # Add new templates
        added_count = 0
        updated_count = 0
        
        for template_data in DEFAULT_TEMPLATES:
            template_id = template_data["template_id"]
            
            existing = existing_by_id.get(template_id)
            if existing is not None:
                # Preserve the operator-controlled enabled state.
                for field_name in UPDATABLE_TEMPLATE_FIELDS:
                    setattr(existing, field_name, template_data[field_name])
                
                session.add(existing)
                updated_count += 1
                logger.info("Updated template: %s", template_id)
            else:
                # Create new template
                template = LinkTemplate(
                    template_id=template_id,
                    name=template_data["name"],
                    icon_name=template_data["icon_name"],
                    tooltip_template=template_data["tooltip_template"],
                    url_template=template_data["url_template"],
                    field_names=template_data["field_names"],
                    conditions=template_data["conditions"],
                    surface_scopes=template_data["surface_scopes"],
                    entity_types=template_data["entity_types"],
                    enabled=template_data["enabled"],
                    display_order=template_data["display_order"],
                )
                session.add(template)
                added_count += 1
                logger.info("Added new template: %s", template_id)
        
        # Commit all changes
        await session.commit()
        
        logger.info("✓ Seeding complete: %d added, %d updated", added_count, updated_count)
        logger.info("✓ Total link templates: %d", len(existing_templates) + added_count)


async def main():
    """Main entry point."""
    try:
        await seed_link_templates()
        logger.info("Link template seeding completed successfully")
        return 0
    except Exception as e:
        logger.error("Failed to seed link templates: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
