#!/bin/bash
# register-debezium.sh
# Registers the Debezium PostgreSQL CDC connector with Kafka Connect.

set -e

CONNECT_URL="http://debezium-connect:8083"
CONNECTOR_CONFIG="/config/debezium/postgres-connector.json"

echo "Waiting for Kafka Connect to be ready..."
until curl -sf "$CONNECT_URL/connectors" > /dev/null 2>&1; do
  sleep 3
done
echo "Kafka Connect is ready."

# Check if connector already exists
if curl -sf "$CONNECT_URL/connectors/ebap-postgres-cdc" > /dev/null 2>&1; then
  echo "Connector 'ebap-postgres-cdc' already exists. Skipping registration."
else
  echo "Registering Debezium connector..."
  curl -s -X POST "$CONNECT_URL/connectors" \
    -H "Content-Type: application/json" \
    -d @"$CONNECTOR_CONFIG"
  echo ""
  echo "Connector registered successfully."
fi

echo "Active connectors:"
curl -s "$CONNECT_URL/connectors" | python3 -m json.tool 2>/dev/null || \
  curl -s "$CONNECT_URL/connectors"
