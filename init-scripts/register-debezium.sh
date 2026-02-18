#!/bin/bash
# register-debezium.sh
# Registers the Debezium PostgreSQL CDC connector with Kafka Connect.

set -e

CONNECT_URL="http://debezium-connect:8083"
CONNECTOR_CONFIG="/config/postgres-connector.json"
MAX_WAIT=120
WAITED=0

echo "Waiting for Kafka Connect to be ready..."
until curl -sf "$CONNECT_URL/connectors" > /dev/null 2>&1; do
  WAITED=$((WAITED + 3))
  if [ "$WAITED" -ge "$MAX_WAIT" ]; then
    echo "ERROR: Kafka Connect not ready after ${MAX_WAIT}s. Exiting."
    exit 1
  fi
  sleep 3
done
echo "Kafka Connect is ready (waited ${WAITED}s)."

# Check if connector already exists
if curl -sf "$CONNECT_URL/connectors/ebap-postgres-cdc" > /dev/null 2>&1; then
  echo "Connector 'ebap-postgres-cdc' already exists. Skipping registration."
else
  echo "Registering Debezium connector..."
  RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$CONNECT_URL/connectors" \
    -H "Content-Type: application/json" \
    -d @"$CONNECTOR_CONFIG")
  HTTP_CODE=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    echo "Connector registered successfully (HTTP $HTTP_CODE)."
  else
    echo "ERROR: Failed to register connector (HTTP $HTTP_CODE)."
    echo "$BODY"
    exit 1
  fi
fi

echo "Active connectors:"
curl -s "$CONNECT_URL/connectors"
echo ""
