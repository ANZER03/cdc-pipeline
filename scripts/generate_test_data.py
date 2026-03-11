#!/usr/bin/env python3
"""Generate Nexus PostgreSQL CDC and direct Kafka test traffic.

Uses Faker for realistic e-commerce simulation (Amazon-like):
real names, addresses, product names, user agents, and behaviour patterns.
Supports high-throughput via batched SQL and configurable presets.
"""

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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from faker import Faker

    _faker = Faker()
    Faker.seed(0)
    _HAS_FAKER = True
except ImportError:
    _HAS_FAKER = False


ROOT = Path(__file__).resolve().parents[1]
SQL_COMMAND_TIMEOUT_SECONDS = int(os.getenv("SQL_COMMAND_TIMEOUT_SECONDS", "120"))
KAFKA_PRODUCE_TIMEOUT_SECONDS = int(os.getenv("KAFKA_PRODUCE_TIMEOUT_SECONDS", "120"))

# ---------------------------------------------------------------------------
# Avro schemas (unchanged — schema contract must not break)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Regions — fixed list that Spark aggregates on (coordinates must not change)
# ---------------------------------------------------------------------------

REGIONS = [
    "North America (East)",
    "North America (West)",
    "Western Europe",
    "Japan",
    "Southeast Asia",
    "Australia",
    "Brazil",
    "India",
    "South Africa",
]

# Weights: more traffic from large consumer markets
REGION_WEIGHTS = [0.20, 0.18, 0.16, 0.10, 0.10, 0.06, 0.08, 0.08, 0.04]

# ---------------------------------------------------------------------------
# Platform / user-agent table
# ---------------------------------------------------------------------------

PLATFORM_AGENTS: dict[str, list[str]] = {
    "Desktop": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    ],
    "Mobile": [
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    ],
    "iOS": [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPad; CPU OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    ],
    "Android": [
        "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
        "com.amazon.mShop.android.shopping/24.18.0.100 (Android/14; Pixel 8; Build/UP1A.231005.007)",
    ],
}

PLATFORMS = list(PLATFORM_AGENTS.keys())
PLATFORM_WEIGHTS = [0.40, 0.25, 0.20, 0.15]

# ---------------------------------------------------------------------------
# Product catalog — realistic categories with price ranges
# ---------------------------------------------------------------------------

PRODUCT_CATEGORIES: dict[str, dict[str, Any]] = {
    "Electronics": {
        "items": [
            "Wireless Noise-Cancelling Headphones",
            '4K Smart TV 55"',
            'Laptop 15" Core i7',
            "Mechanical Keyboard",
            "USB-C Hub 7-in-1",
            "Portable Bluetooth Speaker",
            "Smartwatch Series 9",
            "Webcam 4K Pro",
            "Gaming Mouse RGB",
            "SSD 1TB NVMe",
            'Monitor 27" QHD',
            'Tablet 10.9" WiFi',
            "Earbuds True Wireless",
            "Phone Charger 65W GaN",
            "Smart Home Hub",
        ],
        "price_range": (15.0, 2500.0),
        "price_distribution": "log_normal",  # most items cheaper, a few expensive
    },
    "Books": {
        "items": [
            "The Pragmatic Programmer",
            "Clean Code",
            "Designing Data-Intensive Applications",
            "Atomic Habits",
            "The Psychology of Money",
            "Zero to One",
            "Sapiens",
            "The Lean Startup",
            "Deep Work",
            "Thinking, Fast and Slow",
            "The Art of War",
            "Meditations",
            "Rich Dad Poor Dad",
            "Educated",
            "The Midnight Library",
        ],
        "price_range": (7.99, 49.99),
        "price_distribution": "uniform",
    },
    "Clothing": {
        "items": [
            "Men's Running Shoes",
            "Women's Yoga Pants",
            "Classic White T-Shirt",
            "Slim-Fit Jeans",
            "Waterproof Rain Jacket",
            "Cotton Hoodie Fleece",
            "Athletic Shorts",
            "Wool Sweater",
            "Summer Dress Floral",
            "Work Boots Steel Toe",
            "Merino Wool Socks",
            "Baseball Cap Adjustable",
            "Winter Gloves Touchscreen",
            "Sports Bra High Impact",
            "Denim Jacket",
        ],
        "price_range": (12.0, 350.0),
        "price_distribution": "log_normal",
    },
    "Home & Kitchen": {
        "items": [
            "Air Fryer 5.8 QT",
            "Coffee Maker Programmable",
            "Robot Vacuum Cleaner",
            "Instant Pot 7-in-1",
            'Cast Iron Skillet 12"',
            "Stand Mixer Professional",
            "Memory Foam Pillow",
            "Egyptian Cotton Sheets",
            "Shower Head High Pressure",
            "LED Desk Lamp Dimmer",
            "Bamboo Cutting Board",
            "Knife Set 15-Piece",
            "Stainless Steel Water Bottle",
            "Laundry Hamper Collapsible",
            "Door Mat Anti-Fatigue",
        ],
        "price_range": (10.0, 600.0),
        "price_distribution": "log_normal",
    },
    "Sports & Outdoors": {
        "items": [
            "Yoga Mat Non-Slip",
            "Resistance Bands Set",
            "Adjustable Dumbbells 50lb",
            "Hiking Backpack 50L",
            "Camping Tent 4-Person",
            "Bicycle Helmet MIPS",
            "Jump Rope Speed",
            "Pull-Up Bar Doorway",
            "Foam Roller Deep Tissue",
            "Trekking Poles Carbon",
            "Sleeping Bag -20°C",
            "Kayak Paddle Lightweight",
            "Golf Club Set Beginner",
            "Tennis Racket Graphite",
            "Swimming Goggles Anti-Fog",
        ],
        "price_range": (10.0, 800.0),
        "price_distribution": "log_normal",
    },
}

