# Reprocessing Guide

## When to Reprocess

Use the `--reprocess` flag when you need to re-transform bronze records that were already processed. Common scenarios:

1. **Schema changes** — After modifying `storage/delta/schemas.py`, existing silver records need to be regenerated with the new schema.

2. **Enrichment upgrades** — When `classify_breaking_changes.py` is updated with better classification logic, old releases should be re-enriched.

3. **Bug fixes** — If a transform bug produced incorrect silver data, reprocessing corrects it.

4. **Delta Lake corruption** — In rare cases, silver Delta tables may need to be rebuilt from bronze.

## How to Reprocess

### Single tool

```bash
spark-submit processing/spark_jobs/transform_releases.py \
    --tool-name apache-kafka \
    --reprocess
```

### Single tool, specific date

```bash
spark-submit processing/spark_jobs/transform_releases.py \
    --tool-name apache-kafka \
    --date 2024-06-01 \
    --reprocess
```

### All tools (via Airflow)

Trigger the `process_releases` DAG with config:

```json
{"reprocess": true}
```

## What Happens During Reprocess

1. **Bronze**: ALL records for the tool are read (the `processed=False` filter is skipped).
2. **Transform**: Normal pipeline runs — parse, normalize, extract breaking changes, classify.
3. **Silver**: Delta MERGE upserts results by `(tool_name, version)`. Existing rows are updated, new rows are inserted.
4. **Bronze update**: Processed flag is set to `True` (idempotent — already-true rows are unaffected).

## Safety

- **Idempotent**: Running `--reprocess` multiple times produces the same result.
- **Non-destructive**: Uses Delta MERGE (upsert), not overwrite. Silver data for other tools is untouched.
- **Rollback**: Delta Lake time-travel allows rollback if needed:
  ```python
  # Restore silver_releases to previous version
  spark.read.format("delta").option("versionAsOf", 5).load("s3a://silver/silver_releases/")
  ```

## After Reprocessing

After reprocessing silver releases, rebuild the Gold summary to reflect updated data:

```bash
spark-submit processing/spark_jobs/build_gold_summary.py
```
