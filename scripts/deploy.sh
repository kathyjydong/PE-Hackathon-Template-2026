#!/bin/bash

set -e  # exit on error

echo "🚀 Starting deployment..."

cd ~/mlh-portfolio

echo "1. Pulling latest code..."
git fetch origin main
git reset --hard origin/main

echo "2. Installing uv (if not already installed)..."
if ! command -v uv &> /dev/null
then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "3. Syncing Python dependencies with uv..."
uv sync

echo "4. Stopping existing containers..."
docker compose -f docker-compose.prod.yml down

echo "5. Rebuilding and starting containers..."
docker compose -f docker-compose.prod.yml up -d --build

echo "✅ Deployment complete!"