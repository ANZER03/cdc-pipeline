# Product Requirements Document (PRD)

**Project Name:** Enterprise Behavioral Analytics Platform (EBAP)
**Version:** 1.0
**Status:** Draft
**Date:** 2025-10-27

---

## **1. Executive Summary**

### **1.1 Purpose**

The **Enterprise Behavioral Analytics Platform (EBAP)** is a unified data system designed to ingest, process, and visualize user interactions and system health metrics at scale.

Current solutions are often fragmented—operational teams use one tool for real-time monitoring, while data analysts use another for historical reporting. EBAP solves this by implementing a **Hybrid Architecture** (Lambda/Kappa evolution). It combines low-latency streaming for immediate operational awareness with a robust data lakehouse for deep historical analysis.

### **1.2 Scope**

The platform will support the end-to-end data lifecycle:

1. **Ingestion:** Capturing high-volume "Event Streams" (User Actions) and "Time-Series Metrics" (System Telemetry) via **Apache Kafka**.
2. **Contextualization:** Enriching raw streams with transactional data (User Profiles) using **Kafka Connect (Debezium CDC)**.
3. **Processing:** Performing windowed aggregations and stateful anomaly detection using **Spark Structured Streaming**.
4. **Storage:** Storing governed, acid-compliant datasets in **Apache Iceberg** backed by **MinIO** object storage.
5. **Access:** Providing SQL access via **Trino** and visualization via **Grafana**.

### **1.3 High-Level Architecture**

The system operates on three speed layers as defined in the technical specifications:

* **Hot Path (Real-Time):** Kafka  Spark Streaming  Redis  Grafana (Live Dashboards).
* **Warm Path (Operational):** Prometheus/Cortex for recent time-series metrics (24h history).
* **Cold Path (Historical):** Spark Streaming  Apache Iceberg (MinIO)  Trino  BI Tools.

---

## **2. Goals & Success Metrics**

### **2.1 Business Goals**

* **Unified View:** Eliminate data silos by serving both Engineering (System Health) and Product (User Behavior) teams from a single source of truth.
* **Faster Reaction Time:** Reduce the "Time to Detect" (TTD) for critical issues (e.g., checkout failures, regional outages) from >15 minutes to **<1 minute**.
* **Historical Insight:** Enable "Time Travel" queries to compare current launch performance against historical baselines (e.g., "Compare Black Friday 2025 vs. 2024").

### **2.2 Technical Success Metrics (KPIs)**

| Metric Category | Target | Description |
| --- | --- | --- |
| **Latency (Hot Path)** | **< 60 Seconds** | End-to-end latency from "User Click" to "Grafana Dashboard Update". |
| **Query Performance** | **< 3 Seconds** | Average response time for Trino SQL queries on aggregated Iceberg tables. |
| **Throughput** | **10,000+ EPS** | Capability to handle peak Event Per Second loads without backpressure. |
| **Data Integrity** | **Exactly-Once** | Zero data loss or duplication for critical "Commerce" events (e.g., `purchase`). |
| **Storage Efficiency** | **Compacted** | Implementation of Iceberg compaction to preventing "Small File Problem" in MinIO. |

---

## **3. User Stories & Use Cases**

This section defines how different stakeholders interact with the **Time-Series**, **Event Stream**, and **Regional Health** data schemas.

### **3.1 Persona: The DevOps Engineer (Operational Health)**

**Goal:** Monitor system stability and regional availability.

* **User Story:** "As a DevOps Engineer, I want to see a real-time heatmap of 'Regional Health' so I can identify if a specific region (e.g., `us-east-1`) is experiencing high latency."
* **Data Reliance:** Uses the **Regional Health Schema**.
* *Inputs:* `coords` [Lat, Lng], `intensity` (Load %), `name`.


* **Acceptance Criteria:**
* Dashboard updates every 10 seconds.
* Alert triggers if `intensity` > 90% for more than 5 minutes (State Machine: Pending  Firing).



### **3.2 Persona: The Product Manager (User Behavior)**

