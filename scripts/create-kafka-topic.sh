#!/usr/bin/env bash
set -euo pipefail

TOPIC_NAME="${1:-app-logs}"
BOOTSTRAP_SERVER="${BOOTSTRAP_SERVER:-localhost:9092}"

# Allow override and support both Apache (.sh) and Homebrew (no .sh) command names.
KAFKA_TOPICS_CMD="${KAFKA_TOPICS_CMD:-}"
if [[ -z "$KAFKA_TOPICS_CMD" ]]; then
  if command -v kafka-topics.sh >/dev/null 2>&1; then
    KAFKA_TOPICS_CMD="kafka-topics.sh"
  elif command -v kafka-topics >/dev/null 2>&1; then
    KAFKA_TOPICS_CMD="kafka-topics"
  else
    echo "Error: Kafka CLI not found. Install Kafka tools or set KAFKA_TOPICS_CMD." >&2
    echo "Tried: kafka-topics.sh, kafka-topics" >&2
    exit 127
  fi
fi

"$KAFKA_TOPICS_CMD" \
  --create \
  --if-not-exists \
  --topic "$TOPIC_NAME" \
  --bootstrap-server "$BOOTSTRAP_SERVER"

echo "Created/verified topic '$TOPIC_NAME' on $BOOTSTRAP_SERVER"
