#!/usr/bin/env bash
# Create the pytest database (conftest points at TEST_DATABASE_URL).
set -eu

pg_ctlcluster 16 main start 2>/dev/null || true

su - postgres -c "psql -v ON_ERROR_STOP=1" <<'SQL'
SELECT 'CREATE DATABASE moneymatch_test OWNER moneymatch'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'moneymatch_test')\gexec
SQL

su - postgres -c "psql -d moneymatch_test -v ON_ERROR_STOP=1" <<'SQL'
GRANT ALL ON SCHEMA public TO moneymatch;
ALTER SCHEMA public OWNER TO moneymatch;
SQL

echo TESTDB_READY
