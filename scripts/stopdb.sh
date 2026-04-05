#!/usr/bin/env bash

COMPOSE_FILE="docker-compose.dev.yml"
PROJECT_NAME="pe-hack"

if command -v docker-compose &> /dev/null; then
  COMPOSE_CMD="docker-compose"
else
  COMPOSE_CMD="docker compose"
fi

echo "🛑 Stopping services..."
$COMPOSE_CMD -p "$PROJECT_NAME" -f "$COMPOSE_FILE" down