ALL_CATEGORY_NAMES = list(PRODUCT_CATEGORIES.keys())
CATEGORY_WEIGHTS = [0.30, 0.15, 0.20, 0.20, 0.15]

# ---------------------------------------------------------------------------
# Request endpoints — expanded to resemble a real e-commerce API
# ---------------------------------------------------------------------------

REQUEST_ENDPOINTS = [
    ("GET", "/api/products"),
    ("GET", "/api/products/featured"),
    ("GET", "/api/products/{id}"),
    ("GET", "/api/products/search"),
    ("GET", "/api/cart"),
    ("POST", "/api/cart/items"),
    ("DELETE", "/api/cart/items/{id}"),
    ("POST", "/api/checkout"),
    ("GET", "/api/checkout/confirm"),
    ("GET", "/api/orders"),
    ("GET", "/api/orders/{id}"),
    ("GET", "/api/profile"),
    ("PUT", "/api/profile"),
    ("GET", "/api/recommendations"),
    ("GET", "/api/deals"),
    ("GET", "/api/reviews/{product_id}"),
    ("POST", "/api/reviews"),
    ("GET", "/api/wishlist"),
    ("POST", "/api/wishlist"),
    ("DELETE", "/api/wishlist/{id}"),
]

# Weighted so reads dominate (realistic API traffic)
ENDPOINT_WEIGHTS = [
    0.12,
    0.08,
    0.10,
    0.08,  # product browse/search
    0.06,
    0.05,
    0.02,  # cart
    0.04,
    0.02,  # checkout
    0.05,
    0.03,  # orders
    0.04,
    0.01,  # profile
    0.06,  # recommendations
    0.04,  # deals
    0.05,
    0.02,  # reviews
    0.05,
    0.03,
    0.02,  # wishlist
]

# ---------------------------------------------------------------------------
# User journey patterns — Amazon-like behavioural flows
# ---------------------------------------------------------------------------

USER_EVENT_PATTERNS = [
    # Full purchase funnel (search → browse → add to cart → buy)
    [
        "login",
        "page_view",
        "page_view",
        "add_to_cart",
        "page_view",
        "checkout_start",
        "checkout_complete",
    ],
    # Browse and logout without buying
    ["login", "page_view", "page_view", "logout"],
    # Passive browsing (no login)
    ["page_view", "page_view", "page_view"],
    # Search and compare (multiple products)
    ["login", "search", "page_view", "page_view", "page_view", "logout"],
    # Add to wishlist flow
    ["login", "page_view", "add_to_wishlist", "page_view", "add_to_wishlist", "logout"],
    # Deep funnel: cart abandonment after checkout_start
    ["login", "page_view", "add_to_cart", "checkout_start", "logout"],
    # Repeat buyer: quick checkout
    ["login", "add_to_cart", "checkout_start", "checkout_complete"],
    # Return / refund flow
    ["login", "page_view", "checkout_complete", "return_request"],
    # Review submission after purchase
    ["login", "page_view", "checkout_complete", "review_submit"],
    # Window shopping with recommendations
    ["page_view", "page_view", "view_recommendations", "page_view"],
    # Mobile quick-buy
    ["login", "search", "add_to_cart", "checkout_start", "checkout_complete"],
    # Category browse
    ["page_view", "search", "page_view", "page_view", "page_view", "logout"],
]