**Goal:** Track feature adoption and conversion funnels during a launch.

* **User Story:** "As a PM, I want to track the 'Active Users' count and 'Cart Abandonment Rate' in real-time to decide if we need to roll back a new feature."
* **Data Reliance:** Uses the **User Activity Schema**.
* *Inputs:* `action` (Enum: `view`, `cart`, `purchase`), `user_id`, `timestamp`.


* **Acceptance Criteria:**
* Ability to filter metrics by `platform` (iOS vs. Android) using the **Metrics Schema** labels.
* Visual indication of "Normal" vs. "Abnormal" churn rates.



### **3.3 Persona: The Data Analyst (Historical Forensics)**

**Goal:** Deep-dive analysis and complex joining of datasets.

* **User Story:** "As an Analyst, I want to join last month's 'User Activity' logs with the 'User Profile' snapshot to understand which subscription tier has the highest lifetime value."
* **Data Reliance:** Uses **Apache Iceberg** tables via **Trino**.
* **Acceptance Criteria:**
* Ability to run ANSI SQL queries on data stored in MinIO.
* Access to full event fidelity (no aggregation) for forensic analysis.



### **3.4 Persona: The SRE (Alerting & Incident Response)**

**Goal:** Automated noise reduction in paging.

* **User Story:** "As an SRE, I want alerts to follow a 'State Machine' logic so that I am not woken up by transient spikes that resolve themselves in under 1 minute."
* **Data Reliance:** Uses the **Alerting State Machine**.
* *States:* `Normal`  `Pending` (Yellow)  `Firing` (Red).


* **Acceptance Criteria:**
* Alerts must support "For" duration (e.g., "Error Rate > 1% **for** 5 minutes").



---

## **4. System Architecture Details**

### **4.1 Architectural Pattern: The Hybrid Model**

EBAP utilizes a modern evolution of the **Lambda Architecture**, combining a low-latency "Speed Layer" with a high-fidelity "Batch/Serving Layer." This ensures that operational dashboards are updated in seconds while historical analysis remains accurate and cost-effective.

### **4.2 Component Breakdown**

#### **A. The Ingestion Layer (The Nervous System)**

* **Message Broker:** **Apache Kafka**
* **Role:** Acts as the central nervous system, buffering high-volume streams before processing.
* **Topics:**
* `ebap.events.raw`: Immutable logs of user actions (clicks, views).
* `ebap.metrics.telemetry`: Aggregated system health metrics.
* `ebap.cdc.users`: Change Data Capture (CDC) stream of user profile updates.




* **CDC Connector:** **Kafka Connect (Debezium)**
* **Role:** Streams changes from the transactional database (PostgreSQL) into Kafka, enabling real-time context injection (e.g., enriching a "click" with "user membership status").



#### **B. The Processing Layer (The Brain)**

* **Stream Engine:** **Spark Structured Streaming**
* **Role:** Consumes from Kafka topics to perform windowed aggregations and stateful complex event processing (CEP).
* **Logic:**
* **Watermarking:** Handles late data arrival (up to 10 minutes).
* **Joins:** Stream-Stream joins between `events.raw` and `cdc.users`.
* **State Management:** Implements the "Alerting State Machine" logic (Normal  Pending  Firing).





#### **C. The Storage Layer (The Memory)**

* **Hot Storage:** **Redis**
* **Role:** Stores the "current state" for immediate dashboarding (e.g., "Active Users Now").
* **TTL:** Keys expire after 24 hours.


* **Cold Storage (Data Lake):** **MinIO (S3 Compatible)**
* **Format:** **Apache Iceberg**
* **Role:** The permanent, immutable record of truth. Iceberg enables ACID transactions, allowing Spark to perform "Upserts" (updates) on the data lake without rewriting entire partitions.
* **Partitioning:** Data is partitioned by `Day` and `Region` for efficient querying.



#### **D. The Serving Layer (The Interface)**

