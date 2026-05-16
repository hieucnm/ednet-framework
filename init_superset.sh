#!/bin/bash
# scripts/init_superset.sh
# Run this ONCE after first `docker compose up -d`
# Usage: bash scripts/init_superset.sh

set -e
echo "=== Initializing Apache Superset ==="

echo "[1/4] Running database upgrade..."
docker compose exec -T superset superset db upgrade

echo "[2/4] Creating admin user (admin / admin)..."
docker compose exec -T superset superset fab create-admin \
  --username admin \
  --firstname Admin \
  --lastname User \
  --email admin@ednet.local \
  --password admin 2>/dev/null || echo "Admin user already exists, skipping."

echo "[3/4] Initializing Superset roles and permissions..."
docker compose exec -T superset superset init

echo "[4/4] Done."
echo ""
echo "Superset is ready at http://localhost:8088"
echo "Login: admin / admin"
echo ""
echo "Next step: run  python scripts/setup_superset.py"
