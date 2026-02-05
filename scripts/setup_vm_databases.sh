#!/bin/bash
# =============================================================================
# GCP VM Database Setup Script
# Run this ONCE on the GCP VM to set up PostgreSQL with pgvector
# =============================================================================

set -e

echo "=== RAG Platform Database Setup ==="
echo ""

# Configuration
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-formulation_rag}"
POSTGRES_DATA_DIR="${POSTGRES_DATA_DIR:-/data/postgres}"

# Create data directories
echo "Creating data directories..."
sudo mkdir -p $POSTGRES_DATA_DIR
sudo chmod 777 $POSTGRES_DATA_DIR

# Stop existing container if running
echo "Stopping existing database container..."
sudo docker stop rag-postgres 2>/dev/null || true
sudo docker rm rag-postgres 2>/dev/null || true

# Pull image
echo "Pulling PostgreSQL + pgvector image..."
sudo docker pull pgvector/pgvector:pg16

# Start PostgreSQL with pgvector
echo "Starting PostgreSQL with pgvector..."
sudo docker run -d \
    --name rag-postgres \
    --restart unless-stopped \
    --network host \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=$POSTGRES_PASSWORD \
    -e POSTGRES_DB=$POSTGRES_DB \
    -v $POSTGRES_DATA_DIR:/var/lib/postgresql/data \
    pgvector/pgvector:pg16

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if sudo docker exec rag-postgres pg_isready -U postgres > /dev/null 2>&1; then
        echo "PostgreSQL is ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

echo ""
echo "=== Database container started ==="
echo ""
sudo docker ps | grep rag-postgres
echo ""
echo "Next step: Run init_vm_postgres.sh to create all tables"
