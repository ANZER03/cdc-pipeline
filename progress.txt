# EBAP — Progress Log

> Every issue encountered, fix applied, or workaround discovered is logged here.
> Format: [DATE] Phase X — short description of the problem and solution.

---

## Phase 5 — Stream Processing (2026-02-18)

**Issue 1:** `NoClassDefFoundError: software/amazon/awssdk/core/exception/SdkException`
- **Cause:** `org.apache.iceberg.aws.s3.S3FileIO` lives in `iceberg-aws-bundle`, not in `iceberg-spark-runtime`.
- **Fix:** Added `iceberg-aws-bundle-1.7.1.jar` (49 MB) as a separate layer in the `Dockerfile`.

**Issue 2:** `SdkClientException: Unable to load region`
- **Cause:** AWS SDK v2 (inside `iceberg-aws-bundle`) requires the `AWS_REGION` environment variable to be set even for non-AWS (MinIO) deployments.
- **Fix:** Added `AWS_REGION: us-east-1` to all Spark container `environment` blocks in `docker-compose.yml`.

**Issue 3:** `ModuleNotFoundError: No module named 'redis'`
- **Cause:** The `spark-redis` JAR provides the Java/Scala connector, but the Python `redis` package is needed separately for `foreachBatch` Python sink functions.
- **Fix:** Added `pip3 install redis==5.2.1` to the `Dockerfile`.

**Issue 4:** Stream-stream LEFT OUTER join not supported without time-range condition
- **Cause:** Spark Structured Streaming requires a watermark AND a time-range join predicate for left outer stream-stream joins.
- **Fix:** Changed to `inner` join. Acceptable because Debezium snapshots all existing users at startup (`op=r`), so all active `user_id` values are present in the CDC stream before live events arrive.

**Issue 5:** `AnalysisException: Append output mode not supported for stream-stream join`
- **Cause:** Stream-stream join output must use `append` mode, not `update`.
- **Fix:** Changed the `iceberg-enriched-events` query `outputMode` to `"append"`. The windowed aggregation queries (no join) continued to use `"update"` correctly.

**Issue 6:** Windowed aggregation for Redis referencing `enriched_df` instead of `events_df`
- **Cause:** `enriched_df` comes from the stream-stream join which requires `append` mode. The 1-minute Redis window query used `update` mode — incompatible.
- **Fix:** Rewrote `build_windowed_metrics()` to use `events_df` (raw events, no join). Used `coalesce(location, "unknown")` aliased as `region` for Redis key compatibility.

**Issue 7:** Windowed aggregation with watermark only emits rows when watermark advances past `window_end + watermark_duration`
- **Observation:** In `update` mode, windows don't emit until the watermark has advanced sufficiently. Verified by producing events with timestamps ≥ window_end + 10 minutes.
- **Workaround:** This is expected Spark behavior. For testing, produce events with future timestamps to force window closure.

**Issue 8:** Spark master UI port 8080 conflict
- **Cause:** Port 8080 was already in use on the host machine.
- **Fix:** Mapped Spark master UI to host port `8082` (`"8082:8080"` in `docker-compose.yml`).

**Issue 9:** Docker layer cache corruption during Dockerfile build
- **Symptom:** JAR download steps resolved from corrupt cache, producing broken JARs.
- **Fix:** Ran `docker compose build --no-cache` to force a clean rebuild.

**Issue 10:** `ebap-net` network warning `"not created for project"`
- **Observation:** Cosmetic Docker Compose warning when re-upping an already-running stack. Network is created and functional.
- **Disposition:** Harmless; no fix needed.

**Issue 11:** Kafka topic names with periods generate metric warning
- **Observation:** `[AdminClient] Error in admin client` warning about topic names with dots (e.g., `ebap.events.raw`). Cosmetic only.
- **Disposition:** Harmless; no fix needed.

---

## Phase 5 — Stream Processing (post-commit fixes, 2026-02-18)

