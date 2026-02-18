#!/bin/bash
# create-topics.sh
# Waits for Kafka to be ready, then creates the EBAP topics.

set -e

KAFKA_BOOTSTRAP="kafka:9092"

echo "Waiting for Kafka to be ready..."
until kafka-topics --bootstrap-server "$KAFKA_BOOTSTRAP" --list > /dev/null 2>&1; do
  sleep 2
done
echo "Kafka is ready."

echo "Creating EBAP topics..."

kafka-topics --bootstrap-server "$KAFKA_BOOTSTRAP" --create --if-not-exists \
  --topic ebap.events.raw \
  --partitions 6 \
  --replication-factor 1

kafka-topics --bootstrap-server "$KAFKA_BOOTSTRAP" --create --if-not-exists \
  --topic ebap.metrics.telemetry \
  --partitions 6 \
  --replication-factor 1

kafka-topics --bootstrap-server "$KAFKA_BOOTSTRAP" --create --if-not-exists \
  --topic ebap.cdc.users \
  --partitions 3 \
  --replication-factor 1

kafka-topics --bootstrap-server "$KAFKA_BOOTSTRAP" --create --if-not-exists \
  --topic ebap.audit.logs \
  --partitions 1 \
  --replication-factor 1

echo "All EBAP topics created:"
kafka-topics --bootstrap-server "$KAFKA_BOOTSTRAP" --list | grep "^ebap\."
