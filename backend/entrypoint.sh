#!/bin/bash
set -e

echo "🔄 Acquiring migration lock and running migrations..."
python -c "
import os
import subprocess
import psycopg2

# Convert asyncpg URL to psycopg2
db_url = os.environ.get('DATABASE_URL', '')
sync_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')

# Parse connection string
from urllib.parse import urlparse
parsed = urlparse(sync_url)

conn = psycopg2.connect(
    host=parsed.hostname,
    port=parsed.port or 5432,
    user=parsed.username,
    password=parsed.password,
    dbname=parsed.path[1:]  # Remove leading /
)
conn.autocommit = True
cursor = conn.cursor()

# Use advisory lock (lock ID 1 for migrations)
# pg_advisory_lock blocks until lock is available
cursor.execute('SELECT pg_advisory_lock(1)')
print('🔒 Migration lock acquired')

try:
    result = subprocess.run(['alembic', 'upgrade', 'head'], check=True)
    print('✅ Migrations complete')
finally:
    cursor.execute('SELECT pg_advisory_unlock(1)')
    print('🔓 Migration lock released')
    cursor.close()
    conn.close()
"

if [ "$AUTO_SEED" = "true" ]; then
    echo "🌱 Auto-seeding initial users..."
    python -m scripts.seed_test_users || echo "⚠️  Seeding failed (non-fatal)"
    echo "🌱 Auto-seeding link templates..."
    python -m scripts.seed_link_templates || echo "⚠️  Seeding failed (non-fatal)"
fi

echo "🚀 Starting backend server..."
exec "$@"