# Weights: full funnel less common than casual browsing
PATTERN_WEIGHTS = [0.10, 0.12, 0.15, 0.10, 0.08, 0.08, 0.07, 0.05, 0.05, 0.08, 0.06, 0.06]

NODES = [
    "api-node-1",
    "api-node-2",
    "api-node-3",
    "db-node-1",
    "cache-node-1",
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


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
    category: str | None = None
    name: str | None = None


DEFAULT_PRODUCTS = [
    ProductRecord(
        id=1, price=1299.0, merchant_region="North America (West)", category="Electronics"
    ),
    ProductRecord(id=7, price=249.0, merchant_region="India", category="Electronics"),
    ProductRecord(id=12, price=59.0, merchant_region="North America (West)", category="Clothing"),
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
    "high": {"rate": 100, "duration": 300, "size": "large", "error_rate": 0.08},
    "extreme": {"rate": 200, "duration": 180, "size": "large", "error_rate": 0.10},
}


@dataclass
class GeneratorState:
    next_request_log_id: int
    next_system_metric_id: int
    active_sessions: dict[int, str] = field(default_factory=dict)
    user_cursor: int = 0


# ---------------------------------------------------------------------------
# Faker helpers
# ---------------------------------------------------------------------------


def faker_ip() -> str:
    if _HAS_FAKER:
        return _faker.ipv4_public()
    return f"203.0.113.{random.randint(1, 254)}"


def faker_user_agent(platform: str | None) -> str:
    plat = platform or random.choices(PLATFORMS, weights=PLATFORM_WEIGHTS)[0]
    agents = PLATFORM_AGENTS.get(plat, PLATFORM_AGENTS["Desktop"])
    if _HAS_FAKER:
        # occasionally use a fully random Faker UA
        if random.random() < 0.15:
            return _faker.user_agent()
    return random.choice(agents)


def faker_display_name() -> str:
    if _HAS_FAKER:
        return _faker.name()
    return f"User{random.randint(1000, 9999)}"


def faker_product_name(category: str | None = None) -> str:
    cat = category or random.choices(ALL_CATEGORY_NAMES, weights=CATEGORY_WEIGHTS)[0]
    return random.choice(PRODUCT_CATEGORIES[cat]["items"])


def realistic_price(category: str | None = None) -> float:
    cat = category or random.choices(ALL_CATEGORY_NAMES, weights=CATEGORY_WEIGHTS)[0]
    cfg = PRODUCT_CATEGORIES[cat]
    lo, hi = cfg["price_range"]
    if cfg["price_distribution"] == "log_normal":
        # log-normal centred around geometric mean of range
        mu = (math.log(lo) + math.log(hi)) / 2
        sigma = (math.log(hi) - math.log(lo)) / 4
        price = math.exp(random.gauss(mu, sigma))
        price = max(lo, min(hi, price))
    else:
        price = random.uniform(lo, hi)
    # Round to nearest .99 or .00 — e-commerce pricing
    rounded = round(price, 2)
    if random.random() < 0.60:
        rounded = round(price) - 0.01
    return max(0.01, rounded)


def realistic_latency_ms(error: bool = False) -> int:
    """Log-normal latency with occasional long-tail spikes (P99 > 200ms)."""
    if error:
        # errors tend to be faster (auth fail) or slower (timeouts)
        if random.random() < 0.4:
            return random.randint(2, 30)  # fast client error
        return random.randint(150, 3000)  # slow server error / timeout
    # Base: log-normal, median ~65ms, mean ~90ms
    ms = math.exp(random.gauss(4.2, 0.7))
    # 3% chance of a spike (P99 behaviour)
    if random.random() < 0.03:
        ms += random.uniform(200, 1500)
    return max(1, int(ms))


def pick_region() -> str:
    return random.choices(REGIONS, weights=REGION_WEIGHTS)[0]


def pick_platform() -> str:
    return random.choices(PLATFORMS, weights=PLATFORM_WEIGHTS)[0]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Nexus CDC and Kafka test traffic")
    parser.add_argument(
        "--preset",
        choices=["custom", "light", "demo", "stress", "high", "extreme"],
        default="custom",
    )
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


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


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
        "SELECT id, username, display_name, COALESCE(country_code, ''), COALESCE(city, ''), "
        "COALESCE(region_name, ''), COALESCE(platform, '') FROM users ORDER BY id;",
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
    )


