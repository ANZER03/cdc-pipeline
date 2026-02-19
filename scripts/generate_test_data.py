#!/usr/bin/env python3
"""
scripts/generate_test_data.py
EBAP — Synthetic event producer for Kafka.

Produces a configurable number of random user events to ebap.events.raw.
Useful for smoke-testing the streaming pipeline without real traffic.

Usage:
  python scripts/generate_test_data.py [--count N] [--interval SECONDS]
  make generate-data
"""

import json
import random
import time
import argparse
import uuid
from datetime import datetime, timezone

KAFKA_BROKERS  = "localhost:29092"   # External port (host machine)
TOPIC          = "ebap.events.raw"
ACTIONS        = ["purchase", "view", "add_to_cart", "login", "checkout", "error"]
LOCATIONS      = ["us-east", "us-west", "eu-west", "ap-south", "ap-northeast"]
USER_IDS       = [f"user-{i:04d}" for i in range(1, 11)]  # matches seed-postgres.sql


def make_event() -> dict:
    action = random.choice(ACTIONS)
    event = {
        "id":        str(uuid.uuid4()),
        "user_id":   random.choice(USER_IDS),
        "action":    action,
        "location":  random.choice(LOCATIONS),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata":  {},
    }
    if action == "purchase":
        event["metadata"]["amount"]  = str(round(random.uniform(5.0, 500.0), 2))
        event["metadata"]["item_id"] = f"item-{random.randint(100, 999)}"
    return event


def main():
    parser = argparse.ArgumentParser(description="Produce synthetic events to Kafka")
    parser.add_argument("--count",    type=int,   default=20,  help="Number of events to produce")
    parser.add_argument("--interval", type=float, default=0.5, help="Seconds between events")
    args = parser.parse_args()

    try:
        from kafka import KafkaProducer  # type: ignore
    except ImportError:
        print("kafka-python not installed. Run: pip install kafka-python")
        print("\nFalling back to docker exec approach...")
        print("Run the following to produce a single test event:")
        print(f"""  echo '{json.dumps(make_event())}' | \\
  docker exec -i ebap-kafka kafka-console-producer \\
    --bootstrap-server kafka:9092 --topic {TOPIC}""")
        return

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BROKERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    print(f"Producing {args.count} events to {TOPIC} on {KAFKA_BROKERS}...")
    for i in range(args.count):
        event = make_event()
        producer.send(TOPIC, value=event)
        print(f"  [{i+1:3d}/{args.count}] {event['action']:12s}  user={event['user_id']}  loc={event['location']}")
        time.sleep(args.interval)

    producer.flush()
    producer.close()
    print(f"\nDone. {args.count} events sent.")


if __name__ == "__main__":
    main()
