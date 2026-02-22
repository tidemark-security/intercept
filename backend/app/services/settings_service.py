"""
Settings service for managing application configuration.

Provides CRUD operations for app settings with:
- Environment variable precedence
- Encryption for secret values
- Audit logging for changes
- Type coercion (STRING, NUMBER, BOOLEAN, JSON)
"""
import os
import json
import logging
from typing import Optional, List, Any, Dict
from datetime import datetime, timezone
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.models import (
    AppSetting,
    AppSettingCreate,
    AppSettingUpdate,
    AppSettingRead,
)
from app.models.enums import SettingType
from app.core.security import get_encryption_service

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for managing application settings."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.encryption = get_encryption_service()

    async def get_all_settings(
        self,
        category: Optional[str] = None,
        include_secrets: bool = False,
    ) -> List[AppSettingRead]:
        """
        Get all settings, optionally filtered by category.
        
        Args:
            category: Filter by category (optional)
            include_secrets: If True, decrypt secret values; otherwise mask them
            
        Returns:
            List of settings
        """
        query = select(AppSetting)
        
        if category:
            query = query.where(AppSetting.category == category)
        
        result = await self.db.execute(query)
        settings = result.scalars().all()
        
        # Process settings to apply environment variable precedence and masking
        settings_list = []
        for setting in settings:
            setting_dict = setting.model_dump()
            
            # Check for environment variable override
            env_key = self._get_env_key(setting.key)
            env_value = os.getenv(env_key)
            
            if env_value is not None:
                # Environment variable takes precedence
                setting_dict['value'] = env_value
            elif setting.is_secret:
                if include_secrets:
                    # Decrypt the value
                    setting_dict['value'] = self.encryption.decrypt(setting.value or "")
                else:
                    # Mask the secret
                    setting_dict['value'] = self.encryption.mask_secret(setting.value)
            
            settings_list.append(AppSettingRead(**setting_dict))
        
        return settings_list

    async def get_setting(
        self,
        key: str,
        include_secret: bool = False,
    ) -> Optional[AppSettingRead]:
        """
        Get a single setting by key.
        
        Args:
            key: Setting key
            include_secret: If True, decrypt secret value; otherwise mask it
            
        Returns:
            Setting or None if not found
        """
        # Check environment variable first
        env_key = self._get_env_key(key)
        env_value = os.getenv(env_key)
        
        # Get from database
        result = await self.db.execute(
            select(AppSetting).where(AppSetting.key == key)
        )
        setting = result.scalar_one_or_none()
        
        if setting:
            setting_dict = setting.model_dump()
            
            if env_value is not None:
                # Environment variable takes precedence
                setting_dict['value'] = env_value
            elif setting.is_secret:
                if include_secret:
                    # Decrypt the value
                    setting_dict['value'] = self.encryption.decrypt(setting.value or "")
                else:
                    # Mask the secret
                    setting_dict['value'] = self.encryption.mask_secret(setting.value)
            
            return AppSettingRead(**setting_dict)
        
        # Setting not in database, but might have env var
        if env_value is not None:
            # Return a pseudo-setting from environment
            return AppSettingRead(
                id=0,
                key=key,
                value=env_value,
                value_type=SettingType.STRING,
                is_secret=False,
                description=f"From environment variable {env_key}",
                category="environment",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        
        return None

    async def create_setting(
        self,
        setting_create: AppSettingCreate,
    ) -> AppSettingRead:
        """
        Create a new setting.
        
        Args:
            setting_create: Setting creation data
            
        Returns:
            Created setting
            
        Raises:
            ValueError: If setting key already exists
        """
        # Check if setting already exists
        existing = await self.db.execute(
            select(AppSetting).where(AppSetting.key == setting_create.key)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Setting with key '{setting_create.key}' already exists")
        
        # Encrypt value if it's a secret
        value_to_store = setting_create.value
        if setting_create.is_secret and value_to_store:
            value_to_store = self.encryption.encrypt(value_to_store)
        
        # Create the setting
        setting = AppSetting(
            **setting_create.model_dump(exclude={"value"}),
            value=value_to_store,
        )
        
        self.db.add(setting)
        await self.db.commit()
        await self.db.refresh(setting)
        
        logger.info(
            f"Created setting: key={setting.key}, category={setting.category}, "
            f"is_secret={setting.is_secret}"
        )
        
        # Return with masked secret
        setting_dict = setting.model_dump()
        if setting.is_secret:
            setting_dict['value'] = self.encryption.mask_secret(setting.value)
        
        return AppSettingRead(**setting_dict)

    async def update_setting(
        self,
        key: str,
        setting_update: AppSettingUpdate,
    ) -> AppSettingRead:
        """
        Update an existing setting.
        
        Args:
            key: Setting key
            setting_update: Setting update data
            
        Returns:
            Updated setting
            
        Raises:
            ValueError: If setting not found
        """
        # Get existing setting
        result = await self.db.execute(
            select(AppSetting).where(AppSetting.key == key)
        )
        setting = result.scalar_one_or_none()
        
        if not setting:
            raise ValueError(f"Setting with key '{key}' not found")
        
        # Store old value for audit log
        old_value = setting.value
        if setting.is_secret and old_value:
            old_value = self.encryption.mask_secret(old_value)
        
        # Update fields
        update_data = setting_update.model_dump(exclude_unset=True)
        
        # Encrypt new value if it's a secret
        if 'value' in update_data and setting.is_secret:
            if update_data['value']:
                update_data['value'] = self.encryption.encrypt(update_data['value'])
        
        for field, value in update_data.items():
            setattr(setting, field, value)
        
        setting.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        await self.db.refresh(setting)
        
        # Log the change
        new_value = setting.value
        if setting.is_secret and new_value:
            new_value = self.encryption.mask_secret(new_value)
        
        logger.info(
            f"Updated setting: key={key}, old_value={old_value}, new_value={new_value}"
        )
        
        # Return with masked secret
        setting_dict = setting.model_dump()
        if setting.is_secret:
            setting_dict['value'] = self.encryption.mask_secret(setting.value)
        
        return AppSettingRead(**setting_dict)

    async def delete_setting(self, key: str) -> bool:
        """
        Delete a setting.
        
        Args:
            key: Setting key
            
        Returns:
            True if deleted, False if not found
        """
        result = await self.db.execute(
            select(AppSetting).where(AppSetting.key == key)
        )
        setting = result.scalar_one_or_none()
        
        if not setting:
            return False
        
        await self.db.delete(setting)
        await self.db.commit()
        
        logger.info(f"Deleted setting: key={key}")
        
        return True

    async def get_typed_value(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """
        Get a setting value with type coercion.
        
        Args:
            key: Setting key
            default: Default value if setting not found
            
        Returns:
            Typed value (str, int, float, bool, dict/list)
        """
        setting = await self.get_setting(key, include_secret=True)
        
        if not setting:
            return default
        
        value = setting.value
        
        if value is None:
            return default
        
        # Type coercion based on value_type
        try:
            if setting.value_type == SettingType.NUMBER:
                # Try int first, then float
                try:
                    return int(value)
                except ValueError:
                    return float(value)
            elif setting.value_type == SettingType.BOOLEAN:
                # Handle various boolean representations
                return value.lower() in ('true', '1', 'yes', 'on')
            elif setting.value_type == SettingType.JSON:
                return json.loads(value)
            else:  # STRING
                return value
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(
                f"Failed to coerce value for setting {key}: {e}. "
                f"Returning raw value."
            )
            return value

    @staticmethod
    def _get_env_key(setting_key: str) -> str:
        """
        Convert setting key to environment variable name.
        
        Examples:
            langflow.base_url -> LANGFLOW__BASE_URL
            langflow.api_key -> LANGFLOW__API_KEY
        """
        return setting_key.upper().replace('.', '__')

    async def get_flow_id_for_context(self, context_type: str) -> str:
        """
        Get the LangFlow flow ID for a given context type.
        
        Args:
            context_type: Context type (general, case, task, alert)
            
        Returns:
            Flow ID for the context type, or default flow ID if not configured
            
        Raises:
            ValueError: If no flow ID is configured for the context and no default exists
        """
        from app.models.enums import LangFlowContextType
        
        # Map context types to setting keys
        context_to_setting = {
            LangFlowContextType.general: "langflow.default_flow_id",
            LangFlowContextType.case: "langflow.case_detail_flow_id",
            LangFlowContextType.task: "langflow.task_detail_flow_id",
            LangFlowContextType.alert: "langflow.alert_triage_flow_id",
        }
        
        # Normalize context_type to enum
        try:
            context_enum = LangFlowContextType(context_type)
        except ValueError:
            context_enum = LangFlowContextType.general
        
        # Get the setting key for this context
        setting_key = context_to_setting.get(context_enum, "langflow.default_flow_id")
        
        # Try to get the context-specific flow ID
        flow_id = await self.get_typed_value(setting_key)
        
        # Fall back to default flow ID if context-specific is not set
        if not flow_id and context_enum != LangFlowContextType.general:
            flow_id = await self.get_typed_value("langflow.default_flow_id")
        
        if not flow_id:
            raise ValueError(
                f"No flow ID configured for context '{context_type}'. "
                f"Please set '{setting_key}' or 'langflow.default_flow_id' in settings."
            )
        
        return flow_id
