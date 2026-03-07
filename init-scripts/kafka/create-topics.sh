#!/bin/bash
# Waits for Kafka to be ready, then creates the Nexus topics.

set -e

KAFKA_BOOTSTRAP="kafka:9092"

echo "Waiting for Kafka to be ready..."
until kafka-topics --bootstrap-server "$KAFKA_BOOTSTRAP" --list > /dev/null 2>&1; do
  sleep 2
done
echo "Kafka is ready."

create_topic() {
  local topic="$1"
  local partitions="$2"

  kafka-topics --bootstrap-server "$KAFKA_BOOTSTRAP" --create --if-not-exists \
    --topic "$topic" \
    --partitions "$partitions" \
    --replication-factor 1
}

echo "Creating Nexus topics..."

# CDC topics
create_topic "pg.public.users" 6
create_topic "pg.public.products" 3
create_topic "pg.public.orders" 12
create_topic "pg.public.order_items" 12
create_topic "pg.public.cart_items" 6
create_topic "pg.public.user_events" 12
create_topic "pg.public.sessions" 6

# Direct-to-Kafka topics
create_topic "raw.request_log" 12
create_topic "raw.system_metrics" 6

# Enriched / intermediate topics
create_topic "enriched.activities" 6
create_topic "aggregated.kpis" 3
create_topic "aggregated.regions" 3
create_topic "aggregated.traffic" 3
create_topic "evaluated.alerts" 3

echo "Nexus topics created:"
kafka-topics --bootstrap-server "$KAFKA_BOOTSTRAP" --list | grep -E '^(pg\.|raw\.|enriched\.|aggregated\.|evaluated\.)'
