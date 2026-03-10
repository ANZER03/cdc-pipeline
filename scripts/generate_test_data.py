#!/usr/bin/env python3
"""Generate Nexus PostgreSQL CDC and direct Kafka test traffic."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SQL_COMMAND_TIMEOUT_SECONDS = int(os.getenv("SQL_COMMAND_TIMEOUT_SECONDS", "120"))
KAFKA_PRODUCE_TIMEOUT_SECONDS = int(os.getenv("KAFKA_PRODUCE_TIMEOUT_SECONDS", "120"))

REQUEST_LOG_SCHEMA = {
    "type": "record",
    "name": "RequestLog",
    "namespace": "com.nexus.infra",
    "fields": [
        {"name": "id", "type": "long"},
        {"name": "endpoint", "type": ["null", "string"], "default": None},
        {"name": "method", "type": ["null", "string"], "default": None},
        {"name": "status_code", "type": "int"},
        {"name": "latency_ms", "type": "int"},
        {"name": "user_id", "type": ["null", "long"], "default": None},
        {"name": "session_id", "type": ["null", "string"], "default": None},
        {"name": "region_name", "type": ["null", "string"], "default": None},
        {"name": "user_display_name", "type": ["null", "string"], "default": None},
        {"name": "platform", "type": ["null", "string"], "default": None},
        {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    ],
}

SYSTEM_METRIC_SCHEMA = {
    "type": "record",
    "name": "SystemMetric",
    "namespace": "com.nexus.infra",
    "fields": [
        {"name": "id", "type": "long"},
        {"name": "node_name", "type": "string"},
        {"name": "metric_name", "type": "string"},
        {"name": "metric_value", "type": "double"},
        {"name": "recorded_at", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    ],
}

REQUEST_ENDPOINTS = [
    ("GET", "/api/products"),
    ("GET", "/api/products/featured"),
    ("GET", "/api/cart"),
    ("POST", "/api/cart/items"),
    ("POST", "/api/checkout"),
    ("GET", "/api/orders"),
    ("GET", "/api/profile"),
]

USER_EVENT_PATTERNS = [
    [
        "login",
        "page_view",
        "page_view",
        "add_to_cart",
        "page_view",
        "checkout_start",
        "checkout_complete",
    ],
    ["login", "page_view", "page_view", "logout"],
    ["page_view", "page_view", "page_view"],
]

PLATFORM_AGENTS = {
    "Desktop": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mobile": "Mozilla/5.0 (Linux; Android 15)",
    "iOS": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)",
    "Android": "Mozilla/5.0 (Linux; Android 15; Pixel 9)",
}

NODES = ["api-node-1", "api-node-2", "api-node-3", "db-node-1"]


@dataclass(frozen=True)
class UserRecord:
    id: int
    username: str
    display_name: str
    country_code: str | None
    city: str | None
    region_name: str | None
    platform: str | None


@dataclass(frozen=True)
class ProductRecord:
    id: int
    price: float
    merchant_region: str | None


DEFAULT_PRODUCTS = [
    ProductRecord(id=1, price=1299.0, merchant_region="North America (West)"),
    ProductRecord(id=7, price=249.0, merchant_region="India"),
    ProductRecord(id=12, price=59.0, merchant_region="North America (West)"),
]

SIZE_MULTIPLIERS = {
    "small": 1,
    "medium": 2,
    "large": 4,
}

PRESET_DEFAULTS = {
    "light": {"rate": 5, "duration": 120, "size": "small", "error_rate": 0.02},
    "demo": {"rate": 20, "duration": 300, "size": "medium", "error_rate": 0.05},
    "stress": {"rate": 60, "duration": 600, "size": "large", "error_rate": 0.12},
}


@dataclass
class GeneratorState:
    next_request_log_id: int
    next_system_metric_id: int
    active_sessions: dict[int, str]
    user_cursor: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Nexus CDC and Kafka test traffic")
    parser.add_argument("--preset", choices=["custom", "light", "demo", "stress"], default="custom")
    parser.add_argument("--mode", choices=["all", "postgres", "kafka"], default="all")
    parser.add_argument("--rate", type=int, default=10, help="Target request events per second")
    parser.add_argument("--duration", type=int, default=300, help="Run length in seconds")
    parser.add_argument("--size", choices=["small", "medium", "large"], default="medium")
    parser.add_argument(
        "--error-rate", type=float, default=0.05, help="Approximate HTTP error ratio"
    )
    parser.add_argument("--users", type=str, default="", help="Optional CSV file for users")
    parser.add_argument("--postgres-container", default="nexus-postgres")
    parser.add_argument(
        "--schema-registry-url",
        default=os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081"),
    )
    parser.add_argument(
        "--kafka-brokers",
        default=os.getenv("KAFKA_BROKERS", "localhost:9092,localhost:9093"),
    )
    parser.add_argument("--kafka-producer-container", default="nexus-schema-registry")
    parser.add_argument(
        "--summary-only", action="store_true", help="Print generated plan without writes"
    )
    return parser.parse_args()


def size_multiplier(size: str) -> int:
    return SIZE_MULTIPLIERS.get(size, 1)


def apply_preset_defaults(args: argparse.Namespace) -> argparse.Namespace:
    if args.preset == "custom":
        return args

    preset = PRESET_DEFAULTS[args.preset]
    if args.rate == 10:
        args.rate = preset["rate"]
    if args.duration == 300:
        args.duration = preset["duration"]
    if args.size == "medium":
        args.size = preset["size"]
    if args.error_rate == 0.05:
        args.error_rate = preset["error_rate"]
    return args


def run_sql(container: str, sql: str) -> str:
    command = [
        "docker",
        "exec",
        "-i",
        container,
        "psql",
        "-U",
        os.getenv("POSTGRES_USER", "admin"),
        "-d",
        os.getenv("POSTGRES_DB", "nexus_db"),
        "-At",
        "-F",
        "|",
        "-c",
        sql,
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
        timeout=SQL_COMMAND_TIMEOUT_SECONDS,
    )
    return result.stdout.strip()


def parse_returning_id(output: str) -> int:
    match = re.search(r"(\d+)", output)
    if not match:
        raise ValueError(f"Unable to parse id from SQL output: {output!r}")
    return int(match.group(1))


def load_users(container: str) -> list[UserRecord]:
    rows = run_sql(
        container,
        "SELECT id, username, display_name, COALESCE(country_code, ''), COALESCE(city, ''), COALESCE(region_name, ''), COALESCE(platform, '') FROM users ORDER BY id;",
    )
    users = []
    for line in rows.splitlines():
        user_id, username, display_name, country_code, city, region_name, platform = line.split("|")
        users.append(
            UserRecord(
                id=int(user_id),
                username=username,
                display_name=display_name,
                country_code=country_code or None,
                city=city or None,
                region_name=region_name or None,
                platform=platform or None,
            )
        )
    return users


def load_users_from_csv(file_path: str) -> list[UserRecord]:
    users: list[UserRecord] = []
    with open(file_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            users.append(
                UserRecord(
                    id=int(row["id"]),
                    username=row["username"],
                    display_name=row.get("display_name", row["username"]),
                    country_code=row.get("country_code") or None,
                    city=row.get("city") or None,
                    region_name=row.get("region_name") or None,
                    platform=row.get("platform") or None,
                )
            )
    return users


def load_products(container: str) -> list[ProductRecord]:
    rows = run_sql(
        container,
        "SELECT id, price, COALESCE(merchant_region, '') FROM products ORDER BY id;",
    )
    products = []
    for line in rows.splitlines():
        product_id, price, merchant_region = line.split("|")
        products.append(
            ProductRecord(
                id=int(product_id),
                price=float(price),
                merchant_region=merchant_region or None,
            )
        )
    return products


def load_state(container: str) -> GeneratorState:
    request_log_max = run_sql(container, "SELECT 1000000;")
    system_metric_max = run_sql(container, "SELECT 2000000;")
    active = run_sql(
        container, "SELECT user_id, id FROM sessions WHERE is_active = true AND ended_at IS NULL;"
    )
    active_sessions: dict[int, str] = {}
    for line in active.splitlines():
        if not line:
            continue
        user_id, session_id = line.split("|")
        active_sessions[int(user_id)] = session_id
    return GeneratorState(
        next_request_log_id=int(request_log_max),
        next_system_metric_id=int(system_metric_max),
        active_sessions=active_sessions,
    )


def default_state() -> GeneratorState:
    return GeneratorState(
        next_request_log_id=1_000_000,
        next_system_metric_id=2_000_000,
        active_sessions={},
    )


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return "NULL"
        return str(value)
    if isinstance(value, dict):
        payload = json.dumps(value).replace("'", "''")
        return f"'{payload}'::jsonb"
    if isinstance(value, datetime):
        return f"'{value.astimezone(timezone.utc).isoformat()}'::timestamptz"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def execute_statements(container: str, statements: list[str], summary_only: bool) -> None:
    if not statements:
        return
    if summary_only:
        for statement in statements:
            print(statement)
        return
    run_sql(container, "\n".join(statements))


def produce_avro_records(
    container: str,
    topic: str,
    schema: dict[str, Any],
    records: list[dict[str, Any]],
) -> None:
    if not records:
        return

    command = [
        "docker",
        "exec",
        "-i",
        container,
        "kafka-avro-console-producer",
        "--bootstrap-server",
        "kafka-1:9092,kafka-2:9093",
        "--topic",
        topic,
        "--property",
        "schema.registry.url=http://schema-registry:8081",
        "--property",
        f"value.schema={json.dumps(schema, separators=(',', ':'))}",
    ]
    payload = (
        "\n".join(
            json.dumps(_encode_avro_json(record, schema), separators=(",", ":"))
            for record in records
        )
        + "\n"
    )
    subprocess.run(
        command,
        input=payload,
        text=True,
        capture_output=True,
        check=True,
        timeout=KAFKA_PRODUCE_TIMEOUT_SECONDS,
    )


def _encode_avro_json(value: Any, schema: Any) -> Any:
    if isinstance(schema, list):
        if value is None:
            return None
        for branch in schema:
            if branch == "null":
                continue
            return {_union_branch_name(branch): _encode_avro_json(value, branch)}
        raise ValueError(f"Unable to encode union value for schema: {schema!r}")

    if isinstance(schema, dict):
        schema_type = schema.get("type")
        if isinstance(schema_type, list):
            return _encode_avro_json(value, schema_type)
        if schema_type == "record":
            if value is None:
                return None
            return {
                field["name"]: _encode_avro_json(value.get(field["name"]), field["type"])
                for field in schema["fields"]
            }
        return value

    return value


def _union_branch_name(branch: Any) -> str:
    if isinstance(branch, dict):
        branch_type = branch.get("type")
        if isinstance(branch_type, str):
            return branch_type
        raise ValueError(f"Unsupported union branch: {branch!r}")
    return str(branch)


def choose_user(users: list[UserRecord], state: GeneratorState) -> UserRecord:
    user = users[state.user_cursor % len(users)]
    state.user_cursor += 1
    return user


def choose_product(products: list[ProductRecord]) -> ProductRecord:
    return random.choice(products)


def random_ip() -> str:
    return f"203.0.113.{random.randint(1, 254)}"


def page_url_for(product: ProductRecord | None) -> str:
    if product is None:
        return random.choice(["/home", "/collections/new", "/search", "/deals"])
    return f"/products/{product.id}"


def generate_postgres_cycle(
    container: str,
    users: list[UserRecord],
    products: list[ProductRecord],
    state: GeneratorState,
    summary_only: bool,
) -> None:
    user = choose_user(users, state)
    product = choose_product(products)
    now = datetime.now(timezone.utc)
    session_id = state.active_sessions.get(user.id)

    if session_id is None or random.random() < 0.25:
        session_id = str(uuid.uuid4())
        state.active_sessions[user.id] = session_id
        execute_statements(
            container,
            [
                "INSERT INTO sessions (id, user_id, started_at, ended_at, platform, country_code, city, region_name, is_active, created_at) VALUES ("
                + ", ".join(
                    [
                        sql_literal(session_id),
                        sql_literal(user.id),
                        sql_literal(now),
                        "NULL",
                        sql_literal(user.platform or "Desktop"),
                        sql_literal(user.country_code),
                        sql_literal(user.city),
                        sql_literal(user.region_name),
                        "TRUE",
                        sql_literal(now),
                    ]
                )
                + ");"
            ],
            summary_only,
        )

    pattern = random.choice(USER_EVENT_PATTERNS)
    statements: list[str] = []
    order_id = None
    order_total = round(product.price * random.randint(1, 3), 2)
    completion_time = now + timedelta(seconds=random.randint(5, 15))
    final_status = "failed" if random.random() < 0.1 else "completed"

    if "checkout_start" in pattern:
        order_id = parse_returning_id(
            run_sql(
                container,
                "INSERT INTO orders (user_id, total_amount, currency, status, region_name, user_display_name, platform, created_at, updated_at) VALUES ("
                + ", ".join(
                    [
                        sql_literal(user.id),
                        sql_literal(order_total),
                        sql_literal("USD"),
                        sql_literal("pending"),
                        sql_literal(user.region_name),
                        sql_literal(user.display_name),
                        sql_literal(user.platform),
                        sql_literal(now + timedelta(seconds=5)),
                        sql_literal(now + timedelta(seconds=5)),
                    ]
                )
                + ") RETURNING id;",
            )
        )
        execute_statements(
            container,
            [
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price, created_at) VALUES ("
                + ", ".join(
                    [
                        sql_literal(order_id),
                        sql_literal(product.id),
                        sql_literal(1),
                        sql_literal(product.price),
                        sql_literal(now + timedelta(seconds=6)),
                    ]
                )
                + ");"
            ],
            summary_only,
        )

    for step, event_type in enumerate(pattern):
        event_time = now + timedelta(seconds=step)
        metadata: dict[str, Any] = {}
        page_url = page_url_for(
            product
            if event_type in {"page_view", "add_to_cart", "checkout_start", "checkout_complete"}
            else None
        )
        referrer = "/home" if step == 0 else "/search"

        if event_type == "add_to_cart":
            metadata = {"product_id": product.id, "quantity": 1}
            statements.append(
                "INSERT INTO cart_items (user_id, product_id, quantity, added_at) VALUES ("
                + ", ".join(
                    [
                        sql_literal(user.id),
                        sql_literal(product.id),
                        "1",
                        sql_literal(event_time),
                    ]
                )
                + ");"
            )
        elif event_type == "checkout_start":
            metadata = {"cart_value": order_total, "order_id": order_id}
        elif event_type == "checkout_complete":
            metadata = {"order_id": order_id or 0}
        elif event_type == "login":
            metadata = {"auth": random.choice(["password", "google", "otp"])}
        elif event_type == "page_view":
            metadata = {"product_id": product.id}

        statements.append(
            "INSERT INTO user_events (user_id, event_type, page_url, referrer_url, user_agent, ip_address, session_id, metadata, user_display_name, region_name, city, country_code, platform, amount, created_at) VALUES ("
            + ", ".join(
                [
                    sql_literal(user.id),
                    sql_literal(event_type),
                    sql_literal(page_url),
                    sql_literal(referrer),
                    sql_literal(
                        PLATFORM_AGENTS.get(user.platform or "Desktop", PLATFORM_AGENTS["Desktop"])
                    ),
                    sql_literal(random_ip()),
                    sql_literal(session_id),
                    sql_literal(metadata),
                    sql_literal(user.display_name),
                    sql_literal(user.region_name),
                    sql_literal(user.city),
                    sql_literal(user.country_code),
                    sql_literal(user.platform),
                    sql_literal(order_total if event_type == "checkout_complete" else None),
                    sql_literal(event_time),
                ]
            )
            + ");"
        )

    execute_statements(container, statements, summary_only)

    if order_id is not None:
        execute_statements(
            container,
            [
                "UPDATE orders SET status = "
                + sql_literal(final_status)
                + ", updated_at = "
                + sql_literal(completion_time)
                + " WHERE id = "
                + sql_literal(order_id)
                + ";",
            ],
            summary_only,
        )

    if random.random() < 0.15:
        end_time = now + timedelta(minutes=random.randint(5, 30))
        execute_statements(
            container,
            [
                "UPDATE sessions SET is_active = FALSE, ended_at = "
                + sql_literal(end_time)
                + " WHERE id = "
                + sql_literal(session_id)
                + ";"
            ],
            summary_only,
        )
        state.active_sessions.pop(user.id, None)


def make_request_log_payload(
    state: GeneratorState, users: list[UserRecord], error_rate: float
) -> dict[str, Any]:
    user = choose_user(users, state)
    method, endpoint = random.choice(REQUEST_ENDPOINTS)
    state.next_request_log_id += 1
    status_roll = random.random()
    server_error_rate = max(0.0, min(error_rate, 0.4))
    client_error_rate = max(0.0, min(error_rate / 2.0, 0.2))
    success_rate = max(0.0, 1.0 - server_error_rate - client_error_rate)
    if status_roll < success_rate:
        status_code = 200
    elif status_roll < success_rate + client_error_rate:
        status_code = random.choice([400, 401, 404, 429])
    else:
        status_code = random.choice([500, 502, 503])
    latency = max(5, int(random.gauss(100, 50)))
    created_at = int(datetime.now(timezone.utc).timestamp() * 1000)
    return {
        "id": state.next_request_log_id,
        "endpoint": endpoint,
        "method": method,
        "status_code": status_code,
        "latency_ms": latency,
        "user_id": user.id,
        "session_id": state.active_sessions.get(user.id),
        "region_name": user.region_name,
        "user_display_name": user.display_name,
        "platform": user.platform,
        "created_at": created_at,
    }


def make_system_metric_payload(state: GeneratorState) -> list[dict[str, Any]]:
    recorded_at = int(datetime.now(timezone.utc).timestamp() * 1000)
    payloads: list[dict[str, Any]] = []
    for node in random.sample(NODES, k=random.randint(3, min(5, len(NODES)))):
        for metric_name, mean, stddev in (("cpu_percent", 40, 15), ("memory_percent", 55, 10)):
            state.next_system_metric_id += 1
            metric_value = max(0.0, min(100.0, random.gauss(mean, stddev)))
            payloads.append(
                {
                    "id": state.next_system_metric_id,
                    "node_name": node,
                    "metric_name": metric_name,
                    "metric_value": round(metric_value, 2),
                    "recorded_at": recorded_at,
                }
            )
    return payloads


def run_kafka_generation(
    users: list[UserRecord],
    state: GeneratorState,
    args: argparse.Namespace,
) -> None:
    effective_rate = args.rate * size_multiplier(args.size)
    if args.summary_only:
        started_at = time.monotonic()
        next_metrics_at = started_at
        while time.monotonic() - started_at < args.duration:
            second_start = time.monotonic()
            for _ in range(effective_rate):
                payload = make_request_log_payload(state, users, args.error_rate)
                print(json.dumps({"topic": "raw.request_log", "payload": payload}))
            if time.monotonic() >= next_metrics_at:
                for payload in make_system_metric_payload(state):
                    print(json.dumps({"topic": "raw.system_metrics", "payload": payload}))
                next_metrics_at += 10.0
            elapsed = time.monotonic() - second_start
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
        return

    started_at = time.monotonic()
    next_metrics_at = started_at
    while time.monotonic() - started_at < args.duration:
        second_start = time.monotonic()
        request_records: list[dict[str, Any]] = []
        for _ in range(effective_rate):
            payload = make_request_log_payload(state, users, args.error_rate)
            request_records.append(payload)

        produce_avro_records(
            args.kafka_producer_container,
            "raw.request_log",
            REQUEST_LOG_SCHEMA,
            request_records,
        )

        if time.monotonic() >= next_metrics_at:
            metrics = make_system_metric_payload(state)
            produce_avro_records(
                args.kafka_producer_container,
                "raw.system_metrics",
                SYSTEM_METRIC_SCHEMA,
                metrics,
            )
            next_metrics_at += 10.0

        elapsed = time.monotonic() - second_start
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)


def run_postgres_generation(
    users: list[UserRecord],
    products: list[ProductRecord],
    state: GeneratorState,
    args: argparse.Namespace,
) -> None:
    started_at = time.monotonic()
    while time.monotonic() - started_at < args.duration:
        for _ in range(size_multiplier(args.size)):
            generate_postgres_cycle(
                args.postgres_container, users, products, state, args.summary_only
            )
            if time.monotonic() - started_at >= args.duration:
                break
        time.sleep(min(1.0, 60.0 / max(args.rate, 1)))


def main() -> int:
    args = apply_preset_defaults(parse_args())

    if args.summary_only and not args.users:
        print("--summary-only requires --users when the stack is not running", file=sys.stderr)
        return 1

    if args.summary_only:
        try:
            users = load_users_from_csv(args.users)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        products = DEFAULT_PRODUCTS
        state = default_state()
    else:
        try:
            users = (
                load_users_from_csv(args.users)
                if args.users
                else load_users(args.postgres_container)
            )
            products = load_products(args.postgres_container)
            state = load_state(args.postgres_container)
        except subprocess.CalledProcessError as exc:
            print(exc.stderr or exc.stdout, file=sys.stderr)
            return 1
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if args.mode == "all":
        postgres_thread = threading.Thread(
            target=run_postgres_generation,
            args=(users, products, state, args),
            daemon=False,
        )
        kafka_thread = threading.Thread(
            target=run_kafka_generation,
            args=(users, state, args),
            daemon=False,
        )
        postgres_thread.start()
        kafka_thread.start()
        postgres_thread.join()
        kafka_thread.join()
    elif args.mode == "postgres":
        run_postgres_generation(users, products, state, args)
    elif args.mode == "kafka":
        run_kafka_generation(users, state, args)

    print(
        json.dumps(
            {
                "mode": args.mode,
                "preset": args.preset,
                "duration": args.duration,
                "rate": args.rate,
                "effectiveRate": args.rate * size_multiplier(args.size),
                "size": args.size,
                "sizeMultiplier": size_multiplier(args.size),
                "errorRate": args.error_rate,
                "postgres_users": len(users),
                "products": len(products),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
