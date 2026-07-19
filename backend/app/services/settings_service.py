"""
Unified settings service for managing application configuration.

Resolves settings through a strict precedence chain:
    1. Environment variable (real env var)
    2. .env file (resolved via Pydantic BaseSettings / os.getenv)
    3. Database (app_settings table) — skipped for local_only settings
    4. Default from the declarative registry

Provides CRUD operations for DB-backed settings with:
- Encryption for secret values
- Type coercion (STRING, NUMBER, BOOLEAN, JSON)
- Registry-driven metadata (local_only, category, description)
"""
from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_encryption_service
from app.core.settings_registry import (
    SETTINGS_REGISTRY,
    SettingDefinition,
    coerce_setting_value,
    get_environment_value,
)
from app.models.enums import SettingType
from app.models.models import (
    AppSetting,
    AppSettingCreate,
    AppSettingRead,
    AppSettingUpdate,
)
from app.services.audit_service import AuditContext, get_audit_service

logger = logging.getLogger(__name__)


class SettingWriteError(ValueError):
    """Base class for expected setting-write rejections."""


class SettingValidationError(SettingWriteError):
    """Raised when a setting cannot be written in the requested form."""


class SettingConflictError(SettingWriteError):
    """Raised when a setting create conflicts with an existing row."""


class SettingNotFoundError(SettingWriteError):
    """Raised when a setting targeted for update does not exist."""


class SettingConfigurationError(RuntimeError):
    """Raised when a required effective setting has not been configured."""


class SettingDecryptionError(RuntimeError):
    """Raised when persisted secret setting data cannot be decrypted."""


