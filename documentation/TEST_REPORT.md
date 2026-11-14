# Test report (core logic; run in authoring sandbox, Python 3.12)
API tests (tests/test_api.py) were NOT run: fastapi/httpx/sqlalchemy unavailable there.

```
PASS test_alert_dedupe
PASS test_baseline_values
PASS test_combined_pipeline_detects_injected_synthetic
PASS test_csv_import
PASS test_gradual_drift_gives_amber_with_explanation
PASS test_high_priority_rule_gives_red
PASS test_missing_data_not_green
PASS test_ml_alone_tradeoff_synthetic
PASS test_model_train_persist_load
PASS test_normal_reading_is_green
PASS test_pdf_and_csv_export
PASS test_radiation_units
PASS test_repeated_amber_escalates
PASS test_rules_red_and_amber
PASS test_sync_idempotent
PASS test_validation_flags_missing_and_implausible
failures: 0
```
