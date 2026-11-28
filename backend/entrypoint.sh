#!/bin/bash
set -e

echo "🔄 Acquiring migration lock and running migrations..."
python -c "
import os
import subprocess
import psycopg2
from sqlalchemy.engine import make_url

db_url = make_url(os.environ.get('DATABASE_URL') or 'postgresql://')
conn = psycopg2.connect(**db_url.translate_connect_args(username='user', database='dbname'))
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
    echo "🌱 Ensuring initial admin user exists..."
    python -m scripts.seed_initial_admin
    echo "🌱 Auto-seeding link templates..."
    python -m scripts.seed_link_templates || echo "⚠️  Link template seeding failed (non-fatal)"
fi

echo "🚀 Starting backend server..."
exec "$@"