* **Interactive Query Engine:** **Trino (formerly PrestoSQL)**
* **Role:** Allows Data Analysts to run standard SQL queries against the Iceberg tables in MinIO.


* **Visualization:** **Grafana**
* **Role:** The "Single Pane of Glass."
* **Dual-Source Dashboards:**
* *Real-time panels* query **Redis**.
* *Historical panels* query **Trino**.





---

## **5. Data Dictionary & Schema Design**

This section defines the strict schemas enforced by the platform to ensure enterprise-grade observability.

### **5.1 Event Streams (User Activity)**

These are immutable, high-volume logs representing granular user actions. We utilize "Flattened Event Schemas" to optimize for sub-millisecond querying.

**Topic:** `ebap.events.raw`

| Field | Type | Description |
| --- | --- | --- |
| `id` | UUID | Unique identifier for the event trace |
| `user_id` | String | Obfuscated or internal user identifier |
| `action` | Enum | Valid values: `purchase`, `view`, `cart`, `login` |
| `metadata` | Object | Contextual data (e.g., `amount`, `item_id`) |
| `location` | String | Geo-string or coordinates (e.g., "34.05,-118.25") |
| `timestamp` | DateTime | ISO-8601 formatted time of occurrence |

### **5.2 Metrics (Time-Series Telemetry)**

Aggregated system health data following the **OpenMetrics** standard for high-cardinality slicing.

**Topic:** `ebap.metrics.telemetry`

| Field | Type | Description |
| --- | --- | --- |
| `metric_name` | String | Dot-notation identifier (e.g., `system.latency.p99`, `checkout.error_rate`) |
| `labels` | Map | Key-value dimensions (e.g., `region: us-east-1`, `platform: ios`) |
| `timestamp` | Int64 | Unix timestamp in milliseconds |
| `value` | Float64 | The measured numerical value |

### **5.3 Regional Health (Spatial Topology)**

Aggregated spatial data used to visualize system load across global regions.

**Stored in:** Redis (Hash Map)

| Field | Type | Description |
| --- | --- | --- |
| `name` | String | Region identifier (e.g., "Western Europe") |
| `coords` | [Lat, Lng] | Centroid coordinates for map visualization |
| `intensity` | Integer (0-100) | Percentage of capacity utilized (System Load) |
| `sales` | Float64 | Aggregate currency volume for that region |

---

## **6. Functional Requirements**

### **6.1 Ingestion & Connectivity**

* **FR-01 (CDC Integration):** The system must use **Kafka Connect** to capture row-level changes from the User Database and stream them to the `ebap.cdc.users` topic with less than 500ms latency.
* **FR-02 (Schema Validation):** All incoming events must be validated against a central Schema Registry. Invalid events must be routed to a `dead-letter-queue` (DLQ) for manual inspection.

### **6.2 Streaming Logic (Spark Structured Streaming)**

* **FR-03 (Windowing):** The system must calculate 1-minute, 5-minute, and 1-hour tumbling windows for all "User Activity" metrics.
* **FR-04 (Stateful Alerting):** The system must implement the "Alerting State Machine" logic:
* **State 1 (Normal):** Value is within safe thresholds.
* **State 2 (Pending):** Threshold breached but duration < X minutes. Visual Indicator: Yellow.
* **State 3 (Firing):** Threshold breached for > X minutes. Visual Indicator: Red.


* **FR-05 (Late Data Handling):** A watermark of 10 minutes must be applied. Data arriving after this window is discarded from the real-time stream but logged to Cold Storage.

### **6.3 Storage & Lakehouse (Iceberg/MinIO)**

* **FR-06 (ACID Transactions):** The storage layer must support concurrent writes and reads using **Apache Iceberg**.
* **FR-07 (Partitioning):** Data stored in MinIO must be partitioned by `date(timestamp)` and `region` to optimize Trino query performance.
* **FR-08 (Compaction):** A periodic batch job must run every 6 hours to compact small data files into larger files (target size: 128MB) to maintain read performance.

### **6.4 Visualization (Grafana)**

