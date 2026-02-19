#!/usr/bin/env python3
"""
scripts/health_check.py
EBAP — Service health verification.

Checks all EBAP services are reachable and healthy.
Run with: python scripts/health_check.py
Or:       make health
"""

import sys
import socket
import urllib.request
import urllib.error


def check_tcp(host: str, port: int, label: str) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
            print(f"  [OK]  {label} ({host}:{port})")
            return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        print(f"  [FAIL] {label} ({host}:{port}) — not reachable")
        return False


def check_http(url: str, label: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            if resp.status < 500:
                print(f"  [OK]  {label} ({url})")
                return True
    except Exception:
        pass
    print(f"  [FAIL] {label} ({url}) — not reachable")
    return False


def main():
    print("\nEBAP Health Check\n" + "=" * 40)

    checks = [
        check_tcp("localhost", 9092,  "Kafka broker 1"),
        check_tcp("localhost", 9093,  "Kafka broker 2"),
        check_http("http://localhost:8081/subjects", "Schema Registry"),
        check_http("http://localhost:8083/connectors", "Debezium Connect"),
        check_http("http://localhost:8084/api/clusters", "Kafka UI"),
        check_tcp("localhost", 5432,  "PostgreSQL"),
        check_tcp("localhost", 6379,  "Redis"),
        check_http("http://localhost:9000/minio/health/live", "MinIO"),
        check_http("http://localhost:8082", "Spark Master UI"),
    ]

    print()
    passed = sum(checks)
    total  = len(checks)
    print(f"Result: {passed}/{total} services healthy")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