**Issue 12:** Spark Application UI (port 4040) not accessible from host browser
- **Symptom:** Clicking app details in Spark Master UI opened `http://<container-id>:4040/` — browser couldn't resolve the container hostname.
- **Cause:** Port 4040 was not mapped to the host, and `spark.driver.host` was unset so Spark advertised the container's random hostname in the UI link.
- **Fix:**
  1. Added `ports: ["4040:4040"]` to `spark-streaming-submit` in `docker-compose.yml`.
  2. Added `--conf spark.ui.port=4040` to the `spark-submit` entrypoint.
  3. Added `--conf spark.driver.host=spark-streaming-submit` (fixed DNS name, not `localhost`).
  4. Added `--conf spark.driver.bindAddress=0.0.0.0` so the UI binds on all interfaces.
  5. Added `hostname: spark-streaming-submit` to the service so Docker DNS resolves it correctly.
- **Note:** Using `spark.driver.host=localhost` (first attempt) broke executor→driver communication because the worker container could not reach "localhost" on the submit container. The fixed hostname must be the container's own DNS name within `ebap-net`.

**Issue 13:** Streaming micro-batches not firing after container restart (stale checkpoint)
- **Symptom:** After `spark-streaming-submit` was recreated, `write_to_redis` foreachBatch was invoked but returned 0 rows. `kpi:total_revenue` remained `0.00` and `kpi:last_updated` stayed at a previous session's timestamp.
- **Cause:** The old checkpoint in `s3a://ebap-checkpoints/streaming/` encoded a different session's state store layout. The new session picked up the stale checkpoint, producing an empty DataFrame on the first micro-batch.
- **Fix:** Cleared all checkpoint directories from MinIO:
  ```bash
  docker exec ebap-minio sh -c "mc alias set local http://localhost:9000 admin password && mc rm --recursive --force local/ebap-checkpoints/streaming/"
  ```
  Then restarted `ebap-spark-streaming-submit`. Fresh checkpoints were created and micro-batches began producing data.

**Issue 14:** `kafka-console-producer` heredoc (`<<'EOF'`) in `docker exec` drops messages silently
- **Symptom:** Events produced via `docker exec ebap-kafka kafka-console-producer ... <<'EOF' ... EOF` appeared to succeed (no error), but Kafka partition offsets did not increment.
- **Cause:** The heredoc closes stdin before the producer has connected to the broker, so no messages are flushed.
- **Fix:** Use `printf ... | docker exec -i ebap-kafka kafka-console-producer ...` (pipe via `-i` flag) instead:
  ```bash
  printf '%s\n' '{"id":"evt_001",...}' '{"id":"evt_002",...}' | \
    docker exec -i ebap-kafka kafka-console-producer \
      --bootstrap-server localhost:9092 --topic ebap.events.raw
  ```

**Issue 15:** Windowed aggregation in `update` mode emits empty DataFrame until watermark advances
- **Observation:** First micro-batch after a fresh checkpoint always produces 0 rows from the windowed aggregation even when events are present. The window is open (not yet closed by the watermark), so `update` mode emits nothing.
- **Explanation:** In `update` mode, Spark only emits rows for windows whose watermark has advanced past `window_end`. Events with `event_ts` near current time don't close until a later event pushes `max(event_ts) - watermark_delay` past the window end.
- **Workaround:** Send an additional event with a far-future timestamp to advance the watermark and force windows to close:
  ```bash
  printf '{"id":"wm","user_id":"usr_001","action":"page_view","metadata":{},"location":"us-east-1","timestamp":"2026-02-18T05:00:00Z"}\n' | \
    docker exec -i ebap-kafka kafka-console-producer \
      --bootstrap-server localhost:9092 --topic ebap.events.raw
  ```

---

## CDC — Debezium `before` field null on UPDATE/DELETE (2026-02-18)

**Issue 16:** Debezium `before` field is `null` for UPDATE and DELETE events
- **Cause:** PostgreSQL's default `REPLICA IDENTITY DEFAULT` only writes the primary key columns to the WAL for old row images. Debezium reads the WAL and can only populate `before` with what Postgres logged — everything except the PK comes back as `null`.
- **Fix:** Set `REPLICA IDENTITY FULL` on the `users` table so Postgres logs the entire old row for every UPDATE and DELETE:
  ```sql
  ALTER TABLE users REPLICA IDENTITY FULL;
  ```
  Applied immediately to the running container and persisted in `init-scripts/seed-postgres.sql` (after the `CREATE TABLE` block) for future fresh deployments.
- **Verification:** Confirmed via `pg_class.relreplident = 'f'` and by consuming `ebap.cdc.users` — UPDATE events now show full `before` + `after`, DELETE events show full `before` with `after: null`.

