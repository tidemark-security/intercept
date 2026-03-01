"""
Legacy config module — kept for backward compatibility.

All application settings are now defined in ``app.core.settings_registry``
and resolved through ``get_local()`` (sync) or ``SettingsService`` (async).

This module previously held a Pydantic ``BaseSettings`` singleton that
resolved env vars and ``.env`` values.  That functionality is now handled by
the settings registry's ``_load_dotenv()`` and ``os.getenv()`` calls.
"""
from __future__ import annotations
