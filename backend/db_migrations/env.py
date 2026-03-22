from logging.config import fileConfig
import sys
import os

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add the app directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Import SQLModel and our models
from sqlmodel import SQLModel
from app.models import models  # This imports all our SQLModel classes

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override sqlalchemy.url from DATABASE_URL environment variable if set
# The env var uses asyncpg but alembic needs sync psycopg2, so we convert
database_url = os.environ.get("DATABASE_URL")
if database_url:
    # Convert asyncpg URL to psycopg2 for Alembic (sync operations)
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    config.set_main_option("sqlalchemy.url", sync_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(object, name, type_, reflected, compare_to):
    """Filter objects for autogenerate to ignore external/runtime objects.
    
    Excludes:
    - pgqueuer tables (created at runtime by the task queue library)
    - search_vector columns (created via raw SQL in migrations)
    - GIN indexes for full-text search, trigrams, and JSONB (created via raw SQL)
    - Partial indexes with WHERE clauses (created via raw SQL)
    """
    # Exclude pgqueuer tables
    if type_ == "table" and name.startswith("pgqueuer"):
        return False
    
    # Exclude search_vector columns (managed via raw SQL triggers)
    if type_ == "column" and name == "search_vector":
        return False
    
    # Exclude GIN indexes created via raw SQL
    if type_ == "index":
        excluded_index_patterns = (
            "idx_alerts_search_vector",
            "idx_cases_search_vector",
            "idx_tasks_search_vector",
            "idx_alerts_timeline_gin",
            "idx_cases_timeline_gin",
            "idx_tasks_timeline_gin",
            "idx_alerts_title_trgm",
            "idx_alerts_description_trgm",
            "idx_cases_title_trgm",
            "idx_cases_description_trgm",
            "idx_tasks_title_trgm",
            "idx_tasks_description_trgm",
            "ix_user_accounts_email_human",  # Partial index with WHERE clause
        )
        if name in excluded_index_patterns:
            return False
    
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
