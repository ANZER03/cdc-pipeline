#!/bin/bash
# Creates the application and future catalog databases for Nexus.
# This runs before seed-postgres.sql, which reconnects to nexus_db.

set -e

create_database() {
    local db_name="$1"

    echo "Ensuring ${db_name} database exists..."
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" -tc \
        "SELECT 1 FROM pg_database WHERE datname = '${db_name}'" | grep -q 1 || \
        psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" -c \
        "CREATE DATABASE ${db_name} OWNER $POSTGRES_USER"
}

create_database "nexus_db"
create_database "iceberg_catalog"

echo "Databases ready: nexus_db, iceberg_catalog."
