#!/usr/bin/env bash

# 🚀 Start local dev infra (Postgres + Redis via docker-compose)

COMPOSE_FILE="docker-compose.dev.yml"

# 🔍 Check Docker
if ! command -v docker &> /dev/null; then
  echo -e "❌ Docker is not installed.\nInstall guide: https://docs.docker.com/engine/install/"
  exit 1
fi

# 🔍 Detect compose command (v1 vs v2)
if command -v docker-compose &> /dev/null; then
  COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
else
  echo "❌ Docker Compose not found"
  exit 1
fi

# 🔍 Ensure compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
  echo "❌ $COMPOSE_FILE not found"
  exit 1
fi

# 📥 Load env (optional but useful)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

echo "🚀 Starting local database + redis..."

# ▶️ Start services
$COMPOSE_CMD -f "$COMPOSE_FILE" up -d

# 🔍 Check status
sleep 2
$COMPOSE_CMD -f "$COMPOSE_FILE" ps

echo ""
echo "✅ Services started!"
echo ""
echo "📡 Connection info:"
echo "Postgres (write): postgresql://postgres:postgres@localhost:5432/hackathon_db"
echo "Postgres (read):  postgresql://postgres:postgres@localhost:5433/hackathon_db"
echo "Redis:            redis://:${REDIS_PASSWORD:-devpassword}@localhost:6379/0"