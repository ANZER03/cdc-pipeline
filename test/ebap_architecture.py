"""
EBAP - Enterprise Behavioral Analytics Platform
Architecture Diagram using the `diagrams` library.

Key design:
  - Top row:    Data Sources (streaming + batch)
  - Middle row: Ingestion (Kafka KRaft) | Batch Processing (Spark Batch)
  - Lower rows: Stream Processing -> Storage -> Serving -> Visualization -> Consumers

Generates: test/ebap_architecture.png
"""

from diagrams import Diagram, Cluster, Edge

# --- Node providers ---
from diagrams.onprem.queue import Kafka
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.inmemory import Redis
from diagrams.onprem.analytics import Spark
from diagrams.onprem.monitoring import Grafana
from diagrams.onprem.tracing import Jaeger           # placeholder: Schema Registry
from diagrams.generic.storage import Storage          # placeholder: MinIO / Iceberg
from diagrams.generic.database import SQL             # placeholder: Trino
from diagrams.programming.language import Python      # event generator
from diagrams.onprem.client import User
from diagrams.onprem.compute import Server            # micro-services
from diagrams.onprem.network import Nginx             # API gateway

# ── Colour palette for edges ─────────────────────────────────────────
C_STREAM   = "#1565c0"   # blue  – streaming data path
C_CDC      = "#e65100"   # orange – CDC path
C_BATCH    = "#2e7d32"   # dark green – batch / file path
C_HOT      = "#c62828"   # red – hot path (Redis)
C_COLD     = "#4a148c"   # purple – cold / serving path
C_INTERNAL = "#9e9e9e"   # gray – internal / management
C_UI       = "#37474f"   # dark gray – UI delivery

# ── Diagram attributes ───────────────────────────────────────────────
graph_attr = {
    "fontsize":  "30",
    "fontname":  "Helvetica Bold",
    "bgcolor":   "#fafafa",
    "pad":       "1.0",
    "nodesep":   "0.9",
    "ranksep":   "1.4",
    "splines":   "ortho",
    "compound":  "true",
    "label":     "Enterprise Behavioral Analytics Platform (EBAP)\nArchitecture Overview — Hybrid (Stream + Batch)",
    "labelloc":  "t",
}

node_attr = {
    "fontsize":  "11",
    "fontname":  "Helvetica",
}

edge_attr = {
    "fontsize":  "9",
    "fontname":  "Helvetica",
}

