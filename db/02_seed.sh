#!/bin/bash
set -e

# Only run if the variable is set (Safety check)
if [ -n "$DEV_USER_ID" ]; then
    echo "🔧 Seeding Development User from Environment Variables..."
    
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
        INSERT INTO users (id, email, password_hash)
        VALUES ('$DEV_USER_ID', 'dev@local', 'hash_placeholder')
        ON CONFLICT (id) DO NOTHING;
EOSQL
    
    echo "✅ Dev User ($DEV_USER_ID) injected successfully."
else
    echo "⚠️ DEV_USER_ID not set. Skipping seed."
fi