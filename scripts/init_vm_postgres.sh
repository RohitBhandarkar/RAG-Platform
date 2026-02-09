#!/bin/bash
# =============================================================================
# Initialize Database Tables on GCP VM
# Run this after setup_vm_databases.sh to create all tables
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_DIR="$(cd "$SCRIPT_DIR/../sql/feature" && pwd)"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-formulation_rag}"

echo "=== Initializing PostgreSQL Tables (from $SQL_DIR) ==="

# Check if PostgreSQL is running
if ! sudo docker exec rag-postgres pg_isready -U postgres > /dev/null 2>&1; then
    echo "ERROR: PostgreSQL is not running. Run setup_vm_databases.sh first."
    exit 1
fi

# Run init then migrations (same order as deploy workflows)
if [ -f "$SQL_DIR/init_db.sql" ]; then
    echo "Running init_db.sql..."
    sudo docker exec -i rag-postgres psql -U postgres -d $POSTGRES_DB < "$SQL_DIR/init_db.sql"
fi
for f in "$SQL_DIR"/migrate_*.sql; do
    [ -f "$f" ] || continue
    echo "Running $(basename "$f")..."
    sudo docker exec -i rag-postgres psql -U postgres -d $POSTGRES_DB < "$f" || true
done

# Verify tables were created
echo ""
echo "=== Verifying tables ==="
sudo docker exec rag-postgres psql -U postgres -d $POSTGRES_DB -c "
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_type = 'BASE TABLE'
ORDER BY table_name;
"

# Verify pgvector extension
echo ""
echo "=== Verifying pgvector extension ==="
sudo docker exec rag-postgres psql -U postgres -d $POSTGRES_DB -c "
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
"

echo ""
echo "=== PostgreSQL initialization complete ==="
