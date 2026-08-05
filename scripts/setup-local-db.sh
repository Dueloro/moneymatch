#!/usr/bin/env bash
set -euo pipefail
echo nameserver 8.8.8.8 > /etc/resolv.conf

pg_ctlcluster 16 main start || true

CONF=/etc/postgresql/16/main/postgresql.conf
HBA=/etc/postgresql/16/main/pg_hba.conf

sed -i "s/^#\?listen_addresses.*/listen_addresses = '*'/" "$CONF"
grep -q "0.0.0.0/0" "$HBA" || echo "host all all 0.0.0.0/0 scram-sha-256" >> "$HBA"

pg_ctlcluster 16 main restart

su - postgres -c "psql -v ON_ERROR_STOP=1" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'moneymatch') THEN
    CREATE ROLE moneymatch LOGIN PASSWORD 'moneymatch';
  ELSE
    ALTER ROLE moneymatch WITH LOGIN PASSWORD 'moneymatch';
  END IF;
END
$$;
SELECT 'CREATE DATABASE moneymatch OWNER moneymatch'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'moneymatch')\gexec
GRANT ALL PRIVILEGES ON DATABASE moneymatch TO moneymatch;
SQL

# Needed for Alembic/extensions on Postgres 15+
su - postgres -c "psql -d moneymatch -v ON_ERROR_STOP=1" <<'SQL'
GRANT ALL ON SCHEMA public TO moneymatch;
ALTER SCHEMA public OWNER TO moneymatch;
SQL

ss -ltn | grep 5432 || true
echo DB_READY
