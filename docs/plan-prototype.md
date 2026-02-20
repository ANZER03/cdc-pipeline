### **Phase 1: Infrastructure Foundations (The "Plumbing")**

**Goal:** Spin up the entire containerized stack and ensure services can talk to each other.

1. **Environment Setup:**
* Create the project directory structure (standard Data Engineering layout: `/infrastructure`, `/src`, `/config`, `/notebooks`).
* Finalize the `docker-compose.yaml` (from Chapter 8) to include network bridges and volume mounts for persistence.


2. **Service Health Checks:**
* **Kafka:** Verify broker availability and create the required topics (`ebap.events.raw`, `ebap.metrics.telemetry`) to ensure the cluster is ready.
* **MinIO:** Initialize the "Bronze" and "Silver" buckets and generate Access/Secret keys.
* **Postgres:** Configure `postgresql.conf` to set `wal_level=logical` (Critical for Debezium CDC).



### **Phase 2: Ingestion & Data Generation (The "Input")**

**Goal:** Establish a continuous flow of synthetic but realistic data into Kafka.

1. **CDC Pipeline (Database Changes):**
* **Seed Script:** Write a Python script to populate the Postgres `users` table with initial mock data.
* **Connector Config:** POST the Debezium configuration to Kafka Connect to start streaming `users` table changes to the `ebap.cdc.users` topic.


2. **Event Simulation (The "Clickstream"):**
* **Generator:** Develop a Python producer using the `Faker` library to generate high-volume JSON events.
* **Logic:** Implement the "Markov Chain" logic mentioned in the `README.md` to simulate realistic user journeys (e.g., `View` -> `Cart` -> `Purchase`) rather than random noise.
* **Throughput:** specific parameter to control "Events Per Second" (EPS) to test backpressure.



### **Phase 3: Stream Processing Logic (The "Brain")**

**Goal:** Build the Spark Structured Streaming job that processes raw data into insights.

1. **Stream Initialization:**
* Define the read stream from Kafka for both `ebap.events.raw` and `ebap.cdc.users`.
* Define the **Schema Enforcement** using PySpark structs to match the PRD schemas (Events & Metrics).


2. **Enrichment (Stream-Stream Join):**
* Implement the join logic: Join "Clicks" with "User CDC" on `user_id`.
* *Engineering Constraint:* Handle "Late Data" using Watermarking (10-minute threshold) to prevent state explosion.


3. **Aggregation (Windowing):**
* Compute "Active Users" using **Tumbling Windows** (1 minute).
* Compute "Regional Health" aggregations.


4. **Sinks (Dual-Write Strategy):**
* **Hot Path:** Write aggregated metrics to **Redis** using `foreachBatch` (Key = `metric:timestamp`, Value = Count).
* **Cold Path:** Write raw enriched events to **MinIO** in **Iceberg** format (Partitioned by `Day/Region`).



### **Phase 4: The Lakehouse & Serving Layer (The "Memory")**

**Goal:** Make the data queryable via SQL without using Spark.

1. **Trino Configuration:**
* Configure the `iceberg.properties` catalog to point to MinIO.
* Register the schemas in the Trino metastore so it recognizes the tables created by Spark.


2. **Data Validation:**
* Run test SQL queries (`SELECT count(*) FROM ebap.events`) to verify data is persisting and partitions are being recognized.



### **Phase 5: Visualization & Monitoring (The "Face")**

**Goal:** Build the Operational and Analytical dashboards.

1. **Microservices & SSE Setup:**
* **Redis Streamer:** Build a microservice to push real-time metrics via SSE.
* **API Gateway:** Expose endpoints querying historical data via Trino.


2. **Web/Mobile App Dashboard Creation:**
* **Real-Time View:** Consume SSE to build live "Speedometers" for EPS and "Geomaps" for Regional Health.
* **Historical View:** Consume APIs to build line charts showing "Daily Active Users" trends.