with Diagram(
    "",
    filename="test/ebap_architecture",
    show=False,
    direction="LR",
    outformat="png",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):

    # ================================================================
    # 1. STREAMING DATA SOURCES
    # ================================================================
    with Cluster("Streaming Data Sources", graph_attr={
        "bgcolor": "#e8f5e9", "style": "rounded", "fontsize": "14",
    }):
        users = User("End Users")
        event_gen = Python("Event Generator\n(Faker + Markov)")

        with Cluster("Micro-Services", graph_attr={
            "bgcolor": "#c8e6c9", "style": "rounded",
        }):
            api_gw       = Nginx("API Gateway\n(REST / gRPC)")
            svc_orders   = Server("Order\nService")
            svc_payments = Server("Payment\nService")
            svc_inventory = Server("Inventory\nService")

        user_db = PostgreSQL("PostgreSQL\n(User Profiles)\nWAL: logical")

    # ================================================================
    # 2. BATCH DATA SOURCES
    # ================================================================
    with Cluster("Batch Data Sources", graph_attr={
        "bgcolor": "#e0f2f1", "style": "rounded", "fontsize": "14",
    }):
        csv_files     = Storage("CSV Files\n(Exports, Reports)")
        json_files    = Storage("JSON Files\n(API Dumps, Logs)")
        parquet_files = Storage("Parquet Files\n(Data Warehouse\nExtracts)")
        log_files     = Storage("Log Files\n(Application Logs\nAccess Logs)")

    # ================================================================
    # 3. INGESTION LAYER – Kafka KRaft
    # ================================================================
    with Cluster("Ingestion Layer — Kafka (KRaft Mode)", graph_attr={
        "bgcolor": "#e3f2fd", "style": "rounded", "fontsize": "14",
    }):
        schema_reg = Jaeger("Schema Registry\n(Avro)")

        with Cluster("Kafka Cluster (KRaft — No Zookeeper)"):
            kafka_ctrl    = Kafka("KRaft Controller\n(Metadata Quorum)")
            kafka_events  = Kafka("ebap.events.raw")
            kafka_metrics = Kafka("ebap.metrics\n.telemetry")
            kafka_cdc     = Kafka("ebap.cdc.users")

        kafka_connect = Kafka("Kafka Connect\n(Debezium CDC)")

    # ================================================================
    # 4a. STREAM PROCESSING LAYER – Spark Structured Streaming
    # ================================================================
    with Cluster("Stream Processing — Spark Structured Streaming", graph_attr={
        "bgcolor": "#fff3e0", "style": "rounded", "fontsize": "14",
    }):
        stream_master = Spark("Spark Master\n(Streaming)")

        with Cluster("Streaming Workers"):
            sw_agg   = Spark("Windowed\nAggregations\n(1m / 5m / 1h)")
            sw_join  = Spark("Stream-Stream\nJoins\n(Events + Users)")
            sw_state = Spark("Alerting\nState Machine\n(Normal→Pending→Firing)")

    # ================================================================
    # 4b. BATCH PROCESSING LAYER – Spark Batch
    # ================================================================
    with Cluster("Batch Processing — Spark Batch Jobs", graph_attr={
        "bgcolor": "#f3e5f5", "style": "rounded", "fontsize": "14",
    }):
        batch_master = Spark("Spark Master\n(Batch)")

        with Cluster("Batch Workers"):
            bw_etl      = Spark("ETL\nTransform\n& Cleanse")
            bw_compact  = Spark("Iceberg\nCompaction\n(every 6h)")
            bw_backfill = Spark("Historical\nBackfill\n& Re-processing")

    # ================================================================
    # 5. STORAGE LAYER
    # ================================================================
    with Cluster("Storage Layer", graph_attr={
        "bgcolor": "#fce4ec", "style": "rounded", "fontsize": "14",
    }):
        with Cluster("Hot Storage (TTL: 24h)"):
            redis = Redis("Redis\n(Live KPIs\nRegional Health)")

        with Cluster("Cold Storage — Data Lakehouse"):
            minio   = Storage("MinIO (S3)\nObject Storage")
            iceberg = Storage("Apache Iceberg\n(ACID Tables)\nPartitioned:\nDay / Region")

    # ================================================================
    # 6. SERVING LAYER
    # ================================================================
    with Cluster("Serving Layer", graph_attr={
        "bgcolor": "#ede7f6", "style": "rounded", "fontsize": "14",
    }):
        trino = SQL("Trino\n(Distributed\nSQL Engine)")

    # ================================================================
    # 7. VISUALIZATION LAYER
    # ================================================================
    with Cluster("Visualization — Grafana", graph_attr={
        "bgcolor": "#fffde7", "style": "rounded", "fontsize": "14",
    }):
        grafana = Grafana("Grafana\n(Single Pane\nof Glass)")

        with Cluster("Dashboard Panels"):
            panel_live = Grafana("Live Panels\n(5s auto-refresh)")
            panel_hist = Grafana("Historical Panels\n(1h query cache)")
            panel_geo  = Grafana("Geo-Map\n(Regional Health)")

    # ================================================================
    # 8. CONSUMERS
    # ================================================================
    with Cluster("Consumers", graph_attr={
        "bgcolor": "#efebe9", "style": "rounded", "fontsize": "14",
    }):
        devops  = User("DevOps / SRE")
        pm      = User("Product\nManager")
        analyst = User("Data Analyst")

    # ================================================================
    # EDGES — Data Flow (with descriptions)
    # ================================================================

    # ── 1. Streaming Sources → Kafka ─────────────────────────────────

    users >> Edge(
        label="User interactions\n(clicks, views, purchases)",
        color=C_STREAM,
    ) >> event_gen

    event_gen >> Edge(
        label="Simulated clickstream\n(JSON, high-volume)",
        color=C_STREAM,
    ) >> kafka_events

    event_gen >> Edge(
        label="System telemetry\n(CPU, latency, error rates)",
        color=C_STREAM,
    ) >> kafka_metrics

    # Micro-services routing
    api_gw >> Edge(
        label="Route\nrequests",
        color=C_STREAM, style="dashed",
    ) >> svc_orders

    api_gw >> Edge(color=C_STREAM, style="dashed") >> svc_payments
    api_gw >> Edge(color=C_STREAM, style="dashed") >> svc_inventory

    svc_orders >> Edge(
        label="Order created/updated\nevents (JSON)",
        color=C_STREAM,
    ) >> kafka_events

    svc_payments >> Edge(
        label="Payment processed\nevents (JSON)",
        color=C_STREAM,
    ) >> kafka_events

    svc_inventory >> Edge(
        label="Stock level\nmetrics",
        color=C_STREAM,
    ) >> kafka_metrics

    # ── 2. CDC Path (Postgres → Kafka) ──────────────────────────────

    user_db >> Edge(
        label="WAL changes\n(row-level CDC)",
        color=C_CDC,
    ) >> kafka_connect

    kafka_connect >> Edge(
        label="User profile\ninserts/updates/deletes",
        color=C_CDC,
    ) >> kafka_cdc

    # ── 3. Kafka internals (KRaft) ──────────────────────────────────

    kafka_ctrl >> Edge(
        label="Metadata quorum\n(leader election,\npartition state)",
        color=C_INTERNAL, style="dashed",
    ) >> kafka_events

    kafka_ctrl >> Edge(
        color=C_INTERNAL, style="dashed",
    ) >> kafka_metrics

    kafka_ctrl >> Edge(
        color=C_INTERNAL, style="dashed",
    ) >> kafka_cdc

    schema_reg >> Edge(
        label="Schema validation\n(Avro compatibility\nchecks)",
        color=C_INTERNAL, style="dashed",
    ) >> kafka_events

    schema_reg >> Edge(
        label="Validate CDC\nschema evolution",
        color=C_INTERNAL, style="dashed",
    ) >> kafka_cdc

    # ── 4. Kafka → Stream Processing ────────────────────────────────

    kafka_events >> Edge(
        label="Consume raw events\n(micro-batch every 10s)",
        color=C_STREAM,
    ) >> stream_master

    kafka_cdc >> Edge(
        label="Consume user\nprofile changes",
        color=C_CDC,
    ) >> stream_master

    stream_master >> Edge(
        label="Distribute\nto workers",
        color=C_STREAM,
    ) >> sw_agg

    stream_master >> Edge(color=C_STREAM) >> sw_join
    stream_master >> Edge(color=C_STREAM) >> sw_state

    # ── 5. Batch Sources → Spark Batch ──────────────────────────────

    csv_files >> Edge(
        label="Read CSV\n(schema inference)",
        color=C_BATCH,
    ) >> batch_master

    json_files >> Edge(
        label="Parse JSON\n(nested structures)",
        color=C_BATCH,
    ) >> batch_master

    parquet_files >> Edge(
        label="Read Parquet\n(columnar, efficient)",
        color=C_BATCH,
    ) >> batch_master

    log_files >> Edge(
        label="Parse logs\n(regex extraction)",
        color=C_BATCH,
    ) >> batch_master

    batch_master >> Edge(
        label="Distribute\nbatch tasks",
        color=C_BATCH,
    ) >> bw_etl

    batch_master >> Edge(color=C_BATCH) >> bw_compact
    batch_master >> Edge(color=C_BATCH) >> bw_backfill

    # ── 6. Stream Processing → Storage (Dual-Write) ─────────────────

    sw_agg >> Edge(
        label="Windowed counts\n(active users, EPS)\nSET key TTL 24h",
        color=C_HOT,
    ) >> redis

    sw_state >> Edge(
        label="Alert state updates\n(Normal/Pending/Firing)",
        color=C_HOT,
    ) >> redis

    sw_join >> Edge(
        label="Enriched events\n(user + click joined)\nIceberg ACID write",
        color=C_COLD,
    ) >> minio

    # ── 7. Batch Processing → Storage ────────────────────────────────

    bw_etl >> Edge(
        label="Cleansed & transformed\nbatch data\n(Iceberg append)",
        color=C_BATCH,
    ) >> minio

    bw_compact >> Edge(
        label="Merge small files\ninto 128MB targets\n(Iceberg rewrite)",
        color=C_BATCH, style="dashed",
    ) >> iceberg

    bw_backfill >> Edge(
        label="Re-process\nhistorical partitions\n(overwrite mode)",
        color=C_BATCH, style="dashed",
    ) >> iceberg

    # ── 8. MinIO ↔ Iceberg ───────────────────────────────────────────

    minio >> Edge(
        label="Iceberg metadata\n+ Parquet data files",
        color=C_COLD, style="dashed",
    ) >> iceberg

    # ── 9. Storage → Serving ─────────────────────────────────────────

    iceberg >> Edge(
        label="Catalog scan\n(partition pruning\n+ predicate pushdown)",
        color=C_COLD,
    ) >> trino

    # ── 10. Storage / Serving → Visualization ────────────────────────

    redis >> Edge(
        label="Poll every 5s\n(GET / HGETALL)\nreal-time KPIs",
        color=C_HOT,
    ) >> panel_live

    redis >> Edge(
        label="Regional load %\nand sales volume",
        color=C_HOT,
    ) >> panel_geo

    trino >> Edge(
        label="SQL query results\n(cached 1h)\nhistorical trends",
        color=C_COLD,
    ) >> panel_hist

    panel_live >> Edge(color=C_UI) >> grafana
    panel_hist >> Edge(color=C_UI) >> grafana
    panel_geo  >> Edge(color=C_UI) >> grafana

    # ── 11. Visualization / Serving → Consumers ──────────────────────

    grafana >> Edge(
        label="System health\nalerts & dashboards",
        color=C_UI,
    ) >> devops

    grafana >> Edge(
        label="User behavior\nfunnels & KPIs",
        color=C_UI,
    ) >> pm

    trino >> Edge(
        label="Ad-hoc SQL queries\n(direct access via\nTrino CLI / JDBC)",
        color=C_COLD,
    ) >> analyst
