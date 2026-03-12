"""Nexus streaming architecture diagram using the diagrams library.

The diagram mirrors the stack implemented in this repository:
generator -> PostgreSQL + raw Kafka -> Debezium CDC -> Kafka/Schema Registry
-> Spark structured streaming jobs -> Redis -> FastAPI -> dashboard clients.

Generates: docs/architecture/diagrams/nexus_architecture.png
"""

from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.custom import Custom
from diagrams.generic.blank import Blank
from diagrams.onprem.analytics import Spark
from diagrams.onprem.client import Client, User
from diagrams.onprem.compute import Server
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.inmemory import Redis
from diagrams.onprem.network import Nginx
from diagrams.onprem.queue import Kafka
from diagrams.programming.framework import Fastapi
from diagrams.programming.language import Python


C_GEN = "#1565c0"
C_CDC = "#ef6c00"
C_STREAM = "#2e7d32"
C_HOT = "#c62828"
C_API = "#455a64"
C_CONTROL = "#6d4c41"


graph_attr = {
    "fontsize": "26",
    "fontname": "Helvetica Bold",
    "bgcolor": "#fafafa",
    "pad": "0.8",
    "nodesep": "0.8",
    "ranksep": "1.1",
    "splines": "ortho",
    "compound": "true",
    "label": "Nexus Streaming Pipeline\nCurrent Repository Architecture",
    "labelloc": "t",
}

node_attr = {
    "fontsize": "11",
    "fontname": "Helvetica",
}

edge_attr = {
    "fontsize": "9",
    "fontname": "Helvetica",
}

SCHEMA_REGISTRY_LOGO = str(Path(__file__).with_name("confluent-schema-reistry-logo.png"))
DEBEZIUM_LOGO = str(Path(__file__).with_name("Debezium-900x900-1.png"))


