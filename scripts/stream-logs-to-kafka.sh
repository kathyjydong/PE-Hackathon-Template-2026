#!/usr/bin/env bash
set -euo pipefail

TOPIC_NAME="${TOPIC_NAME:-app-logs}"
BOOTSTRAP_SERVER="${BOOTSTRAP_SERVER:-localhost:9092}"
APP_CMD="${APP_CMD:-uv run run.py}"

# Unbuffered output ensures logs are streamed to Kafka immediately.
export PYTHONUNBUFFERED=1

# Allow override and support both Apache (.sh) and Homebrew (no .sh) command names.
KAFKA_PRODUCER_CMD="${KAFKA_PRODUCER_CMD:-}"
if [[ -z "$KAFKA_PRODUCER_CMD" ]]; then
  if command -v kafka-console-producer.sh >/dev/null 2>&1; then
    KAFKA_PRODUCER_CMD="kafka-console-producer.sh"
  elif command -v kafka-console-producer >/dev/null 2>&1; then
    KAFKA_PRODUCER_CMD="kafka-console-producer"
  else
    echo "Error: Kafka producer CLI not found. Install Kafka tools or set KAFKA_PRODUCER_CMD." >&2
    echo "Tried: kafka-console-producer.sh, kafka-console-producer" >&2
    exit 127
  fi
fi

echo "Streaming app logs to Kafka topic '$TOPIC_NAME' on $BOOTSTRAP_SERVER"

eval "$APP_CMD" 2>&1 | "$KAFKA_PRODUCER_CMD" \
  --topic "$TOPIC_NAME" \
  --bootstrap-server "$BOOTSTRAP_SERVER"