* **FR-09 (Real-Time Dashboards):** Panels labeled "Live" must query **Redis** and refresh every 5 seconds.
* **FR-10 (Historical Dashboards):** Panels labeled "Trends" must query **Trino** and cache results for 1 hour.
* **FR-11 (Geo-Spatial Map):** A "World Map" panel must visualize the `Regional Health` schema, using circle size for `sales` and color intensity for `intensity` (load).



---

## **7. Non-Functional Requirements (NFRs)**

This chapter defines the constraints and quality attributes for the **Enterprise Behavioral Analytics Platform (EBAP)**. These requirements are strictly enforced to meet the "High Scale" standards referenced in the system design.

### **7.1 Performance & Scalability**

#### **7.1.1 Latency Budgets**

The system adheres to a strict "Time-to-Insight" budget across its two speed layers:

* **Hot Path (Real-Time):**
* **Maximum E2E Latency:** < 60 seconds (from `User Action` to `Grafana Display`).
* **P99 Latency:** < 2 seconds for Redis lookups on the "Live Cart" dashboard.


* **Cold Path (Analytical):**
* **Data Freshness:** New data must appear in Trino/Iceberg within 15 minutes of occurrence (Micro-batch interval).
* **Query Performance:** 95% of standard SQL queries on the last 30 days of data must complete in **< 3 seconds**.



#### **7.1.2 Throughput & Auto-Scaling**

* **Baseline Load:** The system must handle a steady state of **10,000 Events Per Second (EPS)** without backpressure.
* **Peak Load:** The architecture must support burst loads of **50,000 EPS** (e.g., during marketing campaigns) for up to 1 hour.
* **Scaling Strategy:**
* **Compute (Spark):** Horizontal Pod Autoscaling (HPA) triggers when CPU usage > 70%.
* **Ingestion (Kafka):** Partition count set to 50 per topic to allow parallel consumer scaling.



#### **7.1.3 Data Integrity (The "Exactly-Once" Guarantee)**

To prevent financial discrepancies (e.g., double-counting revenue), the system enforces **Exactly-Once Semantics (EOS)**:

* **Producer:** Kafka Idempotency enabled (`enable.idempotence=true`).
* **Processor:** Spark Structured Streaming uses **Checkpointing** and **Write-Ahead Logs (WAL)** to track offsets.
* **Sink:** The Redis sink must implement idempotent writes (using `SET` instead of `INCR` where possible, or unique request IDs).

---

### **7.2 Security & Compliance**

#### **7.2.1 PII Obfuscation & Data Privacy**

Per privacy regulations (GDPR/CCPA), Personally Identifiable Information (PII) must be protected:

* **User ID Hashing:** The `user_id` field in the `ebap.events.raw` topic must be hashed using **SHA-256** before entering the Cold Storage (Iceberg) layer, unless explicitly authorized for "Customer Support" roles.
* **Field-Level Encryption:** Sensitive metadata (e.g., `email`, `payment_hash`) must be encrypted at rest in MinIO using **AES-256**.

#### **7.2.2 Access Control (RBAC)**

Access to data is governed by a strict Role-Based Access Control model:

| Role | Grafana Access | Trino/Data Access |
| --- | --- | --- |
| **DevOps** | **Edit** (System Health Dashboards) | **Read-Only** (System Metrics Tables) |
| **Product Mgr** | **View** (User Behavior Dashboards) | **Deny** (Raw Data) |
| **Data Analyst** | **View** (All Dashboards) | **Read-Only** (All Iceberg Tables) |
| **Admin** | **Admin** (All) | **Admin** (All) |

#### **7.2.3 Audit Logging**

* **Requirement:** Every `SELECT` query executed in Trino must be logged to an immutable audit topic (`ebap.audit.logs`), recording the `user`, `query_text`, and `timestamp`.

---

### **7.3 Reliability & Disaster Recovery**

#### **7.3.1 Availability Targets**

