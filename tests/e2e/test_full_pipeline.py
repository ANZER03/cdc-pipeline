import json


def test_full_pipeline_contract_examples_are_non_empty() -> None:
    sample = {
        "metrics": {"activeUsers": 14502, "revenue": 42500.0},
        "traffic": [{"timestamp": 1709654400000, "value": 1247, "label": "02:15:30 PM"}],
        "alerts": {
            "rules": [{"id": "alert_1", "status": "firing"}],
            "summary": {"criticalCount": 1},
        },
    }
    encoded = json.dumps(sample)
    restored = json.loads(encoded)
    assert restored["metrics"]["activeUsers"] > 0
    assert restored["traffic"]
    assert restored["alerts"]["rules"]
