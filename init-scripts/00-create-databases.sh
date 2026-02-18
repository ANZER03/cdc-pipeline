#!/bin/bash
# 00-create-databases.sh
# Creates additional databases needed by EBAP.
# This script runs before SQL files because docker-entrypoint-initdb.d
# sorts files alphabetically (00- < seed-).
#
# The default database (ebap_db) is created automatically by POSTGRES_DB env var.
# Here we create the Iceberg JDBC catalog database.

set -e

echo "Creating iceberg_catalog database for Iceberg JDBC catalog..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE iceberg_catalog OWNER $POSTGRES_USER'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'iceberg_catalog');
EOSQL

# Use a simpler approach: createdb with --if-not-exists equivalent
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" -tc \
    "SELECT 1 FROM pg_database WHERE datname = 'iceberg_catalog'" | grep -q 1 || \
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" -c \
    "CREATE DATABASE iceberg_catalog OWNER $POSTGRES_USER"

echo "iceberg_catalog database ready."