class SettingsService:
    """Unified service for resolving, reading, and writing application settings.

    Reads use the precedence chain: env var → .env → database → registry default.
    Writes target the ``app_settings`` database table (rejected for local_only keys).
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._encryption: Optional[Any] = None

    def _audit_value(self, value: Optional[str], *, is_secret: bool, encrypted: bool) -> Optional[str]:
        if value is None:
            return None

        display_value = value
        if is_secret:
            if encrypted:
                try:
                    display_value = self.encryption.decrypt(value)
                except Exception:
                    display_value = value
            display_value = self.encryption.mask_secret(str(display_value))
        return str(display_value)

    def _setting_audit_snapshot(
        self,
        *,
        key: str,
        value: Optional[str],
        value_type: SettingType,
        is_secret: bool,
        description: Optional[str],
        category: str,
        encrypted: bool,
    ) -> Dict[str, Any]:
        return {
            "key": key,
            "value": self._audit_value(value, is_secret=is_secret, encrypted=encrypted),
            "value_type": value_type.value,
            "is_secret": is_secret,
            "description": description,
            "category": category,
        }

    def _registered_setting_read(
        self,
        definition: SettingDefinition,
        db_row: Optional[AppSetting],
        *,
        include_secret: bool,
        now: datetime,
    ) -> AppSettingRead:
        value, source = self._resolve_value(definition, db_row)
        if definition.is_secret and value is not None and not include_secret:
            value = self.encryption.mask_secret(str(value))

        return AppSettingRead.model_validate(
            {
                "id": db_row.id if db_row else 0,
                "key": definition.key,
                "value": self._serialize_display_value(value, definition.value_type),
                "value_type": definition.value_type,
                "is_secret": definition.is_secret,
                "description": definition.description,
                "category": definition.category,
                "local_only": definition.local_only,
                "source": source,
                "created_at": db_row.created_at if db_row else now,
                "updated_at": db_row.updated_at if db_row else now,
            }
        )

    def _database_setting_read(
        self,
        db_row: AppSetting,
        *,
        include_secret: bool,
    ) -> AppSettingRead:
        value = db_row.value
        source = "database"
        env_key = db_row.key.upper().replace(".", "__")
        env_value = self._env_lookup(env_key)
        if env_value is not None:
            value = env_value
            source = "env"
        elif db_row.is_secret and value:
            value = self.encryption.decrypt(value)

        if db_row.is_secret and value and not include_secret:
            value = self.encryption.mask_secret(value)

        return AppSettingRead.model_validate(
            {
                "id": db_row.id,
                "key": db_row.key,
                "value": value,
                "value_type": db_row.value_type,
                "is_secret": db_row.is_secret,
                "description": db_row.description,
                "category": db_row.category,
                "local_only": False,
                "source": source,
                "created_at": db_row.created_at,
                "updated_at": db_row.updated_at,
            }
        )

    def _write_setting_read(self, setting: AppSetting) -> AppSettingRead:
        setting_data = setting.model_dump()
        if setting.is_secret:
            setting_data["value"] = self.encryption.mask_secret(setting.value)
        setting_data["local_only"] = False
        setting_data["source"] = "database"
        return AppSettingRead(**setting_data)

    @property
    def encryption(self):
        """Lazy-load encryption service (only needed for secret values)."""
        if self._encryption is None:
            self._encryption = get_encryption_service()
        return self._encryption

    @staticmethod
    def _env_lookup(env_var: str) -> Optional[str]:
        """Look up an env var from os.environ, then fall back to .env file."""
        return get_environment_value(env_var)

    @staticmethod
    def _validate_value_type(
        key: str,
        raw_value: Optional[str],
        value_type: SettingType,
    ) -> None:
        """Validate a raw setting value against its declared SettingType."""
        if raw_value is None:
            return

        if value_type == SettingType.BOOLEAN:
            normalized = raw_value.strip().lower()
            if normalized not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
                raise SettingValidationError(
                    f"Invalid value for setting '{key}': expected BOOLEAN "
                    f"(accepted: true/false/1/0/yes/no/on/off), got {raw_value!r}"
                )
            return

        try:
            coerce_setting_value(raw_value, value_type)
        except (TypeError, ValueError) as exc:
            raise SettingValidationError(
                f"Invalid value for setting '{key}': expected {value_type.value}, got {raw_value!r}"
            ) from exc

    # ------------------------------------------------------------------
    # Unified resolution
    # ------------------------------------------------------------------

    async def get(self, key: str, default: Any = None) -> Any:
        """Resolve a single setting value through the full precedence chain.

        Returns the *typed* value (coerced via ``SettingType`` from the
        registry).  If the key is unknown to the registry the method still
        falls back to the database so that ad-hoc settings continue to work.
        """
        definition = SETTINGS_REGISTRY.get(key)
        db_row: Optional[AppSetting] = None
        if definition is None or not definition.local_only:
            result = await self.db.execute(
                select(AppSetting).where(AppSetting.key == key)
            )
            db_row = result.scalar_one_or_none()

        if definition is not None:
            return self._resolve_typed_value(definition, db_row, default)
        return self._resolve_ad_hoc_value(db_row, key=key, default=default)

    async def get_many(self, defaults: Mapping[str, Any]) -> Dict[str, Any]:
        """Resolve several settings through the precedence chain with one DB query."""
        unresolved_db_keys = []
        for key in defaults:
            definition = SETTINGS_REGISTRY.get(key)
            if definition is not None and self._env_lookup(definition.env_var) is not None:
                continue
            if definition is None or not definition.local_only:
                unresolved_db_keys.append(key)

        db_rows: Dict[str, AppSetting] = {}
        if unresolved_db_keys:
            result = await self.db.execute(
                select(AppSetting).where(AppSetting.key.in_(unresolved_db_keys))
            )
            db_rows = {row.key: row for row in result.scalars().all()}

        resolved: Dict[str, Any] = {}
        for key, caller_default in defaults.items():
            definition = SETTINGS_REGISTRY.get(key)
            row = db_rows.get(key)

            if definition is not None:
                resolved[key] = self._resolve_typed_value(
                    definition,
                    row,
                    caller_default,
                )
                continue
            resolved[key] = self._resolve_ad_hoc_value(
                row,
                key=key,
                default=caller_default,
            )

        return resolved

    # ------------------------------------------------------------------
    # Read (API-facing, includes metadata)
    # ------------------------------------------------------------------

    async def get_all_settings(
        self,
        category: Optional[str] = None,
        include_secrets: bool = False,
    ) -> List[AppSettingRead]:
        """Return all registered settings with resolved values.

        Iterates the full ``SETTINGS_REGISTRY`` so that every known setting
        appears in the response — even those that only exist in env vars or
        as defaults.  Also includes any *ad-hoc* database rows not in the
        registry.
        """
        # Load all DB settings in one query
        query = select(AppSetting)
        result = await self.db.execute(query)
        db_settings: Dict[str, AppSetting] = {
            s.key: s for s in result.scalars().all()
        }

        settings_list: List[AppSettingRead] = []
        now = datetime.now(timezone.utc)

        for defn in SETTINGS_REGISTRY.values():
            if category and defn.category != category:
                continue

            db_row = db_settings.pop(defn.key, None)
            settings_list.append(
                self._registered_setting_read(
                    defn,
                    db_row,
                    include_secret=include_secrets,
                    now=now,
                )
            )

        # Include ad-hoc DB rows that are NOT in the registry
        for key, db_row in db_settings.items():
            if category and db_row.category != category:
                continue

            settings_list.append(
                self._database_setting_read(
                    db_row,
                    include_secret=include_secrets,
                )
            )

        return settings_list

    async def get_setting(
        self,
        key: str,
        include_secret: bool = False,
    ) -> Optional[AppSettingRead]:
        """Return a single setting with resolved value and metadata."""
        defn = SETTINGS_REGISTRY.get(key)
        now = datetime.now(timezone.utc)

        # Load DB row (unless local_only)
        db_row: Optional[AppSetting] = None
        if defn is None or not defn.local_only:
            res = await self.db.execute(
                select(AppSetting).where(AppSetting.key == key)
            )
            db_row = res.scalar_one_or_none()

        if defn is not None:
            return self._registered_setting_read(
                defn,
                db_row,
                include_secret=include_secret,
                now=now,
            )

        # Not in registry — fall back to DB-only behaviour
        if db_row is not None:
            return self._database_setting_read(
                db_row,
                include_secret=include_secret,
            )

        return None

    # ------------------------------------------------------------------
    # Write operations (DB-backed settings only)
    # ------------------------------------------------------------------

    async def create_setting(
        self,
        setting_create: AppSettingCreate,
        *,
        performed_by: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
    ) -> AppSettingRead:
        """Create a new DB-backed setting.

        Raises a typed ``SettingWriteError`` for rejected writes.
        """
        setting = await self.create_setting_in_transaction(
            setting_create,
            performed_by=performed_by,
            audit_context=audit_context,
        )
        response = self._write_setting_read(setting)
        await self.db.commit()

        logger.info(
            "Created setting: key=%s, category=%s, is_secret=%s",
            response.key,
            response.category,
            response.is_secret,
        )

        return response

    async def create_setting_in_transaction(
        self,
        setting_create: AppSettingCreate,
        *,
        performed_by: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
    ) -> AppSetting:
        """Create a registered setting while leaving commit ownership to the caller."""
        defn = SETTINGS_REGISTRY.get(setting_create.key)
        if defn is None:
            raise SettingValidationError(
                "Settings must be registered before they can be created"
            )
        if defn.local_only:
            raise SettingValidationError(
                f"Setting '{setting_create.key}' is local-only and cannot be "
                f"stored in the database. Set it via the {defn.env_var} "
                f"environment variable instead."
            )

        existing = await self.db.execute(
            select(AppSetting).where(AppSetting.key == setting_create.key)
        )
        if existing.scalar_one_or_none():
            raise SettingConflictError(
                f"Setting with key '{setting_create.key}' already exists"
            )

        self._validate_value_type(
            setting_create.key,
            setting_create.value,
            defn.value_type,
        )

        value_to_store = setting_create.value
        if defn.is_secret and value_to_store:
            value_to_store = self.encryption.encrypt(value_to_store)

        setting = AppSetting(
            key=setting_create.key,
            value=value_to_store,
            value_type=defn.value_type,
            is_secret=defn.is_secret,
            category=defn.category,
            description=defn.description,
        )
        self.db.add(setting)
        await self.db.flush()
        await get_audit_service(self.db).log_event(
            event_type="settings.created",
            entity_type="setting",
            entity_id=setting.key,
            description=f"Setting created: {setting.key}",
            new_value=self._setting_audit_snapshot(
                key=setting.key,
                value=setting.value,
                value_type=setting.value_type,
                is_secret=setting.is_secret,
                description=setting.description,
                category=setting.category,
                encrypted=setting.is_secret,
            ),
            performed_by=performed_by,
            context=audit_context,
        )
        await self.db.flush()
        return setting

    async def update_setting(
        self,
        key: str,
        setting_update: AppSettingUpdate,
        *,
        performed_by: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
    ) -> AppSettingRead:
        """Update an existing DB-backed setting.

        Raises a typed ``SettingWriteError`` for rejected writes.
        """
        setting = await self.update_setting_in_transaction(
            key,
            setting_update,
            performed_by=performed_by,
            audit_context=audit_context,
        )
        response = self._write_setting_read(setting)
        await self.db.commit()

        logger.info(
            "Updated setting: value_changed=%s",
            "value" in setting_update.model_fields_set,
        )

        return response

    async def update_setting_in_transaction(
        self,
        key: str,
        setting_update: AppSettingUpdate,
        *,
        performed_by: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
    ) -> AppSetting:
        """Update and audit a setting while leaving commit ownership to the caller."""
        defn = SETTINGS_REGISTRY.get(key)
        if defn is not None and defn.local_only:
            raise SettingValidationError(
                f"Setting '{key}' is local-only and cannot be updated via "
                f"the admin API. Set it via the {defn.env_var} environment "
                f"variable instead."
            )

        res = await self.db.execute(
            select(AppSetting).where(AppSetting.key == key).with_for_update()
        )
        setting = res.scalar_one_or_none()
        if not setting:
            raise SettingNotFoundError(f"Setting with key '{key}' not found")

        old_snapshot = self._setting_audit_snapshot(
            key=setting.key,
            value=setting.value,
            value_type=setting.value_type,
            is_secret=setting.is_secret,
            description=setting.description,
            category=setting.category,
            encrypted=setting.is_secret,
        )

        update_data = setting_update.model_dump(exclude_unset=True)
        effective_is_secret = defn.is_secret if defn is not None else setting.is_secret
        if setting.is_secret != effective_is_secret:
            setting.is_secret = effective_is_secret

        if "value" in update_data:
            effective_value_type = defn.value_type if defn is not None else setting.value_type
            self._validate_value_type(
                key,
                update_data.get("value"),
                effective_value_type,
            )
        if "value" in update_data and effective_is_secret and update_data["value"]:
            update_data["value"] = self.encryption.encrypt(update_data["value"])

        for field, value in update_data.items():
            setattr(setting, field, value)
        setting.updated_at = datetime.now(timezone.utc)

        new_snapshot = self._setting_audit_snapshot(
            key=setting.key,
            value=setting.value,
            value_type=setting.value_type,
            is_secret=setting.is_secret,
            description=setting.description,
            category=setting.category,
            encrypted=setting.is_secret,
        )

        await get_audit_service(self.db).log_event(
            event_type="settings.updated",
            entity_type="setting",
            entity_id=setting.key,
            description=f"Setting updated: {setting.key}",
            old_value=old_snapshot,
            new_value=new_snapshot,
            performed_by=performed_by,
            context=audit_context,
        )
        await self.db.flush()
        return setting

    async def upsert_setting_in_transaction(
        self,
        setting_create: AppSettingCreate,
        *,
        performed_by: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
    ) -> AppSetting:
        """Create or update one registered setting without committing the transaction."""
        result = await self.db.execute(
            select(AppSetting.id).where(AppSetting.key == setting_create.key)
        )
        if result.scalar_one_or_none() is None:
            return await self.create_setting_in_transaction(
                setting_create,
                performed_by=performed_by,
                audit_context=audit_context,
            )

        return await self.update_setting_in_transaction(
            setting_create.key,
            AppSettingUpdate(value=setting_create.value),
            performed_by=performed_by,
            audit_context=audit_context,
        )

    async def delete_setting(
        self,
        key: str,
        *,
        performed_by: Optional[str] = None,
        audit_context: Optional[AuditContext] = None,
    ) -> bool:
        """Delete a DB-backed setting.

        Returns True if deleted, False if not found.
        Raises ``SettingValidationError`` for local-only keys.
        """
        defn = SETTINGS_REGISTRY.get(key)
        if defn is not None and defn.local_only:
            raise SettingValidationError(
                f"Setting '{key}' is local-only and cannot be deleted."
            )

        res = await self.db.execute(
            select(AppSetting).where(AppSetting.key == key)
        )
        setting = res.scalar_one_or_none()
        if not setting:
            return False

        deleted_snapshot = self._setting_audit_snapshot(
            key=setting.key,
            value=setting.value,
            value_type=setting.value_type,
            is_secret=setting.is_secret,
            description=setting.description,
            category=setting.category,
            encrypted=setting.is_secret,
        )

        await get_audit_service(self.db).log_event(
            event_type="settings.deleted",
            entity_type="setting",
            entity_id=setting.key,
            description=f"Setting deleted: {setting.key}",
            old_value=deleted_snapshot,
            performed_by=performed_by,
            context=audit_context,
        )

        await self.db.delete(setting)
        await self.db.commit()
        logger.info("Deleted setting: key=%s", key)
        return True

    # ------------------------------------------------------------------
    # LangFlow flow resolution (preserved for backward compatibility)
    # ------------------------------------------------------------------

    async def get_flow_id_for_context(self, context_type: str) -> str:
        """Get the LangFlow flow ID for a given context type."""
        from app.models.enums import LangFlowContextType

        context_to_setting = {
            LangFlowContextType.general: "langflow.default_flow_id",
            LangFlowContextType.case: "langflow.case_detail_flow_id",
            LangFlowContextType.task: "langflow.task_detail_flow_id",
            LangFlowContextType.alert: "langflow.alert_triage_flow_id",
        }

        try:
            context_enum = LangFlowContextType(context_type)
        except ValueError:
            context_enum = LangFlowContextType.general

        setting_key = context_to_setting.get(
            context_enum, "langflow.default_flow_id"
        )
        flow_id = await self.get(setting_key)

        if not flow_id and context_enum != LangFlowContextType.general:
            flow_id = await self.get("langflow.default_flow_id")

        if not flow_id:
            raise SettingConfigurationError(
                f"No flow ID configured for context '{context_type}'. "
                f"Please set '{setting_key}' or 'langflow.default_flow_id' "
                f"in settings."
            )
        return flow_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_value(
        self, defn: SettingDefinition, db_row: Optional[AppSetting]
    ) -> tuple[Any, str]:
        """Return ``(value, source)`` using the precedence chain."""
        # 1. Env var (real env + .env)
        env_val = self._env_lookup(defn.env_var)
        if env_val is not None:
            return env_val, "env"

        # 2. Database (skip for local_only)
        if not defn.local_only and db_row is not None and db_row.value is not None:
            value = db_row.value
            if db_row.is_secret:
                try:
                    value = self.encryption.decrypt(value)
                except Exception as exc:
                    raise SettingDecryptionError(
                        f"Failed to decrypt setting '{defn.key}'"
                    ) from exc
            return value, "database"

        # 3. Registry default
        if defn.default is not None:
            return defn.default, "default"

        return None, "default"

    def _resolve_typed_value(
        self,
        definition: SettingDefinition,
        db_row: Optional[AppSetting],
        default: Any,
    ) -> Any:
        value, source = self._resolve_value(definition, db_row)
        if value is None:
            return default
        if source in {"env", "database"}:
            return coerce_setting_value(value, definition.value_type)
        return value

    def _resolve_ad_hoc_value(
        self,
        db_row: Optional[AppSetting],
        *,
        key: str,
        default: Any,
    ) -> Any:
        if db_row is None or db_row.value is None:
            return default

        value = db_row.value
        if db_row.is_secret:
            try:
                value = self.encryption.decrypt(value)
            except Exception as exc:
                raise SettingDecryptionError(
                    f"Failed to decrypt setting '{key}'"
                ) from exc
        return value

    @staticmethod
    def _serialize_display_value(value: Any, value_type: SettingType) -> Optional[str]:
        """Serialize resolved values for API display consistently."""
        if value is None:
            return None

        if value_type == SettingType.BOOLEAN and isinstance(value, bool):
            return "true" if value else "false"

        if value_type == SettingType.JSON and not isinstance(value, str):
            return json.dumps(value)

        return str(value)
