#!/usr/bin/env bash
set -euo pipefail

TOPIC_NAME="${TOPIC_NAME:-app-logs}"
BOOTSTRAP_SERVER="${BOOTSTRAP_SERVER:-localhost:9092}"
FROM_BEGINNING="${FROM_BEGINNING:-false}"

ARGS=(
  --topic "$TOPIC_NAME"
  --bootstrap-server "$BOOTSTRAP_SERVER"
)

if [[ "$FROM_BEGINNING" == "true" ]]; then
  ARGS+=(--from-beginning)
fi

# Allow override and support both Apache (.sh) and Homebrew (no .sh) command names.
KAFKA_CONSUMER_CMD="${KAFKA_CONSUMER_CMD:-}"
if [[ -z "$KAFKA_CONSUMER_CMD" ]]; then
  if command -v kafka-console-consumer.sh >/dev/null 2>&1; then
    KAFKA_CONSUMER_CMD="kafka-console-consumer.sh"
  elif command -v kafka-console-consumer >/dev/null 2>&1; then
    KAFKA_CONSUMER_CMD="kafka-console-consumer"
  else
    echo "Error: Kafka consumer CLI not found. Install Kafka tools or set KAFKA_CONSUMER_CMD." >&2
    echo "Tried: kafka-console-consumer.sh, kafka-console-consumer" >&2
    exit 127
  fi
fi

echo "Consuming logs from topic '$TOPIC_NAME' on $BOOTSTRAP_SERVER"
"$KAFKA_CONSUMER_CMD" "${ARGS[@]}"