* **Ingestion (Kafka):** 99.99% Availability (Multi-AZ deployment).
* **Serving (Trino/Grafana):** 99.9% Availability (business hours).

#### **7.3.2 Data Retention Policy**

* **Hot Storage (Redis):** 24 Hours (TTL).
* **Warm Storage (Kafka):** 7 Days (Retention Bytes/Time).
* **Cold Storage (MinIO/Iceberg):** 7 Years (Compliance Archival).


---

## **8. Infrastructure & Deployment**

### **8.1 Deployment Strategy**

To ensure consistency between development and production environments, EBAP utilizes containerization for all components.

* **Production:** The system is designed to be deployed on **Kubernetes (EKS, GKE, or AKS)**. It utilizes **Helm Charts** for package management to handle the complexity of distributed stateful sets (Kafka/Zookeeper) and auto-scaling stateless services (Spark Workers).
* **Local Development:** For rapid iteration, the entire platform runs as a unified stack using a container orchestration tool (like Docker Compose), allowing developers to spin up the full architecture on a single machine.

### **8.2 Component Architecture & Service Roles**

The platform is composed of the following interconnected services:

| Service | Role | Connectivity |
| --- | --- | --- |
| **Zookeeper** | **Coordination** | Manages the state and leader election for the Kafka brokers. |
| **Kafka** | **Event Backbone** | The central nervous system. All other services (Producer, Spark, Connect) must have network access to the Kafka brokers. |
| **Schema Registry** | **Governance** | Stores the versioned history of Avro schemas. Producers push schemas here; Consumers pull them to deserialize data. |
| **Kafka Connect** | **Ingestion (CDC)** | A pluggable runtime that hosts the **Debezium Postgres Connector**. It reads the Write-Ahead Log (WAL) from the User DB and writes to Kafka. |
| **PostgreSQL** | **Source System** | The transactional database hosting User Profiles. It must be configured with `logical_replication` enabled. |
| **Spark Master/Worker** | **Processing** | The compute engine. The Master distributes tasks to Workers. Workers need access to both Kafka (for streams) and MinIO (for state/storage). |
| **MinIO** | **Object Storage** | An S3-compatible object store. It acts as the Data Lake, storing Iceberg tables and Spark Checkpoints. |
| **Trino** | **Query Engine** | A distributed SQL engine. It connects to MinIO to read Iceberg metadata and data files for analytical queries. |
| **Redis** | **Hot State** | In-memory key-value store. Spark writes "Live" metrics here; Grafana reads them for real-time dashboards. |
| **Grafana** | **Visualization** | The frontend UI. It connects to **Redis** (via a Redis Datasource) and **Trino** (via a SQL Datasource). |

### **8.3 Environment Configuration**

#### **A. Network Topology**

All containers operate on a shared bridge network to allow DNS resolution by service name.

* **Kafka Listeners:** Configured with dual listeners—one for internal container traffic and one for external access (host machine).
* **Storage Access:** MinIO is configured to emulate AWS S3 regions (e.g., `us-east-1`), allowing Spark and Trino to use standard S3 client libraries.

#### **B. Storage & Connectors**

* **Iceberg Configuration:** Trino is configured with a custom catalog property file. This file directs the Iceberg connector to use MinIO as the file system backend instead of HDFS or real S3.
* **CDC Auto-Configuration:** On startup, a script submits a JSON configuration payload to the Kafka Connect REST API. This payload initializes the Debezium connector, defining which Postgres tables (e.g., `users`) to monitor.

### **8.4 Access & Interfaces**

Once the infrastructure is running, the following interfaces are exposed for management and observability:

1. **Grafana Dashboard:** The primary interface for end-users to view Real-Time and Historical data.
2. **MinIO Console:** A web-based file explorer to inspect raw Parquet files and Iceberg metadata in the Data Lake.
3. **Spark Master UI:** A dashboard to monitor active streaming jobs, processing rates, and executor memory usage.
4. **Trino CLI / UI:** A SQL interface for Data Analysts to run ad-hoc queries against the lakehouse.