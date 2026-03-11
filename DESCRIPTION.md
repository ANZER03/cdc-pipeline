# Nexus Dashboard -- Full Application Description

> **Purpose of this document**: Serve as the single source of truth for the Nexus Dashboard application -- what it displays, what data it consumes, and the exact schemas/contracts produced by the upstream data pipeline (PostgreSQL > Debezium CDC > Kafka > Schema Registry > Spark Streaming > Redis).

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Overview](#2-architecture-overview)
3. [Dashboard Tabs & Features](#3-dashboard-tabs--features)
4. [Data Schemas](#4-data-schemas)
5. [Target Data Contracts (Pipeline Output)](#5-target-data-contracts-pipeline-output)
6. [PostgreSQL Source Tables](#6-postgresql-source-tables)
7. [Kafka Topics & Schema Registry](#7-kafka-topics--schema-registry)
8. [Spark Streaming Jobs](#8-spark-streaming-jobs)
9. [Redis Data Model](#9-redis-data-model)
10. [End-to-End Data Flow Mapping](#10-end-to-end-data-flow-mapping)

---

## 1. Project Overview

### What Is Nexus Dashboard

Nexus Dashboard is a real-time e-commerce operations monitoring application. It provides a unified view of:

- **Live business KPIs** -- active users, revenue, orders, error rates, latency
- **Traffic throughput** -- time-series chart of request volume
- **Geographic distribution** -- interactive 3D globe showing regional sales, node intensity, and live data flows between regions
- **User behavior stream** -- real-time feed of user actions (purchases, cart additions, page views, logins)
- **Platform analytics** -- device/OS breakdown of traffic
- **Infrastructure health** -- CPU, memory, API cluster status
- **Alerting** -- rule-based threshold monitoring with severity levels and notification channels

### Tech Stack

| Layer | Technology |
|-------|-----------|
| UI Framework | React 19 + TypeScript |
| Build Tool | Vite |
| Styling | Tailwind CSS (CDN) |
| Charts | Recharts 3 (AreaChart, PieChart) |
| Globe/Map | D3.js 7 (orthographic projection, GeoJSON) |
| Icons | Lucide React |
| Package Delivery | ESM via import maps (esm.sh CDN) |

### Implemented Architecture

The Nexus Dashboard is fully connected to a live CDC pipeline. All data displayed in the UI originates from real pipeline computations — no simulation, no hardcoded values, no in-browser data generation.

| Aspect | Implementation |
|--------|---------------|
| Data source | PostgreSQL transactional DB + event log |
| Data transport | Debezium CDC > Kafka > Spark Streaming > Redis |
| Dashboard reads from | FastAPI backend (WebSocket push + REST snapshots) backed by Redis |
| Freshness | 30-second Spark micro-batch windows, pushed immediately via WebSocket |
| Alert evaluation | Spark evaluates thresholds, writes results to Redis, WebSocket pushes to frontend |

---

## 2. Architecture Overview

### Current Architecture

```
+------------------+     +----------+     +------------------+     +-----------------+
|   PostgreSQL     |---->| Debezium |---->|      Kafka       |---->| Spark Streaming |
|                  |     |   CDC    |     | (Schema Registry)|     |                 |
| - orders         |     +----------+     |                  |     | - Aggregations  |
| - cart_items     |                      | CDC Topics:      |     | - Windowed KPIs |
| - users          |                      | - pg.public.*    |     | - Geo rollups   |
| - products       |                      |                  |     | - Alert eval    |
| - user_events    |                      | Direct Topics:   |     |                 |
| - sessions       |                      | - raw.request_log|     +--------+--------+
+------------------+                      | - raw.system_    |              |
                                          |   metrics        |              v
                                          +------------------+     +------------------+
                                                                   |      Redis       |
                                                                   |                  |
                                                                   | - KPI hashes     |
                                                                   | - Traffic TS     |
                                                                   | - Activity lists |
                                                                   | - Region hashes  |
                                                                   | - Alert states   |
                                                                   | - Health metrics |
                                                                   +--------+---------+
                                                                            |
                                                                            v
                                                                   +------------------+
                                                                   |  Dashboard API   |
                                                                   | (FastAPI + WS)   |
                                                                   |                  |
                                                                   | - Subscribes to  |
                                                                   |   Redis pub/sub  |
                                                                   | - Fans out WS    |
                                                                   |   to all clients |
                                                                   | - REST snapshots |
                                                                   |   for initial    |
                                                                   |   page load      |
                                                                   +--------+---------+
                                                                            |
                                                                            v
                                                                   +------------------+
                                                                   | Nexus Dashboard  |
                                                                   | (React Frontend) |
                                                                   |                  |
                                                                   | WebSocket client |
                                                                   | ws://localhost:  |
                                                                   | 8000/ws          |
                                                                   +------------------+
```

### Data Flow Summary

1. **PostgreSQL** stores transactional data (orders, carts, users, products) and a behavioral event log (page views, clicks, logins, searches)
2. **Debezium CDC** captures row-level changes from PostgreSQL WAL and publishes them to Kafka topics
3. **Kafka + Schema Registry** transports events with enforced Avro schemas
4. **Spark Streaming** consumes Kafka topics in micro-batch windows (10-30s), computes aggregations (KPIs, regional rollups, traffic time-series, alert evaluations), and writes results to Redis
5. **Redis** serves as the low-latency read layer for the dashboard
6. **Dashboard API** (FastAPI + aioredis) subscribes to Redis Pub/Sub channels and fans out updates to React clients via **WebSocket** (`ws://localhost:8000/ws`). It also exposes REST snapshot endpoints for initial page load.
7. **React Dashboard** connects to the WebSocket on mount via `NexusWsClient` (`services/wsClient.ts`). On connect, the API sends a full snapshot of all 9 data types immediately. Subsequent incremental updates are pushed as Redis pub/sub fires. All state is managed in `hooks/useNexusData.tsx` via the `NexusDataProvider` context -- no simulation, no in-browser computation.

---

## 3. Dashboard Tabs & Features

The application has 4 navigation tabs plus 2 decorative sidebar items.

### 3.1 Dashboard Tab (Overview)

The primary operational view. Contains 5 sections:

#### Section A: KPI Cards (Top Row)

5 key performance indicators displayed in a responsive grid.

| # | Label | Icon | Example Value | Unit | Trend | Description |
|---|-------|------|---------------|------|-------|-------------|
| 1 | Live Visitors | Users | 14,502 | -- | +5.2% | Currently active users on the platform |
| 2 | Revenue | DollarSign | $42.5k | -- | +12.5% | Cumulative revenue (formatted as `$Xk`) |
| 3 | Orders | ShoppingCart | 842 | -- | -2.1% | Total order count |
| 4 | Errors | AlertTriangle | 0.04% | -- | +0.5% | Error rate percentage |
| 5 | Latency | Clock | 124 | ms | -1.2% | Average API response latency in milliseconds |

Each KPI card shows:
- The metric label (uppercase, small)
- The current value (large, color-coded)
- An optional unit suffix
- A trend indicator: up arrow (green) or down arrow (red) with percentage and "vs last hour"

Trend values are computed as hour-over-hour deltas from the pipeline (`*Trend` fields in `nexus:kpi:current`).

#### Section B: Traffic Throughput (AreaChart)

- **Type**: Recharts AreaChart (single series, monotone interpolation)
- **Data**: Rolling window of 21 time-series data points
- **X-axis**: Timestamp labels (HH:MM:SS format)
- **Y-axis**: Request throughput value (numeric, auto-scaled)
- **Visual**: Indigo (#5e5ce6) stroke with gradient fill, dashed grid lines
- **Update frequency**: Every Spark micro-batch window (30s)

#### Section C: Regional Distribution (3D Globe)

- **Type**: D3.js orthographic projection globe
- **Data**: 9 geographic regions with sales and intensity metrics
- **Features**:
  - Country landmass rendering (GeoJSON from GitHub)
  - Green hotspot circles at region coordinates (size proportional to sales)
  - Orange animated arc lines between regions (data flows)
  - Drag-to-rotate interaction
  - Hover tooltips showing region name, sales, intensity
  - HUD overlay with rotation coordinates and legend

#### Section D: Real-time Events (Activity Feed)

- **Type**: Scrollable list, max 10 items
- **Per event**: User name, action type, location, amount (for purchases), timestamp
- **Action types**: `purchase`, `view`, `cart`, `login`
- **Color coding**: Green dot = purchase, Yellow dot = cart, Blue dot = view/login
- **Update frequency**: Pushed via WebSocket as events arrive from Redis pub/sub

#### Section E: Device Platform (PieChart)

- **Type**: Recharts donut PieChart
- **Data**: 4 segments -- Desktop, Mobile, iOS, Android
- **Source**: `nexus:platform:breakdown` Redis key, computed by the `nexus-derived` Spark job from `pg.public.sessions`.

#### Section F: Health Check

- **Type**: 3 horizontal progress bars
- **Metrics**: CPU Utilization, Memory Load, API Cluster status
- **Source**: `nexus:health:current` Redis key, computed by the `nexus-infrastructure` Spark job from `raw.system_metrics`.

### 3.2 Geo Monitor Tab

A full-screen command center view with 3 panels:

#### Left Panel: Node Monitoring
- Lists all 9 geographic regions as cards
- Per card: region name, sales ($), intensity (%), progress bar
- Sortable by sales (descending), filterable by search query
- Cards are selectable (blue highlight)

#### Center Panel: 3D Globe
- Same `WorldMap` component as Dashboard tab
- Larger viewport, scanline visual effect overlay
- Drag-to-rotate, hotspot tooltips, animated data flow arcs

#### Right Panel: Stream Log
- Real-time feed of user activity events (up to 15)
- Per entry: location, timestamp, user, action type
- Timeline-style layout with left border markers

#### Header Bar
- Uptime: sourced from `nexus:geo:header` (`uptime` field)
- Global Load: sourced from `nexus:geo:header` (`globalLoad` field)
- Engine Version: V4-Orbit (static label)
- Protocol Status: Secure (static label)

### 3.3 Alerting Tab

Alert rule management and monitoring view.

#### Summary Cards (Top Row)
| Card | Description |
|------|-------------|
| Critical Failures | Count of alerts in `firing` state with `critical` severity |
| Warnings | Count of alerts in `pending` or `firing` state with `warning` severity |
| Healthy Rules | Count of alerts in `ok` state |

#### Rules Table
Each row displays an alert rule with:
- Severity indicator (colored dot: red/yellow/blue)
- Rule name and folder
- Current state (Firing / Pending / Normal)
- Metric being evaluated (e.g., `system.latency.p99`)
- Current value vs. threshold
- Last evaluation time and frequency

#### Contact Points
Notification channels:
- Slack: #ops-alerts (active)
- Email: SRE Team (active)
- PagerDuty: Primary (inactive)

### 3.4 Explore Tab

Placeholder for future advanced analytics / ad-hoc query builder. Currently shows a loading state with "Data Explorer / Tableau Style" message.

---

## 4. Data Schemas

All data is consumed from the live pipeline. This section documents every schema and value shape used by the dashboard.

### 4.1 TypeScript Interfaces

#### `DataPoint` (Traffic Throughput)

```typescript
interface DataPoint {
  timestamp: number;   // Unix epoch milliseconds
  value: number;       // Traffic throughput value (requests per window)
  label: string;       // Human-readable time in 12-hour format: "HH:MM:SS AM/PM" e.g. "02:15:30 PM"
}
```

#### `Activity` (User Behavior Event)

```typescript
interface Activity {
  id: string;                                      // Unique event ID (9-char alphanumeric)
  user: string;                                    // User display name
  action: 'purchase' | 'view' | 'cart' | 'login'; // Event type
  amount?: number;                                 // Dollar amount (only for purchases, $20-$519)
  timestamp: Date;                                 // When the event occurred
  location: string;                                // "City, CountryCode" format
}
```

#### `Metrics` (Dashboard KPIs)

```typescript
interface Metrics {
  activeUsers: number;  // Live visitor count
  revenue: number;      // Cumulative revenue in dollars
  orders: number;       // Cumulative order count
  errorRate: number;    // Error percentage (e.g., 0.04 means 0.04%)
  latency: number;      // Average latency in milliseconds
}
```

#### `RegionMetric` (Geographic Region)

```typescript
interface RegionMetric {
  name: string;              // Region display name
  coords: [number, number];  // [Longitude, Latitude]
  intensity: number;          // Activity intensity 0-100%
  sales: number;              // Regional sales in dollars
}
```

#### `DataFlow` (Inter-Region Data Arc)

```typescript
interface DataFlow {
  id: string;                    // Unique flow ID
  source: [number, number];      // [Longitude, Latitude] of origin
  target: [number, number];      // [Longitude, Latitude] of destination
  value: number;                 // Flow magnitude 0-100
}
```

#### `AlertRule` (Alert Configuration)

```typescript
type AlertStatus = 'firing' | 'pending' | 'ok';
type AlertSeverity = 'critical' | 'warning' | 'info';

interface AlertRule {
  id: string;               // Unique rule ID
  name: string;             // Human-readable rule name
  status: AlertStatus;      // Current evaluation state
  severity: AlertSeverity;  // Severity level
  metric: string;           // Metric path (e.g., "system.latency.p99")
  currentValue: number;     // Current measured value
  threshold: number;        // Threshold that triggers alert
  lastEvaluated: Date;      // Last evaluation timestamp
  frequency: string;        // Evaluation interval (e.g., "1m", "30s", "5m")
}
```

### 4.2 Region Definitions

The 9 geographic regions that represent global e-commerce nodes. Coordinates are fixed; `intensity` and `sales` are computed by the `nexus-transactions` Spark job each window:

| # | Name | Longitude | Latitude |
|---|------|-----------|----------|
| 1 | North America (East) | -74 | 40 |
| 2 | North America (West) | -122 | 37 |
| 3 | Western Europe | 2 | 48 |
| 4 | Japan | 139 | 35 |
| 5 | Southeast Asia | 103 | 1 |
| 6 | Australia | 151 | -33 |
| 7 | Brazil | -46 | -23 |
| 8 | India | 77 | 28 |
| 9 | South Africa | 18 | -33 |

### 4.3 Activity Event Types

| `user_events.event_type` | Dashboard `action` | Notes |
|---|---|---|
| `checkout_complete` | `purchase` | Amount from enriched order field |
| `page_view` | `view` | -- |
| `add_to_cart` | `cart` | -- |
| `login` | `login` | -- |

### 4.4 Alert Rules

Alert rules are evaluated by the `nexus-transactions` Spark job and stored in `nexus:alert:rules`. The current rules evaluate latency, error rate, and CPU thresholds.

### 4.5 Update Frequencies (Live Pipeline)

| Data type | Spark trigger | WebSocket push frequency |
|---|---|---|
| KPI metrics | 30s | ~Every 30s |
| Traffic chart | 30s (tumbling) | ~Every 30s (one new point) |
| Activity feed | Per event | As events arrive |
| Regions / flows | 30s | ~Every 30s |
| Platform breakdown | 30s | ~Every 30s |
| Health check | 30s | ~Every 30s |
| Alerts | On state change | Infrequent |

---

## 5. Data Contracts (Pipeline Output)

This section defines the exact data shapes the pipeline produces and writes to Redis for each dashboard component.

### 5.1 KPI Metrics Contract

The dashboard needs a single object with 5 numeric KPIs plus their hour-over-hour trend percentages.

```json
{
  "activeUsers": 14502,
  "activeUsersTrend": 5.2,
  "revenue": 42500,
  "revenueTrend": 12.5,
  "orders": 842,
  "ordersTrend": -2.1,
  "errorRate": 0.04,
  "errorRateTrend": 0.5,
  "latency": 124,
  "latencyTrend": -1.2,
  "updatedAt": 1709654400000
}
```

| Field | Type | Unit | Computation |
|-------|------|------|-------------|
| `activeUsers` | integer | count | Distinct active sessions in last 5 minutes |
| `activeUsersTrend` | float | % | `((current - oneHourAgo) / oneHourAgo) * 100` |
| `revenue` | float | USD | SUM of order totals in current period (cumulative today or rolling window) |
| `revenueTrend` | float | % | Hour-over-hour delta percentage |
| `orders` | integer | count | COUNT of completed orders in current period |
| `ordersTrend` | float | % | Hour-over-hour delta percentage |
| `errorRate` | float | % | `(error_count / total_requests) * 100` in last window |
| `errorRateTrend` | float | % | Hour-over-hour delta percentage |
| `latency` | integer | ms | P50 or average request latency in last window |
| `latencyTrend` | float | % | Hour-over-hour delta percentage |
| `updatedAt` | long | epoch ms | Timestamp of last computation |

### 5.2 Traffic Throughput Contract

Rolling window of time-series points. The dashboard maintains a sliding window of 21 points.

```json
[
  {
    "timestamp": 1709654400000,
    "value": 1247,
    "label": "02:15:30 PM"
  },
  ...
]
```

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | long (epoch ms) | Window end timestamp |
| `value` | integer | Request count in that window |
| `label` | string | Human-readable time in 12-hour format: `"HH:MM:SS AM/PM"` e.g. `"02:15:30 PM"` |

**Production**: Each Spark micro-batch (10-30s) appends one data point. The dashboard keeps the latest 21. Alternatively, Redis stores a capped list of the latest 21 points.

### 5.3 Activity Events Contract

Real-time feed of user behavior events. The dashboard displays the latest 10 (Dashboard tab) or 15 (Geo Monitor tab).

```json
{
  "id": "evt_abc123def",
  "user": "Alex",
  "action": "purchase",
  "amount": 149.99,
  "timestamp": "2026-03-05T14:15:30.000Z",
  "location": "New York, US"
}
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | string | Unique | Event identifier (UUID or similar) |
| `user` | string | Required | User display name or username |
| `action` | enum string | `purchase`, `view`, `cart`, `login` | Type of user behavior |
| `amount` | float or null | Present only for `purchase` | Transaction amount in USD |
| `timestamp` | ISO 8601 string | Required | When the event occurred |
| `location` | string | `"City, CC"` format | User's geographic location |

**Production**: Spark enriches raw CDC events (from `user_events` + `orders` + `cart_items`) with user display name and geolocation, publishes to Redis as a capped list.

### 5.4 Region Metrics Contract

Array of 9 geographic regions with aggregated metrics.

```json
[
  {
    "name": "North America (East)",
    "coords": [-74, 40],
    "intensity": 85.3,
    "sales": 12400
  },
  ...
]
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Region display name (must match one of the 9 defined regions) |
| `coords` | [float, float] | `[Longitude, Latitude]` -- fixed per region |
| `intensity` | float (0-100) | Normalized activity level (based on request volume, session count, or order volume relative to region capacity) |
| `sales` | float | Total sales amount in USD for the current window |

**The 9 regions and their coordinates are fixed** (see Section 4.2). The pipeline computes `intensity` and `sales` by mapping user/order locations to the nearest region.

### 5.5 Data Flows Contract

Array of active inter-region data transfer arcs (max 5).

```json
[
  {
    "id": "flow_xyz789",
    "source": [-74, 40],
    "target": [2, 48],
    "value": 72.5
  },
  ...
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique flow identifier |
| `source` | [float, float] | `[Lon, Lat]` of origin region |
| `target` | [float, float] | `[Lon, Lat]` of destination region |
| `value` | float (0-100) | Flow magnitude (normalized volume of cross-region transactions/requests) |

**Production**: Spark computes cross-region order flows (e.g., user in Region A buying from merchant in Region B) and writes the top 5 most active flows.

### 5.6 Alert Rules Contract

Array of alert rule evaluations.

```json
[
  {
    "id": "alert_1",
    "name": "High Latency p99 > 200ms",
    "status": "firing",
    "severity": "critical",
    "metric": "system.latency.p99",
    "currentValue": 245,
    "threshold": 200,
    "lastEvaluated": "2026-03-05T14:15:30.000Z",
    "frequency": "1m"
  },
  ...
]
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | string | Unique | Rule identifier |
| `name` | string | Required | Human-readable rule description |
| `status` | enum string | `firing`, `pending`, `ok` | Current evaluation state |
| `severity` | enum string | `critical`, `warning`, `info` | Severity level |
| `metric` | string | Required | Metric path being evaluated |
| `currentValue` | float | Required | Latest measured value |
| `threshold` | float | Required | Threshold that triggers the alert |
| `lastEvaluated` | ISO 8601 | Required | When rule was last evaluated |
| `frequency` | string | e.g., `"30s"`, `"1m"`, `"5m"` | Evaluation interval |

**Production**: Spark evaluates metric thresholds at the specified frequency and writes the latest state to Redis.

### 5.7 Alert Summary Contract

Aggregated counts for the summary cards.

```json
{
  "criticalCount": 1,
  "warningCount": 1,
  "healthyCount": 3,
  "criticalImpact": "Currently affecting 15% of users",
  "updatedAt": 1709654400000
}
```

**Production**: Derived from the alert rules array. Spark (or the API layer) aggregates counts by status and severity.

### 5.8 Device Platform Contract

Breakdown of traffic by device/platform.

```json
[
  { "name": "Desktop", "value": 4500 },
  { "name": "Mobile",  "value": 3200 },
  { "name": "iOS",     "value": 2800 },
  { "name": "Android", "value": 2100 }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Platform name (Desktop, Mobile, iOS, Android) |
| `value` | integer | Active session count or request count for this platform in current window |

**Production**: Spark groups sessions or requests by user-agent parsed platform and counts per group.

### 5.9 Health Check Contract

Infrastructure health metrics.

```json
{
  "cpu": 22.4,
  "memory": 58.0,
  "apiClusterStatus": "HEALTHY",
  "apiClusterScore": 95,
  "updatedAt": 1709654400000
}
```

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `cpu` | float | % | Average CPU utilization across cluster |
| `memory` | float | % | Average memory utilization across cluster |
| `apiClusterStatus` | enum string | -- | `HEALTHY`, `DEGRADED`, or `DOWN` |
| `apiClusterScore` | float | % | Percentage of healthy API nodes |
| `updatedAt` | long | epoch ms | Last update timestamp |

**Production**: This is infrastructure data, typically from Prometheus/node-exporter metrics pushed through the pipeline or read from a monitoring sidecar. If routing through Spark, ingest from a `system_metrics` Kafka topic.

### 5.10 Geo Monitor Header Contract

System-level metrics for the Geo Monitor header bar.

```json
{
  "uptime": 99.999,
  "globalLoad": "4.2 PB/S",
  "globalLoadBytes": 4200000000000000,
  "engineVersion": "V4-Orbit",
  "protocolStatus": "Secure",
  "updatedAt": 1709654400000
}
```

**Production**: Uptime from health check aggregation, global load from bandwidth or request volume aggregation.

---

## 6. PostgreSQL Source Tables

The pipeline ingests from two categories of PostgreSQL tables: **transactional** (core business data) and **behavioral** (user event/clickstream log).

### 6.1 Transactional Tables

#### `users`

```sql
CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(100) NOT NULL,
    display_name    VARCHAR(200) NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    country_code    CHAR(2),            -- ISO 3166-1 alpha-2
    city            VARCHAR(100),
    region_name     VARCHAR(100),        -- Maps to one of the 9 dashboard regions
    platform        VARCHAR(50),         -- last known: Desktop, Mobile, iOS, Android
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

#### `products`

```sql
CREATE TABLE products (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(500) NOT NULL,
    category        VARCHAR(100),
    price           DECIMAL(10, 2) NOT NULL,
    merchant_region VARCHAR(100),        -- Merchant's region (for cross-region flow)
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

#### `orders`

```sql
CREATE TABLE orders (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id),
    total_amount    DECIMAL(10, 2) NOT NULL,
    currency        CHAR(3) DEFAULT 'USD',
    status          VARCHAR(20) NOT NULL,    -- pending, completed, failed, refunded
    region_name     VARCHAR(100),            -- Derived from user location
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

#### `order_items`

```sql
CREATE TABLE order_items (
    id              BIGSERIAL PRIMARY KEY,
    order_id        BIGINT REFERENCES orders(id),
    product_id      BIGINT REFERENCES products(id),
    quantity        INTEGER NOT NULL DEFAULT 1,
    unit_price      DECIMAL(10, 2) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

#### `cart_items`

```sql
CREATE TABLE cart_items (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id),
    product_id      BIGINT REFERENCES products(id),
    quantity        INTEGER NOT NULL DEFAULT 1,
    added_at        TIMESTAMPTZ DEFAULT NOW(),
    removed_at      TIMESTAMPTZ
);
```

### 6.2 Behavioral / Event Log Tables

#### `user_events`

This is the primary clickstream/behavior table. Each row is a user action.

```sql
CREATE TABLE user_events (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id),
    event_type      VARCHAR(50) NOT NULL,    -- page_view, login, logout, search, click, add_to_cart, checkout_start, checkout_complete, error
    page_url        TEXT,
    referrer_url    TEXT,
    user_agent      TEXT,                    -- For device/platform parsing
    ip_address      INET,
    session_id      UUID,
    metadata        JSONB,                   -- Flexible event-specific data
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**Event type mapping to dashboard `Activity.action`**:

| `user_events.event_type` | Dashboard `action` | Notes |
|---------------------------|-------------------|-------|
| `checkout_complete` | `purchase` | Join with `orders` to get amount |
| `page_view` | `view` | -- |
| `add_to_cart` | `cart` | -- |
| `login` | `login` | -- |

#### `sessions`

```sql
CREATE TABLE sessions (
    id              UUID PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id),
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ,
    platform        VARCHAR(50),             -- Desktop, Mobile, iOS, Android
    country_code    CHAR(2),
    city            VARCHAR(100),
    region_name     VARCHAR(100),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### 6.3 Infrastructure / System Tables

> **Architecture Note**: High-volume operational data (request logs, system metrics) is typically **not** written to PostgreSQL first. Routing it through Debezium CDC adds unnecessary write amplification: every row written to Postgres triggers a WAL entry, a Debezium event, and a Kafka message — three hops before Spark even sees it. The preferred approach for each is described below. The PostgreSQL table DDLs are provided as a fallback if a direct Kafka approach is not feasible.

#### `system_metrics` — Preferred: Direct Prometheus → Kafka

Infrastructure metrics (CPU, memory) are standard Prometheus/node-exporter data. The recommended production approach:

1. **Prometheus** scrapes node-exporter and application metrics
2. A **Kafka exporter or custom bridge** writes Prometheus scrape results directly to a `raw.system_metrics` Kafka topic
3. Spark consumes `raw.system_metrics` directly — no PostgreSQL involved

If routing through PostgreSQL is required (e.g., for compliance auditing), use the table below:

```sql
CREATE TABLE system_metrics (
    id              BIGSERIAL PRIMARY KEY,
    node_name       VARCHAR(100) NOT NULL,
    metric_name     VARCHAR(100) NOT NULL,   -- cpu_percent, memory_percent, request_latency_ms, error_count, request_count
    metric_value    DOUBLE PRECISION NOT NULL,
    recorded_at     TIMESTAMPTZ DEFAULT NOW()
);
```

Debezium topic: `pg.public.system_metrics` (only if PostgreSQL path is used)

#### `request_log` — Preferred: Application → Kafka Direct

Request-level data (latency, error rates, traffic volume) is extremely high volume — potentially millions of rows per hour. Writing this to PostgreSQL first:
- Creates heavy WAL pressure on the primary
- Introduces latency (DB write → WAL → Debezium → Kafka is 100-500ms overhead)
- Risks Debezium lag if the table write rate exceeds connector throughput

**Recommended**: The application (API gateway or backend service) writes request events **directly to a `raw.request_log` Kafka topic** using a Kafka producer. Spark consumes from this topic directly.

If routing through PostgreSQL is required, use the table below. In that case, use `INSERT ... ON CONFLICT DO NOTHING` and partition by day to manage table growth:

```sql
CREATE TABLE request_log (
    id              BIGSERIAL PRIMARY KEY,
    endpoint        VARCHAR(500),
    method          VARCHAR(10),
    status_code     INTEGER,
    latency_ms      INTEGER,
    user_id         BIGINT,
    session_id      UUID,
    region_name     VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT NOW()
) PARTITION BY RANGE (created_at);
```

Debezium topic: `pg.public.request_log` (only if PostgreSQL path is used)

### 6.4 Region Mapping Reference

> **Schema Problem Fixed**: The dashboard splits the US into two regions (North America East and North America West). A simple `country_code CHAR(2) PRIMARY KEY` table cannot handle this — `US` cannot map to two regions. The schema below uses a two-level lookup: a `city_region_mapping` table for precise city-level overrides (handling the US split), falling back to a `country_region_mapping` table for all other countries.

#### `country_region_mapping` (fallback — one entry per country)

```sql
CREATE TABLE country_region_mapping (
    country_code    CHAR(2) NOT NULL,
    region_name     VARCHAR(100) NOT NULL,   -- Must match one of the 9 dashboard region names
    longitude       DOUBLE PRECISION NOT NULL,
    latitude        DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (country_code)
);
```

Example rows:

| country_code | region_name | longitude | latitude |
|-------------|-------------|-----------|----------|
| GB | Western Europe | 2 | 48 |
| FR | Western Europe | 2 | 48 |
| DE | Western Europe | 2 | 48 |
| JP | Japan | 139 | 35 |
| SG | Southeast Asia | 103 | 1 |
| AU | Australia | 151 | -33 |
| BR | Brazil | -46 | -23 |
| IN | India | 77 | 28 |
| ZA | South Africa | 18 | -33 |

#### `city_region_mapping` (override — for countries with multiple dashboard regions)

```sql
CREATE TABLE city_region_mapping (
    id              BIGSERIAL PRIMARY KEY,
    country_code    CHAR(2) NOT NULL,
    city_pattern    VARCHAR(200) NOT NULL,   -- Exact city name or prefix pattern
    region_name     VARCHAR(100) NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    latitude        DOUBLE PRECISION NOT NULL
);

CREATE INDEX idx_city_region_country ON city_region_mapping(country_code);
```

Example rows for US East/West split:

| country_code | city_pattern | region_name | longitude | latitude |
|-------------|--------------|-------------|-----------|----------|
| US | New York | North America (East) | -74 | 40 |
| US | Boston | North America (East) | -74 | 40 |
| US | Washington | North America (East) | -74 | 40 |
| US | Atlanta | North America (East) | -74 | 40 |
| US | Chicago | North America (East) | -74 | 40 |
| US | Miami | North America (East) | -74 | 40 |
| US | Los Angeles | North America (West) | -122 | 37 |
| US | San Francisco | North America (West) | -122 | 37 |
| US | Seattle | North America (West) | -122 | 37 |
| US | Portland | North America (West) | -122 | 37 |
| US | Denver | North America (West) | -122 | 37 |
| US | Phoenix | North America (West) | -122 | 37 |
| CA | Toronto | North America (East) | -74 | 40 |
| CA | Vancouver | North America (West) | -122 | 37 |

**Lookup logic** (in Spark — broadcast join recommended):

```python
# Step 1: Try city-level override
result = user_df.join(
    broadcast(city_region_df),
    (user_df.country_code == city_region_df.country_code) &
    (user_df.city == city_region_df.city_pattern),
    how="left"
)

# Step 2: Fall back to country-level mapping for nulls
result = result.join(
    broadcast(country_region_df),
    result.country_code == country_region_df.country_code,
    how="left"
).withColumn(
    "region_name",
    coalesce(col("city_region.region_name"), col("country_region.region_name"), lit("Unknown"))
)
```

Both tables are static reference data. Load them as broadcast variables at Spark job startup — do not re-read from the database on every micro-batch.

---

## 7. Kafka Topics & Schema Registry

### 7.1 CDC Raw Topics (Debezium Output)

Debezium captures row-level changes from PostgreSQL. Each source table gets its own Kafka topic.

| Source Table | Kafka Topic | Key | Partitions | Description |
|-------------|-------------|-----|------------|-------------|
| `users` | `pg.public.users` | `id` | 6 | User profile changes |
| `orders` | `pg.public.orders` | `id` | 12 | Order lifecycle events (created, updated, completed, failed) |
| `order_items` | `pg.public.order_items` | `order_id` | 12 | Order line items |
| `cart_items` | `pg.public.cart_items` | `user_id` | 6 | Cart additions/removals |
| `user_events` | `pg.public.user_events` | `user_id` | 12 | All user behavior events (highest volume) |
| `sessions` | `pg.public.sessions` | `user_id` | 6 | Session lifecycle |
| `products` | `pg.public.products` | `id` | 3 | Product catalog changes (low volume) |
| `request_log` | `pg.public.request_log` \| `raw.request_log`* | `region_name` | 12 | API request log (high volume) |
| `system_metrics` | `pg.public.system_metrics` \| `raw.system_metrics`* | `node_name` | 6 | Infrastructure metrics |

> \* `request_log` and `system_metrics`: prefer direct application → Kafka ingestion to avoid PostgreSQL write amplification (see Section 6.3). If using the direct Kafka path, the topic name is `raw.request_log` / `raw.system_metrics` and Debezium is not involved. Spark job topic references must be updated accordingly.

**Debezium connector config key points**:
- `slot.name`: `nexus_cdc_slot`
- `publication.name`: `nexus_cdc_pub`
- `plugin.name`: `pgoutput`
- `transforms`: `unwrap` (use `io.debezium.transforms.ExtractNewRecordState`) to flatten the envelope
- `key.converter`: `io.confluent.connect.avro.AvroConverter`
- `value.converter`: `io.confluent.connect.avro.AvroConverter`

### 7.2 Avro Schemas (Schema Registry)

#### Schema: `UserEvent` (for `pg.public.user_events`)

```json
{
  "type": "record",
  "name": "UserEvent",
  "namespace": "com.nexus.events",
  "fields": [
    {"name": "id", "type": "long"},
    {"name": "user_id", "type": "long"},
    {"name": "event_type", "type": "string"},
    {"name": "page_url", "type": ["null", "string"], "default": null},
    {"name": "referrer_url", "type": ["null", "string"], "default": null},
    {"name": "user_agent", "type": ["null", "string"], "default": null},
    {"name": "ip_address", "type": ["null", "string"], "default": null},
    {"name": "session_id", "type": ["null", "string"], "default": null},
    {"name": "metadata", "type": ["null", "string"], "default": null},
    {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-millis"}}
  ]
}
```

#### Schema: `Order` (for `pg.public.orders`)

```json
{
  "type": "record",
  "name": "Order",
  "namespace": "com.nexus.transactions",
  "fields": [
    {"name": "id", "type": "long"},
    {"name": "user_id", "type": "long"},
    {"name": "total_amount", "type": {"type": "bytes", "logicalType": "decimal", "precision": 10, "scale": 2}},
    {"name": "currency", "type": "string", "default": "USD"},
    {"name": "status", "type": "string"},
    {"name": "region_name", "type": ["null", "string"], "default": null},
    {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    {"name": "updated_at", "type": {"type": "long", "logicalType": "timestamp-millis"}}
  ]
}
```

#### Schema: `Session` (for `pg.public.sessions`)

```json
{
  "type": "record",
  "name": "Session",
  "namespace": "com.nexus.sessions",
  "fields": [
    {"name": "id", "type": "string"},
    {"name": "user_id", "type": "long"},
    {"name": "started_at", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    {"name": "ended_at", "type": ["null", {"type": "long", "logicalType": "timestamp-millis"}], "default": null},
    {"name": "platform", "type": ["null", "string"], "default": null},
    {"name": "country_code", "type": ["null", "string"], "default": null},
    {"name": "city", "type": ["null", "string"], "default": null},
    {"name": "region_name", "type": ["null", "string"], "default": null},
    {"name": "is_active", "type": "boolean", "default": true},
    {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-millis"}}
  ]
}
```

#### Schema: `CartItem` (for `pg.public.cart_items`)

```json
{
  "type": "record",
  "name": "CartItem",
  "namespace": "com.nexus.transactions",
  "fields": [
    {"name": "id", "type": "long"},
    {"name": "user_id", "type": "long"},
    {"name": "product_id", "type": "long"},
    {"name": "quantity", "type": "int", "default": 1},
    {"name": "added_at", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    {"name": "removed_at", "type": ["null", {"type": "long", "logicalType": "timestamp-millis"}], "default": null}
  ]
}
```

#### Schema: `RequestLog` (for `pg.public.request_log`)

```json
{
  "type": "record",
  "name": "RequestLog",
  "namespace": "com.nexus.infra",
  "fields": [
    {"name": "id", "type": "long"},
    {"name": "endpoint", "type": ["null", "string"], "default": null},
    {"name": "method", "type": ["null", "string"], "default": null},
    {"name": "status_code", "type": "int"},
    {"name": "latency_ms", "type": "int"},
    {"name": "user_id", "type": ["null", "long"], "default": null},
    {"name": "session_id", "type": ["null", "string"], "default": null},
    {"name": "region_name", "type": ["null", "string"], "default": null},
    {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-millis"}}
  ]
}
```

#### Schema: `SystemMetric` (for `pg.public.system_metrics`)

```json
{
  "type": "record",
  "name": "SystemMetric",
  "namespace": "com.nexus.infra",
  "fields": [
    {"name": "id", "type": "long"},
    {"name": "node_name", "type": "string"},
    {"name": "metric_name", "type": "string"},
    {"name": "metric_value", "type": "double"},
    {"name": "recorded_at", "type": {"type": "long", "logicalType": "timestamp-millis"}}
  ]
}
```

### 7.3 Enriched / Intermediate Topics (Spark Output to Kafka -- Optional)

If you want to keep processed data in Kafka for other consumers:

| Topic | Key | Schema | Description |
|-------|-----|--------|-------------|
| `enriched.activities` | `user_id` | `EnrichedActivity` | User events enriched with display name, location, order amount |
| `aggregated.kpis` | `window_end` | `KpiSnapshot` | Windowed KPI aggregations |
| `aggregated.regions` | `region_name` | `RegionSnapshot` | Per-region aggregated metrics |
| `aggregated.traffic` | `window_end` | `TrafficPoint` | Traffic throughput time-series points |
| `evaluated.alerts` | `rule_id` | `AlertEvaluation` | Alert rule evaluation results |

#### Schema: `EnrichedActivity`

```json
{
  "type": "record",
  "name": "EnrichedActivity",
  "namespace": "com.nexus.enriched",
  "fields": [
    {"name": "id", "type": "string"},
    {"name": "user_display_name", "type": "string"},
    {"name": "action", "type": {"type": "enum", "name": "ActionType", "symbols": ["purchase", "view", "cart", "login"]}},
    {"name": "amount", "type": ["null", {"type": "bytes", "logicalType": "decimal", "precision": 10, "scale": 2}], "default": null},
    {"name": "location", "type": "string"},
    {"name": "region_name", "type": "string"},
    {"name": "timestamp", "type": {"type": "long", "logicalType": "timestamp-millis"}}
  ]
}
```

---

## 8. Spark Streaming Jobs

Spark Streaming consumes Kafka topics in micro-batch mode (10-30 second trigger intervals) and writes aggregated results to Redis.

### 8.0 Debezium Event Structure and `op` Field Handling

**All Spark jobs consuming Debezium CDC topics must handle the `op` (operation) field.** Debezium does not publish insert-only streams — it publishes the full row-level change log from PostgreSQL WAL, which includes creates, updates, and deletes.

After applying the `ExtractNewRecordState` unwrap transform (configured in the Debezium connector), each Kafka message has an `op` field with one of these values:

| `op` value | Meaning | When it occurs |
|-----------|---------|---------------|
| `c` | Create (INSERT) | New row inserted |
| `u` | Update (UPDATE) | Existing row updated |
| `d` | Delete (DELETE) | Row deleted (value is null, key only) |
| `r` | Read (snapshot) | Initial snapshot at connector startup |

**Key business cases that depend on UPDATE events**:

- `orders.status`: Orders are inserted as `pending` and transitioned to `completed`, `failed`, or `refunded` via UPDATE. KPIs (revenue, order count) must filter on `op IN ('c', 'u') AND status = 'completed'`, not just inserts.
- `sessions.is_active` / `sessions.ended_at`: Sessions end via an UPDATE that sets `is_active = false` and `ended_at`. Active user counts depend on correctly processing these updates to remove ended sessions.
- `cart_items.removed_at`: Cart removals are UPDATEs setting `removed_at`, not deletes.

**Standard filter pattern for each job**:

```python
# In PySpark Structured Streaming, after schema parsing:
active_orders = df.filter(
    (col("op").isin("c", "u", "r")) &
    (col("status") == "completed")
)

active_sessions = df.filter(
    (col("op").isin("c", "u", "r")) &
    (col("is_active") == True) &
    col("ended_at").isNull()
)

# Always exclude deletes from aggregations unless deletion is meaningful
# Always exclude snapshot reads ('r') if you only want incremental changes
```

### 8.1 Job: `KpiAggregator`

**Consumes**: `pg.public.orders`, `pg.public.sessions`, `pg.public.request_log`

**Produces**: KPI hash in Redis (see Section 9.1)

**Processing logic**:

```
Window: 30 seconds, sliding every 10 seconds

activeUsers = COUNT(DISTINCT session_id) FROM sessions WHERE is_active = true AND ended_at IS NULL

revenue = SUM(total_amount) FROM orders WHERE status = 'completed' AND created_at IN current_window
-- For cumulative daily: maintain running total in Redis, add window delta

orders = COUNT(*) FROM orders WHERE status = 'completed' AND created_at IN current_window

errorRate = (COUNT(*) FROM request_log WHERE status_code >= 500) / (COUNT(*) FROM request_log) * 100
-- In current window

latency = PERCENTILE_APPROX(latency_ms, 0.5) FROM request_log WHERE created_at IN current_window
-- Or use AVG; P50 recommended

-- Trend computation:
-- Store 1-hour-ago snapshot in Redis (separate key with TTL)
-- trend = ((current - oneHourAgo) / oneHourAgo) * 100
```

### 8.2 Job: `TrafficTimeSeriesBuilder`

**Consumes**: `pg.public.request_log`

**Produces**: Traffic time-series list in Redis (see Section 9.2)

**Processing logic**:

```
Window: 10 seconds (tumbling)

For each window:
  value = COUNT(*) FROM request_log WHERE created_at IN window
  timestamp = window_end_epoch_ms
  label = FORMAT_TIMESTAMP(window_end, 'hh:mm:ss a')  -- 12-hour with AM/PM e.g. "02:15:30 PM"

Output: one DataPoint per window
Append to Redis list, trim to latest 21 entries
```

### 8.3 Job: `ActivityEnricher`

**Consumes**: `pg.public.user_events`, `pg.public.orders`, `pg.public.cart_items` (joined with `pg.public.users` for display name and location)

**Produces**: Enriched activity list in Redis (see Section 9.3)

**Processing logic**:

```
For each user_event:
  1. Lookup user display_name and location from users table (broadcast join or Redis lookup)
  2. Map event_type to dashboard action:
     - checkout_complete -> purchase (join with orders for amount)
     - page_view -> view
     - add_to_cart -> cart
     - login -> login
  3. Format location as "City, CC"
  4. Write enriched event to Redis list (LPUSH, LTRIM to 15)
```

### 8.4 Job: `RegionAggregator`

**Consumes**: `pg.public.orders`, `pg.public.request_log`, `pg.public.sessions`

**Produces**: Region metrics hash and data flows in Redis (see Sections 9.4, 9.5)

**Processing logic**:

```
Window: 30 seconds

For each of the 9 regions:
  sales = SUM(total_amount) FROM orders WHERE region_name = region AND status = 'completed' AND created_at IN window
  
  request_count = COUNT(*) FROM request_log WHERE region_name = region AND created_at IN window
  max_request_count = MAX(request_count) across all regions
  intensity = (request_count / max_request_count) * 100
  -- Or normalize against a baseline capacity per region

Data Flows (top 5):
  For each pair of (user_region, merchant_region) where user_region != merchant_region:
    flow_volume = COUNT(*) of cross-region orders
  Sort by flow_volume DESC, take top 5
  Normalize value to 0-100 scale
```

### 8.5 Job: `DevicePlatformAggregator`

**Consumes**: `pg.public.sessions`

**Produces**: Device platform breakdown in Redis (see Section 9.6)

**Processing logic**:

```
Window: 5 minutes (tumbling), or use current active sessions

platform_counts = GROUP BY platform FROM sessions WHERE is_active = true
  SELECT platform, COUNT(*) as value

Output: Array of {name, value} objects
Platforms: Desktop, Mobile, iOS, Android
```

### 8.6 Job: `AlertEvaluator`

**Consumes**: `aggregated.kpis` Kafka topic (output of `KpiAggregator`), `aggregated.regions` Kafka topic (output of `RegionAggregator`), alert rule definitions (from a config file or a dedicated `nexus:alert:config` Redis key set at deployment time)

> **Why Kafka, not Redis**: Reading metric values from Redis inside a Spark executor is an anti-pattern. It creates runtime coupling between Spark and Redis, causes connection pool exhaustion at scale (each executor opens its own connection), and makes the job untestable in isolation. Instead, the `AlertEvaluator` consumes the already-aggregated Kafka topics produced by upstream Spark jobs. This keeps the pipeline decoupled and testable.

**Produces**: Alert rule states in Redis (see Section 9.7) + publishes to `nexus.alerts` channel

**Processing logic**:

```
For each micro-batch of aggregated KPI/region events:
  1. Load alert rule definitions from config (not from Redis at runtime)
  2. For each rule, extract the relevant metric from the batch:
       - "system.latency.p99"  -> latency field from aggregated.kpis
       - "checkout.error_rate" -> errorRate field from aggregated.kpis
       - "db.cpu.percent"      -> cpu field from aggregated.kpis (via health)
  3. Compare currentValue against threshold:
       - If currentValue > threshold for N consecutive micro-batches -> status = 'firing'
         (use Spark stateful streaming: mapGroupsWithState or flatMapGroupsWithState)
       - If currentValue > threshold but < N consecutive             -> status = 'pending'
       - If currentValue <= threshold                               -> status = 'ok'
  4. If any rule changed status since last evaluation:
       - Write full rules array to nexus:alert:rules
       - Write summary counts to nexus:alert:summary
       - PUBLISH to nexus.alerts channel (only on state change, not every tick)

Consecutive breach tracking requires stateful streaming:
  State per rule_id: { breachCount: int, lastStatus: string }
  N = 3 consecutive breaches recommended before transitioning pending -> firing
```

### 8.7 Job: `HealthCheckAggregator`

**Consumes**: `pg.public.system_metrics`

**Produces**: Health check hash in Redis (see Section 9.8)

**Processing logic**:

```
Window: 30 seconds

cpu = AVG(metric_value) FROM system_metrics WHERE metric_name = 'cpu_percent' AND recorded_at IN window
memory = AVG(metric_value) FROM system_metrics WHERE metric_name = 'memory_percent' AND recorded_at IN window

total_nodes = COUNT(DISTINCT node_name) FROM system_metrics WHERE recorded_at IN window
healthy_nodes = COUNT(DISTINCT node_name) WHERE latest cpu_percent < 90 AND latest memory_percent < 95
apiClusterScore = (healthy_nodes / total_nodes) * 100
apiClusterStatus = CASE
  WHEN apiClusterScore >= 90 THEN 'HEALTHY'
  WHEN apiClusterScore >= 50 THEN 'DEGRADED'
  ELSE 'DOWN'
END
```

### 8.8 Job: `GeoHeaderAggregator`

**Consumes**: Health check data, request log aggregations

**Produces**: Geo monitor header metrics in Redis (see Section 9.9)

**Processing logic**:

```
uptime = (total_time - downtime) / total_time * 100
-- downtime = periods where apiClusterStatus != 'HEALTHY'
-- Maintain running counter in Redis

globalLoad = SUM(response_body_size) FROM request_log IN window
-- Format as human-readable (PB/S, TB/S, etc.)
```

---

## 9. Redis Data Model

### Key Naming Convention

```
nexus:{domain}:{resource}[:{qualifier}]
```

All keys use colon `:` as separator. Domains: `kpi`, `traffic`, `activity`, `region`, `flow`, `alert`, `health`, `geo`, `platform`.

### 9.1 KPI Metrics

| Key | Type | Structure | TTL |
|-----|------|-----------|-----|
| `nexus:kpi:current` | HASH | All current KPI fields | None (overwritten every window) |
| `nexus:kpi:snapshot:{epoch_hour}` | HASH | Hourly KPI snapshot for trend computation | 2 hours |

**Hash fields for `nexus:kpi:current`**:

```
HSET nexus:kpi:current
  activeUsers       "14502"
  activeUsersTrend  "5.2"
  revenue           "42500.00"
  revenueTrend      "12.5"
  orders            "842"
  ordersTrend       "-2.1"
  errorRate         "0.04"
  errorRateTrend    "0.5"
  latency           "124"
  latencyTrend      "-1.2"
  updatedAt         "1709654400000"
```

**Dashboard reads**: `HGETALL nexus:kpi:current`

### 9.2 Traffic Throughput Time Series

| Key | Type | Structure | TTL |
|-----|------|-----------|-----|
| `nexus:traffic:timeseries` | LIST | JSON-encoded DataPoint objects (newest first) | None (trimmed to 21) |

**Write pattern** (Spark):

```
LPUSH nexus:traffic:timeseries '{"timestamp":1709654400000,"value":1247,"label":"02:15:30 PM"}'
LTRIM nexus:traffic:timeseries 0 20
```

**Dashboard reads**: `LRANGE nexus:traffic:timeseries 0 20` then reverse (or store oldest-first and RPUSH).

### 9.3 Activity Events (User Behavior Stream)

| Key | Type | Structure | TTL |
|-----|------|-----------|-----|
| `nexus:activity:feed` | LIST | JSON-encoded Activity objects (newest first) | None (trimmed to 15) |

**Write pattern** (Spark):

```
LPUSH nexus:activity:feed '{"id":"evt_abc123","user":"Alex","action":"purchase","amount":149.99,"timestamp":"2026-03-05T14:15:30.000Z","location":"New York, US"}'
LTRIM nexus:activity:feed 0 14
```

**Dashboard reads**:
- Dashboard tab: `LRANGE nexus:activity:feed 0 9` (latest 10)
- Geo Monitor tab: `LRANGE nexus:activity:feed 0 14` (latest 15)

### 9.4 Region Metrics

| Key | Type | Structure | TTL |
|-----|------|-----------|-----|
| `nexus:region:{region_name}` | HASH | Per-region metrics | None (overwritten each window) |
| `nexus:region:_index` | SET | Set of all region keys | None |

**Hash fields for each region** (e.g., `nexus:region:japan`):

```
HSET nexus:region:japan
  name       "Japan"
  lon        "139"
  lat        "35"
  intensity  "95.3"
  sales      "18500"
  updatedAt  "1709654400000"
```

**Dashboard reads**: `SMEMBERS nexus:region:_index` to get all keys, then `HGETALL` each. Or use a single key:

**Alternative (simpler)**:

| Key | Type | Structure | TTL |
|-----|------|-----------|-----|
| `nexus:regions:current` | STRING | JSON array of all 9 RegionMetric objects | None |

```
SET nexus:regions:current '[{"name":"Japan","coords":[139,35],"intensity":95.3,"sales":18500}, ...]'
```

**Dashboard reads**: `GET nexus:regions:current`, parse JSON.

### 9.5 Data Flows (Inter-Region Arcs)

| Key | Type | Structure | TTL |
|-----|------|-----------|-----|
| `nexus:flows:current` | STRING | JSON array of top 5 DataFlow objects | None |

```
SET nexus:flows:current '[{"id":"flow_1","source":[-74,40],"target":[2,48],"value":72.5}, ...]'
```

**Dashboard reads**: `GET nexus:flows:current`, parse JSON.

### 9.6 Device Platform Breakdown

| Key | Type | Structure | TTL |
|-----|------|-----------|-----|
| `nexus:platform:breakdown` | STRING | JSON array of platform counts | None |

```
SET nexus:platform:breakdown '[{"name":"Desktop","value":4500},{"name":"Mobile","value":3200},{"name":"iOS","value":2800},{"name":"Android","value":2100}]'
```

**Dashboard reads**: `GET nexus:platform:breakdown`, parse JSON.

### 9.7 Alert Rules

| Key | Type | Structure | TTL |
|-----|------|-----------|-----|
| `nexus:alert:rules` | STRING | JSON array of all AlertRule objects | None |
| `nexus:alert:summary` | HASH | Aggregated counts | None |

**Alert rules**:

```
SET nexus:alert:rules '[{"id":"alert_1","name":"High Latency p99 > 200ms","status":"firing","severity":"critical","metric":"system.latency.p99","currentValue":245,"threshold":200,"lastEvaluated":"2026-03-05T14:15:30.000Z","frequency":"1m"}, ...]'
```

**Alert summary**:

```
HSET nexus:alert:summary
  criticalCount   "1"
  warningCount    "1"
  healthyCount    "3"
  criticalImpact  "Currently affecting 15% of users"
  updatedAt       "1709654400000"
```

**Dashboard reads**: `GET nexus:alert:rules`, `HGETALL nexus:alert:summary`

### 9.8 Health Check

| Key | Type | Structure | TTL |
|-----|------|-----------|-----|
| `nexus:health:current` | HASH | Infrastructure health metrics | None |

```
HSET nexus:health:current
  cpu               "22.4"
  memory            "58.0"
  apiClusterStatus  "HEALTHY"
  apiClusterScore   "95"
  updatedAt         "1709654400000"
```

**Dashboard reads**: `HGETALL nexus:health:current`

### 9.9 Geo Monitor Header

| Key | Type | Structure | TTL |
|-----|------|-----------|-----|
| `nexus:geo:header` | HASH | System-level metrics for geo header | None |

```
HSET nexus:geo:header
  uptime          "99.999"
  globalLoad      "4.2 PB/S"
  engineVersion   "V4-Orbit"
  protocolStatus  "Secure"
  updatedAt       "1709654400000"
```

**Dashboard reads**: `HGETALL nexus:geo:header`

### 9.10 Redis Pub/Sub Channels (WebSocket Push Layer)

Redis Pub/Sub is the **primary real-time delivery mechanism**. It is not optional. Spark writes aggregated results to Redis keys (snapshots) and **immediately** publishes a notification to the corresponding pub/sub channel. The FastAPI backend subscribes to all channels and fans out each message to every connected WebSocket client via `ws://localhost:8000/ws`.

#### 9.10.1 Two-Step Write Pattern (Spark Responsibility)

Every Spark job MUST follow this pattern atomically:

```
Step 1: Write result to Redis snapshot key   (for REST initial-load reads)
Step 2: PUBLISH result to pub/sub channel    (triggers SSE push to frontend)
```

**Critical**: These are two separate Redis operations. Pub/Sub has no persistence — if the backend is not subscribed at the moment of publish, the message is lost. The snapshot keys in steps 9.1–9.9 are the durability layer; pub/sub is the WebSocket push notification layer.

Example (PySpark + redis-py):

```python
import json, redis

r = redis.Redis(host="redis", port=6379)

# Step 1: write snapshot (durable, readable by REST endpoints)
r.hset("nexus:kpi:current", mapping=kpi_dict)

# Step 2: publish notification (triggers SSE push, fire-and-forget)
r.publish("nexus.kpi", json.dumps(kpi_dict))
```

Do NOT publish without also writing to the snapshot key. The REST snapshot endpoints (used for initial WebSocket snapshot-on-connect and REST API calls) read only from the keys, never from pub/sub.

#### 9.10.2 Channel Definitions

Channel names use dot `.` as separator (distinct from key names which use colon `:`).

| Channel | Published By | Trigger | Payload |
|---------|-------------|---------|---------|
| `nexus.kpi` | `KpiAggregator` | Every micro-batch window (~10s) | Full KPI JSON object |
| `nexus.traffic` | `TrafficTimeSeriesBuilder` | Every tumbling window (~10s) | Single `DataPoint` JSON |
| `nexus.activity` | `ActivityEnricher` | Per enriched event (near real-time) | Single `Activity` JSON |
| `nexus.regions` | `RegionAggregator` | Every micro-batch window (~15-30s) | Full regions array JSON |
| `nexus.flows` | `RegionAggregator` | Every micro-batch window (~15-30s) | Full flows array JSON |
| `nexus.alerts` | `AlertEvaluator` | On any rule state change | Full alert rules array JSON |
| `nexus.platform` | `DevicePlatformAggregator` | Every 5-minute window | Platform breakdown array JSON |
| `nexus.health` | `HealthCheckAggregator` | Every micro-batch window (~15-30s) | Health JSON object |
| `nexus.geo` | `GeoHeaderAggregator` | Every 30s window | Geo header JSON object |

#### 9.10.3 Exact PUBLISH Payloads

These are the exact JSON strings Spark must pass to `PUBLISH`. The shapes match the contracts defined in Section 5.

**`nexus.kpi`**:
```json
{
  "activeUsers": 14502, "activeUsersTrend": 5.2,
  "revenue": 42500.00, "revenueTrend": 12.5,
  "orders": 842, "ordersTrend": -2.1,
  "errorRate": 0.04, "errorRateTrend": 0.5,
  "latency": 124, "latencyTrend": -1.2,
  "updatedAt": 1709654400000
}
```

**`nexus.traffic`** (one point per publish):
```json
{ "timestamp": 1709654400000, "value": 1247, "label": "02:15:30 PM" }
```

**`nexus.activity`** (one event per publish):
```json
{
  "id": "evt_abc123def",
  "user": "Alex",
  "action": "purchase",
  "amount": 149.99,
  "timestamp": "2026-03-05T14:15:30.000Z",
  "location": "New York, US"
}
```

**`nexus.regions`**:
```json
[
  { "name": "Japan", "coords": [139, 35], "intensity": 95.3, "sales": 18500 },
  { "name": "North America (East)", "coords": [-74, 40], "intensity": 85.0, "sales": 12400 }
]
```

**`nexus.flows`**:
```json
[
  { "id": "flow_1", "source": [-74, 40], "target": [2, 48], "value": 72.5 },
  { "id": "flow_2", "source": [139, 35], "target": [103, 1], "value": 58.1 }
]
```

**`nexus.alerts`** (publish only when at least one rule changes state):
```json
[
  {
    "id": "alert_1", "name": "High Latency p99 > 200ms",
    "status": "firing", "severity": "critical",
    "metric": "system.latency.p99", "currentValue": 245, "threshold": 200,
    "lastEvaluated": "2026-03-05T14:15:30.000Z", "frequency": "1m"
  }
]
```

**`nexus.platform`**:
```json
[
  { "name": "Desktop", "value": 4500 }, { "name": "Mobile", "value": 3200 },
  { "name": "iOS", "value": 2800 }, { "name": "Android", "value": 2100 }
]
```

**`nexus.health`**:
```json
{ "cpu": 22.4, "memory": 58.0, "apiClusterStatus": "HEALTHY", "apiClusterScore": 95, "updatedAt": 1709654400000 }
```

**`nexus.geo`**:
```json
{ "uptime": 99.999, "globalLoad": "4.2 PB/S", "globalLoadBytes": 4200000000000000, "engineVersion": "V4-Orbit", "protocolStatus": "Secure", "updatedAt": 1709654400000 }
```

#### 9.10.4 WebSocket Message Types (FastAPI → Frontend)

The FastAPI backend converts each pub/sub message into a WebSocket JSON frame and sends it to all connected clients via `ws://localhost:8000/ws`. The frontend (`NexusWsClient` in `services/wsClient.ts`) dispatches on the `type` field.

| Pub/Sub Channel | WS `type` field | Frontend handler |
|----------------|----------------|-----------------|
| `nexus.kpi` | `metrics` | Updates all 5 KPI cards and trends |
| `nexus.traffic` | `traffic` | Appends to chart, drops oldest (21-point window) |
| `nexus.activity` | `activity` | Prepends to feed, drops oldest (10/15 items) |
| `nexus.regions` | `regions` | Re-renders globe hotspots and node cards |
| `nexus.flows` | `flows` | Re-renders globe arc lines |
| `nexus.alerts` | `alert` | Updates alert table and summary counts |
| `nexus.platform` | `platform` | Re-renders device platform pie chart |
| `nexus.health` | `health` | Updates health check bars |
| `nexus.geo` | `geo` | Updates Geo Monitor header metrics |

WebSocket message wire format (each message is a single JSON string):

```json
{"type": "metrics", "data": {"activeUsers":14502,"revenue":42500,...}}
{"type": "activity", "data": {"id":"evt_abc123","user":"Alex","action":"purchase",...}}
```

On connect, the API immediately sends a full snapshot message for all 9 types before switching to incremental pub/sub pushes.

#### 9.10.5 WebSocket Reconnect and State Resync

Redis Pub/Sub has **no message persistence**. If a client disconnects and reconnects, all messages published during the gap are permanently lost. The WebSocket snapshot-on-connect behavior handles this automatically.

**Reconnect behavior** (implemented in `NexusWsClient`):

1. WebSocket `onclose` or `onerror` fires
2. `NexusWsClient` reconnects with exponential backoff (1s, 2s, 4s, 8s, up to ~30s max)
3. On successful reconnect, the API automatically sends a full snapshot of all 9 data types
4. No separate REST fetches needed — the WS snapshot-on-connect is the resync mechanism

If stronger replay guarantees are needed in the future, replace Redis Pub/Sub with **Redis Streams** (XREAD with consumer groups) which supports message persistence and offset tracking.

#### 9.10.6 REST Snapshot Endpoints

The FastAPI backend exposes these REST endpoints. They read directly from Redis snapshot keys (no pub/sub). Used by external clients and for testing; the dashboard itself uses the WebSocket snapshot-on-connect instead.

| Method | Endpoint | Redis Command | Response |
|--------|----------|---------------|----------|
| `GET` | `/api/metrics` | `HGETALL nexus:kpi:current` | KPI JSON object |
| `GET` | `/api/traffic` | `LRANGE nexus:traffic:timeseries 0 20` | Array of 21 DataPoints (oldest-first) |
| `GET` | `/api/activities` | `LRANGE nexus:activity:feed 0 14` | Array of up to 15 Activity objects |
| `GET` | `/api/regions` | `GET nexus:regions:current` | Array of 9 RegionMetric objects |
| `GET` | `/api/flows` | `GET nexus:flows:current` | Array of up to 5 DataFlow objects |
| `GET` | `/api/alerts` | `GET nexus:alert:rules` + `HGETALL nexus:alert:summary` | `{rules: [...], summary: {...}}` |
| `GET` | `/api/platform` | `GET nexus:platform:breakdown` | Platform array |
| `GET` | `/api/health` | `HGETALL nexus:health:current` | Health JSON object |
| `GET` | `/api/geo` | `HGETALL nexus:geo:header` | Geo header JSON object |
| `GET` | `/events` | Subscribes to all `nexus.*` channels | SSE stream (long-lived) |

The `/events` endpoint is a long-lived SSE connection. All other endpoints are standard HTTP GET returning JSON.

### 9.11 Redis Memory Estimate

| Key Pattern | Count | Approx Size Per Key | Total |
|------------|-------|-------------------|-------|
| `nexus:kpi:current` | 1 | ~500 bytes | 500 B |
| `nexus:kpi:snapshot:*` | ~2 (hourly, 2h TTL) | ~500 bytes | 1 KB |
| `nexus:traffic:timeseries` | 1 (21 elements) | ~2 KB | 2 KB |
| `nexus:activity:feed` | 1 (15 elements) | ~3 KB | 3 KB |
| `nexus:regions:current` | 1 | ~2 KB | 2 KB |
| `nexus:flows:current` | 1 | ~1 KB | 1 KB |
| `nexus:platform:breakdown` | 1 | ~500 bytes | 500 B |
| `nexus:alert:rules` | 1 | ~2 KB | 2 KB |
| `nexus:alert:summary` | 1 | ~200 bytes | 200 B |
| `nexus:health:current` | 1 | ~200 bytes | 200 B |
| `nexus:geo:header` | 1 | ~200 bytes | 200 B |
| **Total** | **~12 keys** | | **~12 KB** |

Redis memory usage is minimal. The bottleneck is write frequency, not memory.

---

## 10. End-to-End Data Flow Mapping

This table maps every dashboard component to its complete data lineage: which Redis key it reads, which Spark job writes that key, which Kafka topics the Spark job consumes, and which PostgreSQL tables are the ultimate source.

### 10.1 Dashboard Tab

| Dashboard Component | Redis Key | Spark Job | Kafka Topics | PG Source Tables |
|--------------------|-----------|-----------|-------------|-----------------|
| **KPI: Live Visitors** | `nexus:kpi:current` (`activeUsers`) | `KpiAggregator` | `pg.public.sessions` | `sessions` |
| **KPI: Revenue** | `nexus:kpi:current` (`revenue`) | `KpiAggregator` | `pg.public.orders` | `orders` |
| **KPI: Orders** | `nexus:kpi:current` (`orders`) | `KpiAggregator` | `pg.public.orders` | `orders` |
| **KPI: Errors** | `nexus:kpi:current` (`errorRate`) | `KpiAggregator` | `pg.public.request_log` | `request_log` |
| **KPI: Latency** | `nexus:kpi:current` (`latency`) | `KpiAggregator` | `pg.public.request_log` | `request_log` |
| **KPI Trends (all)** | `nexus:kpi:current` (`*Trend`) | `KpiAggregator` | (same as above) + `nexus:kpi:snapshot:*` | (same) |
| **Traffic Throughput Chart** | `nexus:traffic:timeseries` | `TrafficTimeSeriesBuilder` | `pg.public.request_log` | `request_log` |
| **Regional Distribution Globe** | `nexus:regions:current`, `nexus:flows:current` | `RegionAggregator` | `pg.public.orders`, `pg.public.request_log`, `pg.public.sessions` | `orders`, `request_log`, `sessions`, `region_mapping` |
| **Real-time Events** | `nexus:activity:feed` | `ActivityEnricher` | `pg.public.user_events`, `pg.public.orders`, `pg.public.cart_items` | `user_events`, `orders`, `cart_items`, `users` |
| **Device Platform Pie** | `nexus:platform:breakdown` | `DevicePlatformAggregator` | `pg.public.sessions` | `sessions` |
| **Health Check Bars** | `nexus:health:current` | `HealthCheckAggregator` | `pg.public.system_metrics` | `system_metrics` |

### 10.2 Geo Monitor Tab

| Dashboard Component | Redis Key | Spark Job | Kafka Topics | PG Source Tables |
|--------------------|-----------|-----------|-------------|-----------------|
| **Header: Uptime** | `nexus:geo:header` (`uptime`) | `GeoHeaderAggregator` | `pg.public.system_metrics` | `system_metrics` |
| **Header: Global Load** | `nexus:geo:header` (`globalLoad`) | `GeoHeaderAggregator` | `pg.public.request_log` | `request_log` |
| **Node Monitoring Cards** | `nexus:regions:current` | `RegionAggregator` | `pg.public.orders`, `pg.public.request_log`, `pg.public.sessions` | `orders`, `request_log`, `sessions` |
| **3D Globe** | `nexus:regions:current`, `nexus:flows:current` | `RegionAggregator` | (same as above) | (same) |
| **Stream Log** | `nexus:activity:feed` | `ActivityEnricher` | `pg.public.user_events`, `pg.public.orders`, `pg.public.cart_items` | `user_events`, `orders`, `cart_items`, `users` |

### 10.3 Alerting Tab

| Dashboard Component | Redis Key | Spark Job | Kafka Topics | PG Source Tables |
|--------------------|-----------|-----------|-------------|-----------------|
| **Summary Cards** | `nexus:alert:summary` | `AlertEvaluator` | Reads from Redis (KPI, health) | (indirect) |
| **Rules Table** | `nexus:alert:rules` | `AlertEvaluator` | Reads from Redis (KPI, health) | (indirect) |
| **Contact Points** | N/A (config) | N/A | N/A | N/A (application config) |

### 10.4 Shared Components

| Component | Used In | Redis Key(s) | Spark Job(s) |
|-----------|---------|-------------|-------------|
| `WorldMap` (Globe) | Dashboard, Geo Monitor | `nexus:regions:current`, `nexus:flows:current` | `RegionAggregator` |
| `KpiCard` | Dashboard (5), Alerting (3 summary) | `nexus:kpi:current`, `nexus:alert:summary` | `KpiAggregator`, `AlertEvaluator` |

---

## Appendix A: WebSocket Event Reference and REST Snapshot Endpoints

The dashboard uses a push-based WebSocket architecture, not polling. This appendix summarises all WebSocket message types the frontend handles, and the REST endpoints available for external access.

### A.1 WebSocket Message Types

The frontend opens a single WebSocket connection to `ws://localhost:8000/ws` via `NexusWsClient`. All real-time updates arrive as JSON frames with a `type` field.

| WS `type` | Source channel | Payload shape | Frontend impact |
|----------|---------------|---------------|----------------|
| `metrics` | `nexus.kpi` | Full KPI object (10 fields + `updatedAt`) | Update all 5 KPI cards and trends |
| `traffic` | `nexus.traffic` | Single `DataPoint` | Append to chart, drop oldest (maintain 21 points) |
| `activity` | `nexus.activity` | Single `Activity` | Prepend to feed, drop oldest (maintain 10/15 items) |
| `regions` | `nexus.regions` | Full 9-element regions array | Re-render globe hotspots and node monitoring cards |
| `flows` | `nexus.flows` | Full flows array (max 5) | Re-render globe arc lines |
| `alert` | `nexus.alerts` | Full alert rules array | Update alert table and summary counts |
| `platform` | `nexus.platform` | 4-element platform array | Re-render device platform pie chart |
| `health` | `nexus.health` | Health object | Update health check bars |
| `geo` | `nexus.geo` | Geo header object | Update Geo Monitor header metrics |

On connect, the API sends all 9 message types immediately (snapshot-on-connect) before switching to incremental pub/sub pushes.

### A.2 REST Snapshot Endpoints

Available for external clients and testing. The dashboard itself uses the WebSocket snapshot-on-connect instead of these REST calls.

| Endpoint | Redis source | Response |
|----------|-------------|----------|
| `GET /api/metrics` | `HGETALL nexus:kpi:current` | KPI JSON object |
| `GET /api/traffic` | `LRANGE nexus:traffic:timeseries 0 20` (reversed) | Array[21] DataPoint, oldest-first |
| `GET /api/activities` | `LRANGE nexus:activity:feed 0 14` | Array[15] Activity, newest-first |
| `GET /api/regions` | `GET nexus:regions:current` | Array[9] RegionMetric |
| `GET /api/flows` | `GET nexus:flows:current` | Array[≤5] DataFlow |
| `GET /api/alerts` | `GET nexus:alert:rules` + `HGETALL nexus:alert:summary` | `{rules:[...], summary:{...}}` |
| `GET /api/platform` | `GET nexus:platform:breakdown` | Array[4] platform |
| `GET /api/health` | `HGETALL nexus:health:current` | Health JSON object |
| `GET /api/geo` | `HGETALL nexus:geo:header` | Geo header JSON object |

### A.3 Update Frequency Reference

| Data type | Spark trigger | WS push frequency | Frontend effect |
|-----------|--------------|------------------|----------------|
| KPI metrics | Every 30s | ~Every 30s | KPI cards update each window |
| Traffic chart | Every 30s (tumbling) | ~Every 30s | One new point per event, 21-point rolling window |
| Activity feed | Per event (near real-time) | As events arrive | Individual event cards animate in |
| Regions / flows | Every 30s | ~Every 30s | Globe re-renders smoothly (D3 handles transitions) |
| Alerts | On state change only | Infrequent | Alert table refreshes only when a rule changes status |
| Platform breakdown | Every 30s | ~Every 30s | Pie chart updates each window |
| Health check | Every 30s | ~Every 30s | Progress bars update smoothly |

---

## Appendix B: Spark Job Trigger Intervals (Implemented)

All three Spark jobs run with a 30-second trigger interval:

| Spark Job (container) | Trigger Interval | Primary outputs |
|----------------------|-----------------|----------------|
| `nexus-transactions` | 30s | KPIs, alerts, activity, regions, flows |
| `nexus-infrastructure` | 30s | Traffic, health, geo |
| `nexus-derived` | 30s | Platform breakdown |

Each job is submitted with `--total-executor-cores 6` (2 executors × 3 cores each). The two Spark workers auto-detect host resources (~10 cores, ~14.6 GiB each).

---

## Appendix C: Remaining Placeholder Items

The pipeline and core dashboard data flow are fully implemented. The following items remain as UI placeholders or future work:

| Feature | Current State | Notes |
|---------|--------------|-------|
| **Explore tab** | Loading placeholder | Ad-hoc query engine not yet built |
| **Contact points** | Hardcoded UI | Slack/Email/PagerDuty listed statically |
| **Sidebar: Inventory** | No-op button | Future feature |
| **Sidebar: Configuration** | No-op button | Future feature |
| **Search button** | No-op button | Future feature |
| **Time range picker** | "Last 1h" label, no-op | Historical query support not yet built |

---

## Appendix D: Frontend Data Integration Points

All dashboard data is consumed via the WebSocket connection managed by `NexusWsClient` (`services/wsClient.ts`) and distributed to components through the `NexusDataProvider` context in `hooks/useNexusData.tsx`.

| Component / hook | Data consumed | Source |
|-----------------|--------------|--------|
| `hooks/useNexusData.tsx` | All 9 data types | WebSocket `NexusWsClient`, dispatches on `type` field |
| KPI cards | `metrics` WS message | `nexus:kpi:current` via WS snapshot + incremental |
| Traffic chart | `traffic` WS message | `nexus:traffic:timeseries` via WS snapshot + incremental |
| Activity feed | `activity` WS message | `nexus:activity:feed` via WS snapshot + incremental |
| Globe / region cards | `regions`, `flows` WS messages | `nexus:regions:current`, `nexus:flows:current` |
| Platform pie | `platform` WS message | `nexus:platform:breakdown` |
| Health bars | `health` WS message | `nexus:health:current` |
| Geo header | `geo` WS message | `nexus:geo:header` |
| Alerts table | `alert` WS message | `nexus:alert:rules`, `nexus:alert:summary` |