with Diagram(
    "",
    filename="docs/architecture/diagrams/nexus_architecture",
    show=False,
    direction="LR",
    outformat="png",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    with Cluster("Sources", graph_attr={"bgcolor": "#e3f2fd", "style": "rounded"}):
        operator = User("Operator")
        generator = Python("scripts/\ngenerate_test_data.py")
        postgres = PostgreSQL("PostgreSQL\norders, sessions,\nuser_events, products, users")

        with Cluster("Direct Raw Topics", graph_attr={"bgcolor": "#bbdefb", "style": "rounded"}):
            raw_request = Kafka("raw.request_log")
            raw_system = Kafka("raw.system_metrics")

    with Cluster("Kafka + CDC", graph_attr={"bgcolor": "#fff3e0", "style": "rounded"}):
        schema_registry = Custom("Schema Registry\nAvro schemas", SCHEMA_REGISTRY_LOGO)
        debezium = Custom("Debezium Connect", DEBEZIUM_LOGO)

        with Cluster("Kafka Cluster", graph_attr={"bgcolor": "#ffe0b2", "style": "rounded"}):
            kafka_cluster = Kafka("kafka-1 / kafka-2\nKRaft brokers")
            cdc_orders = Kafka("pg.public.orders")
            cdc_sessions = Kafka("pg.public.sessions")
            cdc_user_events = Kafka("pg.public.user_events")
            cdc_products = Kafka("pg.public.products")
            cdc_users = Kafka("pg.public.users")
            aggregated_kpis = Kafka("aggregated.kpis")

    with Cluster("Spark Cluster", graph_attr={"bgcolor": "#f1f8e9", "style": "rounded"}):
        spark_master = Spark("Spark Master\n7077 / 8082")

        with Cluster("Workers", graph_attr={"bgcolor": "#dcedc8", "style": "rounded"}):
            spark_worker_1 = Spark("spark-worker\n8091")
            spark_worker_2 = Spark("spark-worker-2\n8092")

        with Cluster("Streaming Jobs", graph_attr={"bgcolor": "#c5e1a5", "style": "rounded"}):
            tx_job = Spark("nexus-transactions\n4040")
            infra_job = Spark("nexus-infrastructure\n4041")
            derived_job = Spark("nexus-derived\n4042")

    with Cluster("Hot Outputs", graph_attr={"bgcolor": "#ffebee", "style": "rounded"}):
        redis = Redis("Redis\nkeys + pub/sub")
        redis_contract = Blank(
            "nexus:kpi:current\nnexus:traffic:timeseries\nnexus:activity:feed\nnexus:regions:current\nnexus:flows:current\nnexus:platform:breakdown\nnexus:alert:*\nnexus:health:current\nnexus:geo:header"
        )
        kafka_contract = Blank("Kafka contract\naggregated.kpis")

    with Cluster("API Layer", graph_attr={"bgcolor": "#eceff1", "style": "rounded"}):
        api = Fastapi("FastAPI\nREST + SSE + WS")
        snapshot_routes = Server("Snapshot routes\n/api/*")
        realtime_routes = Nginx("/events + /ws\nRedis fan-out")

    with Cluster("Clients", graph_attr={"bgcolor": "#f3e5f5", "style": "rounded"}):
        dashboard = Client("Dashboard UI")
        monitor = Client("Monitor UI")
        generator_ui = Client("Generator UI")

    operator >> Edge(label="runs synthetic traffic", color=C_GEN) >> generator

    (
        generator
        >> Edge(
            label="fat-event inserts\nmode=all writes relational rows",
            color=C_GEN,
        )
        >> postgres
    )
    generator >> Edge(label="Avro produce", color=C_GEN) >> raw_request
    generator >> Edge(label="Avro produce", color=C_GEN) >> raw_system

    postgres >> Edge(label="WAL changes", color=C_CDC) >> debezium
    debezium >> Edge(label="Confluent Avro CDC", color=C_CDC) >> kafka_cluster

    (
        debezium
        >> Edge(label="register Avro schemas", color=C_CONTROL, style="dashed")
        >> schema_registry
    )
    schema_registry >> Edge(label="fetch writer schemas", color=C_CONTROL, style="dashed") >> tx_job
    (
        schema_registry
        >> Edge(label="fetch writer schemas", color=C_CONTROL, style="dashed")
        >> derived_job
    )

    raw_request >> Edge(label="raw topic", color=C_GEN) >> kafka_cluster
    raw_system >> Edge(label="raw topic", color=C_GEN) >> kafka_cluster

    kafka_cluster >> Edge(label="orders CDC", color=C_CDC) >> cdc_orders
    kafka_cluster >> Edge(label="sessions CDC", color=C_CDC) >> cdc_sessions
    kafka_cluster >> Edge(label="user events CDC", color=C_CDC) >> cdc_user_events
    kafka_cluster >> Edge(label="products CDC", color=C_CDC) >> cdc_products
    kafka_cluster >> Edge(label="users CDC", color=C_CDC) >> cdc_users

    spark_master >> Edge(label="schedule executors", color=C_CONTROL) >> spark_worker_1
    spark_master >> Edge(label="schedule executors", color=C_CONTROL) >> spark_worker_2
    spark_master >> Edge(label="transaction analytics", color=C_STREAM) >> tx_job
    spark_master >> Edge(label="infrastructure analytics", color=C_STREAM) >> infra_job
    spark_master >> Edge(label="derived analytics", color=C_STREAM) >> derived_job

    cdc_orders >> Edge(label="KPI + region inputs", color=C_CDC) >> tx_job
    cdc_sessions >> Edge(label="KPI active session count", color=C_CDC) >> tx_job
    cdc_user_events >> Edge(label="activity feed", color=C_CDC) >> tx_job
    raw_request >> Edge(label="latency + errors", color=C_GEN) >> tx_job

    raw_request >> Edge(label="traffic + geo", color=C_GEN) >> infra_job
    raw_system >> Edge(label="health metrics", color=C_GEN) >> infra_job

    cdc_sessions >> Edge(label="platform breakdown", color=C_CDC) >> derived_job

    (
        tx_job
        >> Edge(
            label="kpi, alerts, activity,\nregions, flows",
            color=C_HOT,
        )
        >> redis
    )
    infra_job >> Edge(label="traffic, health, geo", color=C_HOT) >> redis
    derived_job >> Edge(label="platform", color=C_HOT) >> redis
    tx_job >> Edge(label="JSON snapshots", color=C_STREAM) >> aggregated_kpis

    redis >> Edge(label="snapshot reads", color=C_API) >> api
    redis >> Edge(label="pub/sub events", color=C_API, style="dashed") >> api
    redis >> Edge(label="hot-path keys", color=C_HOT, style="dashed") >> redis_contract
    (
        aggregated_kpis
        >> Edge(label="streaming contract output", color=C_STREAM, style="dashed")
        >> kafka_contract
    )

    api >> Edge(label="GET /api/metrics ... /api/geo", color=C_API) >> snapshot_routes
    api >> Edge(label="GET /events and /ws", color=C_API) >> realtime_routes

    snapshot_routes >> Edge(label="initial snapshots", color=C_API) >> dashboard
    realtime_routes >> Edge(label="incremental WS/SSE", color=C_API) >> dashboard
    snapshot_routes >> Edge(label="monitor snapshots", color=C_API) >> monitor
    realtime_routes >> Edge(label="monitor live updates", color=C_API) >> monitor
    snapshot_routes >> Edge(label="generator control pages", color=C_API) >> generator_ui