# ---------------------------------------------------------------------------
# SQL value encoding
# ---------------------------------------------------------------------------


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
    # Batch all statements in a single psql call — avoids per-statement subprocess overhead
    run_sql(container, "\n".join(statements))


# ---------------------------------------------------------------------------
# Kafka helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# User / product selection
# ---------------------------------------------------------------------------


def choose_user(users: list[UserRecord], state: GeneratorState) -> UserRecord:
    user = users[state.user_cursor % len(users)]
    state.user_cursor += 1
    return user


def choose_product(products: list[ProductRecord]) -> ProductRecord:
    return random.choice(products)


def page_url_for(product: ProductRecord | None, event_type: str | None = None) -> str:
    if event_type == "search":
        queries = ["wireless headphones", "running shoes", "smart home", "gifts", "deals today"]
        return f"/search?q={random.choice(queries).replace(' ', '+')}"
    if event_type == "view_recommendations":
        return "/recommendations"
    if product is None:
        return random.choice(["/home", "/collections/new", "/search", "/deals", "/bestsellers"])
    return f"/products/{product.id}"


# ---------------------------------------------------------------------------
# Postgres cycle — one "user journey" per call (batched SQL)
# ---------------------------------------------------------------------------


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

    # Derive realistic user-agent and IP
    user_agent = faker_user_agent(user.platform)
    ip_address = faker_ip()

    # Possibly start a new session (25% chance even if one exists)
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

    pattern = random.choices(USER_EVENT_PATTERNS, weights=PATTERN_WEIGHTS)[0]
    statements: list[str] = []
    order_id = None
    qty = random.randint(1, 4)
    order_total = round(product.price * qty, 2)
    completion_time = now + timedelta(seconds=random.randint(5, 30))

    # Realistic error simulation
    error_roll = random.random()
    if error_roll < 0.05:
        final_status = "failed"  # payment failure
    elif error_roll < 0.08:
        final_status = "refunded"  # immediate refund
    else:
        final_status = "completed"

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
        statements.append(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price, created_at) VALUES ("
            + ", ".join(
                [
                    sql_literal(order_id),
                    sql_literal(product.id),
                    sql_literal(qty),
                    sql_literal(product.price),
                    sql_literal(now + timedelta(seconds=6)),
                ]
            )
            + ");"
        )

    for step, event_type in enumerate(pattern):
        event_time = now + timedelta(seconds=step * random.randint(2, 8))
        metadata: dict[str, Any] = {}
        page_url = page_url_for(
            product
            if event_type
            in {
                "page_view",
                "add_to_cart",
                "checkout_start",
                "checkout_complete",
                "add_to_wishlist",
                "review_submit",
            }
            else None,
            event_type=event_type,
        )
        referrer = (
            "/home"
            if step == 0
            else random.choice(["/search", "/recommendations", "/deals", page_url])
        )

        if event_type == "add_to_cart":
            metadata = {"product_id": product.id, "quantity": qty, "category": product.category}
            statements.append(
                "INSERT INTO cart_items (user_id, product_id, quantity, added_at) VALUES ("
                + ", ".join(
                    [
                        sql_literal(user.id),
                        sql_literal(product.id),
                        str(qty),
                        sql_literal(event_time),
                    ]
                )
                + ");"
            )
        elif event_type == "checkout_start":
            metadata = {"cart_value": order_total, "order_id": order_id, "item_count": qty}
        elif event_type == "checkout_complete":
            metadata = {"order_id": order_id or 0, "total": order_total, "currency": "USD"}
        elif event_type == "login":
            metadata = {"auth_method": random.choice(["password", "google", "otp", "biometric"])}
        elif event_type == "logout":
            metadata = {"session_duration_s": random.randint(30, 1800)}
        elif event_type == "page_view":
            metadata = {"product_id": product.id, "category": product.category or ""}
        elif event_type == "search":
            metadata = {
                "query": faker_product_name(product.category),
                "result_count": random.randint(0, 200),
            }
        elif event_type == "add_to_wishlist":
            metadata = {"product_id": product.id, "wishlist_size": random.randint(1, 20)}
        elif event_type == "return_request":
            metadata = {
                "order_id": order_id or 0,
                "reason": random.choice(["defective", "wrong_item", "changed_mind", "too_small"]),
            }
        elif event_type == "review_submit":
            metadata = {
                "product_id": product.id,
                "rating": random.randint(1, 5),
                "verified_purchase": True,
            }
        elif event_type == "view_recommendations":
            metadata = {
                "algorithm": random.choice(["collaborative", "content_based", "trending"]),
                "count": 12,
            }

        statements.append(
            "INSERT INTO user_events (user_id, event_type, page_url, referrer_url, user_agent, ip_address, session_id, metadata, user_display_name, region_name, city, country_code, platform, amount, created_at) VALUES ("
            + ", ".join(
                [
                    sql_literal(user.id),
                    sql_literal(event_type),
                    sql_literal(page_url),
                    sql_literal(referrer),
                    sql_literal(user_agent),
                    sql_literal(ip_address),
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

    # Flush all user_event + cart_item inserts in a single psql call
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
                + ";"
            ],
            summary_only,
        )

    # 15% chance to end the session
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


# ---------------------------------------------------------------------------
# Kafka payloads
# ---------------------------------------------------------------------------


def make_request_log_payload(
    state: GeneratorState,
    users: list[UserRecord],
    error_rate: float,
) -> dict[str, Any]:
    user = choose_user(users, state)
    method, endpoint = random.choices(REQUEST_ENDPOINTS, weights=ENDPOINT_WEIGHTS)[0]
    state.next_request_log_id += 1

    server_error_rate = max(0.0, min(error_rate, 0.4))
    client_error_rate = max(0.0, min(error_rate / 2.0, 0.2))
    success_rate = max(0.0, 1.0 - server_error_rate - client_error_rate)
    roll = random.random()

    is_error = roll >= success_rate
    if roll < success_rate:
        status_code = 200
    elif roll < success_rate + client_error_rate:
        status_code = random.choice([400, 401, 403, 404, 422, 429])
    else:
        status_code = random.choice([500, 502, 503, 504])

    latency = realistic_latency_ms(error=is_error)
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
        for metric_name, mean, stddev in (
            ("cpu_percent", 40, 15),
            ("memory_percent", 55, 10),
            ("disk_io_mbps", 25, 8),
            ("network_in_mbps", 120, 30),
        ):
            # Only emit cpu/memory always; others occasionally
            if metric_name not in ("cpu_percent", "memory_percent") and random.random() < 0.5:
                continue
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


# ---------------------------------------------------------------------------
# Generation loops
# ---------------------------------------------------------------------------


def run_kafka_generation(
    users: list[UserRecord],
    state: GeneratorState,
    args: argparse.Namespace,
) -> None:
    effective_rate = args.rate * size_multiplier(args.size)
    started_at = time.monotonic()
    next_metrics_at = started_at

    while time.monotonic() - started_at < args.duration:
        second_start = time.monotonic()
        request_records: list[dict[str, Any]] = []

        for _ in range(effective_rate):
            payload = make_request_log_payload(state, users, args.error_rate)
            request_records.append(payload)

        if args.summary_only:
            for r in request_records:
                print(json.dumps({"topic": "raw.request_log", "payload": r}))
        else:
            produce_avro_records(
                args.kafka_producer_container,
                "raw.request_log",
                REQUEST_LOG_SCHEMA,
                request_records,
            )

        if time.monotonic() >= next_metrics_at:
            metrics = make_system_metric_payload(state)
            if args.summary_only:
                for m in metrics:
                    print(json.dumps({"topic": "raw.system_metrics", "payload": m}))
            else:
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    args = apply_preset_defaults(parse_args())

    if not _HAS_FAKER:
        print(
            "WARNING: 'faker' package not installed — using minimal synthetic data. "
            "Install with: pip install faker",
            file=sys.stderr,
        )

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
                "faker_enabled": _HAS_FAKER,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
